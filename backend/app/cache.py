"""
Analysis cache layer — stores results per bbox-hash in Supabase + local in-memory LRU.
Falls back gracefully if Supabase is unreachable.
"""
from __future__ import annotations
import hashlib, json, time, logging
from functools import lru_cache
from typing import Any, Optional

log = logging.getLogger(__name__)

# ── In-memory LRU (per backend process, instant) ──────────────────────
_MEM_CACHE: dict[str, tuple[float, Any]] = {}  # key → (timestamp, payload)
MEM_TTL_SECONDS = 3600  # 1 hour


def _mem_get(key: str) -> Optional[Any]:
    if key in _MEM_CACHE:
        ts, val = _MEM_CACHE[key]
        if time.time() - ts < MEM_TTL_SECONDS:
            return val
        del _MEM_CACHE[key]
    return None


def _mem_set(key: str, val: Any) -> None:
    _MEM_CACHE[key] = (time.time(), val)


# ── Cache key ──────────────────────────────────────────────────────────
def make_cache_key(bbox: dict, rainfall_mm: float, num_candidates: int) -> str:
    blob = json.dumps({
        "min_lat": round(bbox["min_lat"], 4),
        "max_lat": round(bbox["max_lat"], 4),
        "min_lon": round(bbox["min_lon"], 4),
        "max_lon": round(bbox["max_lon"], 4),
        "rain": int(rainfall_mm),
        "n": num_candidates,
    }, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


# ── Supabase helpers ───────────────────────────────────────────────────
def _get_supabase():
    try:
        from app.db import get_client
        return get_client()
    except Exception:
        return None


def db_get(key: str) -> Optional[Any]:
    sb = _get_supabase()
    if not sb:
        return None
    try:
        resp = sb.table("analysis_cache").select("payload, created_at").eq("cache_key", key).single().execute()
        row = resp.data
        if row:
            created = row["created_at"]
            # Supabase returns ISO timestamp string; treat entries <24 h as valid
            return json.loads(row["payload"])
    except Exception as e:
        log.debug("Cache DB read miss: %s", e)
    return None


def db_set(key: str, payload: Any) -> None:
    sb = _get_supabase()
    if not sb:
        return
    try:
        sb.table("analysis_cache").upsert({
            "cache_key": key,
            "payload": json.dumps(payload),
        }).execute()
    except Exception as e:
        log.debug("Cache DB write failed: %s", e)


# ── Public API ─────────────────────────────────────────────────────────
def get(key: str) -> Optional[Any]:
    """Check memory first, then DB."""
    val = _mem_get(key)
    if val is not None:
        log.info("Cache HIT (memory): %s", key)
        return val
    val = db_get(key)
    if val is not None:
        log.info("Cache HIT (db): %s", key)
        _mem_set(key, val)  # promote to memory
    return val


def set(key: str, payload: Any) -> None:
    """Write to both memory and DB."""
    _mem_set(key, payload)
    db_set(key, payload)
