"""
Terrain analysis: contour extraction, D8 flow direction, flow accumulation,
and catchment (watershed) delineation for a given pour point.
"""
from __future__ import annotations

import numpy as np

# D8 neighbor offsets (row, col) and their compass directions
D8_OFFSETS = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]


def extract_contours(dem: np.ndarray, interval_m: float = 3.0):
    """Extract contour lines at fixed elevation intervals using matplotlib's
    contour generator (marching-squares), returned as GeoJSON-like line
    coordinates in grid-index space (frontend maps these to lat/lon)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    z_min, z_max = float(dem.min()), float(dem.max())
    levels = np.arange(np.floor(z_min), np.ceil(z_max) + interval_m, interval_m)

    fig, ax = plt.subplots()
    cs = ax.contour(dem, levels=levels)
    plt.close(fig)

    features = []
    for level, segs in zip(cs.levels, cs.allsegs):
        for seg in segs:
            if len(seg) < 2:
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": {"elevation_m": float(level)},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": seg.tolist(),
                    },
                }
            )
    return {"type": "FeatureCollection", "features": features}


def compute_slope_pct(dem: np.ndarray, cell_size_m: float) -> np.ndarray:
    """Slope magnitude (%) at every cell using a simple gradient method."""
    gy, gx = np.gradient(dem, cell_size_m)
    slope_rad = np.arctan(np.sqrt(gx**2 + gy**2))
    return np.tan(slope_rad) * 100.0


def d8_flow_direction(dem: np.ndarray) -> np.ndarray:
    """For every cell, pick the neighbor with the steepest downhill gradient.
    Returns an array of the same shape holding an index 0-7 into D8_OFFSETS,
    or -1 for cells with no downhill neighbor (local sinks/pits)."""
    rows, cols = dem.shape
    direction = np.full((rows, cols), -1, dtype=int)

    for r in range(rows):
        for c in range(cols):
            best_slope = 0.0
            best_dir = -1
            for i, (dr, dc) in enumerate(D8_OFFSETS):
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    dist = np.hypot(dr, dc)
                    drop = dem[r, c] - dem[nr, nc]
                    slope = drop / dist
                    if slope > best_slope:
                        best_slope = slope
                        best_dir = i
            direction[r, c] = best_dir
    return direction


def flow_accumulation(direction: np.ndarray) -> np.ndarray:
    """Number of upstream cells draining through each cell, computed by
    topologically processing cells from highest accumulation dependency."""
    rows, cols = direction.shape
    accum = np.ones((rows, cols), dtype=int)

    # Build downstream target for each cell
    downstream = {}
    indegree = np.zeros((rows, cols), dtype=int)
    for r in range(rows):
        for c in range(cols):
            d = direction[r, c]
            if d != -1:
                dr, dc = D8_OFFSETS[d]
                nr, nc = r + dr, c + dc
                downstream[(r, c)] = (nr, nc)
                indegree[nr, nc] += 1

    from collections import deque

    queue = deque((r, c) for r in range(rows) for c in range(cols) if indegree[r, c] == 0)
    processed = np.zeros((rows, cols), dtype=bool)

    while queue:
        r, c = queue.popleft()
        if processed[r, c]:
            continue
        processed[r, c] = True
        if (r, c) in downstream:
            nr, nc = downstream[(r, c)]
            accum[nr, nc] += accum[r, c]
            indegree[nr, nc] -= 1
            if indegree[nr, nc] == 0:
                queue.append((nr, nc))
    return accum


def delineate_catchment(direction: np.ndarray, pour_point: tuple[int, int]) -> np.ndarray:
    """Boolean mask of every cell whose flow path eventually passes through
    pour_point, found by reverse-tracing D8 directions (BFS upstream)."""
    rows, cols = direction.shape
    mask = np.zeros((rows, cols), dtype=bool)

    # Precompute reverse adjacency: for each cell, which neighbors flow into it
    reverse = {}
    for r in range(rows):
        for c in range(cols):
            d = direction[r, c]
            if d != -1:
                dr, dc = D8_OFFSETS[d]
                nr, nc = r + dr, c + dc
                reverse.setdefault((nr, nc), []).append((r, c))

    from collections import deque

    queue = deque([pour_point])
    mask[pour_point] = True
    while queue:
        cell = queue.popleft()
        for upstream_cell in reverse.get(cell, []):
            if not mask[upstream_cell]:
                mask[upstream_cell] = True
                queue.append(upstream_cell)
    return mask


def catchment_area_ha(mask: np.ndarray, cell_size_m: float) -> float:
    cell_area_m2 = cell_size_m**2
    return float(mask.sum() * cell_area_m2 / 10_000.0)