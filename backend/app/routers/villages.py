import numpy as np
from fastapi import APIRouter

from app.schemas import VillageQuery, ContourResponse
from app.services import elevation, terrain, sites as sites_service
from app import repository as repo

router = APIRouter(prefix="/api/villages", tags=["villages"])


@router.post("/{village}/init")
def init_village(village: str, query: VillageQuery):
    """Bootstrap AOI: fetch DEM, compute slope, generate contours & candidate
    sites, persisting everything to Supabase (Postgres)."""
    bbox = query.bbox.model_dump()
    village_row = repo.upsert_village(village, bbox)

    dem_data = elevation.get_dem(bbox)
    dem = np.array(dem_data["elevation"])
    cell_size_m = dem_data["resolution_m"]

    repo.save_dem(village_row["id"], dem_data["elevation"], cell_size_m, dem_data["source"])

    slope = terrain.compute_slope_pct(dem, cell_size_m)
    repo.save_derived_layers(village_row["id"], slope=slope.tolist())

    candidates = sites_service.generate_candidate_sites(dem, slope, bbox, top_n=5)
    saved = repo.save_candidate_sites(village_row["id"], candidates)

    return {
        "village": village,
        "village_id": village_row["id"],
        "dem_source": dem_data["source"],
        "dem_shape": list(dem.shape),
        "resolution_m": cell_size_m,
        "candidate_count": len(saved),
    }


@router.get("/{village}/imagery")
def get_imagery_config(village: str):
    village_row = repo.get_village(village)
    bbox = repo.village_bbox(village_row)
    return {
        "tile_url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attribution": "Esri World Imagery",
        "bounds": [[bbox["min_lat"], bbox["min_lon"]], [bbox["max_lat"], bbox["max_lon"]]],
    }


@router.get("/{village}/contours", response_model=ContourResponse)
def get_contours(village: str):
    village_row = repo.get_village(village)
    dem_row = repo.get_dem(village_row["id"])
    dem = np.array(dem_row["elevation"])
    contours = terrain.extract_contours(dem, interval_m=3.0)
    return {"interval_m": 3.0, "geojson": contours}


@router.get("/{village}/candidates")
def get_candidates(village: str):
    village_row = repo.get_village(village)
    candidates = repo.get_candidate_sites(village_row["id"])
    out = [
        {
            "id": c["id"],
            "lat": c["lat"],
            "lon": c["lon"],
            "slope_pct": c["slope_pct"],
            "land_type": c["land_type"],
            "suitability_score": c["suitability_score"],
        }
        for c in candidates
    ]
    return {"village": village, "candidates": out}