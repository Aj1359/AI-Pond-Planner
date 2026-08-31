"""
Contour map ingestion: KML/KMZ -> DEM grid.

A contour map is a set of polylines, each labeled with a constant
elevation (e.g. every vertex on the "280.0" line is at 280m). This is
fundamentally different from the raster DEM used by the bbox-driven
/init flow (elevation.py) — here we start with scattered, irregularly
spaced (lon, lat, elevation) points and have to interpolate them onto a
regular grid ourselves before any of the D8/slope/catchment machinery
in terrain.py can run, since that machinery only understands raster
grids.

Nothing here is specific to any one input file: the bounding box, grid
resolution, elevation range, and contour interval are all DERIVED from
whatever file is uploaded, never hardcoded, so this generalizes to any
KML/KMZ contour map with the same schema (Placemark name = elevation,
LineString coordinates = lon,lat vertices along that elevation).
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
from scipy.interpolate import griddata

# Practical bounds on the derived grid size — protects against a
# pathologically large/small input producing an unusable or
# resource-exhausting grid, without hardcoding anything about location.
MIN_GRID_DIM = 20
MAX_GRID_DIM = 150
TARGET_LONGEST_DIM = 100  # cells along the longer side of the AOI

METERS_PER_DEGREE_LAT = 111_320.0  # standard approximation, latitude-independent


class ContourParseError(ValueError):
    """Raised when the uploaded file isn't a parseable KML/KMZ contour map."""


def _strip_ns(tag: str) -> str:
    """KML uses a default XML namespace (xmlns="http://www.opengis.net/kml/2.2"),
    which makes every tag show up as '{http://...}Placemark' instead of
    'Placemark' under ElementTree. Stripping it lets us match tags by
    their plain name regardless of namespace, so this also tolerates
    KML variants that declare a different/no namespace."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _extract_kml_bytes(file_bytes: bytes, filename: str) -> bytes:
    """KMZ is just a zip archive containing one or more .kml files
    (conventionally doc.kml). Detect by filename extension first, then
    fall back to sniffing the zip magic bytes in case the extension is
    wrong/missing."""
    is_kmz = filename.lower().endswith(".kmz") or file_bytes[:2] == b"PK"
    if not is_kmz:
        return file_bytes

    with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
        kml_names = [n for n in z.namelist() if n.lower().endswith(".kml")]
        if not kml_names:
            raise ContourParseError("KMZ archive contains no .kml file")
        # Prefer doc.kml if present (KML spec convention), else take the first
        preferred = next((n for n in kml_names if n.lower().endswith("doc.kml")), kml_names[0])
        return z.read(preferred)


def parse_contour_file(file_bytes: bytes, filename: str) -> list[dict]:
    """Returns a list of {"elevation_m": float, "points": [(lon, lat), ...]}
    — one entry per contour-line Placemark found in the file. Elevation
    is read from each Placemark's <name>; falls back to skipping (with
    the parse continuing) any Placemark whose name isn't a plain number,
    since some KML exports include non-contour Placemarks (icons, labels)
    alongside the contour lines."""
    kml_bytes = _extract_kml_bytes(file_bytes, filename)

    try:
        root = ET.fromstring(kml_bytes)
    except ET.ParseError as e:
        raise ContourParseError(f"Could not parse XML: {e}") from e

    contours = []
    for elem in root.iter():
        if _strip_ns(elem.tag) != "Placemark":
            continue

        name_el = None
        coords_text = None
        for child in elem.iter():
            tag = _strip_ns(child.tag)
            if tag == "name" and name_el is None:
                name_el = child
            elif tag == "coordinates":
                coords_text = child.text

        if name_el is None or coords_text is None:
            continue

        try:
            elevation_m = float((name_el.text or "").strip())
        except ValueError:
            continue  # not a contour line (e.g. an icon/label Placemark) — skip, don't fail the whole file

        points = []
        for token in coords_text.split():
            parts = token.split(",")
            if len(parts) < 2:
                continue
            lon, lat = float(parts[0]), float(parts[1])
            points.append((lon, lat))

        if len(points) >= 2:
            contours.append({"elevation_m": elevation_m, "points": points})

    if not contours:
        raise ContourParseError(
            "No valid contour Placemarks found (expected <name> = elevation, <LineString><coordinates>)"
        )
    return contours


def _derive_grid_dimensions(lon_span: float, lat_span: float, mean_lat_deg: float) -> tuple[int, int, float]:
    """Sizes the grid so cells are approximately square in real-world
    metres, purely from the file's own coordinate extent — no fixed
    village size assumed. Returns (rows, cols, cell_size_m)."""
    meters_per_degree_lon = METERS_PER_DEGREE_LAT * np.cos(np.radians(mean_lat_deg))
    width_m = lon_span * meters_per_degree_lon
    height_m = lat_span * METERS_PER_DEGREE_LAT

    longest_m = max(width_m, height_m)
    cell_size_m = longest_m / TARGET_LONGEST_DIM if longest_m > 0 else 1.0

    cols = int(np.clip(round(width_m / cell_size_m), MIN_GRID_DIM, MAX_GRID_DIM))
    rows = int(np.clip(round(height_m / cell_size_m), MIN_GRID_DIM, MAX_GRID_DIM))
    return rows, cols, cell_size_m


def build_dem_from_contours(contours: list[dict]) -> dict:
    """Interpolates scattered (lon, lat, elevation) contour vertices onto
    a regular grid via linear (Delaunay-triangulation-based) interpolation,
    with a nearest-neighbor fill for any grid cells outside the convex
    hull of the input points (linear interpolation can't extrapolate).

    Returns everything downstream code needs, all derived from the input:
      - elevation: 2D grid
      - bbox: {min_lat, min_lon, max_lat, max_lon} — the file's own extent
      - resolution_m, rows, cols
      - contour_count, elevation_range_m, interval_m — summary stats
    """
    all_lons, all_lats, all_elevs = [], [], []
    for c in contours:
        for lon, lat in c["points"]:
            all_lons.append(lon)
            all_lats.append(lat)
            all_elevs.append(c["elevation_m"])

    lons = np.array(all_lons)
    lats = np.array(all_lats)
    elevs = np.array(all_elevs)

    min_lon, max_lon = float(lons.min()), float(lons.max())
    min_lat, max_lat = float(lats.min()), float(lats.max())
    mean_lat = (min_lat + max_lat) / 2

    rows, cols, cell_size_m = _derive_grid_dimensions(max_lon - min_lon, max_lat - min_lat, mean_lat)

    grid_lon = np.linspace(min_lon, max_lon, cols)
    grid_lat = np.linspace(min_lat, max_lat, rows)
    mesh_lon, mesh_lat = np.meshgrid(grid_lon, grid_lat)

    # Downsample source points if there are a huge number of vertices —
    # contour lines are highly redundant (many closely-spaced points along
    # the same line contribute almost no extra interpolation information),
    # so this keeps interpolation fast without materially changing the result.
    max_source_points = 20_000
    if len(lons) > max_source_points:
        idx = np.linspace(0, len(lons) - 1, max_source_points).astype(int)
        lons, lats, elevs = lons[idx], lats[idx], elevs[idx]

    points = np.column_stack([lons, lats])
    grid_elevation = griddata(points, elevs, (mesh_lon, mesh_lat), method="linear")

    # Fill any NaNs (outside the convex hull of contour points) with nearest-neighbor
    nan_mask = np.isnan(grid_elevation)
    if nan_mask.any():
        nearest_fill = griddata(points, elevs, (mesh_lon, mesh_lat), method="nearest")
        grid_elevation[nan_mask] = nearest_fill[nan_mask]

    unique_elevations = sorted(set(c["elevation_m"] for c in contours))
    diffs = np.diff(unique_elevations)
    interval_m = float(np.median(diffs)) if len(diffs) > 0 else None

    return {
        "elevation": grid_elevation,
        "bbox": {"min_lat": min_lat, "min_lon": min_lon, "max_lat": max_lat, "max_lon": max_lon},
        "resolution_m": cell_size_m,
        "rows": rows,
        "cols": cols,
        "contour_count": len(contours),
        "elevation_range_m": [float(min(unique_elevations)), float(max(unique_elevations))],
        "interval_m": interval_m,
    }