from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routes import admin, fmu_library, jobs, projects, websocket

# Built admin panel is copied here during Docker build (see Dockerfile).
# When running locally without a build, this path won't exist and the
# /admin routes simply return 404.
ADMIN_DIST = Path("/app/admin-dist")
_ADMIN_ASSETS = ADMIN_DIST / "assets"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure storage directories exist
    settings.PROJECTS_PATH.mkdir(parents=True, exist_ok=True)
    settings.TEMP_PATH.mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown: nothing to clean up


app = FastAPI(
    title="FMU Composition & Simulation Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(jobs.router)
app.include_router(fmu_library.router)
app.include_router(websocket.router)
app.include_router(admin.router)

# ── Static admin panel ────────────────────────────────────────────────────────
# Serve bundled JS/CSS assets efficiently via StaticFiles.
# All other /admin/* paths fall through to the SPA catch-all below.

if _ADMIN_ASSETS.exists():
    app.mount(
        "/admin/assets",
        StaticFiles(directory=str(_ADMIN_ASSETS)),
        name="admin-assets",
    )


@app.get("/admin", include_in_schema=False)
@app.get("/admin/{path:path}", include_in_schema=False)
async def serve_admin(path: str = "") -> FileResponse:
    """Serve the admin SPA — return index.html for all /admin/* paths
    so React Router can handle client-side navigation.
    """
    if not ADMIN_DIST.exists():
        raise HTTPException(
            status_code=503,
            detail="Admin panel not built. Run 'npm run build' inside admin/.",
        )

    # Allow direct asset requests to fall through when StaticFiles is not
    # mounted (i.e. local dev without a build).
    file_path = ADMIN_DIST / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))

    return FileResponse(str(ADMIN_DIST / "index.html"))


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok"}
