"""Pydantic request/response models shared across routers."""
from typing import List, Optional
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float


class VillageQuery(BaseModel):
    name: str
    bbox: BoundingBox


class ContourResponse(BaseModel):
    interval_m: float
    geojson: dict


class CandidateSite(BaseModel):
    id: int
    lat: float
    lon: float
    slope_pct: float
    land_type: str
    suitability_score: float


class CatchmentResult(BaseModel):
    candidate_id: int
    area_ha: float
    geojson: dict


class RainfallSummary(BaseModel):
    village: str
    years: int
    mean_annual_mm: float
    monthly_avg_mm: List[float] = Field(..., description="12 values, Jan..Dec")
    source: str


class RunoffEstimate(BaseModel):
    candidate_id: int
    catchment_area_ha: float
    runoff_coefficient: float
    mean_annual_rainfall_mm: float
    annual_runoff_volume_m3: float
    recommended_depth_m: float
    recommended_surface_area_m2: float
    storage_capacity_m3: float
    capture_efficiency_pct: float


class RecommendationItem(BaseModel):
    candidate: CandidateSite
    runoff: RunoffEstimate
    rank_score: float
    justification: str