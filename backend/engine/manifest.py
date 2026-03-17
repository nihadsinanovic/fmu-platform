"""Load and parse FMU manifest files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PortDefinition:
    name: str
    type: str  # "Real", "Integer", "Boolean", "String"
    unit: str = ""
    domain: str = ""


@dataclass
class ParameterDefinition:
    name: str
    type: str
    default: Any = None
    unit: str = ""
    min: float | None = None
    max: float | None = None


@dataclass
class FMUManifest:
    fmu_type: str
    fmi_version: str = "2.0"
    fmi_type: str = "ModelExchange"
    version: str = "1.0.0"
    parameters: list[ParameterDefinition] = field(default_factory=list)
    inputs: list[PortDefinition] = field(default_factory=list)
    outputs: list[PortDefinition] = field(default_factory=list)
    compatible_connections: dict[str, list[str]] = field(default_factory=dict)

    def get_parameter(self, name: str) -> ParameterDefinition | None:
        for p in self.parameters:
            if p.name == name:
                return p
        return None

    def get_input_port(self, name: str) -> PortDefinition | None:
        for p in self.inputs:
            if p.name == name:
                return p
        return None

    def get_output_port(self, name: str) -> PortDefinition | None:
        for p in self.outputs:
            if p.name == name:
                return p
        return None


def load_manifest(path: Path) -> FMUManifest:
    with open(path) as f:
        data = json.load(f)
    return parse_manifest(data)


def parse_manifest(data: dict) -> FMUManifest:
    parameters = [
        ParameterDefinition(
            name=p["name"],
            type=p.get("type", "Real"),
            default=p.get("default"),
            unit=p.get("unit", ""),
            min=p.get("min"),
            max=p.get("max"),
        )
        for p in data.get("parameters", [])
    ]

    ports = data.get("ports", {})
    inputs = [
        PortDefinition(
            name=p["name"],
            type=p.get("type", "Real"),
            unit=p.get("unit", ""),
            domain=p.get("domain", ""),
        )
        for p in ports.get("inputs", [])
    ]
    outputs = [
        PortDefinition(
            name=p["name"],
            type=p.get("type", "Real"),
            unit=p.get("unit", ""),
            domain=p.get("domain", ""),
        )
        for p in ports.get("outputs", [])
    ]

    return FMUManifest(
        fmu_type=data["fmu_type"],
        fmi_version=data.get("fmi_version", "2.0"),
        fmi_type=data.get("fmi_type", "ModelExchange"),
        version=data.get("version", "1.0.0"),
        parameters=parameters,
        inputs=inputs,
        outputs=outputs,
        compatible_connections=data.get("compatible_connections", {}),
    )
