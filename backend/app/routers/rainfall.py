from fastapi import APIRouter

from app.schemas import RainfallSummary
from app.services import rainfall as rainfall_service
from app import repository as repo

router = APIRouter(prefix="/api/villages", tags=["rainfall"])


@router.get("/{village}/rainfall", response_model=RainfallSummary)
def get_rainfall(village: str, years: int = 10):
    village_row = repo.get_village(village)
    bbox = repo.village_bbox(village_row)
    lat = (bbox["min_lat"] + bbox["max_lat"]) / 2
    lon = (bbox["min_lon"] + bbox["max_lon"]) / 2

    summary = rainfall_service.get_rainfall_summary(village, lat, lon, years)
    repo.save_rainfall(village_row["id"], summary)
    return summary