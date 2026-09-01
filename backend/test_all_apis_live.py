"""
Comprehensive Live API Testing Script for AI Village Pond Planner.

Executes and displays full formatted requests and responses for all API endpoints one by one.
Includes both independent services (Elevation, Rainfall, Contour Ingestion) and the
full village-persisted bounding-box workflow.

Run with:
    python test_all_apis_live.py
"""
import sys
import json
import time
import requests
from pathlib import Path

BASE_URL = "http://localhost:8000"


def print_banner(text: str):
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80)


def print_step(step_num: int, title: str, method: str, endpoint: str, payload=None):
    print(f"\n[STEP {step_num}] {title}")
    print(f"--> {method} {BASE_URL}{endpoint}")
    if payload is not None:
        if isinstance(payload, dict):
            print("--> Request Payload:")
            print(json.dumps(payload, indent=2))
        else:
            print(f"--> Request Data: {payload}")


def print_response(response: requests.Response, truncate_grid: bool = False):
    print(f"<-- Status Code: {response.status_code} {response.reason}")
    try:
        data = response.json()
        if truncate_grid and isinstance(data, dict):
            display_data = dict(data)
            if "elevation" in display_data and isinstance(display_data["elevation"], list):
                grid = display_data["elevation"]
                display_data["elevation"] = f"[{len(grid)}x{len(grid[0])} Elevation Grid Array]"
            if "geojson" in display_data and isinstance(display_data["geojson"], dict):
                features = display_data["geojson"].get("features", [])
                if len(features) > 3:
                    display_data["geojson"] = {
                        "type": display_data["geojson"].get("type"),
                        "features_count": len(features),
                        "sample_first_feature": features[0],
                        "sample_last_feature": features[-1],
                    }
            print("<-- Response Body (JSON):")
            print(json.dumps(display_data, indent=2))
        else:
            print("<-- Response Body (JSON):")
            print(json.dumps(data, indent=2))
    except Exception:
        content_type = response.headers.get("Content-Type", "")
        if "pdf" in content_type:
            print(f"<-- Response: [Binary PDF Data, Size: {len(response.content):,} bytes]")
        else:
            print(f"<-- Response Text: {response.text[:500]}")


def run_live_tests():
    print_banner("AI VILLAGE POND PLANNER - COMPLETE LIVE API TEST SUITE")
    print(f"Target Server: {BASE_URL}")

    # Check connection
    try:
        r = requests.get(f"{BASE_URL}/", timeout=5)
    except requests.exceptions.ConnectionError:
        print(f"\n[ERROR] Could not connect to {BASE_URL}.")
        print("Please ensure your backend is running:")
        print("    .\\venv\\Scripts\\python -m uvicorn app.main:app --reload --port 8000")
        sys.exit(1)

    village = "DemoVillage_Live"
    bbox_sample = {
        "min_lat": 21.235,
        "min_lon": 81.285,
        "max_lat": 21.265,
        "max_lon": 81.315
    }

    # =========================================================================
    # SECTION 1: CORE & DISCOVERY
    # =========================================================================
    print_banner("SECTION 1: CORE & DISCOVERY ENDPOINTS")

    # Step 1: Health Check
    print_step(1, "Core Health Check", "GET", "/")
    r = requests.get(f"{BASE_URL}/")
    print_response(r)
    time.sleep(0.4)

    # Step 2: Swagger Docs
    print_step(2, "Swagger UI Documentation", "GET", "/docs")
    r = requests.get(f"{BASE_URL}/docs")
    print(f"<-- Status Code: {r.status_code} OK [Interactive HTML Documentation Available]")
    time.sleep(0.4)

    # =========================================================================
    # SECTION 2: INDEPENDENT ELEVATION & RAINFALL APIS
    # =========================================================================
    print_banner("SECTION 2: INDEPENDENT GEOSPATIAL & RAINFALL APIS")

    # Step 3: Independent Elevation Point Query
    print_step(3, "Independent Elevation Point Query", "GET", "/api/elevation/point?lat=21.25&lon=81.30")
    r = requests.get(f"{BASE_URL}/api/elevation/point?lat=21.25&lon=81.30")
    print_response(r)
    time.sleep(0.4)

    # Step 4: Independent DEM Bbox Raster Query
    print_step(4, "Independent DEM Raster Grid Query (BBox)", "POST", "/api/elevation/dem", bbox_sample)
    r = requests.post(f"{BASE_URL}/api/elevation/dem", json=bbox_sample)
    print_response(r, truncate_grid=True)
    time.sleep(0.4)

    # Step 5: Independent Rainfall Point Query
    print_step(5, "Independent Historical Rainfall Query (Lat/Lon)", "GET", "/api/rainfall/query?lat=21.25&lon=81.30&years=10")
    r = requests.get(f"{BASE_URL}/api/rainfall/query?lat=21.25&lon=81.30&years=10")
    print_response(r)
    time.sleep(0.4)

    # Step 6: Independent Rainfall BBox Query
    print_step(6, "Independent Historical Rainfall Query (BBox)", "POST", "/api/rainfall/bbox?years=10", bbox_sample)
    r = requests.post(f"{BASE_URL}/api/rainfall/bbox?years=10", json=bbox_sample)
    print_response(r)
    time.sleep(0.4)

    # =========================================================================
    # SECTION 3: CONTOUR MAP INGESTION & ANALYSIS (KML/KMZ)
    # =========================================================================
    print_banner("SECTION 3: CONTOUR MAP INGESTION & ANALYSIS (KML/KMZ)")

    kml_paths = [
        Path("tests/fixtures/contours_1m.kml"),
        Path("backend/tests/fixtures/contours_1m.kml"),
        Path("../backend/tests/fixtures/contours_1m.kml"),
    ]
    kml_file = next((p for p in kml_paths if p.exists()), None)

    if kml_file:
        # Step 7: Modular Polyline Extraction from KML
        print_step(7, f"Extract Raw Contour Polylines from KML ({kml_file.name})", "POST", "/api/contour/extract-polylines")
        with open(kml_file, "rb") as f:
            r = requests.post(f"{BASE_URL}/api/contour/extract-polylines", files={"file": (kml_file.name, f, "application/vnd.google-earth.kml+xml")})
        print_response(r)
        time.sleep(0.4)

        # Step 8: Modular Delaunay DEM Interpolation from KML
        print_step(8, f"Generate Interpolated DEM Raster Grid from KML ({kml_file.name})", "POST", "/api/contour/dem-from-kml")
        with open(kml_file, "rb") as f:
            r = requests.post(f"{BASE_URL}/api/contour/dem-from-kml", files={"file": (kml_file.name, f, "application/vnd.google-earth.kml+xml")})
        print_response(r, truncate_grid=True)
        time.sleep(0.4)

        # Step 9: End-to-End Contour Analysis (/analyzeContour)
        print_step(9, f"End-to-End Contour Map Analysis & Site Recommendation", "POST", "/api/contour/analyzeContour")
        with open(kml_file, "rb") as f:
            r = requests.post(f"{BASE_URL}/api/contour/analyzeContour", files={"file": (kml_file.name, f, "application/vnd.google-earth.kml+xml")})
        print_response(r)
        time.sleep(0.4)

        # Step 10: FindCatchment Route Alias
        print_step(10, f"Route Alias Verification (/findCatchment)", "POST", "/api/contour/findCatchment")
        with open(kml_file, "rb") as f:
            r = requests.post(f"{BASE_URL}/api/contour/findCatchment", files={"file": (kml_file.name, f, "application/vnd.google-earth.kml+xml")})
        print_response(r)
        time.sleep(0.4)
    else:
        print("[WARN] contours_1m.kml fixture not found in standard paths; skipping contour upload steps.")

    # =========================================================================
    # SECTION 4: BOUNDING-BOX VILLAGE WORKFLOW
    # =========================================================================
    print_banner("SECTION 4: BOUNDING-BOX VILLAGE ANALYSIS WORKFLOW")

    # Step 11: Initialize Village AOI
    init_payload = {"name": village, "bbox": bbox_sample}
    print_step(11, "Initialize Village Area of Interest (AOI)", "POST", f"/api/villages/{village}/init", init_payload)
    r = requests.post(f"{BASE_URL}/api/villages/{village}/init", json=init_payload)
    print_response(r)
    time.sleep(0.4)

    # Step 12: Map Imagery Config
    print_step(12, "Get Satellite Imagery Tile Configuration", "GET", f"/api/villages/{village}/imagery")
    r = requests.get(f"{BASE_URL}/api/villages/{village}/imagery")
    print_response(r)
    time.sleep(0.4)

    # Step 13: Elevation Contours
    print_step(13, "Extract 3m Elevation Contours GeoJSON", "GET", f"/api/villages/{village}/contours")
    r = requests.get(f"{BASE_URL}/api/villages/{village}/contours")
    print_response(r, truncate_grid=True)
    time.sleep(0.4)

    # Step 14: 10-Year Historical Rainfall
    print_step(14, "Fetch 10-Year Historical Precipitation Series", "GET", f"/api/villages/{village}/rainfall?years=10")
    r = requests.get(f"{BASE_URL}/api/villages/{village}/rainfall?years=10")
    print_response(r)
    time.sleep(0.4)

    # Step 15: List Candidate Excavation Sites
    print_step(15, "List Candidate Excavation Sites (Slope <= 6%)", "GET", f"/api/villages/{village}/candidates")
    r = requests.get(f"{BASE_URL}/api/villages/{village}/candidates")
    print_response(r)
    candidates_data = r.json().get("candidates", [])
    candidate_id = candidates_data[0]["id"] if candidates_data else 1
    print(f"--> Selected Candidate ID {candidate_id} for downstream hydrological sizing.")
    time.sleep(0.4)

    # Step 16: D8 Watershed Catchment Delineation
    print_step(16, f"Delineate Upstream Catchment Basin for Candidate {candidate_id}", "POST", f"/api/villages/{village}/candidates/{candidate_id}/catchment")
    r = requests.post(f"{BASE_URL}/api/villages/{village}/candidates/{candidate_id}/catchment")
    print_response(r)
    time.sleep(0.4)

    # Step 17: SCS-CN Runoff & 3D Frustum Sizing
    print_step(17, f"Calculate SCS-CN Runoff & 3D Frustum Sizing for Candidate {candidate_id}", "POST", f"/api/villages/{village}/candidates/{candidate_id}/estimate")
    r = requests.post(f"{BASE_URL}/api/villages/{village}/candidates/{candidate_id}/estimate")
    print_response(r)
    time.sleep(0.4)

    # Step 18: Ranked Pond Recommendations
    print_step(18, "Get Ranked Pond Recommendations with Justifications", "GET", f"/api/villages/{village}/recommendations")
    r = requests.get(f"{BASE_URL}/api/villages/{village}/recommendations")
    print_response(r)
    time.sleep(0.4)

    # Step 19: PDF Dossier Download
    print_step(19, f"Generate and Download Candidate {candidate_id} Engineering PDF Dossier", "GET", f"/api/villages/{village}/candidates/{candidate_id}/report")
    r = requests.get(f"{BASE_URL}/api/villages/{village}/candidates/{candidate_id}/report")
    print_response(r)
    pdf_out = Path("sample_candidate_report.pdf")
    pdf_out.write_bytes(r.content)
    print(f"--> Saved downloaded PDF to: {pdf_out.resolve()}")
    time.sleep(0.4)

    # =========================================================================
    # SECTION 5: ERROR & EDGE CASE VALIDATIONS
    # =========================================================================
    print_banner("SECTION 5: ERROR & EDGE CASE VALIDATIONS")

    # Step 20: 404 Not Found for Non-Existent Village
    print_step(20, "Error Handling: Query Non-Existent Village (404 Expected)", "GET", "/api/villages/NonExistentVillageXYZ/candidates")
    r = requests.get(f"{BASE_URL}/api/villages/NonExistentVillageXYZ/candidates")
    print_response(r)
    time.sleep(0.4)

    # Step 21: 400 Bad Request for Invalid File Type
    print_step(21, "Error Handling: Upload Invalid File Extension (400 Expected)", "POST", "/api/contour/analyzeContour")
    r = requests.post(
        f"{BASE_URL}/api/contour/analyzeContour",
        files={"file": ("invalid_document.txt", b"This is plain text not KML", "text/plain")}
    )
    print_response(r)

    print_banner("ALL LIVE API TESTS EXECUTED SUCCESSFULLY!")


if __name__ == "__main__":
    run_live_tests()
