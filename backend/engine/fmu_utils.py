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


@dataclass
class DataFileValidation:
    """Result of validating an AMESim .data file."""

    valid: bool = False
    has_header: bool = False
    n_points: int = 0
    n_vars: int = 0  # number of variables (excluding time column)
    n_columns: int = 0  # total columns per data row (including time)
    n_comment_lines: int = 0
    repaired: bool = False
    error: str = ""


def _normalize_data_file_for_injection(src: Path, dest: Path) -> bool:
    """Normalize an AMESim .data file for Linux runtime compatibility.

    AMESim's C-based table reader is strict. This function normalizes the
    file to avoid common issues that cause "Undetermined format" errors:

    1. Strips UTF-8 BOM (byte order mark)
    2. Converts Windows line endings (\\r\\n) to Unix (\\n)
    3. Removes blank/empty lines (AMESim treats them as data boundaries)
    4. Sanitizes comment lines to ASCII (non-ASCII chars like °, — can
       confuse the C parser)
    5. Strips trailing whitespace from every line

    The original file on disk is NOT modified — only the injected copy.

    Returns True if the file was modified, False if already clean.
    """
    raw = src.read_bytes()
    modified = False

    # Strip UTF-8 BOM if present
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
        modified = True
        logger.info("Stripped UTF-8 BOM from %s", src.name)

    # Normalize line endings: \r\n → \n and lone \r → \n
    if b"\r" in raw:
        raw = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        modified = True
        logger.info("Normalized line endings in %s", src.name)

    # Process line-by-line: strip comments, remove blanks, strip trailing ws
    # AMESim's SIGUDA01 submodel may not recognize ';' as a comment prefix.
    # Safest approach: remove ALL comment lines — they're human metadata,
    # not needed by the FMU binary at runtime.
    text = raw.decode("utf-8", errors="replace")
    lines = text.split("\n")
    out_lines: list[str] = []
    blanks_removed = 0
    comments_removed = 0

    for line in lines:
        stripped = line.rstrip()

        # Remove blank/empty lines
        if not stripped:
            blanks_removed += 1
            continue

        # Remove comment lines entirely — AMESim's table reader may not
        # support ';' comments (only "'" in some submodels like SIGUDA01)
        if stripped.startswith(";") or stripped.startswith("'"):
            comments_removed += 1
            continue

        out_lines.append(stripped)

    if blanks_removed > 0:
        modified = True
        logger.info("Removed %d blank lines from %s", blanks_removed, src.name)

    if comments_removed > 0:
        modified = True
        logger.info(
            "Stripped %d comment lines from %s for runtime injection",
            comments_removed,
            src.name,
        )

    result_bytes = ("\n".join(out_lines) + "\n").encode("utf-8")

    # Log first few lines of normalized output for diagnostics
    for i, line in enumerate(out_lines[:5]):
        logger.info("  %s normalized line %d: %r", src.name, i + 1, line[:120])

    dest.write_bytes(result_bytes)

    if modified:
        logger.info(
            "Normalized data file %s for injection: %d → %d bytes",
            src.name,
            len(raw),
            len(result_bytes),
        )

    return modified


def _is_comment_line(line: str) -> bool:
    """Check if a line is a comment in AMESim .data format.

    AMESim supports both `;` and `'` (single quote) as comment prefixes.
    """
    stripped = line.strip()
    return stripped.startswith(";") or stripped.startswith("'")


def validate_amesim_data_file(file_path: Path) -> DataFileValidation:
    """Validate an AMESim .data file and check its format.

    AMESim table files have the format:
        ; optional comment lines (start with ; or ')
        npoints  nvars
        t1  v1  v2  ...
        t2  v1  v2  ...

    Where npoints is the number of data rows and nvars is the number of
    value columns (excluding the time column).

    Returns a DataFileValidation with details about the file.
    """
    result = DataFileValidation()

    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        result.error = f"Cannot read file: {exc}"
        return result

    lines = text.splitlines()
    if not lines:
        result.error = "File is empty"
        return result

    # Skip comment lines (starting with ; or ')
    data_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not _is_comment_line(line):
            data_start = i
            break
        result.n_comment_lines += 1

    remaining = lines[data_start:]
    if not remaining:
        result.error = "File contains only comments"
        return result

    # Check if the first non-comment line is a header (npoints nvars)
    first_line = remaining[0].strip()
    parts = first_line.split()

    try:
        maybe_npoints = int(parts[0])
        maybe_nvars = int(parts[1]) if len(parts) >= 2 else 0
        # Header line has integer values and typically 1-2 fields
        if len(parts) <= 2 and maybe_npoints > 0:
            result.has_header = True
            result.n_points = maybe_npoints
            result.n_vars = maybe_nvars
            data_rows = remaining[1:]
        else:
            raise ValueError("not a header")
    except (ValueError, IndexError):
        # No header — treat all remaining lines as data
        result.has_header = False
        data_rows = remaining

    # Count actual data rows and columns
    actual_rows = 0
    col_count = 0
    for line in data_rows:
        stripped = line.strip()
        if not stripped or _is_comment_line(line):
            continue
        actual_rows += 1
        cols = len(stripped.split())
        if col_count == 0:
            col_count = cols
        elif cols != col_count:
            result.error = f"Inconsistent column count: expected {col_count}, got {cols}"
            return result

    result.n_columns = col_count

    if actual_rows == 0:
        result.error = "No data rows found"
        return result

    if not result.has_header:
        result.n_points = actual_rows
        result.n_vars = col_count - 1  # first column is time

    # Validate header matches data if header was present
    if result.has_header:
        # Check for comment lines between header and first data row
        # (this happens when a header was inserted before unrecognized comments)
        has_interleaved_comments = False
        if data_rows:
            for line in data_rows:
                stripped = line.strip()
                if not stripped:
                    continue
                if _is_comment_line(line):
                    has_interleaved_comments = True
                    break
                # First non-empty, non-comment line is data — we're good
                break

        if has_interleaved_comments:
            result.error = (
                f"Comment lines appear after the header, before data rows. "
                f"AMESim cannot parse this — the header must be immediately "
                f"followed by data rows. Re-upload the original file and use "
                f"the repair function to add the header in the correct position."
            )
            result.valid = False
            return result

        if result.n_points != actual_rows:
            result.error = (
                f"Header says {result.n_points} points but file has {actual_rows} data rows"
            )
            return result
        expected_cols = result.n_vars + 1  # time + nvars
        if col_count != expected_cols:
            result.error = (
                f"Header says {result.n_vars} vars (expecting {expected_cols} columns) "
                f"but data has {col_count} columns"
            )
            return result

    # File is only fully valid if it has a correct header
    # (without the header, AMESim will fail with "Undetermined format")
    result.valid = result.has_header
    return result


def repair_amesim_data_file(file_path: Path) -> DataFileValidation:
    """Validate and repair an AMESim .data file in-place.

    If the file is missing the required npoints/nvars header line,
    add it. This makes the file parseable by AMESim's table reader.

    Returns the validation result (with repaired=True if the file was fixed).
    """
    validation = validate_amesim_data_file(file_path)

    if validation.has_header:
        # Already has a proper header — nothing to repair
        return validation

    if validation.error:
        # File has structural issues that can't be auto-repaired
        return validation

    # File has valid data but is missing header — add it
    text = file_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=True)

    # Build header line: npoints nvars (nvars = total_columns - 1 for time)
    header = f"{validation.n_points}\t{validation.n_vars}\n"

    # Insert header after any comment lines
    insert_pos = validation.n_comment_lines
    lines.insert(insert_pos, header)

    file_path.write_text("".join(lines), encoding="utf-8")

    validation.has_header = True
    validation.valid = True
    validation.repaired = True
    logger.info(
        "Repaired AMESim data file %s: added header (%d points, %d vars)",
        file_path.name,
        validation.n_points,
        validation.n_vars,
    )
    return validation


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
    # Temp dir for normalized copies of .data files (cleaned up later)
    norm_dir: Path | None = None
    if data_dir.exists():
        for f in data_dir.iterdir():
            if f.is_file():
                # Validate .data files and warn if issues are detected
                if f.suffix == ".data":
                    validation = validate_amesim_data_file(f)
                    if not validation.has_header:
                        logger.warning(
                            "Data file %s is missing the AMESim table header "
                            "(npoints\\tnvars). The FMU will likely fail with "
                            "'Undetermined format'. Use the admin panel to repair it.",
                            f.name,
                        )
                    if validation.error:
                        logger.warning("Data file %s has issues: %s", f.name, validation.error)

                    # Normalize .data files (BOM, line endings) for Linux runtime
                    if norm_dir is None:
                        norm_dir = Path(tempfile.mkdtemp(prefix="fmu_norm_"))
                    norm_path = norm_dir / f.name
                    _normalize_data_file_for_injection(f, norm_path)
                    inject_resources[f.name] = norm_path
                else:
                    inject_resources[f.name] = f

                size = f.stat().st_size
                logger.info(
                    "Will inject data file into FMU resources: %s (%d bytes)",
                    f.name,
                    size,
                )
                # Log first bytes and lines of .data files for diagnostics
                if f.suffix == ".data":
                    try:
                        raw_bytes = f.read_bytes()[:20]
                        logger.info("  %s first bytes: %r", f.name, raw_bytes)
                        first_lines = f.read_text(
                            encoding="utf-8", errors="replace"
                        ).splitlines()[:3]
                        for i, line in enumerate(first_lines):
                            logger.info("  %s line %d: %r", f.name, i + 1, line[:120])
                    except Exception:
                        pass
    else:
        logger.info("No data/ directory found next to FMU: %s", fmu_path)

    needs_patch = inspection.needs_execution_tool or bool(inject_resources)

    dest_path = work_dir / fmu_path.name

    try:
        if not needs_patch:
            # Still need to ensure resources/ directory exists in the FMU
            _ensure_resources_dir(fmu_path, dest_path)
            return dest_path

        result = patch_fmu(
            fmu_path,
            dest_path,
            fix_needs_execution_tool=inspection.needs_execution_tool,
            inject_resources=inject_resources if inject_resources else None,
            ensure_resources_dir=True,
        )

        # Verify injected data files are present and non-empty in the ZIP
        if inject_resources:
            with zipfile.ZipFile(result, "r") as zf:
                for filename in inject_resources:
                    arcname = f"resources/{filename}"
                    if arcname not in zf.namelist():
                        logger.error(
                            "VERIFICATION FAILED: %s not found in patched FMU ZIP",
                            arcname,
                        )
                    else:
                        info = zf.getinfo(arcname)
                        logger.info(
                            "Verified %s in FMU ZIP: %d bytes (compressed: %d)",
                            arcname,
                            info.file_size,
                            info.compress_size,
                        )
                        if info.file_size == 0:
                            logger.error(
                                "VERIFICATION FAILED: %s is empty in FMU ZIP!",
                                arcname,
                            )
                        # Log first bytes of the injected file from the ZIP
                        if filename.endswith(".data"):
                            with zf.open(arcname) as zentry:
                                head = zentry.read(200)
                                logger.info(
                                    "  %s in ZIP starts with: %r",
                                    arcname,
                                    head[:100],
                                )

        return result
    finally:
        # Clean up temporary normalized files
        if norm_dir is not None:
            shutil.rmtree(str(norm_dir), ignore_errors=True)


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
