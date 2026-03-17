"""High-level composition engine that orchestrates the full pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.connection_resolver import ConnectionGraph, ConnectionResolver
from engine.ssp_generator import SSPGenerator
from engine.topology_parser import ParsedTopology, SimulationConfig, TopologyParser
from engine.validator import SystemValidator, ValidationResult


@dataclass
class ComposedSystem:
    topology: ParsedTopology
    graph: ConnectionGraph
    validation: ValidationResult
    ssp_path: Path | None = None


class CompositionEngine:
    """Transform a building topology JSON into a composed SSP package."""

    def __init__(self, fmu_library_path: Path, manifests: dict | None = None):
        self.fmu_library_path = fmu_library_path
        self.manifests = manifests or {}

    def compose(self, topology: dict[str, Any], output_path: Path) -> ComposedSystem:
        # Step 1: Parse topology
        parsed = TopologyParser.parse(topology)

        # Step 2: Resolve connections
        resolver = ConnectionResolver()
        graph = resolver.resolve(parsed.building)

        # Step 3: Validate
        validator = SystemValidator(self.manifests)
        validation = validator.validate(graph)

        # Step 4: Generate SSP package
        ssp_gen = SSPGenerator(self.fmu_library_path)
        sim_config = {
            "start_time": parsed.simulation.start_time,
            "end_time": parsed.simulation.end_time,
            "step_size": parsed.simulation.step_size,
        }
        ssp_path = ssp_gen.generate(graph, topology, output_path, sim_config)

        return ComposedSystem(
            topology=parsed,
            graph=graph,
            validation=validation,
            ssp_path=ssp_path,
        )
