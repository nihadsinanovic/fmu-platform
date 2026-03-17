import hashlib
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.job import SimulationJob
from app.models.project import Project
from app.schemas.job import JobStatusResponse
from app.schemas.project import ProjectCreate, ProjectListResponse, ProjectResponse
from app.schemas.topology import BuildingTopology

router = APIRouter(prefix="/api/projects", tags=["projects"])

# Placeholder owner_id until auth is implemented
PLACEHOLDER_OWNER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = Project(name=body.name, owner_id=PLACEHOLDER_OWNER_ID, topology={})
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectListResponse])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return result.scalars().all()


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}/topology", response_model=ProjectResponse)
async def update_topology(
    project_id: uuid.UUID,
    topology: BuildingTopology,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project.topology = topology.model_dump()
    await db.flush()
    await db.refresh(project)
    return project


@router.post("/{project_id}/compose", response_model=JobStatusResponse)
async def compose_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.topology:
        raise HTTPException(status_code=400, detail="Project has no topology defined")

    topology_hash = hashlib.sha256(
        json.dumps(project.topology, sort_keys=True).encode()
    ).hexdigest()

    job = SimulationJob(
        project_id=project_id,
        status="queued",
        topology_hash=topology_hash,
        queued_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    # TODO: Dispatch Celery task once workers are connected
    # from workers.tasks import compose_and_simulate
    # compose_and_simulate.delay(str(project_id), str(job.id), project.topology)

    return JobStatusResponse.model_validate(job)


@router.post("/{project_id}/simulate", response_model=JobStatusResponse)
async def simulate_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.ssp_path:
        raise HTTPException(status_code=400, detail="Project has not been composed yet")

    job = SimulationJob(
        project_id=project_id,
        status="queued",
        ssp_path=project.ssp_path,
        queued_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    return JobStatusResponse.model_validate(job)


@router.get("/{project_id}/results")
async def get_results(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(SimulationJob)
        .where(SimulationJob.project_id == project_id, SimulationJob.status == "completed")
        .order_by(SimulationJob.completed_at.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    if not job or not job.result_path:
        raise HTTPException(status_code=404, detail="No completed simulation results found")

    return {
        "job_id": str(job.id),
        "result_path": job.result_path,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/{project_id}/ssp")
async def download_ssp(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.ssp_path:
        raise HTTPException(status_code=404, detail="SSP package not available")

    from fastapi.responses import FileResponse

    return FileResponse(
        project.ssp_path,
        media_type="application/zip",
        filename=f"{project.name}.ssp",
    )
