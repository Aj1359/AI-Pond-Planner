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

Includes clean tabular summaries and optional HTML visual table rendering for browsers.
"""
from __future__ import annotations

import json
import numpy as np
from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse

from app.services import contour_ingest, terrain, sites as sites_service

router = APIRouter(tags=["contour-analysis"])

ALLOWED_EXTENSIONS = (".kml", ".kmz")


async def _extract_file_bytes_and_name(request: Request, file: UploadFile | None = None) -> tuple[bytes, str]:
    """
    Robustly extracts uploaded file bytes and filename across any form field key
    (e.g., 'file', 'contour_file', 'upload_file') or raw body.
    """
    if file is not None and getattr(file, "filename", None):
        content = await file.read()
        if content:
            return content, file.filename

    try:
        form = await request.form()
        for key, val in form.items():
            if hasattr(val, "read") and hasattr(val, "filename"):
                content = await val.read()
                if content:
                    return content, val.filename
    except Exception:
        pass

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

    # Build clean tabular summary list for easy display in tables or dashboards
    table_rows = []
    for rank, site in enumerate(analyzed_candidates, start=1):
        table_rows.append({
            "rank": rank,
            "status": "RECOMMENDED" if rank == 1 else f"Alternative #{rank-1}",
            "latitude": site["location"]["lat"],
            "longitude": site["location"]["lon"],
            "slope_pct": site["slope_pct"],
            "land_type": site["land_type"],
            "catchment_area_ha": site["catchment"]["area_ha"],
            "suitability_score": site["suitability_score"],
            "recommendation_score": site["recommendation_score"]
        })

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
        "summary_table": table_rows,
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


def _render_html_dashboard(data: dict) -> str:
    """Renders a modern, responsive HTML dashboard table for browser views."""
    input_s = data["input_summary"]
    terrain_s = data["derived_terrain"]
    rec = data["recommended_site"]
    table_rows = data.get("summary_table", [])

    rows_html = ""
    for r in table_rows:
        badge_cls = "bg-green-100 text-green-800 border-green-300" if r["rank"] == 1 else "bg-gray-100 text-gray-700 border-gray-200"
        rows_html += f"""
        <tr class="hover:bg-blue-50/50 transition">
            <td class="px-4 py-3 font-semibold text-center"><span class="inline-block px-2 py-0.5 text-xs font-bold rounded-full border {badge_cls}">#{r['rank']} {r['status']}</span></td>
            <td class="px-4 py-3 font-mono text-xs">{r['latitude']:.5f}, {r['longitude']:.5f}</td>
            <td class="px-4 py-3 text-center">{r['slope_pct']}%</td>
            <td class="px-4 py-3 capitalize">{r['land_type'].replace('_', ' ')}</td>
            <td class="px-4 py-3 text-right font-semibold text-blue-600">{r['catchment_area_ha']:.2f} ha</td>
            <td class="px-4 py-3 text-right">{r['suitability_score']:.3f}</td>
            <td class="px-4 py-3 text-right font-bold text-emerald-600">{r['recommendation_score']:.3f}</td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Village Pond Siting Analysis Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>body {{ font-family: 'Inter', sans-serif; }}</style>
</head>
<body class="bg-slate-50 text-slate-800 min-h-screen p-6">
    <div class="max-w-6xl mx-auto space-y-6">
        <!-- Header -->
        <header class="bg-gradient-to-r from-blue-700 to-indigo-800 text-white rounded-2xl p-6 shadow-lg flex justify-between items-center">
            <div>
                <h1 class="text-2xl font-bold">AI-Assisted Village Pond Siting Report</h1>
                <p class="text-blue-100 text-sm mt-1">Delaunay Interpolation | D8 Watershed Routing | Multi-Criteria Siting</p>
            </div>
            <div class="text-right">
                <span class="inline-block bg-emerald-500 text-white px-3 py-1 rounded-full text-xs font-semibold shadow">Phase 1 Complete</span>
                <p class="text-xs text-blue-200 mt-1">File: {input_s['filename']}</p>
            </div>
        </header>

        <!-- Stats Overview Cards -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
                <p class="text-xs font-semibold text-slate-400 uppercase">Contour Lines</p>
                <p class="text-2xl font-bold text-slate-800 mt-1">{input_s['contour_line_count']:,}</p>
                <p class="text-xs text-slate-500 mt-1">Interval: {input_s['contour_interval_m']}m</p>
            </div>
            <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
                <p class="text-xs font-semibold text-slate-400 uppercase">Elevation Range</p>
                <p class="text-2xl font-bold text-indigo-600 mt-1">{input_s['elevation_range_m'][0]}m - {input_s['elevation_range_m'][1]}m</p>
                <p class="text-xs text-slate-500 mt-1">Span: {input_s['elevation_range_m'][1] - input_s['elevation_range_m'][0]}m</p>
            </div>
            <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
                <p class="text-xs font-semibold text-slate-400 uppercase">DEM Grid Resolution</p>
                <p class="text-2xl font-bold text-slate-800 mt-1">{terrain_s['resolution_m']}m / cell</p>
                <p class="text-xs text-slate-500 mt-1">Shape: {terrain_s['grid_size'][0]}x{terrain_s['grid_size'][1]}</p>
            </div>
            <div class="bg-gradient-to-br from-emerald-500 to-teal-600 text-white p-5 rounded-xl shadow-md">
                <p class="text-xs font-semibold text-emerald-100 uppercase">Top Site Catchment</p>
                <p class="text-2xl font-bold mt-1">{rec['catchment']['area_ha']} ha</p>
                <p class="text-xs text-emerald-100 mt-1">Score: {rec['recommendation_score']:.3f} / 1.0</p>
            </div>
        </div>

        <!-- Siting Table -->
        <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div class="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex justify-between items-center">
                <h2 class="font-bold text-slate-800">Evaluated Candidate Pond Locations (Ranked)</h2>
                <span class="text-xs text-slate-500 font-medium">Sorted by composite recommendation utility</span>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-sm text-left">
                    <thead class="bg-slate-100/70 text-slate-600 text-xs font-semibold uppercase tracking-wider">
                        <tr>
                            <th class="px-4 py-3 text-center">Rank</th>
                            <th class="px-4 py-3">Coordinates (Lat, Lon)</th>
                            <th class="px-4 py-3 text-center">Slope</th>
                            <th class="px-4 py-3">Land Cover</th>
                            <th class="px-4 py-3 text-right">Contributing Basin</th>
                            <th class="px-4 py-3 text-right">Suitability</th>
                            <th class="px-4 py-3 text-right">Utility Score</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                        {rows_html}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Methodology Footer -->
        <div class="bg-slate-100 rounded-xl p-4 text-xs text-slate-600 leading-relaxed border border-slate-200">
            <span class="font-bold text-slate-700">Methodology:</span> {data['methodology']}
        </div>
    </div>
</body>
</html>"""


# Route handler that accepts all alias paths, formats, and query parameters
async def _handle_contour_analysis_request(
    request: Request,
    file: UploadFile = File(None),
    num_candidates: int = Query(5),
    resolution: float = Query(None),
    format: str = Query("json"),
):
    file_bytes, filename = await _extract_file_bytes_and_name(request, file)
    result = _run_analysis(file_bytes, filename, num_candidates=num_candidates)

    accept_header = request.headers.get("Accept", "")
    if format == "html" or ("text/html" in accept_header and "application/json" not in accept_header):
        return HTMLResponse(_render_html_dashboard(result))

    return JSONResponse(result)


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
    router.add_api_route(path, _handle_contour_analysis_request, methods=["POST", "GET"])


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