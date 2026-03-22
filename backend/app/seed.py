"""Seed the database with the initial admin user and FMU library entries.

Run with:  python -m app.seed
"""
import asyncio
import json
import logging
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.core.security import hash_password
from app.database import async_session_maker, engine
from app.models.base import Base
from app.models.fmu_library import FMULibrary
from app.models.user import User

log = logging.getLogger(__name__)

SEED_USERNAME = "admin"
SEED_PASSWORD = "MacBook08"

# All atomic FMU types that should be in the library
FMU_TYPES = [
    "central_heatpump",
    "ambient_loop_segment",
    "loop_tee",
    "apartment_heatpump",
    "apartment_thermal_zone",
    "weather_source",
]


async def seed_fmu_library(session) -> None:
    """Register FMU library entries from on-disk manifests."""
    library_root = settings.FMU_LIBRARY_PATH

    for fmu_type in FMU_TYPES:
        # Check if already registered
        result = await session.execute(
            select(FMULibrary).where(FMULibrary.type_name == fmu_type)
        )
        if result.scalar_one_or_none() is not None:
            log.info("FMU '%s' already registered — skipping.", fmu_type)
            continue

        # Find manifest on disk
        manifest_path = library_root / fmu_type / "v1.0.0" / "manifest.json"
        if not manifest_path.exists():
            log.warning("Manifest not found for '%s' at %s — skipping.", fmu_type, manifest_path)
            continue

        with open(manifest_path) as f:
            manifest = json.load(f)

        version = manifest.get("version", "1.0.0")
        fmu_file = library_root / fmu_type / f"v{version}" / f"{fmu_type}.fmu"

        record = FMULibrary(
            type_name=fmu_type,
            version=version,
            fmu_path=str(fmu_file),
            manifest=manifest,
        )
        session.add(record)
        log.info("Seeded FMU '%s' v%s.", fmu_type, version)

    await session.commit()


async def seed() -> None:
    try:
        # Ensure tables exist (creates them if missing — no Alembic needed)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with async_session_maker() as session:
            # Seed admin user
            result = await session.execute(select(User).where(User.username == SEED_USERNAME))
            if result.scalar_one_or_none() is not None:
                log.info("User '%s' already exists — skipping seed.", SEED_USERNAME)
            else:
                user = User(username=SEED_USERNAME, hashed_password=hash_password(SEED_PASSWORD), is_admin=True)
                session.add(user)
                await session.commit()
                log.info("Seeded user '%s'.", SEED_USERNAME)

            # Seed FMU library
            await seed_fmu_library(session)
    except Exception:
        log.exception("Could not complete database seed.")


if __name__ == "__main__":
    asyncio.run(seed())
