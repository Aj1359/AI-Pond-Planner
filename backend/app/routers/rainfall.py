"""
Rainfall API Router.
Provides both independent coordinate queries and village-persisted precipitation history.
"""
from fastapi import APIRouter, Query
from app.schemas import RainfallSummary, BoundingBox
from app.services import rainfall as rainfall_service
from app import repository as repo

router = APIRouter(prefix="/api", tags=["rainfall"])


@router.get("/rainfall/query", response_model=RainfallSummary)
def query_rainfall_point(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    years: int = Query(10, ge=1, le=30),
):
    """Query 10-year monthly rainfall statistics for any latitude/longitude independently."""
    return rainfall_service.get_rainfall_summary("IndependentPoint", lat, lon, years)


@router.post("/rainfall/bbox", response_model=RainfallSummary)
def query_rainfall_bbox(bbox: BoundingBox, years: int = Query(10, ge=1, le=30)):
    """Query rainfall statistics for the center of any bounding box."""
    bbox_dict = bbox.model_dump()
    center_lat = (bbox_dict["min_lat"] + bbox_dict["max_lat"]) / 2.0
    center_lon = (bbox_dict["min_lon"] + bbox_dict["max_lon"]) / 2.0
    return rainfall_service.get_rainfall_summary("IndependentBBox", center_lat, center_lon, years)


@router.get("/villages/{village}/rainfall", response_model=RainfallSummary)
def get_village_rainfall(village: str, years: int = Query(10, ge=1, le=30)):
    """Fetch and persist rainfall history for a pre-registered village."""
    village_row = repo.get_village(village)
    bbox = repo.village_bbox(village_row)
    lat = (bbox["min_lat"] + bbox["max_lat"]) / 2.0
    lon = (bbox["min_lon"] + bbox["max_lon"]) / 2.0

    summary = rainfall_service.get_rainfall_summary(village, lat, lon, years)
    repo.save_rainfall(village_row["id"], summary)
    return summary