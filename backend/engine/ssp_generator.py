"""Build SSP (System Structure and Parameterization) packages."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from engine.connection_resolver import ConnectionGraph, FMUInstance

SSP_NS = "http://ssp-standard.org/SSP1/SystemStructureDescription"
NSMAP = {"ssd": SSP_NS}


class SSPGenerator:
    """Generate .ssp ZIP archive from a connection graph."""

    def __init__(self, fmu_library_path: Path):
        self.fmu_library_path = fmu_library_path

    def generate(
        self,
        graph: ConnectionGraph,
        topology: dict[str, Any],
        output_path: Path,
        simulation_config: dict[str, Any] | None = None,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Generate and write SystemStructure.ssd
            ssd_xml = self._generate_ssd(graph, simulation_config)
            zf.writestr("SystemStructure.ssd", ssd_xml)

            # Copy FMU files into resources/
            self._add_fmu_resources(zf, graph)

            # Generate parameter files
            ssv_xml = self._generate_ssv(graph)
            zf.writestr("parameters/system_parameters.ssv", ssv_xml)

            # Include original topology
            zf.writestr("extra/topology.json", json.dumps(topology, indent=2))

        return output_path

    def _generate_ssd(
        self,
        graph: ConnectionGraph,
        simulation_config: dict[str, Any] | None = None,
    ) -> str:
        root = etree.Element(f"{{{SSP_NS}}}SystemStructureDescription", nsmap=NSMAP)
        root.set("name", "AmbientLoopBuilding")
        root.set("version", "1.0")

        system = etree.SubElement(root, f"{{{SSP_NS}}}System")
        system.set("name", "Building")

        # Elements (components)
        elements = etree.SubElement(system, f"{{{SSP_NS}}}Elements")
        for instance in graph.instances:
            component = etree.SubElement(elements, f"{{{SSP_NS}}}Component")
            component.set("name", instance.name)
            component.set("type", "application/x-fmu-sharedlibrary")
            component.set("source", f"resources/{instance.fmu_type}.fmu")

            connectors = etree.SubElement(component, f"{{{SSP_NS}}}Connectors")
            self._add_connectors(connectors, instance, graph)

        # Connections
        connections_el = etree.SubElement(system, f"{{{SSP_NS}}}Connections")
        for conn in graph.connections:
            conn_el = etree.SubElement(connections_el, f"{{{SSP_NS}}}Connection")
            conn_el.set("startElement", conn.source_instance)
            conn_el.set("startConnector", conn.source_port)
            conn_el.set("endElement", conn.target_instance)
            conn_el.set("endConnector", conn.target_port)

        # Default experiment
        if simulation_config:
            experiment = etree.SubElement(root, f"{{{SSP_NS}}}DefaultExperiment")
            experiment.set("startTime", str(simulation_config.get("start_time", 0)))
            experiment.set("stopTime", str(simulation_config.get("end_time", 31536000)))

        return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8").decode()

    def _add_connectors(
        self,
        connectors_el: etree._Element,
        instance: FMUInstance,
        graph: ConnectionGraph,
    ) -> None:
        # Collect ports used by this instance from connections
        output_ports: set[str] = set()
        input_ports: set[str] = set()

        for conn in graph.connections:
            if conn.source_instance == instance.name:
                output_ports.add(conn.source_port)
            if conn.target_instance == instance.name:
                input_ports.add(conn.target_port)

        for port in sorted(output_ports):
            el = etree.SubElement(connectors_el, f"{{{SSP_NS}}}Connector")
            el.set("name", port)
            el.set("kind", "output")

        for port in sorted(input_ports):
            el = etree.SubElement(connectors_el, f"{{{SSP_NS}}}Connector")
            el.set("name", port)
            el.set("kind", "input")

    def _add_fmu_resources(self, zf: zipfile.ZipFile, graph: ConnectionGraph) -> None:
        added_types: set[str] = set()
        for instance in graph.instances:
            if instance.fmu_type in added_types:
                continue
            added_types.add(instance.fmu_type)

            fmu_file = self.fmu_library_path / instance.fmu_type / f"{instance.fmu_type}.fmu"
            if fmu_file.exists():
                zf.write(fmu_file, f"resources/{instance.fmu_type}.fmu")

    def _generate_ssv(self, graph: ConnectionGraph) -> str:
        """Generate SSV (System Structure Values) XML for all instance parameters."""
        root = etree.Element("ParameterSet")
        root.set("version", "1.0")
        root.set("name", "SystemParameters")

        for instance in graph.instances:
            if not instance.parameters:
                continue
            for param_name, value in instance.parameters.items():
                param_el = etree.SubElement(root, "Parameter")
                param_el.set("name", f"{instance.name}.{param_name}")

                if isinstance(value, float):
                    real_el = etree.SubElement(param_el, "Real")
                    real_el.set("value", str(value))
                elif isinstance(value, int):
                    int_el = etree.SubElement(param_el, "Integer")
                    int_el.set("value", str(value))
                elif isinstance(value, str):
                    str_el = etree.SubElement(param_el, "String")
                    str_el.set("value", value)

        return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8").decode()
