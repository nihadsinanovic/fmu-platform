import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class ProjectResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    topology: dict
    ssp_path: str | None = None
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime
