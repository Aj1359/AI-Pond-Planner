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

import hashlib
from fastapi import APIRouter, HTTPException, Query

from app import cache as cache_svc

router = APIRouter(prefix="/api/location", tags=["Location Intelligence"])

_NOM_HEADERS = {"User-Agent": "JalSetu-PondPlanner/2.0 (academic project; contact: student)"}
_NOM_SEARCH  = "https://nominatim.openstreetmap.org/search"
_NOM_DETAIL  = "https://nominatim.openstreetmap.org/details.json"
_OPENMETEO_GEO = "https://geocoding-api.open-meteo.com/v1/search"
_OPENMETEO     = "https://archive.open-meteo.com/v1/archive"


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
    Falls back to Open-Meteo Geocoding API (GeoNames-backed) for small
    Indian villages that Nominatim doesn't index.
    """
    # ── Cache Check ──
    cache_key = "loc_search_" + hashlib.sha256(f"{q}_{limit}".encode()).hexdigest()[:15]
    cached = cache_svc.get(cache_key)
    if cached:
        return cached

    # ── Primary: Nominatim ──
    params = urllib.parse.urlencode({
        "q": q,
        "format": "json",
        "addressdetails": 1,
        "limit": limit,
        "countrycodes": "in",   # restrict to India
    })
    url = f"{_NOM_SEARCH}?{params}"
    nominatim_results = []
    try:
        req = urllib.request.Request(url, headers=_NOM_HEADERS)
        with urllib.request.urlopen(req, timeout=2) as resp:
            nominatim_results = json.loads(resp.read())
    except Exception:
        pass  # fall through to fallback

    out = []
    for r in nominatim_results:
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

    # ── Fallback: Open-Meteo Geocoding API (GeoNames data) ──
    # Handles small Indian villages that Nominatim doesn't index
    if not out:
        # Strip ", India" / ", State, India" suffixes for cleaner search
        clean_q = q.replace(", India", "").strip()
        parts = [p.strip() for p in clean_q.split(",")]
        village_name = parts[0]

        # Build list of search attempts: exact name + common Hindi transliteration
        # variants (o↔u, e↔i vowel swaps) to handle alternate spellings
        attempts = [village_name]
        lower = village_name.lower()
        variants = set()
        for old, new in [("o", "u"), ("u", "o"), ("e", "i"), ("i", "e")]:
            v = lower.replace(old, new, 1)
            if v != lower:
                variants.add(v)
        # Also try swapping "ko" → "ku", "ke" → "ki" etc. (start of word)
        for old, new in [("ko", "ku"), ("ku", "ko"), ("ke", "ki"), ("ki", "ke")]:
            if lower.startswith(old):
                variants.add(new + lower[len(old):])
        attempts.extend(sorted(variants))

        for attempt_name in attempts:
            if out:
                break
            geo_params = urllib.parse.urlencode({
                "name": attempt_name,
                "count": limit,
                "language": "en",
                "format": "json",
            })
            geo_url = f"{_OPENMETEO_GEO}?{geo_params}"
            try:
                geo_req = urllib.request.Request(geo_url, headers={"User-Agent": "JalSetu/2.0"})
                with urllib.request.urlopen(geo_req, timeout=2) as geo_resp:
                    geo_data = json.loads(geo_resp.read())
                for g in geo_data.get("results", []):
                    # Filter to India only
                    if g.get("country_code", "").upper() != "IN":
                        continue
                    lat = g["latitude"]
                    lon = g["longitude"]
                    delta = 0.01  # ~1.1 km
                    state_name = g.get("admin1", "")
                    district_name = g.get("admin2", "")
                    tehsil_name = g.get("admin3", "")
                    name = g.get("name", village_name)
                    display = f"{name}, {tehsil_name}, {district_name}, {state_name}, India"
                    out.append({
                        "place_id":    g.get("id", 0),
                        "osm_type":    "node",
                        "osm_id":      g.get("id", 0),
                        "display_name": display,
                        "name":        name,
                        "type":        g.get("feature_code", "village"),
                        "class":       "place",
                        "lat":         lat,
                        "lon":         lon,
                        "address": {
                            "village":  name,
                            "tehsil":   tehsil_name,
                            "district": district_name,
                            "state":    state_name,
                        },
                        "bbox": {
                            "min_lat": lat - delta,
                            "max_lat": lat + delta,
                            "min_lon": lon - delta,
                            "max_lon": lon + delta,
                        },
                        "_source": "open_meteo_geocoding",
                    })
            except Exception:
                pass

    result = {"results": out, "count": len(out)}
    cache_svc.set(cache_key, result)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# VILLAGE BOUNDARY POLYGON
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/boundary")
def get_boundary(
    osm_type: Optional[str] = Query(None, description="node | way | relation"),
    osm_id:   Optional[int] = Query(None, description="Nominatim OSM id"),
    q:        Optional[str] = Query(None, description="Fallback: place name to search directly"),
    lat:      Optional[float] = Query(None, description="Fallback lat"),
    lon:      Optional[float] = Query(None, description="Fallback lon"),
):
    """
    Fetch the GeoJSON polygon boundary for a village/settlement.
    Falls back to bounding-box rectangle if no polygon is available.
    """
    if osm_type and osm_id:
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
            with urllib.request.urlopen(req, timeout=2) as resp:
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
            with urllib.request.urlopen(req2, timeout=2) as resp2:
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
        delta_lat = 0.0135  # ~1.5 km radius, 3 km total span (~0.027°)
        delta_lon = 0.0135
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
        with urllib.request.urlopen(req, timeout=2) as resp:
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
