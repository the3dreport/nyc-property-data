from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import property as property_router
from .routers import search as search_router

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "PropertyShark-style NYC property intelligence prototype. "
        "Public product with future accounts / paid tier (see auth_stub)."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search_router.router, prefix=settings.api_prefix)
app.include_router(property_router.router, prefix=settings.api_prefix)


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "feature_auth": settings.feature_auth,
        "feature_paid_tier": settings.feature_paid_tier,
    }


@app.get("/")
async def landing():
    return FileResponse(FRONTEND / "index.html")


@app.get("/property")
async def property_page():
    return FileResponse(FRONTEND / "property.html")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
