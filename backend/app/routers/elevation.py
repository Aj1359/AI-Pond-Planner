"""
Independent Elevation API Router.
Provides direct elevation point and DEM raster queries without requiring village persistence.
"""
from fastapi import APIRouter, Query
from app.schemas import BoundingBox
from app.services import elevation as elevation_service

router = APIRouter(prefix="/api/elevation", tags=["elevation"])


@router.get("/point")
def get_point_elevation(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)):
    """Query elevation for a single geographic coordinate."""
    # Approximate single point as micro bounding box
    delta = 0.001
    bbox = {
        "min_lat": lat - delta,
        "min_lon": lon - delta,
        "max_lat": lat + delta,
        "max_lon": lon + delta,
    }
    dem = elevation_service.get_dem(bbox)
    grid = dem["elevation"]
    center_val = grid[len(grid) // 2][len(grid[0]) // 2]
    return {
        "lat": lat,
        "lon": lon,
        "elevation_m": round(float(center_val), 2),
        "source": dem["source"],
    }


@router.post("/dem")
def get_dem_for_bbox(bbox: BoundingBox):
    """Query 100x100 DEM raster grid and resolution for any bounding box."""
    bbox_dict = bbox.model_dump()
    dem = elevation_service.get_dem(bbox_dict)
    grid = dem["elevation"]
    min_elev = min(min(row) for row in grid)
    max_elev = max(max(row) for row in grid)

    return {
        "bbox": bbox_dict,
        "grid_shape": [len(grid), len(grid[0])],
        "resolution_m": dem["resolution_m"],
        "min_elevation_m": round(float(min_elev), 2),
        "max_elevation_m": round(float(max_elev), 2),
        "source": dem["source"],
        "elevation": grid,
    }
