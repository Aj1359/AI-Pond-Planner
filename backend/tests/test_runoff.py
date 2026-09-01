"""
Unit tests for app/services/runoff.py — hand-calculated expected values,
not just "does it return a number."
"""
import pytest
import math

from app.services import runoff


def test_runoff_coefficient_lookup_known_land_types():
    assert runoff.runoff_coefficient("barren") == 0.65
    assert runoff.runoff_coefficient("forest") == 0.15
    # Unknown land types fall back to a sane default rather than crashing
    assert runoff.runoff_coefficient("unknown_type") == 0.35


def test_scs_curve_number_lookup_known_land_types():
    assert runoff.scs_curve_number("barren") == 86
    assert runoff.scs_curve_number("forest") == 55
    # Unknown land types fall back to a sane default rather than crashing
    assert runoff.scs_curve_number("unknown_type") == 75


def test_estimate_runoff_volume_matches_hand_calculation_scs_branch():
    """Independently recomputes the coupled SCS-CN + Rational Method
    formula (P > Ia branch) for land_type='barren' and checks the
    function's output matches, rather than re-deriving the formula from
    the implementation itself."""
    catchment_area_ha = 10.0
    rainfall_mm = 1000.0  # well above Ia (~8.27mm for barren), exercises the P > Ia branch
    land_type = "barren"

    result = runoff.estimate_runoff_volume(catchment_area_ha, rainfall_mm, land_type)

    C = runoff.RUNOFF_COEFFICIENTS[land_type]
    CN = runoff.CURVE_NUMBERS[land_type]
    S = (25400.0 / CN) - 254.0
    Ia = 0.2 * S
    P = rainfall_mm
    assert P > Ia, "test rainfall must exercise the P > Ia branch"

    Q_scs_mm = ((P - Ia) ** 2) / (P - Ia + S)
    effective_runoff_m = 0.65 * (Q_scs_mm / 1000.0) + 0.35 * (C * P / 1000.0)
    area_m2 = catchment_area_ha * 10_000.0
    expected_gross = effective_runoff_m * area_m2
    expected_net = expected_gross * (1 - runoff.LOSS_FACTOR)

    assert result == pytest.approx(expected_net, rel=1e-6)


def test_estimate_runoff_volume_matches_hand_calculation_low_rainfall_branch():
    """Independently recomputes the P <= Ia branch (rainfall below the
    initial-abstraction threshold, so SCS-CN contributes no direct
    runoff and the model falls back to a discounted Rational Method
    estimate) — this branch had no test coverage before."""
    catchment_area_ha = 10.0
    land_type = "barren"

    CN = runoff.CURVE_NUMBERS[land_type]
    S = (25400.0 / CN) - 254.0
    Ia = 0.2 * S
    rainfall_mm = Ia * 0.5  # deliberately below the Ia threshold
    assert rainfall_mm <= Ia, "test rainfall must exercise the P <= Ia branch"

    result = runoff.estimate_runoff_volume(catchment_area_ha, rainfall_mm, land_type)

    C = runoff.RUNOFF_COEFFICIENTS[land_type]
    effective_runoff_m = C * (rainfall_mm / 1000.0) * 0.5
    area_m2 = catchment_area_ha * 10_000.0
    expected_gross = effective_runoff_m * area_m2
    expected_net = expected_gross * (1 - runoff.LOSS_FACTOR)

    assert result == pytest.approx(expected_net, rel=1e-6)


def test_zero_rainfall_gives_zero_runoff():
    result = runoff.estimate_runoff_volume(50.0, 0.0, "cropland")
    assert result == 0.0


def test_pond_dimensions_respect_depth_bounds():
    sizing = runoff.recommend_pond_dimensions(
        annual_runoff_m3=100_000, available_land_m2=5000, capture_efficiency=0.7
    )
    assert runoff.MIN_POND_DEPTH_M <= sizing["recommended_depth_m"] <= runoff.MAX_POND_DEPTH_M
    assert sizing["recommended_surface_area_m2"] <= 5000
    assert sizing["storage_capacity_m3"] > 0


def test_pond_dimensions_land_constrained_case():
    """When target volume would need more area than is available, the
    engine should use all available land rather than exceeding it."""
    sizing = runoff.recommend_pond_dimensions(
        annual_runoff_m3=1_000_000, available_land_m2=500, capture_efficiency=0.7
    )
    assert sizing["recommended_surface_area_m2"] <= 500


def test_rank_candidates_orders_by_weighted_score_descending():
    estimates = [
        {
            "candidate_id": 1,
            "catchment_area_ha": 5,
            "storage_capacity_m3": 1000,
            "capture_efficiency_pct": 50,
            "recommended_depth_m": 2.0,
            "recommended_surface_area_m2": 500,
            "annual_runoff_volume_m3": 2000,
        },
        {
            "candidate_id": 2,
            "catchment_area_ha": 50,
            "storage_capacity_m3": 10000,
            "capture_efficiency_pct": 80,
            "recommended_depth_m": 3.5,
            "recommended_surface_area_m2": 2857,
            "annual_runoff_volume_m3": 12500,
        },
    ]
    suitability = {1: 0.9, 2: 0.5}
    ranked = runoff.rank_candidates(estimates, suitability)

    assert len(ranked) == 2
    # candidate 2 has much higher storage (50% weight) despite lower suitability
    assert ranked[0]["candidate_id"] == 2
    assert ranked[0]["rank_score"] > ranked[1]["rank_score"]
    assert "justification" in ranked[0]
    assert "1.5:1 side slopes" in ranked[0]["justification"]


def test_rank_candidates_missing_required_field_raises_clear_error():
    """rank_candidates()'s justification string requires
    recommended_depth_m, recommended_surface_area_m2, and
    annual_runoff_volume_m3 on every estimate dict — this documents that
    requirement explicitly, since a caller passing a partial dict (e.g.
    a hand-built dict outside the normal estimation router flow) will
    hit a KeyError rather than a silent wrong answer. The real API flow
    (routers/estimation.py) always supplies these fields, so this isn't
    reachable through normal use, but future callers of rank_candidates()
    directly should know the full field set it expects."""
    incomplete_estimate = [
        {"candidate_id": 1, "catchment_area_ha": 5, "storage_capacity_m3": 1000, "capture_efficiency_pct": 50}
    ]
    with pytest.raises(KeyError):
        runoff.rank_candidates(incomplete_estimate, {1: 0.9})


def test_frustum_volume_matches_hand_calculation():
    """V = (d/3) * (A_top + A_bottom + sqrt(A_top * A_bottom)) — the
    standard frustum volume formula, checked independently."""
    top_area_m2 = 200.0
    depth_m = 2.0
    volume, L_top, W_top, L_bottom, W_bottom = runoff._frustum_volume(top_area_m2, depth_m)

    A_top = L_top * W_top
    A_bottom = L_bottom * W_bottom
    assert A_top == pytest.approx(top_area_m2, rel=1e-6)

    expected_volume = (depth_m / 3.0) * (A_top + A_bottom + math.sqrt(A_top * A_bottom))
    assert volume == pytest.approx(expected_volume, rel=1e-6)


def test_frustum_bottom_smaller_than_top_for_positive_depth():
    """With a positive depth and 1.5:1 side slopes, the bottom footprint
    must be smaller than the top (the pond narrows as it gets deeper)."""
    volume, L_top, W_top, L_bottom, W_bottom = runoff._frustum_volume(500.0, 2.5)
    assert L_bottom < L_top
    assert W_bottom < W_top


def test_frustum_bottom_dimensions_never_go_below_floor():
    """Regression guard: a small top footprint at a large depth could
    geometrically require a negative bottom width/length under a 1.5:1
    slope — the implementation floors bottom dimensions at 1.0m rather
    than producing a physically meaningless negative size."""
    volume, L_top, W_top, L_bottom, W_bottom = runoff._frustum_volume(top_area_m2=50, depth_m=4.0)
    assert L_bottom >= 1.0
    assert W_bottom >= 1.0


def test_solve_top_area_inverts_frustum_volume():
    """_solve_top_area should find a top area that, fed back into
    _frustum_volume at the same depth, reproduces (approximately) the
    original target volume — i.e. the binary search actually converges."""
    target_volume = 15000.0
    depth = 2.5
    solved_area = runoff._solve_top_area(target_volume, depth)

    resulting_volume, *_ = runoff._frustum_volume(solved_area, depth)
    assert resulting_volume == pytest.approx(target_volume, rel=0.01)


def test_recommend_pond_dimensions_includes_frustum_geometry_fields():
    sizing = runoff.recommend_pond_dimensions(annual_runoff_m3=100_000, available_land_m2=5000)
    for field in (
        "top_length_m", "top_width_m", "bottom_length_m", "bottom_width_m",
        "side_slope_ratio", "freeboard_m", "total_depth_m",
    ):
        assert field in sizing, f"missing frustum geometry field: {field}"
    assert sizing["side_slope_ratio"] == runoff.SIDE_SLOPE_Z
    assert sizing["total_depth_m"] == pytest.approx(sizing["recommended_depth_m"] + runoff.FREEBOARD_M)


def test_recommend_pond_dimensions_freeboard_not_counted_as_storage():
    """Storage capacity must be computed at the water-storage depth, not
    the freeboard-inclusive total depth — freeboard is a safety margin
    above the water line, not additional usable capacity."""
    sizing = runoff.recommend_pond_dimensions(annual_runoff_m3=50_000, available_land_m2=8000)

    volume_at_water_depth, *_ = runoff._frustum_volume(
        sizing["recommended_surface_area_m2"], sizing["recommended_depth_m"]
    )
    assert sizing["storage_capacity_m3"] == pytest.approx(volume_at_water_depth, rel=1e-3)


def test_recommend_pond_dimensions_handles_zero_runoff():
    sizing = runoff.recommend_pond_dimensions(annual_runoff_m3=0, available_land_m2=5000)
    assert sizing["storage_capacity_m3"] == 0.0
    assert sizing["capture_efficiency_pct"] == 0.0


def test_rank_candidates_empty_list_returns_empty():
    assert runoff.rank_candidates([], {}) == []
