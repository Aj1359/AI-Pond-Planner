import numpy as np
from fastapi import APIRouter, HTTPException

from app.services import terrain
from app import repository as repo

router = APIRouter(prefix="/api/villages", tags=["catchment"])


@router.post("/{village}/candidates/{candidate_id}/catchment")
def compute_catchment(village: str, candidate_id: int):
    village_row = repo.get_village(village)
    candidate = repo.get_candidate_site(candidate_id)
    if candidate["village_id"] != village_row["id"]:
        raise HTTPException(404, f"Candidate {candidate_id} does not belong to village '{village}'")

    dem_row = repo.get_dem(village_row["id"])
    dem = np.array(dem_row["elevation"])
    cell_size_m = dem_row["resolution_m"]

    # Reuse cached flow-direction if we've computed it before for this
    # village (expensive O(rows*cols) step) — otherwise compute & cache it.
    if dem_row.get("flow_direction"):
        direction = np.array(dem_row["flow_direction"])
    else:
        direction = terrain.d8_flow_direction(dem)
        repo.save_derived_layers(village_row["id"], flow_direction=direction.tolist())

    pour_point = (candidate["grid_row"], candidate["grid_col"])
    mask = terrain.delineate_catchment(direction, pour_point)
    area_ha = terrain.catchment_area_ha(mask, cell_size_m)

    rows, cols = mask.shape
    ys, xs = mask.nonzero()
    bbox = repo.village_bbox(village_row)
    step = max(1, len(ys) // 200)
    boundary_points = [
        [
            bbox["min_lon"] + (x / cols) * (bbox["max_lon"] - bbox["min_lon"]),
            bbox["min_lat"] + (y / rows) * (bbox["max_lat"] - bbox["min_lat"]),
        ]
        for y, x in zip(ys[::step], xs[::step])
    ]
    geojson = {
        "type": "Feature",
        "properties": {"area_ha": round(area_ha, 2)},
        "geometry": {"type": "MultiPoint", "coordinates": boundary_points},
    }

    repo.save_catchment(candidate_id, round(area_ha, 2), geojson)

    return {"candidate_id": candidate_id, "area_ha": round(area_ha, 2), "geojson": geojson}