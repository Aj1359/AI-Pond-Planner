from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import villages, catchment, rainfall, estimation, report

app = FastAPI(
    title="AI-based Village Pond Planning System",
    description="Backend API for terrain, catchment, rainfall and pond-sizing analysis.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(KeyError)
async def key_error_handler(request: Request, exc: KeyError):
    """repository.py raises KeyError for 'not found' lookups (unknown
    village, unknown candidate). Without this handler FastAPI would return
    a raw 500 with a stack trace instead of a clean, client-facing 404 —
    important for a real API consumers (e.g. Postman, the frontend) can
    build reliable error handling against."""
    message = str(exc).strip('"')
    return JSONResponse(status_code=404, content={"detail": message})


app.include_router(villages.router)
app.include_router(catchment.router)
app.include_router(rainfall.router)
app.include_router(estimation.router)
app.include_router(report.router)


@app.get("/")
def root():
    return {"status": "ok", "docs": "/docs"}