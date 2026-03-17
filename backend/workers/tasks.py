"""Celery tasks for composition and simulation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from workers.celery_app import celery_app
from workers.license_manager import LicenseError, license_manager

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, name="workers.compose_and_simulate")
def compose_and_simulate(self, project_id: str, job_id: str, topology: dict) -> dict:
    """Compose FMUs from topology and run simulation.

    Each invocation consumes one AMESim license.
    """
    from app.config import settings
    from engine.composition import CompositionEngine
    from simulation.results import save_results
    from simulation.runner import SimulationRunner

    try:
        with license_manager.acquire():
            # Update job status to running
            _update_job_status(job_id, "running", started_at=datetime.now(timezone.utc))

            # Compose
            project_dir = settings.PROJECTS_PATH / project_id
            ssp_path = project_dir / "composed_system.ssp"

            engine = CompositionEngine(fmu_library_path=settings.FMU_LIBRARY_PATH)
            composed = engine.compose(topology, ssp_path)

            if not composed.validation.valid:
                error_msg = "; ".join(composed.validation.errors)
                _update_job_status(job_id, "failed", error_message=error_msg)
                return {"status": "failed", "error": error_msg}

            # Simulate
            sim_config = topology.get("simulation", {})
            work_dir = settings.TEMP_PATH / f"job_{job_id}"
            runner = SimulationRunner()
            result = runner.run(
                ssp_path=ssp_path,
                work_dir=work_dir,
                start_time=sim_config.get("start_time", 0),
                end_time=sim_config.get("end_time", 31536000),
                step_size=sim_config.get("step_size", 900),
                output_interval=sim_config.get("output_interval", 3600),
            )

            # Save results
            result_dir = project_dir / "results" / f"run_{job_id}"
            save_results(result, result_dir)

            _update_job_status(
                job_id, "completed",
                completed_at=datetime.now(timezone.utc),
                result_path=str(result_dir),
                ssp_path=str(ssp_path),
            )

            return {"status": "completed", "project_id": project_id, "job_id": job_id}

    except LicenseError:
        logger.warning("License unavailable, retrying in 60s")
        raise self.retry(countdown=60)
    except Exception as e:
        logger.exception("Task failed")
        _update_job_status(job_id, "failed", error_message=str(e))
        return {"status": "failed", "error": str(e)}


def _update_job_status(job_id: str, status: str, **kwargs) -> None:
    """Update job status in database (sync, for use in Celery tasks)."""
    try:
        from sqlalchemy import create_engine, text
        from app.config import settings

        engine = create_engine(settings.DATABASE_URL)
        sets = [f"status = :status"]
        params = {"job_id": job_id, "status": status}

        for key, value in kwargs.items():
            sets.append(f"{key} = :{key}")
            params[key] = value

        query = text(f"UPDATE simulation_jobs SET {', '.join(sets)} WHERE id = :job_id")
        with engine.connect() as conn:
            conn.execute(query, params)
            conn.commit()
    except Exception:
        logger.exception(f"Failed to update job {job_id} status to {status}")
