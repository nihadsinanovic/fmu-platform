import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.job import SimulationJob
from app.schemas.job import JobStatusResponse

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


async def _get_queue_position(db: AsyncSession, job: SimulationJob) -> int | None:
    if job.status != "queued":
        return None
    result = await db.execute(
        select(SimulationJob)
        .where(SimulationJob.status == "queued")
        .order_by(SimulationJob.queued_at.asc())
    )
    queued_jobs = result.scalars().all()
    for i, queued_job in enumerate(queued_jobs):
        if queued_job.id == job.id:
            return i + 1
    return None


@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    job = await db.get(SimulationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    position = await _get_queue_position(db, job)
    response = JobStatusResponse.model_validate(job)
    response.position = position
    if position is not None:
        response.estimated_wait_minutes = position * 4.0
    return response
