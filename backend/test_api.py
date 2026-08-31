"""
End-to-End API Integration & Verification Test Suite for Pond Planner.

Can be run directly with:
    python test_api.py
"""
import sys
import io
import requests

BASE_URL = "http://localhost:8000"


def log_step(name: str):
    print(f"\n{'='*15} {name} {'='*15}")


def test_all():
    print(f"Connecting to API at {BASE_URL}...")

    # 1. Health Check
    log_step("1. Health Check (GET /)")
    try:
        r = requests.get(f"{BASE_URL}/", timeout=5)
    except requests.exceptions.ConnectionError:
        print(f"[ERROR] Could not connect to {BASE_URL}. Ensure uvicorn is running:")
        print("  .\\venv\\Scripts\\python -m uvicorn app.main:app --reload --port 8000")
        sys.exit(1)

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    print(f"[PASS] Status: {r.status_code}, Response: {r.json()}")

    village_name = "TestVillage_Auto"
    bbox = {
        "min_lat": 21.235,
        "min_lon": 81.285,
        "max_lat": 21.265,
        "max_lon": 81.315,
    }

    # 2. Init Village
    log_step(f"2. Init Village (POST /api/villages/{village_name}/init)")
    payload = {"name": village_name, "bbox": bbox}
    r = requests.post(f"{BASE_URL}/api/villages/{village_name}/init", json=payload)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    print(f"[PASS] Village Initialized:")
    print(f"       Village ID: {data.get('village_id')}")
    print(f"       DEM Source: {data.get('dem_source')}")
    print(f"       Candidate Count: {data.get('candidate_count')}")

    # 3. Imagery Config
    log_step(f"3. Imagery Config (GET /api/villages/{village_name}/imagery)")
    r = requests.get(f"{BASE_URL}/api/villages/{village_name}/imagery")
    assert r.status_code == 200
    print(f"[PASS] Tile URL: {r.json().get('tile_url')}")

    # 4. Elevation Contours
    log_step(f"4. Elevation Contours (GET /api/villages/{village_name}/contours)")
    r = requests.get(f"{BASE_URL}/api/villages/{village_name}/contours")
    assert r.status_code == 200
    contour_data = r.json()
    feature_count = len(contour_data.get("geojson", {}).get("features", []))
    print(f"[PASS] Extracted {feature_count} contour features (interval: {contour_data.get('interval_m')}m)")

    # 5. Rainfall Summary
    log_step(f"5. Rainfall Summary (GET /api/villages/{village_name}/rainfall)")
    r = requests.get(f"{BASE_URL}/api/villages/{village_name}/rainfall?years=10")
    assert r.status_code == 200
    rain_data = r.json()
    print(f"[PASS] Mean Annual Rainfall: {rain_data.get('mean_annual_mm')} mm (Source: {rain_data.get('source')})")

    # 6. Candidate Sites
    log_step(f"6. Candidate Sites (GET /api/villages/{village_name}/candidates)")
    r = requests.get(f"{BASE_URL}/api/villages/{village_name}/candidates")
    assert r.status_code == 200
    candidates = r.json().get("candidates", [])
    assert len(candidates) > 0, "No candidates returned"
    print(f"[PASS] Found {len(candidates)} candidate excavation sites:")
    for c in candidates:
        print(f"       Candidate #{c['id']}: Lat={c['lat']:.4f}, Lon={c['lon']:.4f}, Slope={c['slope_pct']}%, Type={c['land_type']}")

    first_candidate_id = candidates[0]["id"]

    # 7. Catchment Delineation
    log_step(f"7. Catchment Delineation (POST /api/villages/{village_name}/candidates/{first_candidate_id}/catchment)")
    r = requests.post(f"{BASE_URL}/api/villages/{village_name}/candidates/{first_candidate_id}/catchment")
    assert r.status_code == 200
    catchment_data = r.json()
    print(f"[PASS] Contributing Catchment Area: {catchment_data.get('area_ha')} ha")

    # 8. Runoff & Pond Sizing
    log_step(f"8. Runoff Sizing (POST /api/villages/{village_name}/candidates/{first_candidate_id}/estimate)")
    r = requests.post(f"{BASE_URL}/api/villages/{village_name}/candidates/{first_candidate_id}/estimate")
    assert r.status_code == 200
    estimate_data = r.json()
    print(f"[PASS] Annual Runoff Volume: {estimate_data.get('annual_runoff_volume_m3'):,.1f} m3")
    print(f"       Recommended Depth:   {estimate_data.get('recommended_depth_m')} m")
    print(f"       Surface Area:        {estimate_data.get('recommended_surface_area_m2'):,.1f} m2")
    print(f"       Storage Capacity:    {estimate_data.get('storage_capacity_m3'):,.1f} m3")
    print(f"       Capture Efficiency:  {estimate_data.get('capture_efficiency_pct')}%")

    # 9. Recommendations
    log_step(f"9. Recommendations (GET /api/villages/{village_name}/recommendations)")
    r = requests.get(f"{BASE_URL}/api/villages/{village_name}/recommendations")
    assert r.status_code == 200
    recs = r.json().get("recommendations", [])
    print(f"[PASS] Ranked Recommendations ({len(recs)} candidates evaluated):")
    for rec in recs:
        print(f"       Rank Score: {rec.get('rank_score')} | Justification: {rec.get('justification')}")

    # 10. PDF Report
    log_step(f"10. PDF Dossier Report (GET /api/villages/{village_name}/candidates/{first_candidate_id}/report)")
    r = requests.get(f"{BASE_URL}/api/villages/{village_name}/candidates/{first_candidate_id}/report")
    assert r.status_code == 200
    assert r.headers.get("content-type") == "application/pdf"
    print(f"[PASS] PDF Dossier Generated Successfully ({len(r.content):,} bytes)")

    # 11. Contour File Upload Analysis
    log_step("11. Upload Contour Map Analysis (POST /api/contour/analyzeContour)")
    # Create a synthetic sample KML with contour lines
    sample_kml = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Contour 270m</name>
      <description>Elevation: 270</description>
      <LineString>
        <coordinates>
          81.290,21.240,270 81.295,21.242,270 81.300,21.240,270
        </coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>Contour 280m</name>
      <description>Elevation: 280</description>
      <LineString>
        <coordinates>
          81.290,21.250,280 81.295,21.252,280 81.300,21.250,280
        </coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>"""
    files = {"file": ("test_contours.kml", sample_kml, "application/vnd.google-earth.kml+xml")}
    r = requests.post(f"{BASE_URL}/api/contour/analyzeContour", files=files)
    assert r.status_code == 200
    c_res = r.json()
    print(f"[PASS] Contour Map Ingested & Analyzed:")
    print(f"       Lines Parsed:     {c_res['input_summary']['contour_line_count']}")
    print(f"       Elevation Range:  {c_res['input_summary']['elevation_range_m']} m")
    print(f"       Recommended Site: Lat={c_res['recommended_site']['location']['lat']:.4f}, Lon={c_res['recommended_site']['location']['lon']:.4f}")
    print(f"       Catchment Area:   {c_res['recommended_site']['catchment']['area_ha']} ha")

    print("\n" + "="*50)
    print("ALL API TESTS COMPLETED AND PASSED SUCCESSFULLY!")
    print("="*50 + "\n")


if __name__ == "__main__":
    test_all()
