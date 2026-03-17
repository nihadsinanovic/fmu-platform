"""AMESim license acquisition and release logic."""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Generator

from app.config import settings

logger = logging.getLogger(__name__)


class LicenseError(Exception):
    pass


class LicenseManager:
    """Manage AMESim license pool.

    Since Celery worker_concurrency is set to LICENSE_POOL_SIZE,
    each worker process implicitly holds one license slot.
    This manager provides additional safety via a semaphore and
    handles license server communication if needed.
    """

    def __init__(self, pool_size: int | None = None):
        self.pool_size = pool_size or settings.LICENSE_POOL_SIZE
        self._semaphore = threading.Semaphore(self.pool_size)
        self._license_server = settings.AMESIM_LICENSE_SERVER

    @contextmanager
    def acquire(self, timeout: float = 300) -> Generator[None, None, None]:
        """Acquire a license slot. Blocks until available or timeout."""
        acquired = self._semaphore.acquire(timeout=timeout)
        if not acquired:
            raise LicenseError(
                f"Could not acquire license within {timeout}s. "
                f"All {self.pool_size} licenses in use."
            )
        try:
            logger.info("License acquired")
            yield
        finally:
            self._semaphore.release()
            logger.info("License released")

    @property
    def available(self) -> int:
        # Semaphore doesn't expose count directly; this is approximate
        return self._semaphore._value  # type: ignore[attr-defined]


# Global instance
license_manager = LicenseManager()
