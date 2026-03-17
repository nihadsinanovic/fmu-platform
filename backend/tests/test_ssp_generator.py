"""Tests for SSP generation."""

import tempfile
import zipfile
from pathlib import Path

from lxml import etree

from engine.connection_resolver import ConnectionResolver
from engine.ssp_generator import SSPGenerator
from engine.topology_parser import TopologyParser


class TestSSPGenerator:
    def test_generates_ssp_file(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.ssp"
            gen = SSPGenerator(fmu_library_path=Path(tmpdir) / "fmu-library")
            gen.generate(graph, sample_topology, output)
            assert output.exists()

    def test_ssp_is_valid_zip(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.ssp"
            gen = SSPGenerator(fmu_library_path=Path(tmpdir) / "fmu-library")
            gen.generate(graph, sample_topology, output)
            assert zipfile.is_zipfile(output)

    def test_ssp_contains_ssd(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.ssp"
            gen = SSPGenerator(fmu_library_path=Path(tmpdir) / "fmu-library")
            gen.generate(graph, sample_topology, output)

            with zipfile.ZipFile(output) as zf:
                names = zf.namelist()
                assert "SystemStructure.ssd" in names

    def test_ssp_contains_topology(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.ssp"
            gen = SSPGenerator(fmu_library_path=Path(tmpdir) / "fmu-library")
            gen.generate(graph, sample_topology, output)

            with zipfile.ZipFile(output) as zf:
                assert "extra/topology.json" in zf.namelist()

    def test_ssp_contains_ssv(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.ssp"
            gen = SSPGenerator(fmu_library_path=Path(tmpdir) / "fmu-library")
            gen.generate(graph, sample_topology, output)

            with zipfile.ZipFile(output) as zf:
                assert "parameters/system_parameters.ssv" in zf.namelist()

    def test_ssd_has_valid_xml(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.ssp"
            gen = SSPGenerator(fmu_library_path=Path(tmpdir) / "fmu-library")
            gen.generate(graph, sample_topology, output)

            with zipfile.ZipFile(output) as zf:
                ssd_xml = zf.read("SystemStructure.ssd")
                root = etree.fromstring(ssd_xml)
                assert root.tag.endswith("SystemStructureDescription")

    def test_ssd_contains_components(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.ssp"
            gen = SSPGenerator(fmu_library_path=Path(tmpdir) / "fmu-library")
            gen.generate(graph, sample_topology, output)

            with zipfile.ZipFile(output) as zf:
                ssd_xml = zf.read("SystemStructure.ssd")
                ns = {"ssd": "http://ssp-standard.org/SSP1/SystemStructureDescription"}
                root = etree.fromstring(ssd_xml)
                components = root.xpath("//ssd:Component", namespaces=ns)
                assert len(components) == len(graph.instances)

    def test_ssd_contains_connections(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.ssp"
            gen = SSPGenerator(fmu_library_path=Path(tmpdir) / "fmu-library")
            gen.generate(graph, sample_topology, output)

            with zipfile.ZipFile(output) as zf:
                ssd_xml = zf.read("SystemStructure.ssd")
                ns = {"ssd": "http://ssp-standard.org/SSP1/SystemStructureDescription"}
                root = etree.fromstring(ssd_xml)
                connections = root.xpath("//ssd:Connection", namespaces=ns)
                assert len(connections) == len(graph.connections)
