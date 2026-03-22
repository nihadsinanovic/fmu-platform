"""Admin-only API endpoints for the admin panel.

These endpoints expose data aggregations not available through the standard
user-facing API (e.g. listing all jobs across all projects, reading raw
Parquet result files for the chart viewer).
"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin
from app.core.security import hash_password
from app.database import get_db
from app.models.job import SimulationJob
from app.models.project import Project
from app.models.user import User
from app.schemas.auth import CreateUserRequest, UpdateUserRequest, UserResponse

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/jobs")
async def list_all_jobs(db: AsyncSession = Depends(get_db)):
    """Return every simulation job with its parent project name."""
    result = await db.execute(
        select(SimulationJob, Project.name.label("project_name"))
        .join(Project, SimulationJob.project_id == Project.id)
        .order_by(SimulationJob.queued_at.desc().nullslast())
    )
    rows = result.all()
    return [
        {
            "id": str(row.SimulationJob.id),
            "project_id": str(row.SimulationJob.project_id),
            "project_name": row.project_name,
            "status": row.SimulationJob.status,
            "queued_at": (
                row.SimulationJob.queued_at.isoformat()
                if row.SimulationJob.queued_at
                else None
            ),
            "started_at": (
                row.SimulationJob.started_at.isoformat()
                if row.SimulationJob.started_at
                else None
            ),
            "completed_at": (
                row.SimulationJob.completed_at.isoformat()
                if row.SimulationJob.completed_at
                else None
            ),
            "error_message": row.SimulationJob.error_message,
            "result_path": row.SimulationJob.result_path,
        }
        for row in rows
    ]


@router.get("/results/{job_id}")
async def get_result_data(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Return time-series simulation data for the Results Viewer.

    Reads the Parquet file stored at ``job.result_path`` and returns every
    column as a list of floats under the ``data`` key.  The ``variables`` list
    preserves column order so the frontend can display them consistently.
    """
    job = await db.get(SimulationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=400, detail=f"Job status is '{job.status}', not 'completed'")
    if not job.result_path:
        raise HTTPException(status_code=404, detail="No result data available for this job")

    result_path = Path(job.result_path)
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="Result file not found on disk")

    try:
        import pyarrow.parquet as pq  # noqa: PLC0415 — deferred to avoid startup cost

        table = pq.read_table(str(result_path))
        columns = table.column_names
        return {
            "job_id": str(job_id),
            "variables": columns,
            "data": {col: table.column(col).to_pylist() for col in columns},
        }
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="pyarrow is not installed") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read result file: {exc}") from exc


# ── User Management (admin-only) ─────────────────────────────────────────────


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.created_at))
    users = result.scalars().all()
    return [UserResponse(id=str(u.id), username=u.username, is_admin=u.is_admin) for u in users]


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    body: CreateUserRequest,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    username = body.username.strip().lower()
    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty")
    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Username already exists")
    user = User(username=username, hashed_password=hash_password(body.password), is_admin=body.is_admin)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse(id=str(user.id), username=user.username, is_admin=user.is_admin)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UpdateUserRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if body.password is not None:
        user.hashed_password = hash_password(body.password)
    if body.is_admin is not None:
        # Prevent admin from removing their own admin status
        if user.id == admin.id and not body.is_admin:
            raise HTTPException(status_code=400, detail="Cannot remove your own admin status")
        user.is_admin = body.is_admin
    await db.commit()
    await db.refresh(user)
    return UserResponse(id=str(user.id), username=user.username, is_admin=user.is_admin)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()
