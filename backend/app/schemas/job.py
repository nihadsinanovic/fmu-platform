import uuid
from datetime import datetime

from pydantic import BaseModel


class JobCreate(BaseModel):
    project_id: uuid.UUID


class JobStatusResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    queued_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    position: int | None = None
    estimated_wait_minutes: float | None = None


class JobProgressMessage(BaseModel):
    job_id: str
    status: str
    progress: float | None = None
    message: str = ""
