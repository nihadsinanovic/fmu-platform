"""Seed the database with the initial admin user.

Run with:  python -m app.seed
"""
import asyncio
import logging

from sqlalchemy import select

from app.core.security import hash_password
from app.database import async_session_maker, engine
from app.models.base import Base
from app.models.user import User

log = logging.getLogger(__name__)

SEED_USERNAME = "admin"
SEED_PASSWORD = "MacBook08"


async def seed() -> None:
    try:
        # Ensure tables exist (creates them if missing — no Alembic needed)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with async_session_maker() as session:
            result = await session.execute(select(User).where(User.username == SEED_USERNAME))
            if result.scalar_one_or_none() is not None:
                log.info("User '%s' already exists — skipping seed.", SEED_USERNAME)
                return

            user = User(username=SEED_USERNAME, hashed_password=hash_password(SEED_PASSWORD))
            session.add(user)
            await session.commit()
            log.info("Seeded user '%s'.", SEED_USERNAME)
    except Exception:
        log.exception("Could not seed admin user.")


if __name__ == "__main__":
    asyncio.run(seed())
