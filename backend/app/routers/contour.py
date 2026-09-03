"""
Contour Analysis & Ingestion API Router.

Supports all standard and legacy endpoint paths:
- /analyzeContour
- /findCatchment
- /api/analyzeContour
- /api/findCatchment
- /api/v1/analyzeContour
- /api/contour/analyzeContour
- /api/contour/findCatchment
"""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Query

from app.services import contour_ingest, terrain, sites as sites_service

router = APIRouter(tags=["contour-analysis"])

ALLOWED_EXTENSIONS = (".kml", ".kmz")


async def _extract_file_bytes_and_name(request: Request, file: UploadFile | None = None) -> tuple[bytes, str]:
    """
    Robustly extracts uploaded file bytes and filename across any form field key
    (e.g., 'file', 'contour_file', 'upload_file') or raw body.
    """
    # 1. Direct FastAPI UploadFile parameter
    if file is not None and getattr(file, "filename", None):
        content = await file.read()
        if content:
            return content, file.filename

    # 2. Inspect request form data for any file field
    try:
        form = await request.form()
        for key, val in form.items():
            if hasattr(val, "read") and hasattr(val, "filename"):
                content = await val.read()
                if content:
                    return content, val.filename
    except Exception:
        pass

    # 3. Inspect raw request body (e.g. direct raw KML payload)
    try:
        body = await request.body()
        if body and (b"<kml" in body or b"PK\x03\x04" in body or b"<?xml" in body or b"coordinates" in body):
            return body, "upload.kml"
    except Exception:
        pass

    raise HTTPException(400, "Uploaded file is empty or missing. Please upload a valid .kml or .kmz file.")


def _run_analysis(file_bytes: bytes, filename: str, num_candidates: int = 5) -> dict:
    if not filename.lower().endswith(ALLOWED_EXTENSIONS) and not (b"<kml" in file_bytes or b"PK\x03\x04" in file_bytes):
        raise HTTPException(400, f"Unsupported file type. Expected one of: {ALLOWED_EXTENSIONS}")

    try:
        contours = contour_ingest.parse_contour_file(file_bytes, filename)
        dem_result = contour_ingest.build_dem_from_contours(contours)
    except contour_ingest.ContourParseError as e:
        raise HTTPException(400, f"Could not analyze contour file: {e}")

    dem = dem_result["elevation"]
    bbox = dem_result["bbox"]
    cell_size_m = dem_result["resolution_m"]

    slope = terrain.compute_slope_pct(dem, cell_size_m)
    candidates = sites_service.generate_candidate_sites(dem, slope, bbox, top_n=num_candidates)

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


# Route handler that accepts all alias paths and query parameters
async def _handle_contour_analysis_request(
    request: Request,
    file: UploadFile = File(None),
    num_candidates: int = Query(5),
    resolution: float = Query(None),
):
    file_bytes, filename = await _extract_file_bytes_and_name(request, file)
    return _run_analysis(file_bytes, filename, num_candidates=num_candidates)


# Register all standard and alias routes
for path in [
    "/analyzeContour",
    "/findCatchment",
    "/api/analyzeContour",
    "/api/findCatchment",
    "/api/v1/analyzeContour",
    "/api/contour/analyzeContour",
    "/api/contour/findCatchment",
]:
    router.add_api_route(path, _handle_contour_analysis_request, methods=["POST"])


@router.post("/api/contour/extract-polylines")
async def extract_polylines(request: Request, file: UploadFile = File(None)):
    """Extract raw contour polylines, elevations, and intervals from KML/KMZ."""
    file_bytes, filename = await _extract_file_bytes_and_name(request, file)
    try:
        contours = contour_ingest.parse_contour_file(file_bytes, filename)
    except contour_ingest.ContourParseError as e:
        raise HTTPException(400, f"Could not parse contour file: {e}")

    elevations = sorted(set(c["elevation_m"] for c in contours))
    intervals = np.diff(elevations) if len(elevations) > 1 else [0.0]
    estimated_interval = float(np.median(intervals)) if len(intervals) > 0 else 0.0

    return {
        "filename": filename,
        "total_contour_lines": len(contours),
        "elevation_min_m": min(elevations) if elevations else 0.0,
        "elevation_max_m": max(elevations) if elevations else 0.0,
        "estimated_interval_m": round(estimated_interval, 2),
        "unique_elevation_levels_count": len(elevations),
    }


@router.post("/api/contour/dem-from-kml")
async def dem_from_kml(request: Request, file: UploadFile = File(None)):
    """Interpolate a 100x100 DEM raster grid directly from KML/KMZ contour polylines."""
    file_bytes, filename = await _extract_file_bytes_and_name(request, file)
    try:
        contours = contour_ingest.parse_contour_file(file_bytes, filename)
        dem_result = contour_ingest.build_dem_from_contours(contours)
    except contour_ingest.ContourParseError as e:
        raise HTTPException(400, f"Could not interpolate DEM from contours: {e}")

    return {
        "filename": filename,
        "bbox": dem_result["bbox"],
        "grid_size": [dem_result["rows"], dem_result["cols"]],
        "resolution_m": round(dem_result["resolution_m"], 2),
        "elevation_range_m": dem_result["elevation_range_m"],
        "contour_count": dem_result["contour_count"],
        "elevation": dem_result["elevation"].tolist(),
    }