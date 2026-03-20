from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes import fmu_library, jobs, projects, websocket


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


@app.get("/api/health")
async def health():
    return {"status": "ok"}
