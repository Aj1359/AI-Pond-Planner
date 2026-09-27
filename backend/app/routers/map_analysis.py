"""
Map-area analysis router
  POST /api/map/analyze-area   — user draws polygon on map → full analysis
  POST /api/map/elevation-point — single lat/lon elevation lookup
  GET  /api/map/geocode         — address → lat/lon
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from app.services import geocode as geo_svc
from app.services import terrain as terrain_svc
from app.services import sites as sites_svc
from app.services import runoff as runoff_svc
from app import cache as cache_svc

router = APIRouter(prefix="/api/map", tags=["Map Analysis"])


# ------------------------------------------------------------------ schemas
class PolygonAnalysisRequest(BaseModel):
    """User-drawn polygon on the map (GeoJSON [lon, lat] ring)."""
    coordinates: List[List[float]]          # [[lon, lat], [lon, lat], ...]
    mean_annual_rainfall_mm: float = 1150.0  # can come from rainfall API
    num_candidates: int = 3
    dem_source: str = "satellite"            # "satellite" or "kml" (if preloaded)
    shape_type: str = "polygon"             # "polygon" | "circle" | "bbox"
    radius_m: Optional[float] = None        # required if shape_type == "circle"


class PointElevationRequest(BaseModel):
    lat: float
    lon: float
    bbox: Optional[dict] = None  # if omitted, fetches fresh DEM around the point


# ------------------------------------------------------------------ helpers
def _run_full_pipeline(bbox: dict, polygon_coords: list, rainfall_mm: float,
                       num_candidates: int, shape_type: str = "polygon",
                       radius_m: float | None = None):
    """Core pipeline: DEM → slope → mask → candidates → catchment → runoff → rank."""
    # 1. Fetch DEM (satellite or synthetic fallback)
    dem_result = geo_svc.fetch_dem_for_bbox(bbox, grid_size=60)
    dem = dem_result["dem"]
    cell_size_m = dem_result["cell_size_m"]

    # 2. Slope map
    slope = terrain_svc.compute_slope_pct(dem, cell_size_m)

    # 3. Build spatial mask from the user-drawn shape
    if shape_type == "circle" and radius_m is not None:
        # Circle: use centroid of polygon_coords as center
        lats = [p[1] for p in polygon_coords]
        lons = [p[0] for p in polygon_coords]
        centroid_lat = sum(lats) / len(lats)
        centroid_lon = sum(lons) / len(lons)
        area_mask = terrain_svc.mask_circle(bbox, dem.shape[0], dem.shape[1],
                                            centroid_lat, centroid_lon, radius_m)
    elif shape_type == "polygon" and len(polygon_coords) >= 3:
        area_mask = terrain_svc.mask_polygon(bbox, dem.shape[0], dem.shape[1], polygon_coords)
    else:
        area_mask = None  # bbox mode — no extra filtering

    candidates = sites_svc.generate_candidate_sites(
        dem, slope, bbox, top_n=num_candidates * 2, mask=area_mask
    )
    candidates = candidates[:num_candidates]

    # 4. D8 flow direction (computed once, reused for all candidates)
    direction = terrain_svc.d8_flow_direction(dem)

    # 5. For each candidate: delineate catchment → runoff estimate → pond sizing
    results = []
    for cand in candidates:
        pour_point = (cand["row"], cand["col"])
        mask = terrain_svc.delineate_catchment(direction, pour_point)
        area_ha = terrain_svc.catchment_area_ha(mask, cell_size_m)

        # Catchment GeoJSON boundary
        rows, cols = mask.shape
        ys, xs = mask.nonzero()
        step = max(1, len(ys) // 200)
        boundary_coords = [
            [
                bbox["min_lon"] + (x / cols) * (bbox["max_lon"] - bbox["min_lon"]),
                bbox["min_lat"] + (y / rows) * (bbox["max_lat"] - bbox["min_lat"]),
            ]
            for y, x in zip(ys[::step], xs[::step])
        ]

        # Runoff & pond sizing
        annual_runoff_m3 = runoff_svc.estimate_runoff_volume(area_ha, rainfall_mm, cand["land_type"])
        available_land_m2 = area_ha * 10_000 * 0.15  # assume 15% of catchment available for pond
        pond = runoff_svc.recommend_pond_dimensions(annual_runoff_m3, available_land_m2)

        # Recommendation composite score
        norm_area = min(area_ha / 20.0, 1.0)  # normalise over 20 ha
        rec_score = round(0.6 * norm_area + 0.4 * cand["suitability_score"], 3)

        results.append({
            "location": {"lat": cand["lat"], "lon": cand["lon"]},
            "elevation_m": round(float(dem[cand["row"], cand["col"]]), 1),
            "slope_pct": cand["slope_pct"],
            "land_type": cand["land_type"],
            "suitability_score": cand["suitability_score"],
            "recommendation_score": rec_score,
            "catchment": {
                "area_ha": round(area_ha, 2),
                "boundary_geojson": {
                    "type": "Feature",
                    "properties": {"area_ha": round(area_ha, 2)},
                    "geometry": {"type": "MultiPoint", "coordinates": boundary_coords},
                },
            },
            "hydrology": {
                "mean_annual_rainfall_mm": rainfall_mm,
                "annual_runoff_volume_m3": round(annual_runoff_m3, 0),
            },
            "pond_sizing": pond,
        })

    results.sort(key=lambda r: r["recommendation_score"], reverse=True)

    # Add rank labels
    for i, r in enumerate(results):
        r["rank"] = i + 1
        r["status"] = "RECOMMENDED" if i == 0 else f"Alternative #{i}"

    return results, dem_result


# ------------------------------------------------------------------ routes
@router.post("/analyze-area")
async def analyze_area(req: PolygonAnalysisRequest):
    """
    Accept a user-drawn polygon on the map, fetch satellite DEM for that area,
    and return: recommended pond site + catchment + expected water volume
    with GeoJSON overlays ready for the map.
    """
    if len(req.coordinates) < 3:
        raise HTTPException(400, "Polygon must have at least 3 coordinate pairs [[lon,lat],...]")

    bbox = geo_svc.polygon_bbox(req.coordinates)
    centroid_lat, centroid_lon = geo_svc.polygon_centroid(req.coordinates)

    # ── Cache lookup ──────────────────────────────────────────────────
    cache_key = cache_svc.make_cache_key(bbox, req.mean_annual_rainfall_mm, req.num_candidates)
    cached = cache_svc.get(cache_key)
    if cached:
        cached["cache_hit"] = True
        return cached

    try:
        results, dem_meta = _run_full_pipeline(
            bbox, req.coordinates, req.mean_annual_rainfall_mm, req.num_candidates,
            shape_type=req.shape_type, radius_m=req.radius_m
        )
    except Exception as e:
        raise HTTPException(500, f"Analysis pipeline error: {e}")

    if not results:
        raise HTTPException(422, "No suitable pond sites found within the selected area. Try a larger area.")


    recommended = results[0]

    response = {
        "polygon_bbox": bbox,
        "centroid": {"lat": centroid_lat, "lon": centroid_lon},
        "dem_source": dem_meta["source"],
        "dem_resolution_m": dem_meta["cell_size_m"],
        "elevation_range_m": dem_meta["elevation_range_m"],
        "recommended_site": recommended,
        "alternative_sites": results[1:],
        "all_sites": results,
        "cache_hit": False,
        # Pre-built map overlay payload
        "map_overlays": {
            "pond_marker": {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [recommended["location"]["lon"], recommended["location"]["lat"]]},
                "properties": {
                    "label": "Recommended Pond",
                    "water_volume_m3": recommended["hydrology"]["annual_runoff_volume_m3"],
                    "catchment_ha": recommended["catchment"]["area_ha"],
                    "depth_m": recommended["pond_sizing"]["recommended_depth_m"],
                },
            },
            "catchment_boundary": recommended["catchment"]["boundary_geojson"],
            "pond_polygon": _pond_polygon(recommended),
        },
        "summary": {
            "recommended_location": recommended["location"],
            "catchment_area_ha": recommended["catchment"]["area_ha"],
            "annual_water_volume_m3": recommended["hydrology"]["annual_runoff_volume_m3"],
            "pond_depth_m": recommended["pond_sizing"]["recommended_depth_m"],
            "pond_surface_area_m2": recommended["pond_sizing"]["recommended_surface_area_m2"],
            "storage_capacity_m3": recommended["pond_sizing"]["storage_capacity_m3"],
        }
    }

    # ── Save to cache (async-fire-and-forget style) ───────────────────
    cache_svc.set(cache_key, response)

    return response



def _pond_polygon(site: dict) -> dict:
    """Generate a small square GeoJSON polygon representing the pond footprint."""
    lat, lon = site["location"]["lat"], site["location"]["lon"]
    area_m2 = site["pond_sizing"].get("recommended_surface_area_m2", 2000)
    half_side_deg = (area_m2 ** 0.5) / 2 / 111_320
    return {
        "type": "Feature",
        "properties": {
            "label": "Pond Footprint",
            "area_m2": area_m2,
            "storage_m3": site["pond_sizing"].get("storage_capacity_m3", 0),
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [lon - half_side_deg, lat - half_side_deg],
                [lon + half_side_deg, lat - half_side_deg],
                [lon + half_side_deg, lat + half_side_deg],
                [lon - half_side_deg, lat + half_side_deg],
                [lon - half_side_deg, lat - half_side_deg],
            ]]
        }
    }


@router.post("/elevation-point")
async def elevation_at_point(req: PointElevationRequest):
    """
    Return bilinearly-interpolated elevation + slope at a single lat/lon.
    Fetches a small DEM centred on the point if no bbox is provided.
    """
    if req.bbox:
        bbox = req.bbox
    else:
        pad = 0.01  # ~1 km radius
        bbox = {
            "min_lat": req.lat - pad, "max_lat": req.lat + pad,
            "min_lon": req.lon - pad, "max_lon": req.lon + pad,
        }

    dem_result = geo_svc.fetch_dem_for_bbox(bbox, grid_size=30)
    dem = dem_result["dem"]
    slope = terrain_svc.compute_slope_pct(dem, dem_result["cell_size_m"])

    sample = geo_svc.sample_elevation_at_point(dem, bbox, req.lat, req.lon, slope)
    return {**sample, "dem_source": dem_result["source"], "bbox": bbox}


@router.get("/geocode")
async def geocode_address(address: str = Query(..., description="Full address or village name")):
    """Resolve an address to lat/lon using Nominatim (free, no API key needed)."""
    try:
        lat, lon = geo_svc.address_to_latlon(address)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"lat": lat, "lon": lon, "address": address}
