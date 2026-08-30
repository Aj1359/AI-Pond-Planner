from typing import Any, Dict, List, Optional
from app.db import supabase

def _get_client():
    if supabase is None:
        raise RuntimeError(
            "Supabase client is not initialized. "
            "Please ensure SUPABASE_URL and SUPABASE_SERVICE_KEY are set in your environment / .env file."
        )
    return supabase

def upsert_village(
    name: str, 
    min_lat: float, 
    min_lon: float, 
    max_lat: float, 
    max_lon: float
) -> Dict[str, Any]:
    """
    Upserts a village record based on its unique name.
    Returns the created/updated village record dict.
    """
    client = _get_client()
    payload = {
        "name": name,
        "min_lat": min_lat,
        "min_lon": min_lon,
        "max_lat": max_lat,
        "max_lon": max_lon,
    }
    response = client.table("villages").upsert(payload, on_conflict="name").execute()
    if not response.data:
        raise RuntimeError(f"Failed to upsert village '{name}'")
    return response.data[0]

def get_village_by_name(name: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves a village record by its name. Returns None if not found.
    """
    client = _get_client()
    response = client.table("villages").select("*").eq("name", name).execute()
    return response.data[0] if response.data else None

def save_dem(village_id: str, source: str, elevation: List[List[float]]) -> Dict[str, Any]:
    """
    Saves/updates the digital elevation model grid associated with a village.
    """
    client = _get_client()
    payload = {
        "village_id": village_id,
        "source": source,
        "elevation": elevation,
    }
    response = client.table("dem_grids").upsert(payload).execute()
    if not response.data:
        raise RuntimeError(f"Failed to save DEM for village_id '{village_id}'")
    return response.data[0]

def get_dem(village_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves the DEM grid record for a village. Returns None if not found.
    """
    client = _get_client()
    response = client.table("dem_grids").select("*").eq("village_id", village_id).execute()
    return response.data[0] if response.data else None

def save_rainfall(
    village_id: str, 
    source: str, 
    mean_annual_mm: float, 
    monthly_avg_mm: List[float], 
    years: int
) -> Dict[str, Any]:
    """
    Saves/updates the rainfall summary associated with a village.
    """
    client = _get_client()
    payload = {
        "village_id": village_id,
        "source": source,
        "mean_annual_mm": mean_annual_mm,
        "monthly_avg_mm": monthly_avg_mm,
        "years": years,
    }
    response = client.table("rainfall_summaries").upsert(payload).execute()
    if not response.data:
        raise RuntimeError(f"Failed to save rainfall for village_id '{village_id}'")
    return response.data[0]

def get_rainfall(village_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves the rainfall summary record for a village. Returns None if not found.
    """
    client = _get_client()
    response = client.table("rainfall_summaries").select("*").eq("village_id", village_id).execute()
    return response.data[0] if response.data else None

def save_candidate_sites(village_id: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Upserts a list of candidate sites for a village.
    Translates the local candidate 'id' to 'candidate_id' in the database.
    """
    if not candidates:
        return []
        
    client = _get_client()
    payload = []
    for c in candidates:
        payload.append({
            "village_id": village_id,
            "candidate_id": c.get("id"),
            "row": c.get("row"),
            "col": c.get("col"),
            "lat": c.get("lat"),
            "lon": c.get("lon"),
            "slope_pct": c.get("slope_pct"),
            "land_type": c.get("land_type"),
            "suitability_score": c.get("suitability_score"),
            "recommended_depth_m": c.get("recommended_depth_m"),
            "recommended_surface_area_m2": c.get("recommended_surface_area_m2"),
            "storage_capacity_m3": c.get("storage_capacity_m3"),
            "capture_efficiency_pct": c.get("capture_efficiency_pct"),
            "rank_score": c.get("rank_score"),
            "justification": c.get("justification"),
        })
        
    response = client.table("candidate_sites").upsert(payload, on_conflict="village_id,candidate_id").execute()
    return response.data

def get_candidate_sites(village_id: str) -> List[Dict[str, Any]]:
    """
    Retrieves candidate sites for a village sorted by rank_score descending.
    """
    client = _get_client()
    response = client.table("candidate_sites") \
        .select("*") \
        .eq("village_id", village_id) \
        .order("rank_score", desc=True) \
        .execute()
    return response.data
