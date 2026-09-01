import os
import asyncio
import urllib.request
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import villages, catchment, rainfall, estimation, report, contour, elevation


async def _keep_alive_loop(url: str):
    """Background worker that pings the server every 5 minutes to prevent Render free instance spin-down."""
    # Initial sleep before beginning ping cycle
    await asyncio.sleep(60)
    while True:
        try:
            req = urllib.request.Request(f"{url.rstrip('/')}/", headers={"User-Agent": "Render-KeepAlive/1.0"})
            # Run blocking urllib request in thread pool
            await asyncio.to_thread(urllib.request.urlopen, req, timeout=15)
        except Exception:
            pass
        await asyncio.sleep(300)  # Ping every 5 minutes


@asynccontextmanager
async def lifespan(app: FastAPI):
    # RENDER_EXTERNAL_URL is automatically injected by Render.com in production
    external_url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("APP_URL")
    keep_alive_task = None
    if external_url:
        keep_alive_task = asyncio.create_task(_keep_alive_loop(external_url))
    yield
    if keep_alive_task:
        keep_alive_task.cancel()


app = FastAPI(
    title="AI-based Village Pond Planning System",
    description="Backend API for terrain, catchment, rainfall and pond-sizing analysis.",
    version="0.1.0",
    lifespan=lifespan,
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
app.include_router(elevation.router)
app.include_router(estimation.router)
app.include_router(report.router)
app.include_router(contour.router)


@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {"status": "ok", "docs": "/docs"}