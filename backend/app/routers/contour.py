"""
Contour Analysis & Ingestion API Router.

Provides end-to-end watershed analysis from uploaded KML/KMZ contour files,
as well as modular endpoints for polyline extraction and Delaunay DEM grid generation.
"""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, UploadFile, File, HTTPException

from app.services import contour_ingest, terrain, sites as sites_service

router = APIRouter(prefix="/api/contour", tags=["contour-analysis"])

ALLOWED_EXTENSIONS = (".kml", ".kmz")


def _check_upload(file: UploadFile) -> None:
    if not file.filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(400, f"Unsupported file type. Expected one of: {ALLOWED_EXTENSIONS}")


@router.post("/extract-polylines")
async def extract_polylines(file: UploadFile = File(...)):
    """Extract raw contour polylines, elevations, and intervals from KML/KMZ."""
    _check_upload(file)
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(400, "Uploaded file is empty")

    try:
        contours = contour_ingest.parse_contour_file(file_bytes, file.filename)
    except contour_ingest.ContourParseError as e:
        raise HTTPException(400, f"Could not parse contour file: {e}")

    elevations = sorted(set(c["elevation_m"] for c in contours))
    intervals = np.diff(elevations) if len(elevations) > 1 else [0.0]
    estimated_interval = float(np.median(intervals)) if len(intervals) > 0 else 0.0

    return {
        "filename": file.filename,
        "total_contour_lines": len(contours),
        "elevation_min_m": min(elevations) if elevations else 0.0,
        "elevation_max_m": max(elevations) if elevations else 0.0,
        "estimated_interval_m": round(estimated_interval, 2),
        "unique_elevation_levels_count": len(elevations),
    }


@router.post("/dem-from-kml")
async def dem_from_kml(file: UploadFile = File(...)):
    """Interpolate a 100x100 DEM raster grid directly from KML/KMZ contour polylines."""
    _check_upload(file)
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(400, "Uploaded file is empty")

    try:
        contours = contour_ingest.parse_contour_file(file_bytes, file.filename)
        dem_result = contour_ingest.build_dem_from_contours(contours)
    except contour_ingest.ContourParseError as e:
        raise HTTPException(400, f"Could not interpolate DEM from contours: {e}")

    return {
        "filename": file.filename,
        "bbox": dem_result["bbox"],
        "grid_size": [dem_result["rows"], dem_result["cols"]],
        "resolution_m": round(dem_result["resolution_m"], 2),
        "elevation_range_m": dem_result["elevation_range_m"],
        "contour_count": dem_result["contour_count"],
        "elevation": dem_result["elevation"].tolist(),
    }


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
            "and reverse-BFS from each candidate (services/terrain.py). "
            "Final recommendation ranks candidates by a composite of "
            "normalized catchment area (60%) and site suitability (40%)."
        ),
    }


@router.post("/analyzeContour")
async def analyze_contour(file: UploadFile = File(...)):
    """End-to-end KML/KMZ upload analysis: DEM generation, slope calculation, candidate selection, D8 catchment delineation."""
    _check_upload(file)
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(400, "Uploaded file is empty")

    return _run_analysis(file_bytes, file.filename)


@router.post("/findCatchment")
async def find_catchment(file: UploadFile = File(...)):
    """Alias for /analyzeContour."""
    return await analyze_contour(file)