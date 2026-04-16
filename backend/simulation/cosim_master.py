"""Co-simulation master for stacked apartment simulations.

Orchestrates a pool of subprocess workers (one apartment per worker) using
a Jacobi-style macro-step loop:

1. At each macro-step, every worker advances its FMU from ``t`` to ``t+h``
   using the *previous* macro-step's room temperatures as its floor/ceiling
   boundary inputs.
2. The master fans the ``step`` commands out to all workers in parallel,
   then fans the ``room_temp`` outputs back in.
3. Those outputs become the boundary inputs for the next macro-step.

Stage 1 constraints (until Martti re-exports the FMU):

* One apartment per worker (``canBeInstantiatedOnlyOncePerProcess="true"``).
* Constant supply temperature — the hydraulic loop lives in the future
  main-process path, not here.
* Fixed ground / roof boundaries given per spec.
"""

from __future__ import annotations

import multiprocessing as mp
import time
from dataclasses import dataclass, field
from typing import Any

# Resolved ports on the stackable_apartment FMU (confirmed from the FMU's
# modelDescription.xml — see the session transcript).
FLOOR_INPUT = "amesim_interface.floor_temp"
ROOF_INPUT = "amesim_interface.roof_temp"
SUPPLY_INPUT = "amesim_interface.supply"
ROOM_OUTPUT = "amesim_interface.room_temp"


@dataclass
class ApartmentSpec:
    """One apartment slot in the vertical stack.

    ``floor_temp_source`` and ``roof_temp_source`` are apartment ids of the
    neighbour below / above. ``None`` means that boundary is a fixed
    environmental condition (``ground_temp`` / ``sky_temp``).
    """

    id: str
    floor_temp_source: str | None = None
    roof_temp_source: str | None = None
    supply_temp: float = 35.0     # degC (presumed — unit not declared in FMU)
    ground_temp: float = 10.0     # degC — used when no apartment below
    sky_temp: float = 5.0         # degC — used when no apartment above
    initial_room_temp: float = 20.0


@dataclass
class _Worker:
    """Master-side handle to one subprocess worker."""

    apt_id: str
    process: mp.Process
    parent_conn: Any  # multiprocessing.connection.Connection
    ready: bool = False
    last_room_temp: float = 20.0


class CoSimMaster:
    """Spawn ``len(specs)`` subprocess workers and drive them in lockstep."""

    def __init__(
        self,
        specs: list[ApartmentSpec],
        fmu_type: str = "stackable_apartment",
        macro_step_s: float = 60.0,
        worker_init_timeout_s: float = 180.0,
        step_timeout_s: float = 600.0,
    ) -> None:
        self.specs = specs
        self.fmu_type = fmu_type
        self.macro_step_s = macro_step_s
        self.worker_init_timeout_s = worker_init_timeout_s
        self.step_timeout_s = step_timeout_s
        self.workers: dict[str, _Worker] = {}

    # ── lifecycle ────────────────────────────────────────────────────────

    def __enter__(self) -> "CoSimMaster":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown()

    def start(self) -> None:
        """Spawn workers in parallel and wait for all to become ready."""
        # `spawn` gives us fresh Python interpreters so PyFMI / AMESim globals
        # don't bleed over from the master. `force=True` in case the caller
        # (or pytest, or Celery) already set a method.
        try:
            mp.set_start_method("spawn", force=True)
        except RuntimeError:
            pass  # already set to something compatible

        # Import here so the master never imports pyfmi itself.
        from simulation.subprocess_worker import worker_main

        for spec in self.specs:
            parent_conn, child_conn = mp.Pipe(duplex=True)
            process = mp.Process(
                target=worker_main,
                args=(spec.id, self.fmu_type, child_conn),
                name=f"cosim-worker-{spec.id}",
                daemon=True,
            )
            process.start()
            # Close the child end in the master process; only the child needs it.
            child_conn.close()
            self.workers[spec.id] = _Worker(
                apt_id=spec.id,
                process=process,
                parent_conn=parent_conn,
                last_room_temp=spec.initial_room_temp,
            )

        # Wait for every worker's "ready" message. Doing this in parallel by
        # polling; any failure kills the whole run.
        deadline = time.monotonic() + self.worker_init_timeout_s
        pending = set(self.workers.keys())
        while pending and time.monotonic() < deadline:
            for apt_id in list(pending):
                worker = self.workers[apt_id]
                if worker.parent_conn.poll(timeout=0.2):
                    msg = worker.parent_conn.recv()
                    if not msg.get("ok"):
                        self.shutdown()
                        raise RuntimeError(
                            f"Worker {apt_id} failed to initialize: {msg.get('err')}"
                        )
                    worker.ready = True
                    pending.discard(apt_id)
                if not worker.process.is_alive():
                    self.shutdown()
                    raise RuntimeError(
                        f"Worker {apt_id} exited before becoming ready "
                        f"(exit code {worker.process.exitcode})"
                    )
        if pending:
            self.shutdown()
            raise RuntimeError(
                f"Workers did not become ready within "
                f"{self.worker_init_timeout_s:.0f}s: {sorted(pending)}"
            )

    def shutdown(self) -> None:
        """Send shutdown to all workers and join, with escalation to kill."""
        for worker in self.workers.values():
            try:
                worker.parent_conn.send({"cmd": "shutdown"})
            except Exception:
                pass
        # Brief grace period for clean shutdown.
        for worker in self.workers.values():
            try:
                if worker.parent_conn.poll(timeout=5.0):
                    worker.parent_conn.recv()
            except Exception:
                pass
            try:
                worker.parent_conn.close()
            except Exception:
                pass
        for worker in self.workers.values():
            worker.process.join(timeout=10.0)
            if worker.process.is_alive():
                worker.process.terminate()
                worker.process.join(timeout=5.0)
            if worker.process.is_alive():
                worker.process.kill()
        self.workers.clear()

    # ── stepping ─────────────────────────────────────────────────────────

    def step(self, t: float, h: float | None = None) -> dict[str, float]:
        """Advance every worker by one macro-step and return new room temps."""
        step_h = self.macro_step_s if h is None else h

        # Build input vectors from the previous macro-step's outputs (Jacobi).
        inputs_per_apt: dict[str, dict[str, float]] = {}
        for spec in self.specs:
            floor = (
                self.workers[spec.floor_temp_source].last_room_temp
                if spec.floor_temp_source is not None
                else spec.ground_temp
            )
            roof = (
                self.workers[spec.roof_temp_source].last_room_temp
                if spec.roof_temp_source is not None
                else spec.sky_temp
            )
            inputs_per_apt[spec.id] = {
                FLOOR_INPUT: floor,
                ROOF_INPUT: roof,
                SUPPLY_INPUT: spec.supply_temp,
            }

        # Fan out.
        for spec in self.specs:
            self.workers[spec.id].parent_conn.send(
                {
                    "cmd": "step",
                    "t": t,
                    "h": step_h,
                    "inputs": inputs_per_apt[spec.id],
                    "output_names": [ROOM_OUTPUT],
                }
            )

        # Fan in.
        new_room_temps: dict[str, float] = {}
        for spec in self.specs:
            worker = self.workers[spec.id]
            if not worker.parent_conn.poll(timeout=self.step_timeout_s):
                raise RuntimeError(
                    f"Worker {spec.id} step timed out at t={t:.1f}s"
                )
            msg = worker.parent_conn.recv()
            if not msg.get("ok"):
                raise RuntimeError(
                    f"Worker {spec.id} step failed at t={t:.1f}s: {msg.get('err')}"
                )
            room_temp = msg["outputs"].get(ROOM_OUTPUT)
            if room_temp is None:
                raise RuntimeError(
                    f"Worker {spec.id} did not return {ROOM_OUTPUT} at t={t:.1f}s"
                )
            worker.last_room_temp = room_temp
            new_room_temps[spec.id] = room_temp
        return new_room_temps
