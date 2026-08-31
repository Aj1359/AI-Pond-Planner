"""
Advanced Hydrological Runoff Estimation (SCS-CN & Rational Methods) and
Pond Sizing Engine using 3D Inverted Trapezoidal Frustum Geometry.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

# Runoff coefficients by land type (Rational Method)
RUNOFF_COEFFICIENTS = {
    "barren": 0.65,
    "fallow_cropland": 0.35,
    "cropland": 0.30,
    "grassland": 0.25,
    "forest": 0.15,
    "rocky": 0.75,
    "settlement": 0.55,
}

# USDA Soil Conservation Service (SCS) Curve Numbers for Antecedent Moisture Condition II (AMC-II)
CURVE_NUMBERS = {
    "barren": 86,
    "fallow_cropland": 76,
    "cropland": 72,
    "grassland": 68,
    "forest": 55,
    "rocky": 90,
    "settlement": 82,
}

# Evaporation & conveyance loss factor
LOSS_FACTOR = 0.20

# Target fraction of annual runoff to capture in standard design
DEFAULT_CAPTURE_EFFICIENCY = 0.70

# Embankment side slope ratio (z:1, horizontal:vertical). 1.5:1 is the civil standard for stable earthen slopes.
SIDE_SLOPE_Z = 1.5

# Standard freeboard allowance (m) above water level for storm waves/siltation
FREEBOARD_M = 0.50

# Practical excavation depth limits for village-scale farm/community ponds
MIN_POND_DEPTH_M = 1.5
MAX_POND_DEPTH_M = 4.0

# Typical aspect ratio (Length : Width = 1.5 : 1) for hydraulic efficiency
ASPECT_RATIO = 1.5


def runoff_coefficient(land_type: str) -> float:
    return RUNOFF_COEFFICIENTS.get(land_type, 0.35)


def scs_curve_number(land_type: str) -> int:
    return CURVE_NUMBERS.get(land_type, 75)


def estimate_runoff_volume(catchment_area_ha: float, mean_annual_rainfall_mm: float, land_type: str) -> float:
    """
    Computes annual harvestable runoff using a coupled SCS Curve Number (SCS-CN)
    and Rational Method model, accounting for potential maximum soil retention (S)
    and initial abstraction (Ia = 0.2*S).
    """
    C = runoff_coefficient(land_type)
    CN = scs_curve_number(land_type)

    # Potential maximum soil retention S (mm)
    S = (25400.0 / CN) - 254.0
    Ia = 0.2 * S  # Initial abstraction (canopy interception + depression storage)

    P = mean_annual_rainfall_mm
    if P > Ia:
        # SCS-CN direct runoff depth (mm)
        Q_scs_mm = ((P - Ia) ** 2) / (P - Ia + S)
        # Combine SCS storm retention dynamics with annual Rational Method yield
        effective_runoff_m = 0.65 * (Q_scs_mm / 1000.0) + 0.35 * (C * P / 1000.0)
    else:
        effective_runoff_m = C * (P / 1000.0) * 0.5

    area_m2 = catchment_area_ha * 10_000.0
    gross_runoff_m3 = effective_runoff_m * area_m2
    net_runoff_m3 = gross_runoff_m3 * (1.0 - LOSS_FACTOR)
    return net_runoff_m3


def _frustum_volume(top_area_m2: float, depth_m: float, side_slope: float = SIDE_SLOPE_Z, aspect: float = ASPECT_RATIO) -> tuple[float, float, float, float, float]:
    """
    Calculates storage volume and dimensions for an inverted trapezoidal frustum pond.
    Returns: (volume_m3, L_top, W_top, L_bottom, W_bottom)
    """
    W_top = math.sqrt(top_area_m2 / aspect)
    L_top = W_top * aspect

    # Bottom dimensions after accounting for 2 * side_slope * depth
    dx = 2.0 * side_slope * depth_m
    L_bottom = max(1.0, L_top - dx)
    W_bottom = max(1.0, W_top - dx)

    A_bottom = L_bottom * W_bottom
    A_top = L_top * W_top

    # Prismoidal / Frustum volume formula: V = (d / 3) * (A_top + A_bottom + sqrt(A_top * A_bottom))
    volume_m3 = (depth_m / 3.0) * (A_top + A_bottom + math.sqrt(A_top * A_bottom))
    return volume_m3, L_top, W_top, L_bottom, W_bottom


def _solve_top_area(target_volume_m3: float, depth_m: float, side_slope: float = SIDE_SLOPE_Z) -> float:
    """Binary search inversion to find the exact top surface area required for an inverted frustum."""
    low = (2.0 * side_slope * depth_m + 1.0) ** 2
    high = max(low * 2, (target_volume_m3 / depth_m) * 2.5 + 500.0)

    for _ in range(35):
        mid = (low + high) / 2.0
        v, _, _, _, _ = _frustum_volume(mid, depth_m, side_slope)
        if v < target_volume_m3:
            low = mid
        else:
            high = mid

    return (low + high) / 2.0


def recommend_pond_dimensions(
    annual_runoff_m3: float,
    available_land_m2: float,
    capture_efficiency: float = DEFAULT_CAPTURE_EFFICIENCY,
) -> Dict[str, Any]:
    """
    Optimizes pond depth (d) and surface area (A_top) to capture target runoff volume
    using realistic 3D inverted trapezoidal frustum geometry.
    
    Minimizes evaporation losses (proportional to surface area) while honoring
    land constraints and civil stability slope standards.
    """
    target_volume_m3 = annual_runoff_m3 * capture_efficiency

    # Search for the optimal depth that balances water preservation with available land
    best_depth = 3.0
    best_area = available_land_m2

    if target_volume_m3 <= 0:
        return {
            "recommended_depth_m": MIN_POND_DEPTH_M,
            "recommended_surface_area_m2": 0.0,
            "storage_capacity_m3": 0.0,
            "capture_efficiency_pct": 0.0,
            "top_length_m": 0.0,
            "top_width_m": 0.0,
            "bottom_length_m": 0.0,
            "bottom_width_m": 0.0,
            "side_slope_ratio": SIDE_SLOPE_Z,
            "freeboard_m": FREEBOARD_M,
            "total_depth_m": MIN_POND_DEPTH_M + FREEBOARD_M,
        }

    # Evaluate candidate depths from deep (evaporation-efficient) to shallow
    depth_candidates = [3.5, 3.0, 2.5, 2.0, 1.8, 1.5]
    selected_depth = depth_candidates[0]
    required_top_area = _solve_top_area(target_volume_m3, selected_depth)

    if required_top_area > available_land_m2:
        # Land is constrained: use maximum permitted excavation depth (up to 4.0m) with full available land
        selected_depth = MAX_POND_DEPTH_M
        required_top_area = available_land_m2
        vol, L_top, W_top, L_bottom, W_bottom = _frustum_volume(required_top_area, selected_depth)
        
        # If capacity still exceeds target at 4.0m, scale depth down
        if vol > target_volume_m3:
            # Binary search for depth at fixed available_land_m2
            d_low, d_high = MIN_POND_DEPTH_M, MAX_POND_DEPTH_M
            for _ in range(25):
                d_mid = (d_low + d_high) / 2.0
                v_test, _, _, _, _ = _frustum_volume(available_land_m2, d_mid)
                if v_test < target_volume_m3:
                    d_low = d_mid
                else:
                    d_high = d_mid
            selected_depth = d_high
            vol, L_top, W_top, L_bottom, W_bottom = _frustum_volume(available_land_m2, selected_depth)
    else:
        # Pick the most efficient depth that fits within available land
        for d in depth_candidates:
            area_d = _solve_top_area(target_volume_m3, d)
            if area_d <= available_land_m2:
                selected_depth = d
                required_top_area = area_d
                break
        vol, L_top, W_top, L_bottom, W_bottom = _frustum_volume(required_top_area, selected_depth)

    actual_capture_pct = (vol / annual_runoff_m3 * 100.0) if annual_runoff_m3 > 0 else 0.0

    return {
        "recommended_depth_m": round(selected_depth, 2),
        "recommended_surface_area_m2": round(required_top_area, 1),
        "storage_capacity_m3": round(vol, 1),
        "capture_efficiency_pct": round(min(actual_capture_pct, 100.0), 1),
        "top_length_m": round(L_top, 2),
        "top_width_m": round(W_top, 2),
        "bottom_length_m": round(L_bottom, 2),
        "bottom_width_m": round(W_bottom, 2),
        "side_slope_ratio": SIDE_SLOPE_Z,
        "freeboard_m": FREEBOARD_M,
        "total_depth_m": round(selected_depth + FREEBOARD_M, 2),
    }


def rank_candidates(estimates: List[Dict[str, Any]], suitability_scores: Dict[int, float]) -> List[Dict[str, Any]]:
    """
    Weighted composite ranking model:
      - 50%: Normalized storage capacity
      - 30%: Land & slope suitability
      - 20%: Runoff capture efficiency
    """
    if not estimates:
        return []

    max_storage = max((e["storage_capacity_m3"] for e in estimates), default=1.0) or 1.0

    ranked = []
    for e in estimates:
        cid = e["candidate_id"]
        norm_storage = e["storage_capacity_m3"] / max_storage
        suitability = suitability_scores.get(cid, 0.5)
        capture = e["capture_efficiency_pct"] / 100.0

        score = 0.50 * norm_storage + 0.30 * suitability + 0.20 * capture
        justification = (
            f"Frustum pond capacity: {e['storage_capacity_m3']:,.0f} m³ (depth: {e['recommended_depth_m']}m, "
            f"top area: {e['recommended_surface_area_m2']:,.0f} m² with 1.5:1 side slopes); "
            f"captures {e['capture_efficiency_pct']:.0f}% of {e['annual_runoff_volume_m3']:,.0f} m³ runoff "
            f"from a {e['catchment_area_ha']:.1f} ha catchment. Suitability: {suitability:.2f}/1.0."
        )
        ranked.append({**e, "rank_score": round(score, 3), "justification": justification})

    ranked.sort(key=lambda x: x["rank_score"], reverse=True)
    return ranked