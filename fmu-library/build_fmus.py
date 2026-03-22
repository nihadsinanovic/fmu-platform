#!/usr/bin/env python3
"""Build functional FMI 2.0 Model Exchange FMU files from C source code.

Each FMU is compiled from its C source into a shared library (.so on Linux),
then packaged as a standard .fmu ZIP file containing:
  - modelDescription.xml  (generated from manifest.json)
  - binaries/linux64/<model_identifier>.so

Usage:
    python build_fmus.py              # build all FMUs
    python build_fmus.py --clean      # clean and rebuild
    python build_fmus.py --verbose    # show compiler output
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

LIBRARY_ROOT = Path(__file__).parent
SRC_DIR = LIBRARY_ROOT / "src"
INCLUDE_DIR = SRC_DIR / "include"

# Compiler settings
CC = os.environ.get("CC", "gcc")
CFLAGS = ["-shared", "-fPIC", "-O2", "-Wall", "-fvisibility=hidden"]
LDFLAGS = ["-lm"]

# FMI type mapping
TYPE_MAP = {"Real": "Real", "Integer": "Integer", "Boolean": "Boolean", "String": "String"}

# FMUs that have continuous states (need <Derivatives> in ModelStructure)
FMUS_WITH_STATES = {
    "ambient_loop_segment": {
        "states": [{"name": "T_fluid", "derivative_name": "der_T_fluid", "nominal": 300.0}],
    },
    "apartment_thermal_zone": {
        "states": [{"name": "T_room_state", "derivative_name": "der_T_room", "nominal": 293.0}],
    },
}


def generate_guid(fmu_type: str, version: str) -> str:
    """Generate a deterministic GUID for an FMU."""
    import hashlib
    h = hashlib.sha256(f"{fmu_type}-{version}-functional".encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def manifest_to_model_description(manifest: dict, guid: str) -> str:
    """Convert manifest.json to FMI 2.0 modelDescription.xml.

    Handles continuous states properly for FMUs that have them.
    """
    fmu_type = manifest["fmu_type"]
    description = manifest.get("description", "")
    state_info = FMUS_WITH_STATES.get(fmu_type)

    root = ET.Element("fmiModelDescription")
    root.set("fmiVersion", "2.0")
    root.set("modelName", fmu_type)
    root.set("guid", guid)
    root.set("description", description)
    root.set("generationTool", "fmu-platform build system")
    if state_info:
        root.set("numberOfEventIndicators", "0")

    # ModelExchange element
    me = ET.SubElement(root, "ModelExchange")
    me.set("modelIdentifier", fmu_type)

    # ModelVariables
    mv = ET.SubElement(root, "ModelVariables")
    vr = 1  # value reference counter (must match C code!)
    all_vars = []

    # Parameters
    for param in manifest.get("parameters", []):
        sv = ET.SubElement(mv, "ScalarVariable")
        sv.set("name", param["name"])
        sv.set("valueReference", str(vr))
        sv.set("variability", "fixed")
        sv.set("causality", "parameter")
        if param.get("description"):
            sv.set("description", param["description"])

        fmi_type = TYPE_MAP.get(param.get("type", "Real"), "Real")
        type_elem = ET.SubElement(sv, fmi_type)
        if param.get("default") is not None:
            type_elem.set("start", str(param["default"]))
        if param.get("unit"):
            type_elem.set("unit", param["unit"])

        all_vars.append({"vr": vr, "name": param["name"], "kind": "parameter"})
        vr += 1

    # Inputs
    ports = manifest.get("ports", {})
    for port in ports.get("inputs", []):
        sv = ET.SubElement(mv, "ScalarVariable")
        sv.set("name", port["name"])
        sv.set("valueReference", str(vr))
        sv.set("variability", "continuous")
        sv.set("causality", "input")

        fmi_type = TYPE_MAP.get(port.get("type", "Real"), "Real")
        type_elem = ET.SubElement(sv, fmi_type)
        type_elem.set("start", "0.0")
        if port.get("unit"):
            type_elem.set("unit", port["unit"])

        all_vars.append({"vr": vr, "name": port["name"], "kind": "input"})
        vr += 1

    # Outputs
    output_indices = []
    for port in ports.get("outputs", []):
        sv = ET.SubElement(mv, "ScalarVariable")
        sv.set("name", port["name"])
        sv.set("valueReference", str(vr))
        sv.set("variability", "continuous")
        sv.set("causality", "output")

        fmi_type = TYPE_MAP.get(port.get("type", "Real"), "Real")
        type_elem = ET.SubElement(sv, fmi_type)
        if port.get("unit"):
            type_elem.set("unit", port["unit"])

        output_indices.append(vr)
        all_vars.append({"vr": vr, "name": port["name"], "kind": "output"})
        vr += 1

    # State and derivative variables (if any)
    state_indices = []
    derivative_indices = []
    if state_info:
        for state_def in state_info["states"]:
            # State variable
            sv = ET.SubElement(mv, "ScalarVariable")
            sv.set("name", state_def["name"])
            sv.set("valueReference", str(vr))
            sv.set("variability", "continuous")
            sv.set("causality", "local")
            sv.set("initial", "exact")
            type_elem = ET.SubElement(sv, "Real")
            type_elem.set("start", str(state_def["nominal"]))
            state_vr = vr
            state_index = vr  # 1-based index = vr (since we started at 1)
            state_indices.append(state_index)
            all_vars.append({"vr": vr, "name": state_def["name"], "kind": "state"})
            vr += 1

            # Derivative variable
            sv = ET.SubElement(mv, "ScalarVariable")
            sv.set("name", state_def["derivative_name"])
            sv.set("valueReference", str(vr))
            sv.set("variability", "continuous")
            sv.set("causality", "local")
            sv.set("derivative", str(state_vr))
            type_elem = ET.SubElement(sv, "Real")
            derivative_indices.append(vr)
            all_vars.append({"vr": vr, "name": state_def["derivative_name"], "kind": "derivative"})
            vr += 1

    # ModelStructure
    ms = ET.SubElement(root, "ModelStructure")
    outputs_elem = ET.SubElement(ms, "Outputs")
    for ovr in output_indices:
        uk = ET.SubElement(outputs_elem, "Unknown")
        uk.set("index", str(ovr))

    if state_info:
        derivatives_elem = ET.SubElement(ms, "Derivatives")
        for dvr in derivative_indices:
            uk = ET.SubElement(derivatives_elem, "Unknown")
            uk.set("index", str(dvr))

        initial_unknowns = ET.SubElement(ms, "InitialUnknowns")
        for dvr in derivative_indices:
            uk = ET.SubElement(initial_unknowns, "Unknown")
            uk.set("index", str(dvr))

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def get_platform_binary_dir() -> str:
    """Get the FMI platform binary directory name."""
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "linux64"
    elif machine == "aarch64":
        return "linux64"  # FMI spec uses linux64 for aarch64 too in practice
    else:
        return f"linux_{machine}"


def compile_fmu_source(fmu_type: str, verbose: bool = False) -> Path:
    """Compile the C source for an FMU type into a shared library."""
    src_file = SRC_DIR / f"{fmu_type}.c"
    if not src_file.exists():
        raise FileNotFoundError(f"Source file not found: {src_file}")

    # Build into a temp directory
    build_dir = LIBRARY_ROOT / "build"
    build_dir.mkdir(exist_ok=True)

    output = build_dir / f"{fmu_type}.so"

    cmd = [
        CC,
        *CFLAGS,
        f"-I{INCLUDE_DIR}",
        "-o", str(output),
        str(src_file),
        *LDFLAGS,
    ]

    if verbose:
        print(f"    $ {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"  COMPILE ERROR for {fmu_type}:")
        print(result.stderr)
        raise RuntimeError(f"Compilation failed for {fmu_type}")

    if verbose and result.stderr:
        print(f"    Warnings: {result.stderr.strip()}")

    return output


def create_fmu(manifest_path: Path, clean: bool = False, verbose: bool = False) -> Path:
    """Compile source and create a functional .fmu file."""
    with open(manifest_path) as f:
        manifest = json.load(f)

    fmu_type = manifest["fmu_type"]
    version = manifest.get("version", "1.0.0")
    version_dir = manifest_path.parent
    fmu_path = version_dir / f"{fmu_type}.fmu"

    if clean and fmu_path.exists():
        fmu_path.unlink()
        print(f"  Removed: {fmu_path.name}")

    # Compile C source
    print(f"  Compiling {fmu_type}.c ...")
    so_path = compile_fmu_source(fmu_type, verbose=verbose)

    # Generate modelDescription.xml
    guid = generate_guid(fmu_type, version)
    xml_content = manifest_to_model_description(manifest, guid)

    # Package as FMU (ZIP)
    bin_dir = get_platform_binary_dir()

    with ZipFile(fmu_path, "w", ZIP_DEFLATED) as zf:
        zf.writestr("modelDescription.xml", xml_content)
        zf.write(so_path, f"binaries/{bin_dir}/{fmu_type}.so")

    print(f"  Created: {fmu_path.relative_to(LIBRARY_ROOT)}")
    return fmu_path


def main():
    clean = "--clean" in sys.argv
    verbose = "--verbose" in sys.argv

    print("Building functional FMU files from C sources...\n")

    # Check compiler
    try:
        result = subprocess.run([CC, "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error: C compiler '{CC}' not found. Install gcc or set CC env var.")
            return 1
    except FileNotFoundError:
        print(f"Error: C compiler '{CC}' not found. Install gcc or set CC env var.")
        return 1

    manifests = sorted(LIBRARY_ROOT.glob("*/v*/manifest.json"))
    if not manifests:
        print("No manifest.json files found!")
        return 1

    # Check all source files exist
    missing = []
    for manifest_path in manifests:
        fmu_type = manifest_path.parent.parent.name
        src_file = SRC_DIR / f"{fmu_type}.c"
        if not src_file.exists():
            missing.append(fmu_type)

    if missing:
        print(f"Warning: Missing C source files for: {', '.join(missing)}")
        print("These FMUs will be skipped.\n")

    created = []
    failed = []
    for manifest_path in manifests:
        fmu_type = manifest_path.parent.parent.name
        version = manifest_path.parent.name
        src_file = SRC_DIR / f"{fmu_type}.c"

        if not src_file.exists():
            continue

        print(f"[{fmu_type} {version}]")
        try:
            fmu_path = create_fmu(manifest_path, clean=clean, verbose=verbose)
            created.append(fmu_path)
        except Exception as e:
            print(f"  FAILED: {e}")
            failed.append(fmu_type)

    # Clean up build directory
    build_dir = LIBRARY_ROOT / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)

    print(f"\nDone. Built {len(created)} FMUs successfully.")
    if failed:
        print(f"Failed: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
