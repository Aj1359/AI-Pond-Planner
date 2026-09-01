# AI-based Village Pond Planning & Watershed Analysis System

An intelligent geospatial and hydrological planning system designed to identify optimal earthen pond excavation locations, delineate contributing catchment basins, estimate harvestable monsoon runoff, and calculate optimal 3D pond dimensions.

---

## 🌟 Key Capabilities

* **Dual Operational Workflows**:
  * **Bounding-Box AOI Flow**: Automated multi-step terrain analysis for any designated geographic bounding box.
  * **Upload-Driven Contour Analysis**: Single-step upload (`.kml` / `.kmz`) extracting contour polylines, interpolating DEMs, and delineating watersheds.
* **Hydrological Engineering Mathematics**:
  * **USDA SCS Curve Number (SCS-CN)** & **Rational Method** runoff volume calculations.
  * **3D Inverted Trapezoidal Frustum** pond geometry with 1.5:1 side slope stability and 0.5m freeboard.
  * **D8 Steepest Descent Routing** & reverse breadth-first search (BFS) watershed delineation.
* **Persistent Supabase Storage**: PostgreSQL database with repository pattern keeping queries isolated from business logic.
* **Automated PDF Dossier Generator**: One-click engineering summary report downloads for decision-makers.

---

## 📐 Scientific & Mathematical Formulations

### 1. 3D Inverted Trapezoidal Frustum Pond Geometry
Excavated earthen ponds require stable side slopes ($z:1$, horizontal:vertical, standard $1.5:1$) to prevent bank collapse:

$$V = \frac{d}{3} \cdot \left( A_{\text{top}} + A_{\text{bottom}} + \sqrt{A_{\text{top}} \cdot A_{\text{bottom}}} \right)$$

* Top Dimensions: $W_{\text{top}} = \sqrt{A_{\text{top}} / r}$, $L_{\text{top}} = W_{\text{top}} \cdot r$ (Aspect Ratio $r = 1.5$)
* Bottom Dimensions: $L_{\text{bottom}} = L_{\text{top}} - 2zd$, $W_{\text{bottom}} = W_{\text{top}} - 2zd$
* Freeboard: Adds $+0.5\text{m}$ safety depth above maximum water retention.

### 2. USDA SCS Curve Number Runoff Modeling
Accounts for soil classification, vegetation, and initial abstraction:

$$S = \frac{25400}{CN} - 254 \quad (\text{Potential Max Retention in mm})$$

$$I_a = 0.2 \cdot S \quad (\text{Initial Abstraction: Canopy Interception \& Surface Depression Storage})$$

$$Q_{\text{direct}} = \frac{(P - I_a)^2}{P - I_a + S} \quad \text{for } P > I_a$$

$$\text{Harvestable Runoff } Q_{\text{net}} = Q_{\text{effective}} \times A_{\text{catchment}} \times (1 - \text{Loss Factor})$$

### 3. Terrain Slope & Hydrological Flow Routing
* **Central Difference Slope**:
  $$\text{Slope (\%)} = \tan\left(\sqrt{\left(\frac{\partial z}{\partial x}\right)^2 + \left(\frac{\partial z}{\partial y}\right)^2}\right) \times 100$$
* **D8 Flow Direction**: Identifies the steepest downhill descent among 8 neighbors.
* **Catchment Delineation**: Upstream recursive BFS from the candidate site (pour point).

### 4. Multi-Criteria Candidate Site Ranking
$$\text{Rank Score} = (0.50 \times \text{Normalized Storage}) + (0.30 \times \text{Suitability Score}) + (0.20 \times \text{Capture Efficiency})$$

---

## 📁 Project Structure

```
pond_planner/
├── .gitignore
├── README.md
└── backend/
    ├── .env.example
    ├── requirements.txt
    ├── test_api.py                        # Automated E2E verification test suite
    ├── app/
    │   ├── __init__.py
    │   ├── db.py                          # Supabase client setup from environment
    │   ├── main.py                        # FastAPI application entry point & CORS
    │   ├── repository.py                  # Postgres CRUD persistence layer
    │   ├── schemas.py                     # Pydantic request/response schemas
    │   ├── routers/
    │   │   ├── catchment.py               # Watershed delineation endpoint
    │   │   ├── contour.py                 # KML/KMZ upload analysis endpoint
    │   │   ├── estimation.py              # Runoff volume & pond sizing endpoint
    │   │   ├── rainfall.py                # Precipitation data endpoint
    │   │   ├── report.py                  # PDF dossier generation endpoint
    │   │   └── villages.py                # AOI initialization & contour extraction
    │   └── services/
    │       ├── contour_ingest.py          # KML parser & Delaunay DEM interpolation
    │       ├── elevation.py               # Open-Elevation & synthetic DEM generator
    │       ├── rainfall.py                # Open-Meteo & NASA POWER rainfall service
    │       ├── report.py                  # Matplotlib PDF report builder
    │       ├── runoff.py                  # SCS-CN & Frustum pond sizing engine
    │       ├── sites.py                   # Slope & depression candidate selector
    │       └── terrain.py                 # D8 flow routing & watershed algorithms
    ├── supabase/
    │   └── schemas.sql                    # SQL DDL table definitions
    └── tests/
        ├── test_contour_analysis.py       # Unit tests for contour ingest
        ├── test_db_mocking_regression.py  # Repository layer mocking regression test
        └── fixtures/
            └── contours_1m.kml            # Sample 1-meter contour map fixture
```

---

## 🌐 API Reference Table

| Method | Endpoint | Tag | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Core | Health check & API documentation link |
| `GET` | `/docs` | Core | Interactive Swagger OpenAPI documentation |
| `GET` | `/api/elevation/point` | Elevation | Independent elevation query by lat/lon coordinates |
| `POST` | `/api/elevation/dem` | Elevation | Independent 100x100 DEM raster grid query for any bounding box |
| `GET` | `/api/rainfall/query` | Rainfall | Independent 10-year monthly precipitation query by lat/lon |
| `POST` | `/api/rainfall/bbox` | Rainfall | Independent historical rainfall query for bounding box center |
| `POST` | `/api/contour/extract-polylines` | Contour | Extracts contour line count, min/max elevations, and interval |
| `POST` | `/api/contour/dem-from-kml` | Contour | Generates interpolated Delaunay DEM grid directly from KML/KMZ |
| `POST` | `/api/contour/analyzeContour` | Contour | Ingests `.kml` / `.kmz` contour map and performs end-to-end siting |
| `POST` | `/api/contour/findCatchment` | Contour | Alias for `/api/contour/analyzeContour` |
| `POST` | `/api/villages/{village}/init` | Villages | Initializes AOI, fetches DEM, calculates slopes, and selects candidate sites |
| `GET` | `/api/villages/{village}/imagery` | Villages | Returns Esri World Imagery map tile configuration |
| `GET` | `/api/villages/{village}/contours` | Villages | Extracts 3-meter interval elevation contours as GeoJSON |
| `GET` | `/api/villages/{village}/rainfall` | Villages | Retrieves 10-year monthly precipitation averages for village |
| `GET` | `/api/villages/{village}/candidates` | Villages | Lists candidate excavation sites with slopes and suitability |
| `POST` | `/api/villages/{village}/candidates/{id}/catchment` | Catchment | Delineates contributing watershed basin using D8 flow routing |
| `POST` | `/api/villages/{village}/candidates/{id}/estimate` | Estimation | Calculates harvestable runoff and recommends 3D trapezoidal pond sizing |
| `GET` | `/api/villages/{village}/recommendations` | Estimation | Returns composite-ranked candidate site recommendations |
| `GET` | `/api/villages/{village}/candidates/{id}/report` | Report | Downloads comprehensive candidate engineering PDF dossier |

---

## 🚀 Quickstart Guide

### 1. Start the Backend Server

```powershell
cd backend
.\venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```
* **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)

### 2. Run Complete Live API Test Suite (All 21 Steps)

```powershell
.\venv\Scripts\python test_all_apis_live.py
```

### 3. Run Pytest Suite (All 29 Unit Tests)

```powershell
.\venv\Scripts\python -m pytest tests/ -v
```
