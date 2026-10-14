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


def mfd_flow_fractions(dem: np.ndarray, p: float = 1.1) -> np.ndarray:
    """
    Multiple Flow Direction (MFD, Quinn et al. 1991 / Holmgren 1994).
    Calculates the proportion of flow leaving cell (r, c) toward each of its 8 neighbors.
    Returns an array of shape (rows, cols, 8) with values in [0, 1].
    For cells with no downhill neighbor (sinks), all fractions are 0.
    """
    rows, cols = dem.shape
    fractions = np.zeros((rows, cols, 8), dtype=float)

    for r in range(rows):
        for c in range(cols):
            z_curr = dem[r, c]
            weights = np.zeros(8, dtype=float)
            for i, (dr, dc) in enumerate(D8_OFFSETS):
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    drop = z_curr - dem[nr, nc]
                    if drop > 0:
                        dist = np.hypot(dr, dc)
                        slope = drop / dist
                        weights[i] = slope ** p
            total_w = weights.sum()
            if total_w > 0:
                fractions[r, c] = weights / total_w
    return fractions


def delineate_catchment_mfd(
    dem: np.ndarray,
    pour_point: tuple[int, int],
    p: float = 1.1,
    threshold: float = 0.05,
) -> np.ndarray:
    """
    Delineates the upstream catchment for pour_point using Multiple Flow Direction (MFD).
    Calculates the exact fraction of runoff from every cell that drains into pour_point.
    Returns a boolean mask of cells contributing >= threshold fraction.
    """
    rows, cols = dem.shape
    fractions = mfd_flow_fractions(dem, p=p)

    # P[r, c] represents the fraction of water from (r, c) that reaches pour_point
    P = np.zeros((rows, cols), dtype=float)
    P[pour_point] = 1.0

    # Sort all cells by elevation in ascending order (lowest to highest)
    # Since water flows strictly downhill (z_source > z_target), processing in
    # ascending order guarantees that when cell u is processed, all downhill neighbors
    # v (where z_v < z_u) already have their P[v] values fully determined!
    sorted_cells = np.argsort(dem.ravel())

    pour_z = dem[pour_point]
    for idx in sorted_cells:
        r, c = divmod(int(idx), cols)
        if dem[r, c] < pour_z:
            continue
        if (r, c) == pour_point:
            continue

        # Accumulate contributions through all downhill neighbors
        cell_contrib = 0.0
        for i, (dr, dc) in enumerate(D8_OFFSETS):
            f = fractions[r, c, i]
            if f > 0:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    cell_contrib += f * P[nr, nc]
        P[r, c] = cell_contrib

    mask = P >= threshold
    mask[pour_point] = True
    return mask


# ──────────────────────────────────────────────────────────────────────────────
# HEXAGONAL GRID TOPOLOGY (H6) — Uniform Equidistant Flow Routing
# ──────────────────────────────────────────────────────────────────────────────
# In an "odd-r" offset hexagonal layout, every cell has 6 equidistant neighbors (d = 1.0),
# completely eliminating the sqrt(2) diagonal metric distortion of Cartesian square grids.

HEX_EVEN_R_OFFSETS = [(-1, -1), (-1, 0), (0, 1), (1, 0), (1, -1), (0, -1)]
HEX_ODD_R_OFFSETS  = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (0, -1)]


def get_hex_neighbors(r: int, c: int, rows: int, cols: int) -> list[tuple[int, int]]:
    """Returns list of (nr, nc) coordinates for the 6 equidistant hexagonal neighbors."""
    offsets = HEX_ODD_R_OFFSETS if (r % 2 != 0) else HEX_EVEN_R_OFFSETS
    neighbors = []
    for dr, dc in offsets:
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            neighbors.append((nr, nc))
    return neighbors


def hex_flow_fractions(dem: np.ndarray, p: float = 1.1) -> dict[tuple[int, int], dict[tuple[int, int], float]]:
    """
    Multiple Flow Direction on a Uniform Hexagonal Grid (H6-MFD).
    Because all 6 neighbors are strictly equidistant, slope drop is directly proportional
    to elevation drop without any diagonal sqrt(2) distortion.
    """
    rows, cols = dem.shape
    hex_fractions = {}

    for r in range(rows):
        for c in range(cols):
            z_curr = dem[r, c]
            neighbors = get_hex_neighbors(r, c, rows, cols)
            weights = []
            downhill_neighbors = []
            for nr, nc in neighbors:
                drop = z_curr - dem[nr, nc]
                if drop > 0:
                    downhill_neighbors.append((nr, nc))
                    weights.append(drop ** p)

            total_w = sum(weights)
            if total_w > 0:
                hex_fractions[(r, c)] = {
                    n_coord: w / total_w
                    for n_coord, w in zip(downhill_neighbors, weights)
                }
            else:
                hex_fractions[(r, c)] = {}
    return hex_fractions


def delineate_catchment_hex(
    dem: np.ndarray,
    pour_point: tuple[int, int],
    p: float = 1.1,
    threshold: float = 0.05,
) -> np.ndarray:
    """
    Catchment delineation on a Uniform Hexagonal Grid.
    Eliminates diagonal distance bias (all 6 neighbors share identical edge length and distance).
    """
    rows, cols = dem.shape
    fractions_map = hex_flow_fractions(dem, p=p)

    P = np.zeros((rows, cols), dtype=float)
    P[pour_point] = 1.0

    sorted_cells = np.argsort(dem.ravel())
    pour_z = dem[pour_point]

    for idx in sorted_cells:
        r, c = divmod(int(idx), cols)
        if dem[r, c] < pour_z:
            continue
        if (r, c) == pour_point:
            continue

        cell_contrib = 0.0
        for (nr, nc), f in fractions_map.get((r, c), {}).items():
            cell_contrib += f * P[nr, nc]
        P[r, c] = cell_contrib

    mask = P >= threshold
    mask[pour_point] = True
    return mask


def delineate_catchment(
    direction: np.ndarray,
    pour_point: tuple[int, int],
    dem: np.ndarray | None = None,
    method: str = "hexagonal",
    threshold: float = 0.05,
) -> np.ndarray:
    """Catchment delineation supporting Uniform Hexagonal Grid (H6),
    Multiple Flow Direction (MFD on square grids), and legacy D8 reverse BFS."""
    if method in ("hex", "hexagonal") and dem is not None:
        return delineate_catchment_hex(dem, pour_point, threshold=threshold)
    if method == "mfd" and dem is not None:
        return delineate_catchment_mfd(dem, pour_point, threshold=threshold)

    # Fallback to D8 reverse BFS:
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


# ──────────────────────────────────────────────────────────────────────────────
# SPATIAL MASKING — restrict candidate search to user-drawn shapes
# ──────────────────────────────────────────────────────────────────────────────

def _point_in_polygon(px: float, py: float, polygon: list) -> bool:
    """Ray-casting algorithm: returns True if (px, py) is inside polygon.
    polygon is a list of [x, y] pairs (lon, lat)."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def mask_polygon(bbox: dict, rows: int, cols: int, polygon_coords: list) -> np.ndarray:
    """Create a boolean grid where True = cell center is inside the polygon.
    polygon_coords = [[lon, lat], ...] in GeoJSON order."""
    mask = np.zeros((rows, cols), dtype=bool)
    lat_range = bbox["max_lat"] - bbox["min_lat"]
    lon_range = bbox["max_lon"] - bbox["min_lon"]
    for r in range(rows):
        lat = bbox["min_lat"] + (r + 0.5) / rows * lat_range
        for c in range(cols):
            lon = bbox["min_lon"] + (c + 0.5) / cols * lon_range
            if _point_in_polygon(lon, lat, polygon_coords):
                mask[r, c] = True
    return mask


def mask_circle(bbox: dict, rows: int, cols: int,
                center_lat: float, center_lon: float, radius_m: float) -> np.ndarray:
    """Create a boolean grid where True = cell center is within radius_m of center.
    Uses equirectangular approximation (accurate enough for ≤ 50 km)."""
    mask = np.zeros((rows, cols), dtype=bool)
    lat_range = bbox["max_lat"] - bbox["min_lat"]
    lon_range = bbox["max_lon"] - bbox["min_lon"]
    R = 6_371_000.0  # Earth radius in metres
    clat_rad = np.radians(center_lat)
    for r in range(rows):
        lat = bbox["min_lat"] + (r + 0.5) / rows * lat_range
        dlat = np.radians(lat - center_lat)
        for c in range(cols):
            lon = bbox["min_lon"] + (c + 0.5) / cols * lon_range
            dlon = np.radians(lon - center_lon) * np.cos(clat_rad)
            dist = R * np.sqrt(dlat**2 + dlon**2)
            if dist <= radius_m:
                mask[r, c] = True
    return mask