"""
Geocoding & Satellite DEM Services
  - address_to_latlon()      : Nominatim (free, no key) → (lat, lon)
  - fetch_dem_for_bbox()     : Open-Elevation API → 100x100 DEM grid for any bbox
  - sample_elevation_at_point(): bilinear interpolation lookup on an existing DEM grid
  - polygon_bbox()           : bounding box of a GeoJSON polygon / list of [lon,lat] points
"""
from __future__ import annotations
import time
import urllib.request
import json
import math
import numpy as np
from typing import Any, Dict, List, Tuple, Optional


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_HEADERS = {"User-Agent": "AIPondPlanner/2.0 (academic project)"}


def address_to_latlon(address: str) -> Tuple[float, float]:
    """Return (lat, lon) for a human-readable address using Nominatim.
    Raises ValueError if the address cannot be resolved."""
    params = urllib.parse.urlencode({"q": address, "format": "json", "limit": 1})
    url = f"{_NOMINATIM_URL}?{params}"
    req = urllib.request.Request(url, headers=_NOMINATIM_HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        results = json.loads(resp.read())
    if not results:
        raise ValueError(f"Could not geocode address: {address!r}")
    return float(results[0]["lat"]), float(results[0]["lon"])


import urllib.parse  # noqa: E402 (after the def above that uses it)


# ---------------------------------------------------------------------------
# Polygon / bbox helpers
# ---------------------------------------------------------------------------
def polygon_bbox(coordinates: List[List[float]]) -> Dict[str, float]:
    """
    Given a list of [lon, lat] pairs (GeoJSON order), return the bounding box.
    Adds a small ~200 m padding so the edges don't clip to exactly the polygon.
    """
    lons = [p[0] for p in coordinates]
    lats = [p[1] for p in coordinates]
    pad_lat = 0.002   # ~220 m
    pad_lon = 0.002
    return {
        "min_lat": min(lats) - pad_lat,
        "max_lat": max(lats) + pad_lat,
        "min_lon": min(lons) - pad_lon,
        "max_lon": max(lons) + pad_lon,
    }


def polygon_centroid(coordinates: List[List[float]]) -> Tuple[float, float]:
    """Return (lat, lon) centroid of a [lon,lat] polygon."""
    lons = [p[0] for p in coordinates]
    lats = [p[1] for p in coordinates]
    return sum(lats) / len(lats), sum(lons) / len(lons)


# ---------------------------------------------------------------------------
# Satellite DEM fetch (Open-Elevation → fallback synthetic)
# ---------------------------------------------------------------------------
_OPEN_ELEV_URL = "https://api.open-elevation.com/api/v1/lookup"
_GRID_SIZE = 50  # 50x50 grid per request (keeps payload < 5 kB)


def fetch_dem_for_bbox(bbox: Dict[str, float], grid_size: int = _GRID_SIZE) -> Dict[str, Any]:
    """
    Build a DEM raster (grid_size × grid_size) from the Open-Elevation API.
    Falls back to a synthetic plausible terrain if the API is unavailable.

    Returns a dict compatible with the KML-pipeline output:
        { "dem": np.ndarray, "bbox": bbox, "rows": R, "cols": C,
          "cell_size_m": float, "elevation_range_m": [min, max],
          "interval_m": estimated_interval, "contour_count": int,
          "source": "satellite"|"synthetic" }
    """
    R, C = grid_size, grid_size
    lat_arr = np.linspace(bbox["min_lat"], bbox["max_lat"], R)
    lon_arr = np.linspace(bbox["min_lon"], bbox["max_lon"], C)

    # Build query locations list
    locations = [
        {"latitude": float(lat_arr[r]), "longitude": float(lon_arr[c])}
        for r in range(R)
        for c in range(C)
    ]

    try:
        payload = json.dumps({"locations": locations}).encode()
        req = urllib.request.Request(
            _OPEN_ELEV_URL,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "AIPondPlanner/2.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        elevations_flat = [r["elevation"] for r in data["results"]]
        dem = np.array(elevations_flat, dtype=float).reshape(R, C)
        source = "satellite"
    except Exception:
        # Synthetic fallback: gentle sloped terrain with subtle undulations
        dem = _synthetic_dem(bbox, R, C)
        source = "synthetic"

    # Cell size estimate (metres per cell, latitude direction)
    lat_span_m = abs(bbox["max_lat"] - bbox["min_lat"]) * 111_320
    cell_size_m = lat_span_m / R

    z_min, z_max = float(dem.min()), float(dem.max())
    interval_m = max(1.0, round((z_max - z_min) / 20, 1))
    contour_count = int((z_max - z_min) / interval_m) * C

    return {
        "dem": dem,
        "bbox": bbox,
        "rows": R,
        "cols": C,
        "cell_size_m": round(cell_size_m, 2),
        "elevation_range_m": [round(z_min, 1), round(z_max, 1)],
        "interval_m": interval_m,
        "contour_count": contour_count,
        "source": source,
    }


def _synthetic_dem(bbox: Dict[str, float], R: int, C: int) -> np.ndarray:
    """
    Generate a plausible-looking synthetic DEM when the elevation API is down.
    Uses a base slope + two overlapping Gaussian hills/depressions.
    """
    rng = np.random.default_rng(
        seed=int((bbox["min_lat"] + bbox["min_lon"]) * 1000) % (2**32)
    )
    base_elev = 200.0 + rng.uniform(0, 100)
    rr, cc = np.mgrid[0:R, 0:C]
    # Gentle base slope
    dem = base_elev + (rr / R) * rng.uniform(5, 25) + (cc / C) * rng.uniform(-10, 10)
    # Add a depression (natural pond hollow)
    cr, cc_ = rng.uniform(0.3, 0.6), rng.uniform(0.3, 0.6)
    dem -= rng.uniform(5, 15) * np.exp(-((rr / R - cr) ** 2 + (cc / C - cc_) ** 2) / 0.05)
    # Small ridge
    dem += rng.uniform(3, 8) * np.exp(-((rr / R - 0.2) ** 2) / 0.02)
    return dem.astype(float)


# ---------------------------------------------------------------------------
# Bilinear interpolation lookup on an existing DEM grid
# ---------------------------------------------------------------------------
def sample_elevation_at_point(
    dem: np.ndarray,
    bbox: Dict[str, float],
    lat: float,
    lon: float,
    slope_map: Optional[np.ndarray] = None,
    method: str = "bilinear",
) -> Dict[str, Any]:
    """
    Given an existing DEM (R×C numpy array) and its bbox, find the elevation
    (and optionally slope) at an arbitrary continuous (lat, lon) using bilinear
    interpolation, plus the snapped (r, c) cell for catchment algorithms.

    Returns:
        {
          "elevation_m": float,
          "slope_pct": float | None,
          "grid_cell": (r, c),   # integer, for D8/BFS
          "r_frac": float,       # fractional row
          "c_frac": float,       # fractional col
          "in_bounds": bool
        }
    """
    R, C = dem.shape

    # Step 1 — inverse grid mapping  (lat/lon → fractional grid index)
    r_frac = (lat - bbox["min_lat"]) / (bbox["max_lat"] - bbox["min_lat"]) * (R - 1)
    c_frac = (lon - bbox["min_lon"]) / (bbox["max_lon"] - bbox["min_lon"]) * (C - 1)

    in_bounds = (0.0 <= r_frac <= R - 1) and (0.0 <= c_frac <= C - 1)

    # Snap for D8/BFS computation
    r_snap = int(round(r_frac))
    c_snap = int(round(c_frac))
    r_snap = max(0, min(R - 1, r_snap))
    c_snap = max(0, min(C - 1, c_snap))

    if not in_bounds or method == "nearest":
        elev = float(dem[r_snap, c_snap])
        slope = float(slope_map[r_snap, c_snap]) if slope_map is not None else None
        return {
            "elevation_m": round(elev, 2),
            "slope_pct": round(slope, 2) if slope is not None else None,
            "grid_cell": (r_snap, c_snap),
            "r_frac": round(r_frac, 4),
            "c_frac": round(c_frac, 4),
            "in_bounds": in_bounds,
        }

    # Step 2 — bilinear interpolation across surrounding 4 cells
    r0 = max(0, int(math.floor(r_frac)))
    r1 = min(R - 1, r0 + 1)
    c0 = max(0, int(math.floor(c_frac)))
    c1 = min(C - 1, c0 + 1)

    fr = r_frac - r0
    fc = c_frac - c0

    def _bilin(grid):
        return (
            grid[r0, c0] * (1 - fr) * (1 - fc)
            + grid[r1, c0] * fr * (1 - fc)
            + grid[r0, c1] * (1 - fr) * fc
            + grid[r1, c1] * fr * fc
        )

    elev = _bilin(dem)
    slope = _bilin(slope_map) if slope_map is not None else None

    return {
        "elevation_m": round(float(elev), 2),
        "slope_pct": round(float(slope), 2) if slope is not None else None,
        "grid_cell": (r_snap, c_snap),
        "r_frac": round(r_frac, 4),
        "c_frac": round(c_frac, 4),
        "in_bounds": in_bounds,
    }
