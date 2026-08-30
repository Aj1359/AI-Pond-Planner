"""
Runoff estimation (Rational Method) and pond sizing / ranking engine.
"""
from __future__ import annotations

# Runoff coefficients by land type (typical published ranges, midpoints used)
RUNOFF_COEFFICIENTS = {
    "barren": 0.65,
    "fallow_cropland": 0.35,
    "cropland": 0.30,
    "grassland": 0.25,
    "forest": 0.15,
    "rocky": 0.75,
    "settlement": 0.55,
}

# Fraction of runoff lost to evaporation/seepage before capture, a simple
# first-order approximation for the prototype (would be replaced by a
# monthly water-balance model using PET data in the full system).
LOSS_FACTOR = 0.20

# Target fraction of annual runoff the pond should aim to capture
DEFAULT_CAPTURE_EFFICIENCY = 0.70

# Practical depth bounds for a manually-excavated village pond
MIN_POND_DEPTH_M = 1.5
MAX_POND_DEPTH_M = 4.0


def runoff_coefficient(land_type: str) -> float:
    return RUNOFF_COEFFICIENTS.get(land_type, 0.35)


def estimate_runoff_volume(catchment_area_ha: float, mean_annual_rainfall_mm: float, land_type: str) -> float:
    """Rational Method: Q (m3) = C * (P/1000) * A(m2), with loss factor."""
    C = runoff_coefficient(land_type)
    area_m2 = catchment_area_ha * 10_000
    rainfall_m = mean_annual_rainfall_mm / 1000.0
    gross_runoff_m3 = C * rainfall_m * area_m2
    net_runoff_m3 = gross_runoff_m3 * (1 - LOSS_FACTOR)
    return net_runoff_m3


def recommend_pond_dimensions(
    annual_runoff_m3: float,
    available_land_m2: float,
    capture_efficiency: float = DEFAULT_CAPTURE_EFFICIENCY,
) -> dict:
    """Solve for pond surface area & depth to capture target volume,
    constrained by available land and practical depth limits."""
    target_volume_m3 = annual_runoff_m3 * capture_efficiency

    # Start from a mid-range depth and derive the required surface area
    depth_m = (MIN_POND_DEPTH_M + MAX_POND_DEPTH_M) / 2
    required_area_m2 = target_volume_m3 / depth_m

    if required_area_m2 > available_land_m2:
        # Land-constrained: use all available land, increase depth instead
        required_area_m2 = available_land_m2
        depth_m = target_volume_m3 / required_area_m2 if required_area_m2 > 0 else MIN_POND_DEPTH_M
        depth_m = max(MIN_POND_DEPTH_M, min(depth_m, MAX_POND_DEPTH_M))

    storage_capacity_m3 = required_area_m2 * depth_m
    actual_capture_pct = (storage_capacity_m3 / annual_runoff_m3 * 100) if annual_runoff_m3 > 0 else 0.0

    return {
        "recommended_depth_m": round(depth_m, 2),
        "recommended_surface_area_m2": round(required_area_m2, 1),
        "storage_capacity_m3": round(storage_capacity_m3, 1),
        "capture_efficiency_pct": round(min(actual_capture_pct, 100.0), 1),
    }


def rank_candidates(estimates: list[dict], suitability_scores: dict[int, float]) -> list[dict]:
    """Weighted score: 50% storage capacity (normalized), 30% land
    suitability, 20% capture efficiency. Returns estimates sorted desc
    with a rank_score and short justification attached."""
    if not estimates:
        return []

    max_storage = max(e["storage_capacity_m3"] for e in estimates) or 1.0

    ranked = []
    for e in estimates:
        cid = e["candidate_id"]
        norm_storage = e["storage_capacity_m3"] / max_storage
        suitability = suitability_scores.get(cid, 0.5)
        capture = e["capture_efficiency_pct"] / 100.0

        score = 0.5 * norm_storage + 0.3 * suitability + 0.2 * capture
        justification = (
            f"Estimated {e['storage_capacity_m3']:.0f} m³ storage from a "
            f"{e['catchment_area_ha']:.1f} ha catchment, capturing "
            f"{e['capture_efficiency_pct']:.0f}% of annual runoff; "
            f"site suitability {suitability:.2f}/1.0."
        )
        ranked.append({**e, "rank_score": round(score, 3), "justification": justification})

    ranked.sort(key=lambda x: x["rank_score"], reverse=True)
    return ranked