from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import villages, catchment, rainfall, estimation, report, contour

app = FastAPI(
    title="AI-based Village Pond Planning System",
    description="Backend API for terrain, catchment, rainfall and pond-sizing analysis.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(KeyError)
async def key_error_handler(request: Request, exc: KeyError):
    message = str(exc).strip('"')
    return JSONResponse(status_code=404, content={"detail": message})


app.include_router(villages.router)
app.include_router(catchment.router)
app.include_router(rainfall.router)
app.include_router(estimation.router)
app.include_router(report.router)
app.include_router(contour.router)


@app.get("/")
def root():
    return {"status": "ok", "docs": "/docs"}