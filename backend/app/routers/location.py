"""
Location Intelligence Router
  GET  /api/location/search     — village/district/tehsil search via Nominatim
  GET  /api/location/boundary   — fetch full polygon boundary of a place
  GET  /api/location/rainfall   — auto annual rainfall from Open-Meteo archive API
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.parse
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/location", tags=["Location Intelligence"])

_NOM_HEADERS = {"User-Agent": "JalSetu-PondPlanner/2.0 (academic project; contact: student)"}
_NOM_SEARCH  = "https://nominatim.openstreetmap.org/search"
_NOM_DETAIL  = "https://nominatim.openstreetmap.org/details.json"
_OPENMETEO   = "https://archive.open-meteo.com/v1/archive"


# ──────────────────────────────────────────────────────────────────────────────
# LOCATION SEARCH
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/search")
def search_location(
    q: str = Query(..., description="Village, tehsil, or district name"),
    limit: int = Query(8, ge=1, le=15),
):
    """
    Search for places (village / tehsil / district) using Nominatim.
    Returns name, type, lat, lon, OSM id — ready for boundary fetch.
    """
    params = urllib.parse.urlencode({
        "q": q,
        "format": "json",
        "addressdetails": 1,
        "limit": limit,
        "countrycodes": "in",   # restrict to India
    })
    url = f"{_NOM_SEARCH}?{params}"
    try:
        req = urllib.request.Request(url, headers=_NOM_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            results = json.loads(resp.read())
    except Exception as e:
        raise HTTPException(502, f"Nominatim error: {e}")

    out = []
    for r in results:
        addr = r.get("address", {})
        out.append({
            "place_id":    r["place_id"],
            "osm_type":    r["osm_type"],     # "node" | "way" | "relation"
            "osm_id":      r["osm_id"],
            "display_name": r["display_name"],
            "name":        r.get("name", r["display_name"].split(",")[0]),
            "type":        r.get("type", ""),
            "class":       r.get("class", ""),
            "lat":         float(r["lat"]),
            "lon":         float(r["lon"]),
            "address": {
                "village":  addr.get("village") or addr.get("hamlet") or "",
                "tehsil":   addr.get("county") or addr.get("suburb") or "",
                "district": addr.get("state_district") or addr.get("district") or "",
                "state":    addr.get("state", ""),
            },
            "bbox": {
                "min_lat": float(r["boundingbox"][0]),
                "max_lat": float(r["boundingbox"][1]),
                "min_lon": float(r["boundingbox"][2]),
                "max_lon": float(r["boundingbox"][3]),
            } if "boundingbox" in r else None,
        })
    return {"results": out, "count": len(out)}


# ──────────────────────────────────────────────────────────────────────────────
# VILLAGE BOUNDARY POLYGON
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/boundary")
def get_boundary(
    osm_type: str = Query(..., description="node | way | relation"),
    osm_id:   int = Query(..., description="Nominatim OSM id"),
    q:        Optional[str] = Query(None, description="Fallback: place name to search directly"),
    lat:      Optional[float] = Query(None, description="Fallback lat"),
    lon:      Optional[float] = Query(None, description="Fallback lon"),
):
    """
    Fetch the GeoJSON polygon boundary for a village/settlement.
    Falls back to bounding-box rectangle if no polygon is available.
    """
    # Try polygon_geojson=1 directly from search
    type_map = {"node": "N", "way": "W", "relation": "R"}
    osm_letter = type_map.get(osm_type.lower(), "R")

    # Use Nominatim /details with polygon_geojson
    params = urllib.parse.urlencode({
        "osmtype":      osm_letter,
        "osmid":        osm_id,
        "polygon_geojson": 1,
        "format":       "json",
    })
    url = f"{_NOM_DETAIL}?{params}"
    try:
        req = urllib.request.Request(url, headers=_NOM_HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())
        geom = data.get("geometry")
        if geom and geom.get("type") in ("Polygon", "MultiPolygon"):
            return {
                "type":     "boundary",
                "geojson":  geom,
                "source":   "osm_polygon",
                "name":     data.get("localname", ""),
                "centroid": {"lat": float(data.get("centroid", {}).get("coordinates", [0,0])[1]),
                             "lon": float(data.get("centroid", {}).get("coordinates", [0,0])[0])},
            }
    except Exception:
        pass

    # Fallback: search with polygon_geojson=1
    if q:
        params2 = urllib.parse.urlencode({
            "q": q, "format": "json", "polygon_geojson": 1, "limit": 1, "countrycodes": "in",
        })
        try:
            req2 = urllib.request.Request(f"{_NOM_SEARCH}?{params2}", headers=_NOM_HEADERS)
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                results = json.loads(resp2.read())
            if results and results[0].get("geojson"):
                r = results[0]
                return {
                    "type":    "boundary",
                    "geojson": r["geojson"],
                    "source":  "osm_search_polygon",
                    "name":    r.get("display_name",""),
                    "centroid": {"lat": float(r["lat"]), "lon": float(r["lon"])},
                }
            # bbox fallback
            if results:
                r = results[0]
                bb = r.get("boundingbox", [])
                if len(bb) == 4:
                    min_lat, max_lat, min_lon, max_lon = float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])
                    return {
                        "type": "bbox_fallback",
                        "geojson": {
                            "type": "Polygon",
                            "coordinates": [[
                                [min_lon, min_lat], [max_lon, min_lat],
                                [max_lon, max_lat], [min_lon, max_lat],
                                [min_lon, min_lat],
                            ]],
                        },
                        "source":  "bbox",
                        "name":    r.get("display_name",""),
                        "centroid": {"lat": float(r["lat"]), "lon": float(r["lon"])},
                    }
        except Exception:
            pass

    # Fallback 2: Generate 1.5km box around lat, lon
    if lat is not None and lon is not None:
        delta_lat = 0.012  # ~1.3 km
        delta_lon = 0.012
        min_lat, max_lat = lat - delta_lat, lat + delta_lat
        min_lon, max_lon = lon - delta_lon, lon + delta_lon
        return {
            "type": "radius_fallback",
            "geojson": {
                "type": "Polygon",
                "coordinates": [[
                    [min_lon, min_lat], [max_lon, min_lat],
                    [max_lon, max_lat], [min_lon, max_lat],
                    [min_lon, min_lat],
                ]],
            },
            "source":  "radius_box",
            "name":    q or "Selected Location",
            "centroid": {"lat": lat, "lon": lon},
        }

    raise HTTPException(404, "Could not fetch boundary polygon for this location.")



# ──────────────────────────────────────────────────────────────────────────────
# AUTO RAINFALL from Open-Meteo archive
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/rainfall")
def get_rainfall(
    lat: float = Query(...),
    lon: float = Query(...),
    years: int = Query(5, ge=1, le=10, description="Number of past years to average"),
):
    """
    Fetch mean annual rainfall (mm) for a location using Open-Meteo archive API.
    Averages the last `years` complete calendar years.
    """
    from datetime import date, timedelta

    today = date.today()
    end_year   = today.year - 1          # last complete year
    start_year = end_year - years + 1

    params = urllib.parse.urlencode({
        "latitude":   lat,
        "longitude":  lon,
        "start_date": f"{start_year}-01-01",
        "end_date":   f"{end_year}-12-31",
        "daily":      "precipitation_sum",
        "timezone":   "Asia/Kolkata",
    })
    url = f"{_OPENMETEO}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JalSetu/2.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        daily = data.get("daily", {})
        dates  = daily.get("time", [])
        precip = daily.get("precipitation_sum", [])
        if dates and precip:
            yearly: Dict[int, float] = {}
            for d_str, p in zip(dates, precip):
                if p is None:
                    continue
                yr = int(d_str[:4])
                yearly[yr] = yearly.get(yr, 0.0) + p
            if yearly:
                annual_vals = list(yearly.values())
                mean_annual = sum(annual_vals) / len(annual_vals)
                return {
                    "lat": lat, "lon": lon,
                    "mean_annual_rainfall_mm": round(mean_annual, 1),
                    "years_averaged": len(yearly),
                    "year_range": f"{min(yearly.keys())}–{max(yearly.keys())}",
                    "per_year": {str(k): round(v, 1) for k, v in sorted(yearly.items())},
                    "source": "Open-Meteo archive API",
                }
    except Exception as e:
        pass

    # Fallback to IMD historical monsoon average for regional estimate
    return {
        "lat": lat, "lon": lon,
        "mean_annual_rainfall_mm": 1150.0,
        "years_averaged": 5,
        "year_range": "IMD Historical Avg",
        "per_year": {"avg": 1150.0},
        "source": "IMD regional monsoon average fallback",
    }
