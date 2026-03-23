import asyncio
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.fmu_library import FMULibrary
from engine.fmu_utils import inspect_fmu, validate_amesim_data_file

router = APIRouter(prefix="/api/fmu-library", tags=["fmu-library"])


# ── Response / request schemas ────────────────────────────────────────

class FMUListItem(BaseModel):
    model_config = {"from_attributes": True}

    type_name: str
    version: str


class FMUDetail(BaseModel):
    model_config = {"from_attributes": True}

    type_name: str
    version: str
    fmu_path: str
    manifest: dict


class FMURegister(BaseModel):
    type_name: str
    version: str
    fmu_path: str
    manifest: dict


class FMUUploadResponse(BaseModel):
    type_name: str
    version: str
    fmu_path: str
    fmi_version: str
    fmi_type: str
    generation_tool: str
    inputs: list[str]
    outputs: list[str]
    patched: bool
    warnings: list[str]


class FMUTestRunRequest(BaseModel):
    inputs: dict[str, float] = {}
    start_time: float = 0.0
    end_time: float = 10.0
    ncp: int = 100


class FMUTestRunResult(BaseModel):
    time: list[float]
    outputs: dict[str, list[float]]


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("", response_model=list[FMUListItem])
async def list_fmus(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FMULibrary).order_by(FMULibrary.type_name))
    return result.scalars().all()


@router.get("/{type_name}/manifest")
async def get_manifest(type_name: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FMULibrary).where(FMULibrary.type_name == type_name)
    )
    fmu = result.scalar_one_or_none()
    if not fmu:
        raise HTTPException(status_code=404, detail=f"FMU type '{type_name}' not found")
    return fmu.manifest


@router.post("", response_model=FMUDetail, status_code=status.HTTP_201_CREATED)
async def register_fmu(body: FMURegister, db: AsyncSession = Depends(get_db)):
    """Register an FMU already on the server filesystem (manual registration)."""
    existing = await db.execute(
        select(FMULibrary).where(FMULibrary.type_name == body.type_name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"FMU type '{body.type_name}' already exists")

    fmu = FMULibrary(
        type_name=body.type_name,
        version=body.version,
        fmu_path=body.fmu_path,
        manifest=body.manifest,
    )
    db.add(fmu)
    await db.flush()
    await db.refresh(fmu)
    return fmu


@router.delete("/{type_name}")
async def delete_fmu(type_name: str, db: AsyncSession = Depends(get_db)):
    """Delete an FMU and all its data files from the library."""
    result = await db.execute(
        select(FMULibrary).where(FMULibrary.type_name == type_name)
    )
    fmu_record = result.scalar_one_or_none()
    if not fmu_record:
        raise HTTPException(status_code=404, detail=f"FMU type '{type_name}' not found")

    # Delete files from disk (FMU + data dir)
    fmu_path = Path(fmu_record.fmu_path)
    fmu_dir = fmu_path.parent
    if fmu_dir.exists():
        shutil.rmtree(str(fmu_dir), ignore_errors=True)

    # Delete from database
    await db.delete(fmu_record)
    await db.flush()

    return {"message": f"Deleted FMU '{type_name}'"}


@router.post("/upload", response_model=FMUUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_fmu(
    file: UploadFile,
    type_name: str,
    version: str = "1.0.0",
    db: AsyncSession = Depends(get_db),
):
    """Upload an FMU file, validate it, patch if needed, and register it.

    The FMU is inspected for:
    - Valid FMI 2.0 structure (modelDescription.xml, linux64 binary)
    - needsExecutionTool flag (patched automatically for AMESim FMUs)
    - Inputs and outputs

    The patched FMU is stored in the FMU library directory and registered
    in the database with an auto-generated manifest.
    """
    if not file.filename or not file.filename.endswith(".fmu"):
        raise HTTPException(status_code=400, detail="File must be a .fmu file")

    # Check for duplicate type_name
    existing = await db.execute(
        select(FMULibrary).where(FMULibrary.type_name == type_name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"FMU type '{type_name}' already exists")

    # Save uploaded file to temp location
    temp_dir = settings.TEMP_PATH / "uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / file.filename

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Inspect the FMU
        inspection = inspect_fmu(temp_path)
        warnings = list(inspection.warnings)

        if not inspection.fmi_version:
            raise HTTPException(
                status_code=400,
                detail="Invalid FMU: missing or unparseable modelDescription.xml",
            )

        if not inspection.has_linux64_binary:
            warnings.append(
                "No linux64 binary found. This FMU will not execute on the server. "
                "Re-export from AMESim with linux64 target platform."
            )

        # Store FMU as-is (no modifications). Patching happens at runtime.
        dest_dir = settings.FMU_LIBRARY_PATH / type_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / file.filename
        shutil.copy2(str(temp_path), str(dest_path))

        if inspection.needs_execution_tool:
            warnings.append("FMU has needsExecutionTool='true' — will be patched automatically at runtime")

        # Build manifest from inspection
        manifest = {
            "fmu_type": type_name,
            "fmi_version": inspection.fmi_version,
            "fmi_type": inspection.fmi_type,
            "version": version,
            "generation_tool": inspection.generation_tool,
            "guid": inspection.guid,
            "model_identifier": inspection.model_identifier,
            "inputs": [
                {"name": name, "type": "Real", "causality": "input"}
                for name in inspection.inputs
            ],
            "outputs": [
                {"name": name, "type": "Real", "causality": "output"}
                for name in inspection.outputs
            ],
            "parameters": [],
            "compatible_connections": {},
        }

        # Register in database
        fmu_record = FMULibrary(
            type_name=type_name,
            version=version,
            fmu_path=str(dest_path),
            manifest=manifest,
        )
        db.add(fmu_record)
        await db.flush()
        await db.refresh(fmu_record)

        return FMUUploadResponse(
            type_name=type_name,
            version=version,
            fmu_path=str(dest_path),
            fmi_version=inspection.fmi_version,
            fmi_type=inspection.fmi_type,
            generation_tool=inspection.generation_tool,
            inputs=inspection.inputs,
            outputs=inspection.outputs,
            patched=False,
            warnings=warnings,
        )

    finally:
        # Clean up temp file
        if temp_path.exists():
            temp_path.unlink()


@router.post("/{type_name}/resources")
async def upload_resource(
    type_name: str,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
):
    """Upload a data file for an existing FMU.

    AMESim FMUs sometimes require external data files (e.g., weather data,
    lookup tables) that weren't bundled during export. Files are stored
    alongside the FMU and injected into the FMU's resources/ directory at
    simulation time.

    For AMESim .data files, the format is validated (but not modified).
    """
    result = await db.execute(
        select(FMULibrary).where(FMULibrary.type_name == type_name)
    )
    fmu_record = result.scalar_one_or_none()
    if not fmu_record:
        raise HTTPException(status_code=404, detail=f"FMU type '{type_name}' not found")

    if not file.filename:
        raise HTTPException(status_code=400, detail="File must have a name")

    # Store data file in a 'data/' directory next to the FMU
    fmu_dir = Path(fmu_record.fmu_path).parent
    data_dir = fmu_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    dest = data_dir / file.filename

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    response: dict = {
        "message": f"Data file '{file.filename}' stored for {type_name}",
        "type_name": type_name,
        "resource": file.filename,
    }

    # Validate AMESim .data files (report issues but do NOT modify)
    if file.filename.endswith(".data"):
        validation = validate_amesim_data_file(dest)
        response["validation"] = {
            "format_valid": validation.valid,
            "has_header": validation.has_header,
            "n_points": validation.n_points,
            "n_vars": validation.n_vars,
            "n_columns": validation.n_columns,
            "error": validation.error or None,
        }

    return response


@router.get("/{type_name}/resources")
async def list_resources(
    type_name: str,
    db: AsyncSession = Depends(get_db),
):
    """List data files stored for an FMU."""
    result = await db.execute(
        select(FMULibrary).where(FMULibrary.type_name == type_name)
    )
    fmu_record = result.scalar_one_or_none()
    if not fmu_record:
        raise HTTPException(status_code=404, detail=f"FMU type '{type_name}' not found")

    fmu_dir = Path(fmu_record.fmu_path).parent
    data_dir = fmu_dir / "data"
    files: list[dict] = []
    if data_dir.exists():
        for f in sorted(data_dir.iterdir()):
            if f.is_file():
                entry: dict = {"name": f.name, "size_bytes": f.stat().st_size}
                # Include validation info for .data files
                if f.suffix == ".data":
                    v = validate_amesim_data_file(f)
                    entry["validation"] = {
                        "format_valid": v.valid,
                        "has_header": v.has_header,
                        "n_points": v.n_points,
                        "n_vars": v.n_vars,
                        "n_columns": v.n_columns,
                        "error": v.error or None,
                    }
                files.append(entry)
    return {"type_name": type_name, "resources": files}


@router.delete("/{type_name}/resources/{filename}")
async def delete_resource(
    type_name: str,
    filename: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a data file for an FMU."""
    result = await db.execute(
        select(FMULibrary).where(FMULibrary.type_name == type_name)
    )
    fmu_record = result.scalar_one_or_none()
    if not fmu_record:
        raise HTTPException(status_code=404, detail=f"FMU type '{type_name}' not found")

    fmu_dir = Path(fmu_record.fmu_path).parent
    file_path = fmu_dir / "data" / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Data file '{filename}' not found")

    file_path.unlink()
    return {"message": f"Deleted '{filename}'"}


# ── FMU Test Run ───────────────────────────────────────────────────────


def _run_fmu_test_sync(
    fmu_path: Path,
    inputs: dict[str, float],
    output_names: list[str],
    start_time: float,
    end_time: float,
    ncp: int,
) -> dict:
    """Run a single-FMU test simulation synchronously. Called from a thread pool."""
    import logging
    import os

    import numpy as np

    logger = logging.getLogger(__name__)

    # Set AMESim license env vars and $AME stub directory
    from engine.fmu_utils import setup_amesim_environment
    setup_amesim_environment(settings.TEMP_PATH, settings.AMESIM_LICENSE_SERVER)

    try:
        from pyfmi import load_fmu  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError("PyFMI is not installed on this server") from exc

    with tempfile.TemporaryDirectory(prefix="fmu_test_") as work_dir:
        work_path = Path(work_dir)
        from engine.fmu_utils import prepare_fmu_for_simulation

        logger.info("Preparing FMU for simulation: %s → %s", fmu_path, work_path)
        ready_fmu = prepare_fmu_for_simulation(fmu_path, work_path)
        logger.info("FMU ready at: %s", ready_fmu)

        # Copy data files into working directory so the FMU binary can find them
        # Normalize .data files (BOM, line endings) for Linux runtime
        data_dir = fmu_path.parent / "data"
        if data_dir.exists():
            from engine.fmu_utils import _normalize_data_file_for_injection
            for data_file in data_dir.iterdir():
                if data_file.is_file():
                    dest = work_path / data_file.name
                    if data_file.suffix == ".data":
                        _normalize_data_file_for_injection(data_file, dest)
                    else:
                        shutil.copy2(str(data_file), str(dest))
                    logger.info("Copied data file to work dir: %s", data_file.name)

        # Change to work dir so the FMU binary can find data files by relative path
        original_cwd = os.getcwd()
        os.chdir(work_path)
        logger.info("Changed working directory to: %s", work_path)
        logger.info("Work dir contents: %s", [f.name for f in work_path.iterdir()])

        try:
            model = load_fmu(str(ready_fmu), log_level=4)
        except Exception as exc:
            os.chdir(original_cwd)
            logger.error("load_fmu failed: %s", exc, exc_info=True)
            raise RuntimeError(f"load_fmu failed: {exc}") from exc
        logger.info("FMU loaded successfully")

        # Build a constant input trajectory (two time points, same values)
        input_arg = None
        if inputs:
            input_names = list(inputs.keys())
            t_col = np.array([start_time, end_time])
            val_cols = [np.array([inputs[n], inputs[n]]) for n in input_names]
            val_matrix = np.column_stack([t_col] + val_cols)
            input_arg = (input_names, val_matrix)
            logger.info("Input trajectory built for variables: %s", input_names)

        opts = model.simulate_options()
        opts["ncp"] = ncp
        logger.info("Starting simulation: start=%s, end=%s, ncp=%s", start_time, end_time, ncp)

        try:
            sim_result = model.simulate(
                start_time=start_time,
                final_time=end_time,
                input=input_arg,
                options=opts,
            )
        except Exception as sim_exc:
            # Capture FMU internal log for diagnostics
            fmu_log = ""
            try:
                fmu_log = "\n".join(model.get_log())
            except Exception:
                fmu_log = "(could not retrieve FMU log)"
            logger.error("model.simulate failed: %s\nFMU log:\n%s", sim_exc, fmu_log)

            # Detect AMESim license failure and return a clearer message
            if "lic_init failed" in fmu_log or "Checkout failed" in fmu_log:
                license_server = os.environ.get("SALT_LICENSE_SERVER", "(not set)")
                raise RuntimeError(
                    f"AMESim license checkout failed. The FMU requires a valid "
                    f"Simcenter AMESim license to run.\n\n"
                    f"License server: {license_server}\n"
                    f"Verify that AMESIM_LICENSE_SERVER is set correctly in .env "
                    f"and that the license server is reachable from this host.\n\n"
                    f"FMU log:\n{fmu_log}"
                ) from sim_exc

            # Detect AMESim data file format or file-not-found errors
            if any(s in fmu_log for s in (
                "Undetermined format", "File has no data", "Impossible to open"
            )):
                # List data files on disk (source)
                data_files_info = []
                data_dir = fmu_path.parent / "data"
                if data_dir.exists():
                    for df in data_dir.iterdir():
                        if df.is_file():
                            data_files_info.append(
                                f"  {df.name} ({df.stat().st_size} bytes)"
                            )
                files_detail = "\n".join(data_files_info) if data_files_info else "  (none)"

                raise RuntimeError(
                    f"AMESim data file error. The FMU could not read a "
                    f"required .data file.\n\n"
                    f"Data files on disk:\n{files_detail}\n\n"
                    f"FMU log:\n{fmu_log}"
                ) from sim_exc

            raise RuntimeError(
                f"model.simulate failed: {sim_exc}\n\nFMU log:\n{fmu_log}"
            ) from sim_exc
        finally:
            os.chdir(original_cwd)

        time_data = [float(t) for t in sim_result["time"]]
        outputs_data: dict[str, list[float]] = {}
        for var in output_names:
            try:
                outputs_data[var] = [float(v) for v in sim_result[var]]
            except Exception:
                logger.warning("Could not extract output variable: %s", var)

        return {"time": time_data, "outputs": outputs_data}


@router.post("/{type_name}/test-run", response_model=FMUTestRunResult)
async def test_run_fmu(
    type_name: str,
    body: FMUTestRunRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run a quick single-FMU test simulation with constant inputs.

    Loads the FMU with PyFMI, applies constant input values, simulates, and
    returns the time vector and all output variable trajectories.
    """
    result = await db.execute(
        select(FMULibrary).where(FMULibrary.type_name == type_name)
    )
    fmu_record = result.scalar_one_or_none()
    if not fmu_record:
        raise HTTPException(status_code=404, detail=f"FMU type '{type_name}' not found")

    fmu_path = Path(fmu_record.fmu_path)
    if not fmu_path.exists():
        raise HTTPException(status_code=404, detail="FMU file not found on disk")

    output_names = [p["name"] for p in fmu_record.manifest.get("outputs", [])]

    loop = asyncio.get_event_loop()
    try:
        result_data = await loop.run_in_executor(
            None,
            _run_fmu_test_sync,
            fmu_path,
            dict(body.inputs),
            output_names,
            body.start_time,
            body.end_time,
            body.ncp,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return FMUTestRunResult(**result_data)
