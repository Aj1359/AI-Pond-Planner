import os
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\ranik\.gemini\antigravity-ide\brain\fa7c1ba0-2d70-48dd-9180-7bd32277a7f0"
KML_PATH = r"E:\AI pond\pond_planner\backend\tests\fixtures\contours_1m.kml"

def run():
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1600, 'height': 900})
        page = context.new_page()

        print("Navigating to http://localhost:3000/ui/...")
        page.goto("http://localhost:3000/ui/", wait_until="networkidle")
        page.wait_for_selector("#stateFilter")

        # ----------------------------------------------------------------------
        # SCENARIO 1: West Bengal -> Kolkata -> K = 4
        # ----------------------------------------------------------------------
        print("Selecting West Bengal from stateFilter...")
        page.select_option("#stateFilter", value="West Bengal")
        page.wait_for_timeout(3500)

        print("Searching Kolkata...")
        page.fill("#locSearch", "Kolkata")
        page.wait_for_timeout(1500)
        page.click("#locDropdown .dd-item:first-child")
        page.wait_for_timeout(4000)

        # Wait for boundary to enable btnAnalyze2 or draw shape
        page.wait_for_selector("#btnAnalyze2:not([disabled])", timeout=15000)

        print("Setting K = 4 Sites...")
        page.select_option("#numSites", value="4")
        page.wait_for_timeout(500)

        print("Executing siting analysis...")
        page.click("#btnAnalyze2")
        page.wait_for_timeout(8000)

        img1_path = os.path.join(ARTIFACT_DIR, "shot1_kolkata_k4_analysis.png")
        page.screenshot(path=img1_path)
        print(f"Captured Screenshot 1: {img1_path}")

        print("Opening Site Details Modal Popup for Site 1...")
        page.evaluate("document.getElementById('siteModal').classList.add('open')")
        page.wait_for_timeout(1000)

        img2_path = os.path.join(ARTIFACT_DIR, "shot2_site_details_modal.png")
        page.screenshot(path=img2_path)
        print(f"Captured Screenshot 2: {img2_path}")

        print("Closing Modal...")
        page.evaluate("document.getElementById('siteModal').classList.remove('open')")
        page.wait_for_timeout(500)

        # ----------------------------------------------------------------------
        # SCENARIO 2: Upload Contour Map (contours_1m.kml) -> K = 3
        # ----------------------------------------------------------------------
        print("Switching back to draw tab & Contour Upload mode...")
        page.evaluate("switchTab('draw')")
        page.wait_for_timeout(1000)
        page.click("#btnModeContour")
        page.wait_for_timeout(1500)

        print("Uploading contours_1m.kml...")
        page.set_input_files("#contourFileInput", KML_PATH)
        page.wait_for_timeout(4000)

        print("Setting K = 3 Sites...")
        page.select_option("#numSites", value="3")
        page.wait_for_timeout(500)

        page.wait_for_selector("#btnAnalyze2:not([disabled])", timeout=15000)
        print("Executing Contour Siting Analysis...")
        page.click("#btnAnalyze2")
        page.wait_for_timeout(8000)

        img3_path = os.path.join(ARTIFACT_DIR, "shot3_contour_k3_analysis.png")
        page.screenshot(path=img3_path)
        print(f"Captured Screenshot 3: {img3_path}")

        print("Opening Site Details Modal Popup for Contour Siting...")
        page.evaluate("document.getElementById('siteModal').classList.add('open')")
        page.wait_for_timeout(1000)

        img4_path = os.path.join(ARTIFACT_DIR, "shot4_contour_site_details.png")
        page.screenshot(path=img4_path)
        print(f"Captured Screenshot 4: {img4_path}")

        browser.close()
        print("All 4 screenshots captured successfully!")

if __name__ == "__main__":
    run()
