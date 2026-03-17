"""Validate composed FMU system for correctness."""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.connection_resolver import ConnectionGraph
from engine.manifest import FMUManifest


@dataclass
class ValidationResult:
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


class SystemValidator:
    """Validate a composed FMU system."""

    def __init__(self, manifests: dict[str, FMUManifest]):
        self.manifests = manifests

    def validate(self, graph: ConnectionGraph) -> ValidationResult:
        result = ValidationResult()

        self._check_fmu_types_exist(graph, result)
        self._check_no_orphan_instances(graph, result)
        self._check_connection_references(graph, result)
        self._check_port_types_match(graph, result)

        return result

    def _check_fmu_types_exist(self, graph: ConnectionGraph, result: ValidationResult) -> None:
        for instance in graph.instances:
            if instance.fmu_type not in self.manifests:
                result.add_error(
                    f"Instance '{instance.name}': FMU type '{instance.fmu_type}' "
                    f"not found in library"
                )

    def _check_no_orphan_instances(self, graph: ConnectionGraph, result: ValidationResult) -> None:
        connected_instances = set()
        for conn in graph.connections:
            connected_instances.add(conn.source_instance)
            connected_instances.add(conn.target_instance)

        for instance in graph.instances:
            if instance.name not in connected_instances:
                result.add_warning(f"Instance '{instance.name}' has no connections")

    def _check_connection_references(
        self, graph: ConnectionGraph, result: ValidationResult
    ) -> None:
        instance_names = {inst.name for inst in graph.instances}
        for conn in graph.connections:
            if conn.source_instance not in instance_names:
                result.add_error(
                    f"Connection references unknown source instance '{conn.source_instance}'"
                )
            if conn.target_instance not in instance_names:
                result.add_error(
                    f"Connection references unknown target instance '{conn.target_instance}'"
                )

    def _check_port_types_match(self, graph: ConnectionGraph, result: ValidationResult) -> None:
        instance_types = {inst.name: inst.fmu_type for inst in graph.instances}

        for conn in graph.connections:
            src_type = instance_types.get(conn.source_instance)
            tgt_type = instance_types.get(conn.target_instance)
            if not src_type or not tgt_type:
                continue

            src_manifest = self.manifests.get(src_type)
            tgt_manifest = self.manifests.get(tgt_type)
            if not src_manifest or not tgt_manifest:
                continue

            # Strip array index for port lookup (e.g., "hydr_out_T[0]" → "hydr_out_T")
            src_port_name = conn.source_port.split("[")[0]
            tgt_port_name = conn.target_port.split("[")[0]

            src_port = src_manifest.get_output_port(src_port_name)
            tgt_port = tgt_manifest.get_input_port(tgt_port_name)

            if src_port and tgt_port and src_port.type != tgt_port.type:
                result.add_error(
                    f"Type mismatch: {conn.source_instance}.{conn.source_port} "
                    f"({src_port.type}) → {conn.target_instance}.{conn.target_port} "
                    f"({tgt_port.type})"
                )
