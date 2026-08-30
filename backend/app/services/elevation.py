import hashlib
import logging
from typing import Any, Dict, List, Optional, Union

import numpy as np
import requests
from scipy.ndimage import gaussian_filter

try:
    from app.schemas import BoundingBox
except ImportError:
    BoundingBox = None

logger = logging.getLogger(__name__)


def _extract_bbox_coords(bbox: Union[Dict[str, float], Any]) -> tuple[float, float, float, float]:
    """Extract (min_lat, min_lon, max_lat, max_lon) from a dict or BoundingBox model."""
    if isinstance(bbox, dict):
        return (
            float(bbox["min_lat"]),
            float(bbox["min_lon"]),
            float(bbox["max_lat"]),
            float(bbox["max_lon"]),
        )
    return (
        float(bbox.min_lat),
        float(bbox.min_lon),
        float(bbox.max_lat),
        float(bbox.max_lon),
    )


def _synthetic_dem(
    bbox: Union[Dict[str, float], Any], seed: Optional[int] = None
) -> Dict[str, Any]:
    """
    Generate a reproducible 100x100 synthetic digital elevation model (DEM).
    
    Uses sine/cosine waves for rolling terrain, a Gaussian valley dip for drainage,
    and random noise, smoothed with scipy.ndimage.gaussian_filter.
    """
    min_lat, min_lon, max_lat, max_lon = _extract_bbox_coords(bbox)

    if seed is None:
        coord_key = f"{min_lat:.5f}_{min_lon:.5f}_{max_lat:.5f}_{max_lon:.5f}"
        seed = int(hashlib.md5(coord_key.encode("utf-8")).hexdigest(), 16) % (2**31 - 1)

    rng = np.random.default_rng(seed)

    x = np.linspace(0, 4 * np.pi, 100)
    y = np.linspace(0, 4 * np.pi, 100)
    X, Y = np.meshgrid(x, y)

    # Base elevation and rolling hills (sine / cosine waves)
    base_elevation = 280.0
    rolling = 15.0 * np.sin(X) + 12.0 * np.cos(Y) + 8.0 * np.sin(0.5 * (X + Y))

    # Gaussian "valley" dip for water accumulation / drainage
    cx = rng.uniform(1.2 * np.pi, 2.8 * np.pi)
    cy = rng.uniform(1.2 * np.pi, 2.8 * np.pi)
    sigma_valley = rng.uniform(1.0, 1.8)
    valley = -30.0 * np.exp(-((X - cx) ** 2 + (Y - cy) ** 2) / (2 * (sigma_valley**2)))

    # Terrain roughness / noise
    noise = rng.normal(0, 1.5, size=(100, 100))

    raw_grid = base_elevation + rolling + valley + noise
    smoothed = gaussian_filter(raw_grid, sigma=1.2)

    return {
        "source": "synthetic",
        "elevation": np.round(smoothed, 2).tolist(),
    }


def get_dem(bbox: Union[Dict[str, float], Any]) -> Dict[str, Any]:
    """
    Retrieve 100x100 DEM grid for the given bounding box.
    
    Attempts to fetch from Open-Elevation API with a short timeout.
    Falls through to _synthetic_dem on network error, timeout, or API failure.
    Always indicates the actual source used.
    """
    min_lat, min_lon, max_lat, max_lon = _extract_bbox_coords(bbox)

    # Attempt Open-Elevation API
    try:
        url = "https://api.open-elevation.com/api/v1/lookup"
        # 100x100 grid of lat/lon points
        lats = np.linspace(min_lat, max_lat, 100)
        lons = np.linspace(min_lon, max_lon, 100)
        
        # Build coordinates list (row-major: lat descending or ascending, lon ascending)
        locations = [
            {"latitude": float(lat), "longitude": float(lon)}
            for lat in lats
            for lon in lons
        ]

        response = requests.post(
            url,
            json={"locations": locations},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=3.0,
        )

        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            if len(results) == 10000:
                elevations = [r["elevation"] for r in results]
                grid_2d = np.array(elevations).reshape((100, 100)).tolist()
                return {
                    "source": "open-elevation",
                    "elevation": grid_2d,
                }
    except Exception as e:
        logger.warning("Open-Elevation lookup failed or timed out (%s). Falling back to synthetic DEM.", e)

    # Fallback to synthetic DEM
    return _synthetic_dem(bbox)
