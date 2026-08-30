"""
Rainfall data service — IMD is NOT used here (India Meteorological Dept's
official data portal requires registration/approval and isn't a simple
free REST API, so it doesn't fit a student-project pipeline). Instead
this uses a two-tier fallback chain of genuinely free, keyless APIs,
followed by a synthetic fallback so the pipeline never breaks offline:

  1. Open-Meteo Historical Weather API   (global reanalysis, no key)
  2. NASA POWER API                       (satellite-derived, no key,
                                            good India coverage, used as
                                            a cross-check / backup)
  3. Synthetic monsoon-shaped profile     (last resort, offline/dev use)
"""
from __future__ import annotations

import numpy as np
import requests


def _synthetic_monthly_rainfall(lat: float, years: int) -> list[float]:
    """Produce a plausible Indian monsoon-shaped monthly rainfall profile
    (mm/month), seeded by latitude so repeated calls are stable."""
    rng = np.random.default_rng(int(abs(lat) * 1000) % (2**32))
    # Rough monsoon weighting: heavy Jun-Sep, light rest of year
    weights = np.array([0.02, 0.02, 0.03, 0.04, 0.06, 0.16, 0.22, 0.20, 0.14, 0.06, 0.03, 0.02])
    annual_total = rng.uniform(900, 1400)  # mm, typical for many Indian regions
    monthly = weights * annual_total
    monthly *= rng.uniform(0.9, 1.1, size=12)  # inter-annual noise
    return monthly.tolist()


def _try_open_meteo(village: str, lat: float, lon: float) -> dict | None:
    try:
        resp = requests.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": "2015-01-01",
                "end_date": "2024-12-31",
                "daily": "precipitation_sum",
                "timezone": "auto",
            },
            timeout=3,
        )
        resp.raise_for_status()
        data = resp.json()
        daily = data["daily"]["precipitation_sum"]
        dates = data["daily"]["time"]

        monthly_totals = np.zeros(12)
        for d, val in zip(dates, daily):
            if val is None:
                continue
            month = int(d.split("-")[1]) - 1
            monthly_totals[month] += val

        n_years = max(1, len(set(d[:4] for d in dates)))
        monthly_avg = (monthly_totals / n_years).tolist()
        return {
            "village": village,
            "years": n_years,
            "mean_annual_mm": float(sum(monthly_avg)),
            "monthly_avg_mm": monthly_avg,
            "source": "Open-Meteo Historical Weather API",
        }
    except Exception:
        return None


def _try_nasa_power(village: str, lat: float, lon: float) -> dict | None:
    """NASA POWER's daily point API, satellite/reanalysis-derived
    precipitation (parameter PRECTOTCORR, mm/day), free & keyless."""
    try:
        resp = requests.get(
            "https://power.larc.nasa.gov/api/temporal/daily/point",
            params={
                "parameters": "PRECTOTCORR",
                "community": "AG",
                "longitude": lon,
                "latitude": lat,
                "start": "20150101",
                "end": "20241231",
                "format": "JSON",
            },
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        series = data["properties"]["parameter"]["PRECTOTCORR"]  # {"YYYYMMDD": mm}

        monthly_totals = np.zeros(12)
        years_seen = set()
        for date_str, val in series.items():
            if val is None or val < 0:  # NASA POWER uses -999 for missing
                continue
            month = int(date_str[4:6]) - 1
            monthly_totals[month] += val
            years_seen.add(date_str[:4])

        n_years = max(1, len(years_seen))
        monthly_avg = (monthly_totals / n_years).tolist()
        return {
            "village": village,
            "years": n_years,
            "mean_annual_mm": float(sum(monthly_avg)),
            "monthly_avg_mm": monthly_avg,
            "source": "NASA POWER API (satellite-derived precipitation)",
        }
    except Exception:
        return None


def get_rainfall_summary(village: str, lat: float, lon: float, years: int = 10) -> dict:
    for fetch in (_try_open_meteo, _try_nasa_power):
        result = fetch(village, lat, lon)
        if result is not None:
            return result

    monthly = _synthetic_monthly_rainfall(lat, years)
    return {
        "village": village,
        "years": years,
        "mean_annual_mm": float(sum(monthly)),
        "monthly_avg_mm": monthly,
        "source": "synthetic-fallback (monsoon-profile estimate, for prototype/offline use)",
    }