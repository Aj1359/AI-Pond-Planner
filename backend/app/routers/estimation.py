from fastapi import APIRouter, HTTPException

from app.services import runoff as runoff_service
from app.services import rainfall as rainfall_service
from app import repository as repo

router = APIRouter(prefix="/api/villages", tags=["estimation"])

MAX_LAND_FRACTION_OF_CATCHMENT = 0.015
MIN_AVAILABLE_LAND_M2 = 500.0
MAX_AVAILABLE_LAND_M2 = 15000.0


@router.post("/{village}/candidates/{candidate_id}/estimate")
def estimate(village: str, candidate_id: int):
    village_row = repo.get_village(village)
    candidate = repo.get_candidate_site(candidate_id)
    if candidate["village_id"] != village_row["id"]:
        raise HTTPException(404, f"Candidate {candidate_id} does not belong to village '{village}'")

    catchment = repo.get_catchment(candidate_id)
    if catchment is None:
        raise HTTPException(400, "Run POST .../catchment for this candidate before estimating runoff.")
    catchment_area_ha = catchment["area_ha"]

    rainfall = repo.get_rainfall(village_row["id"])
    if rainfall is None:
        bbox = repo.village_bbox(village_row)
        lat = (bbox["min_lat"] + bbox["max_lat"]) / 2
        lon = (bbox["min_lon"] + bbox["max_lon"]) / 2
        rainfall = rainfall_service.get_rainfall_summary(village, lat, lon)
        repo.save_rainfall(village_row["id"], rainfall)

    annual_runoff_m3 = runoff_service.estimate_runoff_volume(
        catchment_area_ha, rainfall["mean_annual_mm"], candidate["land_type"]
    )

    available_land_m2 = min(
        MAX_AVAILABLE_LAND_M2,
        max(MIN_AVAILABLE_LAND_M2, catchment_area_ha * 10_000 * MAX_LAND_FRACTION_OF_CATCHMENT),
    )
    sizing = runoff_service.recommend_pond_dimensions(annual_runoff_m3, available_land_m2)

    result = {
        "candidate_id": candidate_id,
        "catchment_area_ha": round(catchment_area_ha, 2),
        "runoff_coefficient": runoff_service.runoff_coefficient(candidate["land_type"]),
        "mean_annual_rainfall_mm": round(rainfall["mean_annual_mm"], 1),
        "annual_runoff_volume_m3": round(annual_runoff_m3, 1),
        **sizing,
    }

    repo.save_recommendation(candidate_id, result)
    return result


@router.get("/{village}/recommendations")
def get_recommendations(village: str):
    village_row = repo.get_village(village)
    estimates = repo.get_recommendations_for_village(village_row["id"])
    if not estimates:
        raise HTTPException(400, "No estimates computed yet. Call POST .../estimate for at least one candidate.")

    candidates = {c["id"]: c for c in repo.get_candidate_sites(village_row["id"])}
    suitability_scores = {cid: c["suitability_score"] for cid, c in candidates.items()}

    # Reshape DB rows into the format runoff_service.rank_candidates expects
    formatted = [
        {
            "candidate_id": e["candidate_site_id"],
            "catchment_area_ha": repo.get_catchment(e["candidate_site_id"])["area_ha"],
            "runoff_coefficient": e["runoff_coefficient"],
            "mean_annual_rainfall_mm": e["mean_annual_rainfall_mm"],
            "annual_runoff_volume_m3": e["annual_runoff_volume_m3"],
            "recommended_depth_m": e["recommended_depth_m"],
            "recommended_surface_area_m2": e["recommended_surface_area_m2"],
            "storage_capacity_m3": e["storage_capacity_m3"],
            "capture_efficiency_pct": e["capture_efficiency_pct"],
        }
        for e in estimates
    ]

    ranked = runoff_service.rank_candidates(formatted, suitability_scores)
    for r in ranked:
        repo.update_recommendation_rank(r["candidate_id"], r["rank_score"], r["justification"])
        r["site"] = candidates.get(r["candidate_id"])

    return {"village": village, "recommendations": ranked}