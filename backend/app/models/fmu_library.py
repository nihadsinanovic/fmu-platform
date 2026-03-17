from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import Base, TimestampMixin, UUIDMixin


class FMULibrary(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "fmu_library"

    type_name = Column(String(100), unique=True, nullable=False)
    version = Column(String(20), nullable=False)
    fmu_path = Column(String(500), nullable=False)
    manifest = Column(JSONB, nullable=False)
