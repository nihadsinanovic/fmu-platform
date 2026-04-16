"""Co-simulation worker: one apartment FMU per subprocess.

Each worker owns a single FMU instance (the stackable_apartment FMU has
``canBeInstantiatedOnlyOncePerProcess="true"``, so one instance per process
is the most we can do until Martti re-exports). The worker receives
``step`` commands over a ``multiprocessing.Pipe``, advances its FMU by one
macro-step, and returns the requested outputs.

Spawned with ``multiprocessing.set_start_method('spawn')`` so each worker
gets a fresh Python interpreter — no PyFMI state inherited from the master.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any


def _load_model(fmu_type: str) -> tuple[Any, Path]:
    """Prepare a work dir, load the FMU, and complete its initialization."""
    from sqlalchemy import create_engine, text

    from app.config import settings
    from engine.fmu_utils import (
        _normalize_data_file_for_injection,
        prepare_fmu_for_simulation,
        setup_amesim_environment,
    )

    setup_amesim_environment(settings.TEMP_PATH, settings.AMESIM_LICENSE_SERVER)

    engine = create_engine(settings.sync_database_url)
    with engine.connect() as dbconn:
        row = dbconn.execute(
            text("SELECT fmu_path FROM fmu_library WHERE type_name = :n"),
            {"n": fmu_type},
        ).fetchone()
    if not row:
        raise RuntimeError(f"FMU type '{fmu_type}' not found in library")
    fmu_path = Path(row[0])

    work_dir = Path(tempfile.mkdtemp(prefix=f"cosim_{fmu_type}_"))
    ready_fmu = prepare_fmu_for_simulation(fmu_path, work_dir)

    data_dir = fmu_path.parent / "data"
    if data_dir.exists():
        for f in data_dir.iterdir():
            if not f.is_file():
                continue
            dest = work_dir / f.name
            if f.suffix == ".data":
                _normalize_data_file_for_injection(f, dest)
            else:
                shutil.copy2(f, dest)

    # The FMU references data files by relative path (e.g. ../data/temperature_2025.data)
    # so we must chdir into the work dir before load_fmu.
    os.chdir(work_dir)

    from pyfmi import load_fmu  # type: ignore[import]

    model = load_fmu(str(ready_fmu), log_level=0)
    model.setup_experiment(start_time=0.0)
    model.enter_initialization_mode()
    model.exit_initialization_mode()
    return model, work_dir


def worker_main(apt_id: str, fmu_type: str, conn) -> None:
    """Entry point for a co-simulation subprocess worker.

    Protocol (dict messages via ``conn``):

    Master → Worker:
        ``{"cmd": "step", "t": float, "h": float, "inputs": {name: val, ...},
           "output_names": [name, ...]}``
        ``{"cmd": "shutdown"}``

    Worker → Master:
        ``{"ok": True, "msg": "ready"}``  (sent once after successful init)
        ``{"ok": True, "outputs": {name: val, ...}}``  (after each step)
        ``{"ok": False, "err": "..."}``  (on any failure)
    """
    logging.disable(logging.CRITICAL)
    work_dir: Path | None = None
    model = None

    try:
        model, work_dir = _load_model(fmu_type)
    except Exception as exc:  # noqa: BLE001 — any failure in init is fatal
        try:
            conn.send({"ok": False, "err": f"[{apt_id}] init failed: {exc}"})
        except Exception:
            pass
        return

    conn.send({"ok": True, "msg": "ready"})

    # Get default simulate options once; reuse with initialize=False so the
    # FMU state is preserved between macro-steps.
    opts = model.simulate_options()
    opts["ncp"] = 1
    opts["initialize"] = False
    # Silence PyFMI's default progress output inside the worker.
    if "result_handling" in opts:
        opts["result_handling"] = "memory"

    try:
        while True:
            try:
                cmd = conn.recv()
            except EOFError:
                break

            if not isinstance(cmd, dict):
                conn.send({"ok": False, "err": f"expected dict command, got {type(cmd).__name__}"})
                continue

            action = cmd.get("cmd")
            if action == "shutdown":
                conn.send({"ok": True})
                break

            if action != "step":
                conn.send({"ok": False, "err": f"unknown command: {action!r}"})
                continue

            try:
                t = float(cmd["t"])
                h = float(cmd["h"])
                inputs = cmd.get("inputs", {}) or {}
                output_names = cmd.get("output_names", []) or []

                if inputs:
                    names = list(inputs.keys())
                    values = [float(v) for v in inputs.values()]
                    model.set(names, values)

                result = model.simulate(
                    start_time=t,
                    final_time=t + h,
                    options=opts,
                )

                outputs: dict[str, float] = {}
                for name in output_names:
                    try:
                        outputs[name] = float(result[name][-1])
                    except Exception:
                        outputs[name] = float("nan")
                conn.send({"ok": True, "outputs": outputs})
            except Exception as exc:  # noqa: BLE001
                # Surface FMU internal log to help diagnose solver errors.
                fmu_log = ""
                try:
                    fmu_log = "\n".join(model.get_log()[-30:])
                except Exception:
                    pass
                err = f"[{apt_id}] step failed at t={cmd.get('t')}: {exc}"
                if fmu_log:
                    err += f"\n--- FMU log tail ---\n{fmu_log}"
                conn.send({"ok": False, "err": err})
    finally:
        try:
            if model is not None:
                model.terminate()
        except Exception:
            pass
        try:
            if model is not None:
                model.free_instance()
        except Exception:
            pass
        if work_dir is not None:
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    # Allow running as `python -m simulation.subprocess_worker` for ad-hoc smoke
    # tests. Not used in normal operation (master uses multiprocessing.Process).
    print("subprocess_worker is normally launched via CoSimMaster, not directly.", file=sys.stderr)
    sys.exit(1)
