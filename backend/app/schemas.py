from typing import List, Union
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    min_lat: float = Field(..., description="Minimum latitude (South)")
    min_lon: float = Field(..., description="Minimum longitude (West)")
    max_lat: float = Field(..., description="Maximum latitude (North)")
    max_lon: float = Field(..., description="Maximum longitude (East)")


class VillageQuery(BaseModel):
    name: str = Field(..., description="Village or area name")
    bbox: BoundingBox = Field(..., description="Geographic bounding box for the village")


class DEMResponse(BaseModel):
    source: str = Field(..., description="Source of the DEM data ('open-elevation' or 'synthetic')")
    elevation: List[List[float]] = Field(..., description="100x100 2D grid of elevation values in meters")
