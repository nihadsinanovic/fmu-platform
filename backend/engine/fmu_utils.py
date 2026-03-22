"""FMU file utilities — patching, validation, and inspection.

Handles AMESim-specific quirks like the needsExecutionTool flag and
missing resource files.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


def _any_element_has_needs_execution_tool(root: ET.Element) -> bool:
    """Check if needsExecutionTool='true' exists on root or any child element."""
    for elem in [root] + list(root):
        val = elem.get("needsExecutionTool", "").lower()
        if val == "true":
            return True
    return False


def _clear_needs_execution_tool(root: ET.Element) -> bool:
    """Set needsExecutionTool='false' on root and all child elements that have it.

    Returns True if any element was modified.
    """
    modified = False
    for elem in [root] + list(root):
        val = elem.get("needsExecutionTool", "").lower()
        if val == "true":
            elem.set("needsExecutionTool", "false")
            modified = True
    return modified


@dataclass
class FMUInspection:
    """Result of inspecting an FMU file."""

    fmi_version: str = ""
    model_identifier: str = ""
    generation_tool: str = ""
    guid: str = ""
    needs_execution_tool: bool = False
    fmi_type: str = ""  # "ModelExchange", "CoSimulation", or "Both"
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    required_resources: list[str] = field(default_factory=list)
    bundled_resources: list[str] = field(default_factory=list)
    missing_resources: list[str] = field(default_factory=list)
    has_linux64_binary: bool = False
    warnings: list[str] = field(default_factory=list)


def inspect_fmu(fmu_path: Path) -> FMUInspection:
    """Inspect an FMU file and return metadata without modifying it.

    Reads modelDescription.xml and checks for required resources,
    platform binaries, and AMESim-specific flags.
    """
    result = FMUInspection()

    with zipfile.ZipFile(fmu_path, "r") as zf:
        names = zf.namelist()

        # Check for linux64 binary
        result.has_linux64_binary = any("binaries/linux64/" in n for n in names)
        if not result.has_linux64_binary:
            result.warnings.append("No linux64 binary found — FMU may not run on this server")

        # List bundled resources
        result.bundled_resources = [
            n.replace("resources/", "", 1)
            for n in names
            if n.startswith("resources/") and not n.endswith("/")
        ]

        # Parse modelDescription.xml
        if "modelDescription.xml" not in names:
            result.warnings.append("Missing modelDescription.xml")
            return result

        with zf.open("modelDescription.xml") as md_file:
            tree = ET.parse(md_file)
            root = tree.getroot()

        result.fmi_version = root.get("fmiVersion", "")
        result.guid = root.get("guid", "")
        result.generation_tool = root.get("generationTool", "")
        # Check needsExecutionTool on root AND child elements (ModelExchange, CoSimulation)
        # AMESim may place this attribute on any of these elements
        result.needs_execution_tool = _any_element_has_needs_execution_tool(root)

        # Determine FMI type
        has_me = root.find("ModelExchange") is not None
        has_cs = root.find("CoSimulation") is not None
        if has_me and has_cs:
            result.fmi_type = "Both"
        elif has_me:
            result.fmi_type = "ModelExchange"
        elif has_cs:
            result.fmi_type = "CoSimulation"

        # Get model identifier
        me_el = root.find("ModelExchange")
        cs_el = root.find("CoSimulation")
        if me_el is not None:
            result.model_identifier = me_el.get("modelIdentifier", "")
        elif cs_el is not None:
            result.model_identifier = cs_el.get("modelIdentifier", "")

        # Extract inputs and outputs
        for var in root.iter("ScalarVariable"):
            causality = var.get("causality", "")
            name = var.get("name", "")
            if causality == "input":
                result.inputs.append(name)
            elif causality == "output":
                result.outputs.append(name)

    return result


def patch_fmu(
    fmu_path: Path,
    output_path: Path | None = None,
    *,
    fix_needs_execution_tool: bool = True,
    inject_resources: dict[str, Path] | None = None,
    ensure_resources_dir: bool = False,
) -> Path:
    """Patch an FMU file to fix known compatibility issues.

    Args:
        fmu_path: Path to the original FMU.
        output_path: Where to write the patched FMU. If None, overwrites in-place.
        fix_needs_execution_tool: Set needsExecutionTool="false" (for AMESim FMUs
            that PyFMI refuses to load otherwise).
        inject_resources: Dict of {filename: local_path} to add to the FMU's
            resources/ directory.
        ensure_resources_dir: If True, ensure the ``resources/`` directory
            exists (even if empty) so PyFMI creates it during extraction.

    Returns:
        Path to the patched FMU file.
    """
    if output_path is None:
        output_path = fmu_path

    tmp_dir = tempfile.mkdtemp(prefix="fmu_patch_")
    try:
        # Extract
        with zipfile.ZipFile(fmu_path, "r") as zf:
            zf.extractall(tmp_dir)

        patched = False

        # Fix needsExecutionTool on root AND child elements (ModelExchange, CoSimulation)
        if fix_needs_execution_tool:
            md_path = os.path.join(tmp_dir, "modelDescription.xml")
            if os.path.exists(md_path):
                tree = ET.parse(md_path)
                xml_root = tree.getroot()
                if _clear_needs_execution_tool(xml_root):
                    tree.write(md_path, encoding="unicode", xml_declaration=True)
                    patched = True
                    logger.info("Patched needsExecutionTool=true → false in %s", fmu_path.name)

        # Inject resource files
        if inject_resources:
            res_dir = os.path.join(tmp_dir, "resources")
            os.makedirs(res_dir, exist_ok=True)
            for filename, src_path in inject_resources.items():
                dest = os.path.join(res_dir, filename)
                shutil.copy2(str(src_path), dest)
                logger.info("Injected resource %s into %s", filename, fmu_path.name)
                patched = True

        # Ensure resources/ directory exists (even if empty)
        if ensure_resources_dir:
            res_dir = os.path.join(tmp_dir, "resources")
            if not os.path.isdir(res_dir):
                os.makedirs(res_dir, exist_ok=True)
                patched = True
                logger.info("Created missing resources/ directory in %s", fmu_path.name)

        if not patched and output_path == fmu_path:
            # Nothing to do
            return fmu_path

        # Repackage
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for root, _dirs, files in os.walk(tmp_dir):
                for file in files:
                    full = os.path.join(root, file)
                    arcname = os.path.relpath(full, tmp_dir)
                    zout.write(full, arcname)

        return output_path

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def setup_amesim_environment(temp_path: Path, license_server: str = "") -> None:
    """Ensure AMESim license env vars and $AME stub are configured.

    This must be called before loading any AMESim FMU so the shared library
    can find its license server and unit/material files.

    Args:
        temp_path: Base temp directory (settings.TEMP_PATH) where the
                   ``ame_stub`` directory will be created.
        license_server: Value for ``AMESIM_LICENSE_SERVER`` (e.g.
                        ``"29000@16.16.200.137"``).  If empty, the function
                        still tries ``os.environ["SALT_LICENSE_SERVER"]``.
    """
    # ── license env vars ──────────────────────────────────────────────
    server = license_server or os.environ.get("SALT_LICENSE_SERVER", "")
    if server:
        os.environ["SALT_LICENSE_SERVER"] = server
        os.environ["LMS_LICENSE"] = server
        os.environ["SIEMENS_LICENSE_FILE"] = server
        logger.info("AMESim license server set to: %s", server)
    else:
        logger.warning(
            "No AMESim license server configured — FMU may fail if it requires a license"
        )

    # ── $AME stub directory ───────────────────────────────────────────
    if not os.environ.get("AME"):
        ame_stub = temp_path / "ame_stub"
        ame_stub.mkdir(parents=True, exist_ok=True)

        # Minimal AME.units (suppresses "Can't read $AME/AME.units" warning)
        units_file = ame_stub / "AME.units"
        if not units_file.exists():
            units_file.write_text("; minimal AME.units stub\n", encoding="utf-8")

        # Material lookup directory
        (ame_stub / "libth" / "data" / "materials").mkdir(parents=True, exist_ok=True)

        os.environ["AME"] = str(ame_stub)
        logger.info("Set $AME to stub directory: %s", ame_stub)

    # ── UGS license file ─────────────────────────────────────────────
    # AMESim FMUs look for a license file at $AME/../Common/licensing/UGS.lic
    # when the env-var-based licensing fails.  Create it so the FMU's
    # internal UGS licensing library can connect to the FlexLM server.
    if server:
        ame_dir = Path(os.environ.get("AME", str(temp_path / "ame_stub")))
        lic_dir = ame_dir.parent / "Common" / "licensing"
        lic_file = lic_dir / "UGS.lic"
        if not lic_file.exists():
            # Parse "port@host" format
            parts = server.split("@", 1)
            if len(parts) == 2:
                port, host = parts
                lic_dir.mkdir(parents=True, exist_ok=True)
                lic_file.write_text(
                    f"SERVER {host} ANY {port}\nUSE_SERVER\n",
                    encoding="utf-8",
                )
                logger.info("Created UGS license file: %s", lic_file)


def prepare_fmu_for_simulation(fmu_path: Path, work_dir: Path) -> Path:
    """Prepare an FMU for simulation — patch, inject data files, and copy.

    This is the main entry point called by the simulation runner before
    loading an FMU. It:
    1. Inspects the FMU for compatibility issues
    2. Patches needsExecutionTool if needed
    3. Injects external data files from the adjacent ``data/`` directory
       into the FMU's ``resources/`` directory so the binary can find them
       at runtime (AMESim FMUs look up data files via fmuResourceLocation)
    4. Ensures the ``resources/`` directory entry exists in the ZIP
    5. Returns the path to the simulation-ready FMU

    Args:
        fmu_path: Original FMU path.
        work_dir: Working directory for this simulation run.

    Returns:
        Path to the simulation-ready FMU in work_dir.
    """
    inspection = inspect_fmu(fmu_path)

    for warning in inspection.warnings:
        logger.warning("FMU %s: %s", fmu_path.name, warning)

    # Collect data files to inject into resources/
    data_dir = fmu_path.parent / "data"
    inject_resources: dict[str, Path] = {}
    if data_dir.exists():
        for f in data_dir.iterdir():
            if f.is_file():
                inject_resources[f.name] = f
                logger.info("Will inject data file into FMU resources: %s", f.name)

    needs_patch = inspection.needs_execution_tool or bool(inject_resources)

    dest_path = work_dir / fmu_path.name

    if not needs_patch:
        # Still need to ensure resources/ directory exists in the FMU
        _ensure_resources_dir(fmu_path, dest_path)
        return dest_path

    return patch_fmu(
        fmu_path,
        dest_path,
        fix_needs_execution_tool=inspection.needs_execution_tool,
        inject_resources=inject_resources if inject_resources else None,
        ensure_resources_dir=True,
    )


def _ensure_resources_dir(src_fmu: Path, dest_fmu: Path) -> None:
    """Copy an FMU, ensuring it has a resources/ directory entry.

    Some FMU runtimes (PyFMI/JModelica) expect the resources/ directory to
    exist after extraction.  If the ZIP doesn't contain one, add an empty
    entry so the directory is created.
    """
    shutil.copy2(str(src_fmu), str(dest_fmu))

    with zipfile.ZipFile(dest_fmu, "r") as zf:
        has_resources = any(
            n.startswith("resources/") for n in zf.namelist()
        )

    if not has_resources:
        # Append a directory entry for resources/
        with zipfile.ZipFile(dest_fmu, "a") as zf:
            zf.writestr("resources/", "")
        logger.info("Added missing resources/ directory to %s", dest_fmu.name)
