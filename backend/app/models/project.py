from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Project(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "projects"

    name = Column(String(255), nullable=False)
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    topology = Column(JSONB, nullable=False, default=dict)
    ssp_path = Column(String(500), nullable=True)

    jobs = relationship("SimulationJob", back_populates="project", lazy="selectin")
