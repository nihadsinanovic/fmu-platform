#!/usr/bin/env python3
"""Generate stub FMI 2.0 Model Exchange .fmu files from manifest.json files.

Each .fmu is a ZIP containing a modelDescription.xml that declares the FMU's
variables (parameters, inputs, outputs) according to the FMI 2.0 standard.
These stubs have no actual simulation code — they exist so the composition
engine and SSP generator can work with real FMU files during development
and testing.

Usage:
    python generate_stub_fmus.py          # generates all stubs
    python generate_stub_fmus.py --clean   # removes existing .fmu files first
"""

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

LIBRARY_ROOT = Path(__file__).parent

# FMI type mapping: manifest type → modelDescription variability/causality
TYPE_MAP = {
    "Real": "Real",
    "Integer": "Integer",
    "Boolean": "Boolean",
    "String": "String",
}


def manifest_to_model_description(manifest: dict, guid: str) -> str:
    """Convert a manifest.json dict to FMI 2.0 modelDescription.xml content."""

    fmu_type = manifest["fmu_type"]
    description = manifest.get("description", "")

    root = ET.Element("fmiModelDescription")
    root.set("fmiVersion", "2.0")
    root.set("modelName", fmu_type)
    root.set("guid", guid)
    root.set("description", description)
    root.set("generationTool", "fmu-platform stub generator")

    # ModelExchange element
    me = ET.SubElement(root, "ModelExchange")
    me.set("modelIdentifier", fmu_type)

    # ModelVariables
    mv = ET.SubElement(root, "ModelVariables")
    vr = 1  # value reference counter

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

        all_vars.append((vr, param["name"]))
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

        all_vars.append((vr, port["name"]))
        vr += 1

    # Outputs
    output_vrs = []
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

        output_vrs.append(vr)
        all_vars.append((vr, port["name"]))
        vr += 1

    # ModelStructure
    ms = ET.SubElement(root, "ModelStructure")
    outputs_elem = ET.SubElement(ms, "Outputs")
    for ovr in output_vrs:
        uk = ET.SubElement(outputs_elem, "Unknown")
        uk.set("index", str(ovr))

    # Pretty-print
    ET.indent(root, space="  ")
    xml_str = ET.tostring(root, encoding="unicode", xml_declaration=True)
    return xml_str


def generate_guid(fmu_type: str, version: str) -> str:
    """Generate a deterministic GUID for a stub FMU."""
    import hashlib
    h = hashlib.sha256(f"{fmu_type}-{version}-stub".encode()).hexdigest()
    # Format as UUID-like string
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def create_stub_fmu(manifest_path: Path, clean: bool = False) -> Path:
    """Create a stub .fmu ZIP file from a manifest.json."""
    with open(manifest_path) as f:
        manifest = json.load(f)

    fmu_type = manifest["fmu_type"]
    version = manifest.get("version", "1.0.0")
    version_dir = manifest_path.parent
    fmu_path = version_dir / f"{fmu_type}.fmu"

    if clean and fmu_path.exists():
        fmu_path.unlink()
        print(f"  Removed: {fmu_path.name}")

    guid = generate_guid(fmu_type, version)
    xml_content = manifest_to_model_description(manifest, guid)

    with ZipFile(fmu_path, "w") as zf:
        zf.writestr("modelDescription.xml", xml_content)
        # Create empty binary directories (expected by FMI spec)
        zf.writestr("binaries/linux64/.gitkeep", "")
        zf.writestr("binaries/win64/.gitkeep", "")

    print(f"  Created: {fmu_path.relative_to(LIBRARY_ROOT)}")
    return fmu_path


def main():
    clean = "--clean" in sys.argv

    print("Generating stub FMU files from manifests...\n")

    manifests = sorted(LIBRARY_ROOT.glob("*/v*/manifest.json"))
    if not manifests:
        print("No manifest.json files found!")
        return 1

    created = []
    for manifest_path in manifests:
        fmu_type = manifest_path.parent.parent.name
        version = manifest_path.parent.name
        print(f"[{fmu_type} {version}]")
        fmu_path = create_stub_fmu(manifest_path, clean=clean)
        created.append(fmu_path)

    print(f"\nDone. Generated {len(created)} stub FMU files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
