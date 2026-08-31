"""
Contour file ingestion service: parses KML/KMZ elevation contours and
interpolates them into a regular 2D DEM grid using Delaunay triangulation.
"""
from __future__ import annotations

import io
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Dict, List, Tuple

import numpy as np
from scipy.interpolate import griddata


class ContourParseError(Exception):
    """Raised when uploaded contour file is invalid or lacks elevation data."""
    pass


def _extract_kml_bytes(file_bytes: bytes, filename: str) -> bytes:
    if filename.lower().endswith(".kmz"):
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                kml_names = [n for n in z.namelist() if n.lower().endswith(".kml")]
                if not kml_names:
                    raise ContourParseError("KMZ archive contains no .kml files.")
                return z.read(kml_names[0])
        except zipfile.BadZipFile:
            raise ContourParseError("Invalid KMZ archive file.")
    return file_bytes


def _extract_elevation_from_elem(elem: ET.Element) -> float | None:
    # Try SimpleData or ExtendedData or name or description
    for text_elem in elem.iter():
        text = text_elem.text or ""
        # Check for numeric pattern or key like elevation/elev/contour
        match = re.search(r"[-+]?\d*\.\d+|\d+", text)
        if match and any(k in (elem.tag.lower() + text_elem.tag.lower() + text.lower()) for k in ("elev", "contour", "alt", "height", "z", "m")):
            try:
                return float(match.group(0))
            except ValueError:
                pass

    # Fallback to general number in name / description
    name_el = elem.find(".//{*}name")
    if name_el is not None and name_el.text:
        match = re.search(r"[-+]?\d*\.\d+|\d+", name_el.text)
        if match:
            try:
                return float(match.group(0))
            except ValueError:
                pass
    return None


def parse_contour_file(file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    """
    Parses a KML/KMZ byte string and extracts contour lines with their 3D coordinates.
    """
    kml_bytes = _extract_kml_bytes(file_bytes, filename)
    try:
        root = ET.fromstring(kml_bytes)
    except Exception as e:
        raise ContourParseError(f"Malformed KML/XML structure: {e}")

    contours = []
    # Find all Placemarks or LineStrings
    placemarks = root.findall(".//{*}Placemark")
    if not placemarks:
        # Check direct LineStrings
        placemarks = root.findall(".//{*}LineString")

    for pm in placemarks:
        coord_node = pm.find(".//{*}coordinates")
        if coord_node is None or not coord_node.text:
            continue

        raw_coords = coord_node.text.strip().split()
        parsed_pts = []
        for c_str in raw_coords:
            parts = c_str.split(",")
            if len(parts) >= 2:
                try:
                    lon = float(parts[0])
                    lat = float(parts[1])
                    alt = float(parts[2]) if len(parts) >= 3 else None
                    parsed_pts.append((lon, lat, alt))
                except ValueError:
                    continue

        if len(parsed_pts) < 2:
            continue

        elev = _extract_elevation_from_elem(pm)
        if elev is None and parsed_pts[0][2] is not None:
            elev = parsed_pts[0][2]

        if elev is None:
            elev = 0.0

        contours.append({
            "elevation": elev,
            "coordinates": [(p[0], p[1]) for p in parsed_pts],
            "raw_pts": parsed_pts,
        })

    if not contours:
        raise ContourParseError("No valid contour polylines found in KML file.")

    return contours


def build_dem_from_contours(
    contours: List[Dict[str, Any]], grid_size: int = 100
) -> Dict[str, Any]:
    """
    Interpolates scattered contour vertices into a regular 2D DEM elevation grid.
    """
    all_lons = []
    all_lats = []
    all_elevs = []

    for c in contours:
        elev = c["elevation"]
        for lon, lat in c["coordinates"]:
            all_lons.append(lon)
            all_lats.append(lat)
            all_elevs.append(elev)

    min_lon, max_lon = min(all_lons), max(all_lons)
    min_lat, max_lat = min(all_lats), max(all_lats)

    elevations_arr = np.array(all_elevs)
    min_elev, max_elev = float(elevations_arr.min()), float(elevations_arr.max())

    # Detect interval
    unique_elevs = sorted(set(round(e, 2) for e in all_elevs))
    if len(unique_elevs) > 1:
        diffs = np.diff(unique_elevs)
        interval = float(np.median(diffs[diffs > 0.01])) if len(diffs) > 0 else 1.0
    else:
        interval = 1.0

    # Grid coordinates
    grid_x = np.linspace(min_lon, max_lon, grid_size)
    grid_y = np.linspace(min_lat, max_lat, grid_size)
    gx, gy = np.meshgrid(grid_x, grid_y)

    points = np.column_stack((all_lons, all_lats))
    values = np.array(all_elevs)

    # Linear interpolation with nearest fill outside convex hull
    grid_z = griddata(points, values, (gx, gy), method="linear")
    grid_z_nearest = griddata(points, values, (gx, gy), method="nearest")
    grid_z[np.isnan(grid_z)] = grid_z_nearest[np.isnan(grid_z)]

    # Compute resolution in meters (approx haversine at latitude)
    lat_rad = math.radians((min_lat + max_lat) / 2)
    dy_m = (max_lat - min_lat) * 111_139
    dx_m = (max_lon - min_lon) * 111_139 * math.cos(lat_rad)
    resolution_m = float((dy_m / grid_size + dx_m / grid_size) / 2)

    return {
        "elevation": grid_z,
        "bbox": {
            "min_lat": min_lat,
            "min_lon": min_lon,
            "max_lat": max_lat,
            "max_lon": max_lon,
        },
        "resolution_m": resolution_m,
        "contour_count": len(contours),
        "elevation_range_m": [min_elev, max_elev],
        "interval_m": round(interval, 2),
        "rows": grid_size,
        "cols": grid_size,
    }
