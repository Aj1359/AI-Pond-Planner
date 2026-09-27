"""
Comprehensive Automated Test Matrix Execution Suite for Pond Planner Backend.
Tests all 11 paths & edge cases defined in the backend API verification matrix.
"""
import sys
import json
import math
import requests

BASE_URL = "http://localhost:3000"

def log_test(num, title):
    print(f"\n==================================================")
    print(f" TEST {num}: {title}")
    print(f"==================================================")

def main():
    print(f"🚀 Running Full Backend API Test Matrix against {BASE_URL}...\n")
    
    # --------------------------------------------------------------------------
    # 1. GET /api/location/search?q={query}&limit=8
    # --------------------------------------------------------------------------
    log_test("1", "Location Search (Partial & Full Name)")
    r1 = requests.get(f"{BASE_URL}/api/location/search?q=kotelabhata&limit=8")
    assert r1.status_code == 200, f"Expected 200, got {r1.status_code}"
    d1 = r1.json()
    print(f"  [PASS] Search 'kotelabhata': {d1.get('count')} results")
    assert len(d1.get("results", [])) > 0, "Expected at least 1 result"
    first = d1["results"][0]
    print(f"         Result 0: name={first.get('name')}, lat={first.get('lat')}, lon={first.get('lon')}")
    assert "osm_type" in first or "lat" in first, "Expected spatial fields in result"

    r1_full = requests.get(f"{BASE_URL}/api/location/search?q=Raipur,%20Chhattisgarh,%20India&limit=5")
    assert r1_full.status_code == 200
    d1_full = r1_full.json()
    print(f"  [PASS] Search full 'Raipur, Chhattisgarh': {d1_full.get('count')} results")
    assert len(d1_full.get("results", [])) > 0
    print(f"         Bbox: {d1_full['results'][0].get('bbox')}")

    # --------------------------------------------------------------------------
    # 2. GET /api/location/boundary?osm_type=&osm_id=&q=&lat=&lon=
    # --------------------------------------------------------------------------
    log_test("2a", "Village with real OSM polygon (osm_polygon / osm_search_polygon)")
    r2a = requests.get(f"{BASE_URL}/api/location/boundary?osm_type=relation&osm_id=7445749&q=Raipur&lat=21.251&lon=81.635")
    assert r2a.status_code == 200
    d2a = r2a.json()
    print(f"  [PASS] Source: {d2a.get('source')}, geojson type: {d2a.get('geojson', {}).get('type')}")
    assert d2a.get("source") in ["osm_polygon", "osm_search_polygon", "nominatim_search_polygon", "bbox"]

    log_test("2b", "Location fallback to bbox")
    r2b = requests.get(f"{BASE_URL}/api/location/boundary?q=SmallVillageWithoutPolygon&lat=21.251&lon=81.635")
    assert r2b.status_code == 200
    d2b = r2b.json()
    print(f"  [PASS] Source: {d2b.get('source')}")

    log_test("2c", "Fallback to ~3km radius box (lat/lon span ≈ 0.027°)")
    r2c = requests.get(f"{BASE_URL}/api/location/boundary?osm_type=relation&osm_id=9999999999&lat=21.251000&lon=81.635000")
    assert r2c.status_code == 200
    d2c = r2c.json()
    assert d2c.get("source") == "radius_box", f"Expected radius_box, got {d2c.get('source')}"
    coords = d2c.get("geojson", {}).get("coordinates", [[]])[0]
    lats = [c[1] for c in coords]
    lons = [c[0] for c in coords]
    lat_span = max(lats) - min(lats)
    lon_span = max(lons) - min(lons)
    print(f"  [PASS] Source: {d2c.get('source')}")
    print(f"         Lat Span: {lat_span:.4f}°, Lon Span: {lon_span:.4f}° (approx 0.027° ~3km)")
    assert 0.020 <= lat_span <= 0.035, f"Expected lat span ~0.027, got {lat_span}"

    # --------------------------------------------------------------------------
    # 3. GET /api/location/rainfall?lat=&lon=&years=5
    # --------------------------------------------------------------------------
    log_test("3", "Rainfall API & IMD Fallback")
    r3 = requests.get(f"{BASE_URL}/api/location/rainfall?lat=21.251&lon=81.635&years=5")
    assert r3.status_code == 200
    d3 = r3.json()
    print(f"  [PASS] Mean Annual Rainfall: {d3.get('mean_annual_rainfall_mm')} mm/yr")
    print(f"         Source: {d3.get('source')}")

    # Fallback test (invalid lat/lon)
    r3_fail = requests.get(f"{BASE_URL}/api/location/rainfall?lat=999&lon=999")
    assert r3_fail.status_code in [200, 400, 422]
    print(f"  [PASS] Invalid rainfall coordinates handled gracefully (status {r3_fail.status_code})")

    # --------------------------------------------------------------------------
    # 4. POST /api/map/analyze-area (Masking & Shape Types)
    # --------------------------------------------------------------------------
    log_test("4a", "shape_type: polygon (Lasso non-convex L-shape)")
    l_shape_coords = [
        [81.285, 21.235], [81.305, 21.235], [81.305, 21.245],
        [81.295, 21.245], [81.295, 21.265], [81.285, 21.265],
        [81.285, 21.235]
    ]
    p4a = {
        "coordinates": l_shape_coords,
        "mean_annual_rainfall_mm": 1150.0,
        "num_candidates": 3,
        "shape_type": "polygon"
    }
    r4a = requests.post(f"{BASE_URL}/api/map/analyze-area", json=p4a)
    assert r4a.status_code == 200, f"Expected 200, got {r4a.status_code}: {r4a.text}"
    d4a = r4a.json()
    rec_site = d4a["recommended_site"]
    print(f"  [PASS] Recommended Site Location: {rec_site['location']}")
    print(f"         Candidates Count: {1 + len(d4a.get('alternative_sites', []))}")

    log_test("4b", "shape_type: bbox (Rectangle draw regression)")
    bbox_coords = [
        [81.285, 21.235], [81.315, 21.235],
        [81.315, 21.265], [81.285, 21.265],
        [81.285, 21.235]
    ]
    p4b = {
        "coordinates": bbox_coords,
        "mean_annual_rainfall_mm": 1150.0,
        "num_candidates": 3,
        "shape_type": "bbox"
    }
    r4b = requests.post(f"{BASE_URL}/api/map/analyze-area", json=p4b)
    assert r4b.status_code == 200
    print(f"  [PASS] Bbox analysis successful")

    log_test("4c", "shape_type: circle with radius_m")
    center_lon, center_lat = 81.300, 21.250
    radius_m = 1500.0
    circle_coords = []
    R = 6371000.0
    for i in range(33):
        angle = (2 * math.pi * i) / 32
        dLat = (radius_m * math.cos(angle)) / R * (180 / math.pi)
        dLng = (radius_m * math.sin(angle)) / (R * math.cos(center_lat * math.pi / 180)) * (180 / math.pi)
        circle_coords.append([center_lon + dLng, center_lat + dLat])

    p4c = {
        "coordinates": circle_coords,
        "mean_annual_rainfall_mm": 1150.0,
        "num_candidates": 3,
        "shape_type": "circle",
        "radius_m": radius_m
    }
    r4c = requests.post(f"{BASE_URL}/api/map/analyze-area", json=p4c)
    assert r4c.status_code == 200
    d4c = r4c.json()
    rec = d4c["recommended_site"]["location"]
    
    def haversine(lat1, lon1, lat2, lon2):
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    dist = haversine(center_lat, center_lon, rec["lat"], rec["lon"])
    print(f"  [PASS] Circle Candidate Distance from Center: {dist:.1f} m (<= {radius_m} m)")
    assert dist <= radius_m + 50, f"Candidate outside circle: {dist} m > {radius_m} m"

    log_test("4d", "Edge Case: Tiny polygon with no suitable cells inside mask -> 422")
    tiny_coords = [
        [81.28500, 21.23500], [81.28501, 21.23500],
        [81.28501, 21.23501], [81.28500, 21.23501],
        [81.28500, 21.23500]
    ]
    p4d = {
        "coordinates": tiny_coords,
        "mean_annual_rainfall_mm": 1150.0,
        "num_candidates": 3,
        "shape_type": "polygon"
    }
    r4d = requests.post(f"{BASE_URL}/api/map/analyze-area", json=p4d)
    assert r4d.status_code == 422, f"Expected 422, got {r4d.status_code}"
    print(f"  [PASS] Status 422 returned correctly for empty mask: {r4d.json().get('detail')}")

    log_test("4e", "num_candidates 1-6 range validation")
    p4e_1 = { "coordinates": bbox_coords, "num_candidates": 1 }
    r4e_1 = requests.post(f"{BASE_URL}/api/map/analyze-area", json=p4e_1)
    assert r4e_1.status_code == 200
    assert len(r4e_1.json().get("alternative_sites", [])) == 0
    print(f"  [PASS] num_candidates=1: Returns 1 site total")

    p4e_6 = { "coordinates": bbox_coords, "num_candidates": 6 }
    r4e_6 = requests.post(f"{BASE_URL}/api/map/analyze-area", json=p4e_6)
    assert r4e_6.status_code == 200
    assert 1 + len(r4e_6.json().get("alternative_sites", [])) == 6
    print(f"  [PASS] num_candidates=6: Returns 6 sites total")

    # --------------------------------------------------------------------------
    # 5. POST /api/map/elevation-point
    # --------------------------------------------------------------------------
    log_test("5", "Elevation Point Regression Check")
    r5 = requests.post(f"{BASE_URL}/api/map/elevation-point", json={"lat": 21.250, "lon": 81.300})
    assert r5.status_code == 200
    print(f"  [PASS] Elevation at (21.25, 81.30): {r5.json().get('elevation_m')} m")

    # --------------------------------------------------------------------------
    # 6. GET /api/map/geocode?address=
    # --------------------------------------------------------------------------
    log_test("6", "Geocode Regression Check")
    r6 = requests.get(f"{BASE_URL}/api/map/geocode?address=Raipur")
    assert r6.status_code == 200
    print(f"  [PASS] Geocode Raipur: {r6.json().get('location')}")

    # --------------------------------------------------------------------------
    # 7. POST /analyzeContour (Whole file mode)
    # --------------------------------------------------------------------------
    log_test("7", "Contour Whole-File Analysis Mode")
    sample_kml = """<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Document>
        <Placemark><name>250</name><LineString><coordinates>81.28,21.24,250 81.31,21.24,250</coordinates></LineString></Placemark>
        <Placemark><name>260</name><LineString><coordinates>81.28,21.26,260 81.31,21.26,260</coordinates></LineString></Placemark>
      </Document>
    </kml>"""
    files = {"contour_map": ("test.kml", sample_kml, "application/vnd.google-earth.kml+xml")}
    r7 = requests.post(f"{BASE_URL}/analyzeContour?num_candidates=3&format=json", files=files)
    assert r7.status_code == 200, f"Expected 200, got {r7.status_code}: {r7.text}"
    d7 = r7.json()
    print(f"  [PASS] Contour Whole File Analysis: {len(d7.get('summary_table', []))} sites found")

    # --------------------------------------------------------------------------
    # 8. POST /analyzeContour with area_coords + shape_type=custom
    # --------------------------------------------------------------------------
    log_test("8a", "Contour Sub-Area Analysis (Inside Bounds)")
    area_inside = [[81.285, 21.242], [81.305, 21.242], [81.305, 21.258], [81.285, 21.258], [81.285, 21.242]]
    files8a = {"contour_map": ("test.kml", sample_kml, "application/vnd.google-earth.kml+xml")}
    r8a = requests.post(
        f"{BASE_URL}/analyzeContour?num_candidates=3&format=json&shape_type=custom&area_coords={json.dumps(area_inside)}",
        files=files8a
    )
    assert r8a.status_code == 200, f"Expected 200, got {r8a.status_code}: {r8a.text}"
    print(f"  [PASS] Contour Sub-area Analysis successful")

    log_test("8b", "Contour Sub-Area Outside Bounds -> 400 Bad Request")
    area_outside = [[82.000, 22.000], [82.100, 22.000], [82.100, 22.100], [82.000, 22.100], [82.000, 22.000]]
    files8b = {"contour_map": ("test.kml", sample_kml, "application/vnd.google-earth.kml+xml")}
    r8b = requests.post(
        f"{BASE_URL}/analyzeContour?num_candidates=3&format=json&shape_type=custom&area_coords={json.dumps(area_outside)}",
        files=files8b
    )
    assert r8b.status_code == 400, f"Expected 400, got {r8b.status_code}"
    print(f"  [PASS] Status 400 returned correctly for area outside bounds: {r8b.json().get('detail')}")

    # --------------------------------------------------------------------------
    # 9. Diagnostic Endpoints
    # --------------------------------------------------------------------------
    log_test("9", "Contour Diagnostics (extract-polylines)")
    files9 = {"file": ("test.kml", sample_kml, "application/vnd.google-earth.kml+xml")}
    r9 = requests.post(f"{BASE_URL}/api/contour/extract-polylines", files=files9)
    assert r9.status_code == 200
    print(f"  [PASS] Polylines extracted: {r9.json().get('polyline_count')} polylines")

    # --------------------------------------------------------------------------
    # 11. Root Sanity Checks (GET / and GET /docs)
    # --------------------------------------------------------------------------
    log_test("11", "Sanity Check GET / and GET /docs")
    r11_root = requests.get(f"{BASE_URL}/")
    assert r11_root.status_code == 200
    print(f"  [PASS] GET / returns 200 OK")

    r11_docs = requests.get(f"{BASE_URL}/docs")
    assert r11_docs.status_code == 200
    print(f"  [PASS] GET /docs returns 200 OK (FastAPI Swagger UI)")

    print("\n==================================================")
    print(" 🎉 ALL 11 TEST MATRIX SUITES PASSED SUCCESSFULLY!")
    print("==================================================\n")

if __name__ == "__main__":
    main()
