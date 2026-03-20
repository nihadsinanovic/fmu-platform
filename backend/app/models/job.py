from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, UUIDMixin


class SimulationJob(Base, UUIDMixin):
    __tablename__ = "simulation_jobs"

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    status = Column(String(20), nullable=False, default="queued")
    topology_hash = Column(String(64), nullable=True)
    ssp_path = Column(String(500), nullable=True)
    result_path = Column(String(500), nullable=True)
    queued_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    project = relationship("Project", back_populates="jobs", foreign_keys=[project_id])

    __table_args__ = (
        {"comment": "Tracks composition and simulation jobs"},
    )
