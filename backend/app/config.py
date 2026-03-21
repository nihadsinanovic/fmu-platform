import json
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Database (async for FastAPI, sync for Alembic)
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost/fmu_platform"
    DATABASE_URL_SYNC: str = ""

    @property
    def sync_database_url(self) -> str:
        """Return sync URL for Alembic. Falls back to converting async URL."""
        if self.DATABASE_URL_SYNC:
            return self.DATABASE_URL_SYNC
        return self.DATABASE_URL.replace("+asyncpg", "")

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # License management
    LICENSE_POOL_SIZE: int = 3
    AMESIM_LICENSE_SERVER: str = ""  # e.g. "29000@16.16.200.137"

    # File paths
    FMU_LIBRARY_PATH: Path = Path("/opt/fmu-platform/fmu-library")
    PROJECTS_PATH: Path = Path("/opt/fmu-platform/projects")
    TEMP_PATH: Path = Path("/opt/fmu-platform/temp")

    # Auth
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"

    # CORS — stored as string, parsed via property
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        v = self.CORS_ORIGINS.strip()
        if not v:
            return []
        if v.startswith("["):
            return json.loads(v)
        return [origin.strip() for origin in v.split(",") if origin.strip()]


settings = Settings()
