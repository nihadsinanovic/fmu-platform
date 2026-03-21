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
        result.needs_execution_tool = (
            root.get("needsExecutionTool", "false").lower() == "true"
        )

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
) -> Path:
    """Patch an FMU file to fix known compatibility issues.

    Args:
        fmu_path: Path to the original FMU.
        output_path: Where to write the patched FMU. If None, overwrites in-place.
        fix_needs_execution_tool: Set needsExecutionTool="false" (for AMESim FMUs
            that PyFMI refuses to load otherwise).
        inject_resources: Dict of {filename: local_path} to add to the FMU's
            resources/ directory.

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

        # Fix needsExecutionTool
        if fix_needs_execution_tool:
            md_path = os.path.join(tmp_dir, "modelDescription.xml")
            if os.path.exists(md_path):
                tree = ET.parse(md_path)
                root = tree.getroot()
                current = root.get("needsExecutionTool", "false")
                if current.lower() == "true":
                    root.set("needsExecutionTool", "false")
                    ET.indent(tree, space="  ")
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


def prepare_fmu_for_simulation(fmu_path: Path, work_dir: Path) -> Path:
    """Prepare an FMU for simulation — patch and copy to work directory.

    This is the main entry point called by the simulation runner before
    loading an FMU. It:
    1. Inspects the FMU for compatibility issues
    2. Patches needsExecutionTool if needed
    3. Returns the path to the (possibly patched) FMU

    Args:
        fmu_path: Original FMU path.
        work_dir: Working directory for this simulation run.

    Returns:
        Path to the simulation-ready FMU (may be the original if no patches needed).
    """
    inspection = inspect_fmu(fmu_path)

    for warning in inspection.warnings:
        logger.warning("FMU %s: %s", fmu_path.name, warning)

    needs_patch = inspection.needs_execution_tool

    # Always copy to work_dir to avoid issues with spaces or special chars in the original path
    dest_path = work_dir / fmu_path.name

    if not needs_patch:
        shutil.copy2(str(fmu_path), str(dest_path))
        return dest_path

    return patch_fmu(
        fmu_path,
        dest_path,
        fix_needs_execution_tool=True,
    )
