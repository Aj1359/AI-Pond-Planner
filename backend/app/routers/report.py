from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.services import report as report_service
from app import repository as repo

router = APIRouter(prefix="/api/villages", tags=["report"])


@router.get("/{village}/candidates/{candidate_id}/report")
def get_candidate_report(village: str, candidate_id: int):
    village_row = repo.get_village(village)
    candidate = repo.get_candidate_site(candidate_id)
    if candidate["village_id"] != village_row["id"]:
        raise HTTPException(404, f"Candidate {candidate_id} does not belong to village '{village}'")

    catchment = repo.get_catchment(candidate_id)
    if catchment is None:
        raise HTTPException(400, "Run the catchment step for this candidate before generating a report.")

    rainfall = repo.get_rainfall(village_row["id"])
    if rainfall is None:
        raise HTTPException(400, "Fetch rainfall data for this village before generating a report.")

    estimates = repo.get_recommendations_for_village(village_row["id"])
    estimate = next((e for e in estimates if e["candidate_site_id"] == candidate_id), None)
    if estimate is None:
        raise HTTPException(400, "Run the estimate step for this candidate before generating a report.")

    pdf_bytes = report_service.build_candidate_report_pdf(village, candidate, catchment, rainfall, estimate)

    filename = f"{village}_candidate_{candidate_id}_report.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )