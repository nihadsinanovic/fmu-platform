import json
from pathlib import Path
from typing import Annotated

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings


def _parse_cors(v: str | list[str]) -> list[str]:
    if isinstance(v, list):
        return v
    v = v.strip()
    if not v:
        return []
    if v.startswith("["):
        return json.loads(v)
    return [origin.strip() for origin in v.split(",") if origin.strip()]


CorsOrigins = Annotated[list[str], BeforeValidator(_parse_cors)]


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Database
    DATABASE_URL: str = "postgresql://user:pass@localhost/fmu_platform"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # License management
    LICENSE_POOL_SIZE: int = 3
    AMESIM_LICENSE_SERVER: str = ""

    # File paths
    FMU_LIBRARY_PATH: Path = Path("/opt/fmu-platform/fmu-library")
    PROJECTS_PATH: Path = Path("/opt/fmu-platform/projects")
    TEMP_PATH: Path = Path("/opt/fmu-platform/temp")

    # Auth
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"

    # CORS — accepts JSON array or comma-separated string
    CORS_ORIGINS: CorsOrigins = ["http://localhost:5173", "http://localhost:3000"]


settings = Settings()
