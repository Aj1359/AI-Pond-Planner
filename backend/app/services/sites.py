"""
Land suitability module: generates candidate pond excavation sites from
the DEM's slope map, filtering for gentle slopes and assigning a
land-type + suitability score. In production this would also intersect
government land-record boundaries; here land_type is simulated from a
simple zonal pattern so the pipeline is fully runnable end-to-end.
"""
from __future__ import annotations

import numpy as np

MAX_SUITABLE_SLOPE_PCT = 6.0
LAND_TYPE_ZONES = ["barren", "fallow_cropland", "grassland", "cropland"]


def generate_candidate_sites(dem: np.ndarray, slope: np.ndarray, bbox: dict, top_n: int = 5) -> list[dict]:
    rows, cols = dem.shape
    suitable_mask = slope <= MAX_SUITABLE_SLOPE_PCT

    # Prefer local low points (natural depressions) among suitable cells
    candidates = []
    ys, xs = np.where(suitable_mask)
    if len(ys) == 0:
        return []

    # Sample a spread of low-elevation, low-slope points across the whole
    # suitable area (not just the single global lowest spot) by scanning
    # every suitable cell ordered by elevation and enforcing spacing.
    elevations = dem[ys, xs]
    order = np.argsort(elevations)

    min_spacing = max(3, min(rows, cols) // 12)
    seen_cells = []
    for idx in order:
        r, c = int(ys[idx]), int(xs[idx])
        if any(abs(r - sr) < min_spacing and abs(c - sc) < min_spacing for sr, sc in seen_cells):
            continue
        seen_cells.append((r, c))

        lat = bbox["min_lat"] + (r / rows) * (bbox["max_lat"] - bbox["min_lat"])
        lon = bbox["min_lon"] + (c / cols) * (bbox["max_lon"] - bbox["min_lon"])
        land_type = LAND_TYPE_ZONES[(r + c) % len(LAND_TYPE_ZONES)]
        slope_pct = float(slope[r, c])

        suitability = max(0.0, 1.0 - slope_pct / MAX_SUITABLE_SLOPE_PCT)
        if land_type in ("cropland",):
            suitability *= 0.6  # discourage taking productive farmland

        candidates.append(
            {
                "row": r,
                "col": c,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "slope_pct": round(slope_pct, 2),
                "land_type": land_type,
                "suitability_score": round(suitability, 3),
            }
        )
        if len(candidates) >= top_n * 4:  # gather extra, trimmed after sorting
            break

    candidates.sort(key=lambda c: c["suitability_score"], reverse=True)
    candidates = candidates[:top_n]
    for i, cand in enumerate(candidates):
        cand["id"] = i + 1
    return candidates