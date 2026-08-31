"""
POST /analyzeContour (alias: /findCatchment)

Accepts an uploaded KML/KMZ contour map, derives a DEM purely from its
contents (see services/contour_ingest.py), then reuses the existing
terrain/site-suitability/catchment machinery (services/terrain.py,
services/sites.py) — built for the bbox-driven flow — unchanged. This
route is the only new piece; everything downstream of "here's a DEM
grid" was already generalized and didn't need touching.

Nothing in this route is specific to any one uploaded file: bbox,
resolution, candidate locations, and catchment boundaries are all
computed from whatever contour file is posted.
"""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, UploadFile, File, HTTPException

from app.services import contour_ingest, terrain, sites as sites_service

router = APIRouter(prefix="/api/contour", tags=["contour-analysis"])

ALLOWED_EXTENSIONS = (".kml", ".kmz")


def _run_analysis(file_bytes: bytes, filename: str) -> dict:
    try:
        contours = contour_ingest.parse_contour_file(file_bytes, filename)
        dem_result = contour_ingest.build_dem_from_contours(contours)
    except contour_ingest.ContourParseError as e:
        raise HTTPException(400, f"Could not analyze contour file: {e}")

    dem = dem_result["elevation"]
    bbox = dem_result["bbox"]
    cell_size_m = dem_result["resolution_m"]

    slope = terrain.compute_slope_pct(dem, cell_size_m)
    candidates = sites_service.generate_candidate_sites(dem, slope, bbox, top_n=5)

    if not candidates:
        raise HTTPException(
            422,
            "No suitable pond location found — every point in this contour map exceeds the "
            f"slope threshold ({sites_service.MAX_SUITABLE_SLOPE_PCT}%). The terrain may be too steep.",
        )

    # D8 flow-direction only depends on the DEM, not on which candidate
    # we're checking — compute it once, reuse for every candidate's
    # catchment (same caching principle as routers/catchment.py's
    # per-village reuse in the bbox-driven flow).
    direction = terrain.d8_flow_direction(dem)

    analyzed_candidates = []
    for candidate in candidates:
        pour_point = (candidate["row"], candidate["col"])
        mask = terrain.delineate_catchment(direction, pour_point)
        area_ha = terrain.catchment_area_ha(mask, cell_size_m)

        rows, cols = mask.shape
        ys, xs = mask.nonzero()
        step = max(1, len(ys) // 150)
        boundary_points = [
            [
                bbox["min_lon"] + (x / cols) * (bbox["max_lon"] - bbox["min_lon"]),
                bbox["min_lat"] + (y / rows) * (bbox["max_lat"] - bbox["min_lat"]),
            ]
            for y, x in zip(ys[::step], xs[::step])
        ]

        analyzed_candidates.append(
            {
                "location": {"lat": candidate["lat"], "lon": candidate["lon"]},
                "slope_pct": candidate["slope_pct"],
                "land_type": candidate["land_type"],
                "suitability_score": candidate["suitability_score"],
                "catchment": {
                    "area_ha": round(area_ha, 2),
                    "boundary_geojson": {
                        "type": "Feature",
                        "properties": {"area_ha": round(area_ha, 2)},
                        "geometry": {"type": "MultiPoint", "coordinates": boundary_points},
                    },
                },
            }
        )

    # Recommend by a composite of catchment yield and site suitability, not
    # suitability alone — a perfectly flat site with almost no upstream
    # drainage area is a poor pond location even though it scores well on
    # slope. This mirrors the same storage-weighted principle used by
    # runoff.py's rank_candidates() for the bbox-driven flow, adapted here
    # since this route has no rainfall data to compute actual runoff volume.
    max_area = max((c["catchment"]["area_ha"] for c in analyzed_candidates), default=0) or 1.0
    for c in analyzed_candidates:
        normalized_area = c["catchment"]["area_ha"] / max_area
        c["recommendation_score"] = round(0.6 * normalized_area + 0.4 * c["suitability_score"], 3)

    analyzed_candidates.sort(key=lambda c: c["recommendation_score"], reverse=True)
    recommended = analyzed_candidates[0]

    return {
        "input_summary": {
            "filename": filename,
            "contour_line_count": dem_result["contour_count"],
            "elevation_range_m": dem_result["elevation_range_m"],
            "contour_interval_m": dem_result["interval_m"],
        },
        "derived_terrain": {
            "bbox": bbox,
            "grid_size": [dem_result["rows"], dem_result["cols"]],
            "resolution_m": round(cell_size_m, 2),
        },
        "recommended_site": recommended,
        "alternative_sites": analyzed_candidates[1:],
        "methodology": (
            "DEM interpolated from contour-line vertices via linear (Delaunay) "
            "interpolation with nearest-neighbor fill outside the convex hull. "
            "Candidate sites selected by slope threshold + minimum spacing "
            "(services/sites.py). Catchment delineated via D8 flow-direction "
            "and reverse-BFS from each candidate (services/terrain.py) — "
            "identical algorithm used by the bbox-driven /init pipeline. "
            "Final recommendation ranks candidates by a composite of "
            "normalized catchment area (60%) and site suitability (40%), "
            "since catchment yield matters more than slope alone for a "
            "usable pond site."
        ),
    }


@router.post("/analyzeContour")
async def analyze_contour(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(400, f"Unsupported file type. Expected one of: {ALLOWED_EXTENSIONS}")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(400, "Uploaded file is empty")

    return _run_analysis(file_bytes, file.filename)


@router.post("/findCatchment")
async def find_catchment(file: UploadFile = File(...)):
    """Alias of /analyzeContour — same behavior, offered under the PS's
    alternate suggested route name."""
    return await analyze_contour(file)