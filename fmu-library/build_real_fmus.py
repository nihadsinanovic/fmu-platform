#!/usr/bin/env python3
"""Build real FMI 2.0 Model Exchange FMUs with C physics implementations.

Reads each manifest.json, generates a matching modelDescription.xml,
compiles the C source to a shared library, and packages everything
into a .fmu ZIP file.

Usage:
    python build_real_fmus.py          # build all FMUs
    python build_real_fmus.py --clean  # remove build artifacts first

Requires: gcc
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

LIBRARY_ROOT = Path(__file__).parent
SRC_DIR = LIBRARY_ROOT / "src"
BUILD_DIR = LIBRARY_ROOT / "build"

MAX_BRANCHES = 10  # for loop_tee array port expansion

# FMU types that have continuous states
STATEFUL_FMUS = {
    "apartment_thermal_zone": {
        "states": [("T_room", 10)],  # (name, output VR that mirrors this state)
        "nominals": [293.15],
    },
    "ambient_loop_segment": {
        "states": [("T_fluid", 7)],  # VR of hydr_out_T
        "nominals": [285.0],
    },
}


def generate_guid(fmu_type: str, version: str) -> str:
    """Generate a deterministic GUID for an FMU."""
    h = hashlib.sha256(f"{fmu_type}-{version}-real".encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def expand_loop_tee_ports(manifest: dict) -> dict:
    """Expand [*] array ports in loop_tee manifest to indexed ports [0]..[9]."""
    if manifest["fmu_type"] != "loop_tee":
        return manifest

    manifest = json.loads(json.dumps(manifest))  # deep copy
    new_inputs = []
    new_outputs = []

    for port in manifest["ports"]["inputs"]:
        if "[*]" in port["name"]:
            base = port["name"].replace("[*]", "")
            for i in range(MAX_BRANCHES):
                p = dict(port)
                p["name"] = f"{base}[{i}]"
                new_inputs.append(p)
        else:
            new_inputs.append(port)

    for port in manifest["ports"]["outputs"]:
        if "[*]" in port["name"]:
            base = port["name"].replace("[*]", "")
            for i in range(MAX_BRANCHES):
                p = dict(port)
                p["name"] = f"{base}[{i}]"
                new_outputs.append(p)
        else:
            new_outputs.append(port)

    manifest["ports"]["inputs"] = new_inputs
    manifest["ports"]["outputs"] = new_outputs
    return manifest


def manifest_to_model_description(manifest: dict, guid: str) -> str:
    """Generate FMI 2.0 modelDescription.xml from manifest."""
    fmu_type = manifest["fmu_type"]
    description = manifest.get("description", "")

    root = ET.Element("fmiModelDescription")
    root.set("fmiVersion", "2.0")
    root.set("modelName", fmu_type)
    root.set("guid", guid)
    root.set("description", description)
    root.set("generationTool", "fmu-platform build_real_fmus.py")

    # Count states
    state_info = STATEFUL_FMUS.get(fmu_type, {})
    n_states = len(state_info.get("states", []))
    if n_states > 0:
        root.set("numberOfEventIndicators", "0")

    # ModelExchange element
    me = ET.SubElement(root, "ModelExchange")
    me.set("modelIdentifier", fmu_type)

    # ModelVariables
    mv = ET.SubElement(root, "ModelVariables")
    vr = 0
    all_vars = []
    output_vrs = []
    state_vrs = []
    derivative_vrs = []

    # Parameters
    for param in manifest.get("parameters", []):
        sv = ET.SubElement(mv, "ScalarVariable")
        sv.set("name", param["name"])
        sv.set("valueReference", str(vr))
        sv.set("variability", "fixed")
        sv.set("causality", "parameter")
        if param.get("description"):
            sv.set("description", param["description"])

        fmi_type = param.get("type", "Real")
        type_elem = ET.SubElement(sv, fmi_type)
        if param.get("default") is not None:
            type_elem.set("start", str(param["default"]))
        if param.get("unit"):
            type_elem.set("unit", param["unit"])

        all_vars.append((vr, param["name"], "parameter"))
        vr += 1

    # Inputs
    for port in manifest["ports"].get("inputs", []):
        sv = ET.SubElement(mv, "ScalarVariable")
        sv.set("name", port["name"])
        sv.set("valueReference", str(vr))
        sv.set("variability", "continuous")
        sv.set("causality", "input")

        fmi_type = port.get("type", "Real")
        type_elem = ET.SubElement(sv, fmi_type)
        type_elem.set("start", "0.0")
        if port.get("unit"):
            type_elem.set("unit", port["unit"])

        all_vars.append((vr, port["name"], "input"))
        vr += 1

    # Outputs
    for port in manifest["ports"].get("outputs", []):
        sv = ET.SubElement(mv, "ScalarVariable")
        sv.set("name", port["name"])
        sv.set("valueReference", str(vr))
        sv.set("variability", "continuous")
        sv.set("causality", "output")

        fmi_type = port.get("type", "Real")
        type_elem = ET.SubElement(sv, fmi_type)
        if port.get("unit"):
            type_elem.set("unit", port["unit"])

        output_vrs.append(vr)
        all_vars.append((vr, port["name"], "output"))
        vr += 1

    # State variables (hidden — used internally by solver)
    for i, (state_name, _mirror_vr) in enumerate(state_info.get("states", [])):
        # Continuous state
        sv = ET.SubElement(mv, "ScalarVariable")
        sv.set("name", f"_state_{state_name}")
        sv.set("valueReference", str(vr))
        sv.set("variability", "continuous")
        sv.set("causality", "local")
        sv.set("initial", "exact")
        type_elem = ET.SubElement(sv, "Real")
        type_elem.set("start", str(state_info["nominals"][i]))
        state_vrs.append(vr)
        all_vars.append((vr, f"_state_{state_name}", "state"))
        vr += 1

        # Derivative
        sv = ET.SubElement(mv, "ScalarVariable")
        sv.set("name", f"_der_{state_name}")
        sv.set("valueReference", str(vr))
        sv.set("variability", "continuous")
        sv.set("causality", "local")
        type_elem = ET.SubElement(sv, "Real")
        type_elem.set("derivative", str(state_vrs[-1] + 1))  # 1-based index
        derivative_vrs.append(vr)
        all_vars.append((vr, f"_der_{state_name}", "derivative"))
        vr += 1

    # ModelStructure
    ms = ET.SubElement(root, "ModelStructure")

    outputs_elem = ET.SubElement(ms, "Outputs")
    for ovr in output_vrs:
        uk = ET.SubElement(outputs_elem, "Unknown")
        uk.set("index", str(ovr + 1))  # 1-based

    if state_vrs:
        derivs_elem = ET.SubElement(ms, "Derivatives")
        for dvr in derivative_vrs:
            uk = ET.SubElement(derivs_elem, "Unknown")
            uk.set("index", str(dvr + 1))  # 1-based

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def compile_fmu(fmu_type: str) -> Path:
    """Compile C source to shared library."""
    src_file = SRC_DIR / f"{fmu_type}.c"
    if not src_file.exists():
        raise FileNotFoundError(f"No C source: {src_file}")

    build_type_dir = BUILD_DIR / fmu_type
    build_type_dir.mkdir(parents=True, exist_ok=True)

    so_file = build_type_dir / f"{fmu_type}.so"

    cmd = [
        "gcc",
        "-shared", "-fPIC",
        "-fvisibility=hidden",
        "-O2",
        "-o", str(so_file),
        "-I", str(SRC_DIR),
        str(src_file),
        "-lm",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  COMPILE ERROR for {fmu_type}:")
        print(result.stderr)
        raise RuntimeError(f"Compilation failed for {fmu_type}")

    print(f"  Compiled: {so_file.name} ({so_file.stat().st_size} bytes)")
    return so_file


def package_fmu(fmu_type: str, manifest: dict, version: str) -> Path:
    """Generate modelDescription.xml, compile, and package into .fmu."""
    guid = generate_guid(fmu_type, version)

    # Expand array ports for loop_tee
    expanded_manifest = expand_loop_tee_ports(manifest)

    # Generate modelDescription.xml
    xml_content = manifest_to_model_description(expanded_manifest, guid)

    # Compile C source
    so_file = compile_fmu(fmu_type)

    # Package .fmu
    version_dir = LIBRARY_ROOT / fmu_type / f"v{version}"
    fmu_path = version_dir / f"{fmu_type}.fmu"

    with ZipFile(fmu_path, "w", ZIP_DEFLATED) as zf:
        zf.writestr("modelDescription.xml", xml_content)
        zf.write(so_file, f"binaries/linux64/{fmu_type}.so")

    print(f"  Packaged: {fmu_path.relative_to(LIBRARY_ROOT)} ({fmu_path.stat().st_size} bytes)")
    return fmu_path


def clean():
    """Remove build artifacts."""
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
        print("Cleaned build directory.")


def main():
    if "--clean" in sys.argv:
        clean()
        if len(sys.argv) == 2:
            return 0

    BUILD_DIR.mkdir(exist_ok=True)

    print("Building real FMI 2.0 Model Exchange FMUs...\n")

    manifests = sorted(LIBRARY_ROOT.glob("*/v*/manifest.json"))
    if not manifests:
        print("No manifest.json files found!")
        return 1

    built = []
    errors = []

    for manifest_path in manifests:
        fmu_type = manifest_path.parent.parent.name
        version_str = manifest_path.parent.name.lstrip("v")

        # Check if C source exists
        src_file = SRC_DIR / f"{fmu_type}.c"
        if not src_file.exists():
            print(f"[{fmu_type} v{version_str}] SKIP — no C source at {src_file.name}")
            continue

        print(f"[{fmu_type} v{version_str}]")

        with open(manifest_path) as f:
            manifest = json.load(f)

        try:
            fmu_path = package_fmu(fmu_type, manifest, version_str)
            built.append(fmu_path)
        except Exception as e:
            print(f"  ERROR: {e}")
            errors.append((fmu_type, str(e)))

    print(f"\nDone. Built {len(built)} FMUs.")
    if errors:
        print(f"Errors ({len(errors)}):")
        for fmu_type, err in errors:
            print(f"  - {fmu_type}: {err}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
