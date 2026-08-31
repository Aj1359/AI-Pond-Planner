"""
Repository layer: every read/write to Supabase (Postgres) goes through
here. Routers and services never call the Supabase client directly —
this keeps the persistence layer swappable (e.g. for a future direct
psycopg2/SQLAlchemy connection) without touching business logic.
"""
from __future__ import annotations

from app import db


# ---------------------------------------------------------------- villages
def upsert_village(name: str, bbox: dict) -> dict:
    client = db.get_client()
    existing = client.table("villages").select("*").eq("name", name).execute()
    if existing.data:
        village = existing.data[0]
        client.table("villages").update(
            {
                "min_lat": bbox["min_lat"],
                "min_lon": bbox["min_lon"],
                "max_lat": bbox["max_lat"],
                "max_lon": bbox["max_lon"],
            }
        ).eq("id", village["id"]).execute()
        return village
    result = (
        client.table("villages")
        .insert(
            {
                "name": name,
                "min_lat": bbox["min_lat"],
                "min_lon": bbox["min_lon"],
                "max_lat": bbox["max_lat"],
                "max_lon": bbox["max_lon"],
            }
        )
        .execute()
    )
    return result.data[0]


def get_village(name: str) -> dict:
    client = db.get_client()
    res = client.table("villages").select("*").eq("name", name).execute()
    if not res.data:
        raise KeyError(f"No village named '{name}'. Call POST /init first.")
    return res.data[0]


def village_bbox(village: dict) -> dict:
    return {
        "min_lat": village["min_lat"],
        "min_lon": village["min_lon"],
        "max_lat": village["max_lat"],
        "max_lon": village["max_lon"],
    }


# --------------------------------------------------------------- dem_cache
def save_dem(village_id: int, elevation, resolution_m: float, source: str) -> dict:
    client = db.get_client()
    payload = {
        "village_id": village_id,
        "source": source,
        "resolution_m": resolution_m,
        "elevation": elevation,
    }
    existing = client.table("dem_cache").select("id").eq("village_id", village_id).execute()
    if existing.data:
        client.table("dem_cache").update(payload).eq("village_id", village_id).execute()
    else:
        client.table("dem_cache").insert(payload).execute()
    return payload


def get_dem(village_id: int) -> dict:
    client = db.get_client()
    res = client.table("dem_cache").select("*").eq("village_id", village_id).execute()
    if not res.data:
        raise KeyError("No DEM cached for this village. Call POST /init first.")
    return res.data[0]


def save_derived_layers(village_id: int, slope=None, flow_direction=None) -> None:
    """Cache slope / flow-direction arrays on the same dem_cache row so
    expensive terrain computations aren't repeated on every request."""
    client = db.get_client()
    update = {}
    if slope is not None:
        update["slope"] = slope
    if flow_direction is not None:
        update["flow_direction"] = flow_direction
    if update:
        client.table("dem_cache").update(update).eq("village_id", village_id).execute()


# ---------------------------------------------------------- candidate_sites
def save_candidate_sites(village_id: int, candidates: list[dict]) -> list[dict]:
    client = db.get_client()
    # Clear old candidates for this village so re-running /init doesn't duplicate
    client.table("candidate_sites").delete().eq("village_id", village_id).execute()

    rows = [
        {
            "village_id": village_id,
            "grid_row": c["row"],
            "grid_col": c["col"],
            "lat": c["lat"],
            "lon": c["lon"],
            "slope_pct": c["slope_pct"],
            "land_type": c["land_type"],
            "suitability_score": c["suitability_score"],
        }
        for c in candidates
    ]
    result = client.table("candidate_sites").insert(rows).execute()
    return result.data


def get_candidate_sites(village_id: int) -> list[dict]:
    client = db.get_client()
    res = (
        client.table("candidate_sites")
        .select("*")
        .eq("village_id", village_id)
        .order("suitability_score", desc=True)
        .execute()
    )
    return res.data


def get_candidate_site(candidate_id: int) -> dict:
    client = db.get_client()
    res = client.table("candidate_sites").select("*").eq("id", candidate_id).execute()
    if not res.data:
        raise KeyError(f"No candidate site with id {candidate_id}")
    return res.data[0]


# --------------------------------------------------------------- catchments
def save_catchment(candidate_site_id: int, area_ha: float, geojson: dict) -> dict:
    client = db.get_client()
    payload = {"candidate_site_id": candidate_site_id, "area_ha": area_ha, "geojson": geojson}
    existing = client.table("catchments").select("id").eq("candidate_site_id", candidate_site_id).execute()
    if existing.data:
        client.table("catchments").update(payload).eq("candidate_site_id", candidate_site_id).execute()
    else:
        client.table("catchments").insert(payload).execute()
    return payload


def get_catchment(candidate_site_id: int) -> dict | None:
    client = db.get_client()
    res = client.table("catchments").select("*").eq("candidate_site_id", candidate_site_id).execute()
    return res.data[0] if res.data else None


# ---------------------------------------------------------- rainfall_records
def save_rainfall(village_id: int, summary: dict) -> dict:
    client = db.get_client()
    payload = {
        "village_id": village_id,
        "source": summary["source"],
        "years": summary["years"],
        "mean_annual_mm": summary["mean_annual_mm"],
        "monthly_avg_mm": summary["monthly_avg_mm"],
    }
    existing = client.table("rainfall_records").select("id").eq("village_id", village_id).execute()
    if existing.data:
        client.table("rainfall_records").update(payload).eq("village_id", village_id).execute()
    else:
        client.table("rainfall_records").insert(payload).execute()
    return payload


def get_rainfall(village_id: int) -> dict | None:
    client = db.get_client()
    res = client.table("rainfall_records").select("*").eq("village_id", village_id).execute()
    return res.data[0] if res.data else None


# ------------------------------------------------------ pond_recommendations
def save_recommendation(candidate_site_id: int, estimate: dict) -> dict:
    client = db.get_client()
    payload = {
        "candidate_site_id": candidate_site_id,
        "runoff_coefficient": estimate["runoff_coefficient"],
        "mean_annual_rainfall_mm": estimate["mean_annual_rainfall_mm"],
        "annual_runoff_volume_m3": estimate["annual_runoff_volume_m3"],
        "recommended_depth_m": estimate["recommended_depth_m"],
        "recommended_surface_area_m2": estimate["recommended_surface_area_m2"],
        "storage_capacity_m3": estimate["storage_capacity_m3"],
        "capture_efficiency_pct": estimate["capture_efficiency_pct"],
    }
    existing = client.table("pond_recommendations").select("id").eq("candidate_site_id", candidate_site_id).execute()
    if existing.data:
        client.table("pond_recommendations").update(payload).eq("candidate_site_id", candidate_site_id).execute()
    else:
        client.table("pond_recommendations").insert(payload).execute()
    return payload


def update_recommendation_rank(candidate_site_id: int, rank_score: float, justification: str) -> None:
    client = db.get_client()
    client.table("pond_recommendations").update(
        {"rank_score": rank_score, "justification": justification}
    ).eq("candidate_site_id", candidate_site_id).execute()


def get_recommendations_for_village(village_id: int) -> list[dict]:
    """Joins pond_recommendations -> candidate_sites for all sites in a village."""
    client = db.get_client()
    sites = client.table("candidate_sites").select("id").eq("village_id", village_id).execute().data
    site_ids = [s["id"] for s in sites]
    if not site_ids:
        return []
    res = client.table("pond_recommendations").select("*").in_("candidate_site_id", site_ids).execute()
    return res.data