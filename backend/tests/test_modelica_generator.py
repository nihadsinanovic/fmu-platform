"""Tests for the Modelica system-model generator."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from engine.modelica_generator import generate

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "fmu-library" / "examples"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_example(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text())


class TestGoldenFixture:
    def test_small_building_matches_fixture(self):
        topology = _load_example("small_building_2floors.json")
        generated = generate(topology, model_name="SmallBuilding2Floors")
        golden = (FIXTURES_DIR / "small_building_2floors.mo").read_text()
        assert generated == golden, (
            "Generated output drifted from golden fixture. If this is intentional, "
            "regenerate via:\n"
            "  python -c 'from engine.modelica_generator import generate; "
            "import json, pathlib; "
            "p=pathlib.Path(\"tests/fixtures/small_building_2floors.mo\"); "
            "p.write_text(generate(json.load(open(\"../fmu-library/examples/"
            "small_building_2floors.json\")), model_name=\"SmallBuilding2Floors\"))'"
        )


class TestStructuralAssertions:
    """Run the generator on medium_building_3floors.json and check the shape of the output."""

    @pytest.fixture
    def generated(self) -> str:
        topology = _load_example("medium_building_3floors.json")
        return generate(topology, model_name="MediumBuilding3Floors")

    @pytest.fixture
    def topology(self) -> dict:
        return _load_example("medium_building_3floors.json")

    def test_singletons(self, generated: str):
        assert generated.count("FMUPlatform.Components.WeatherSource weather(") == 1
        assert generated.count("FMUPlatform.Components.CentralHeatPump centralHp(") == 1
        assert generated.count("FMUPlatform.Components.AmbientLoopSegment mainSupply(") == 1
        assert generated.count("FMUPlatform.Components.AmbientLoopSegment mainReturn(") == 1
        assert generated.count("FMUPlatform.Components.LoopTee floorTee(") == 1

    def test_apartment_counts(self, generated: str, topology: dict):
        total_apts = sum(len(f["apartments"]) for f in topology["building"]["floors"])
        hp_decls = re.findall(r"FMUPlatform\.Components\.ApartmentHeatPump (apt_\d+_\d+_hp)\(", generated)
        zone_decls = re.findall(r"FMUPlatform\.Components\.ApartmentThermalZone (apt_\d+_\d+_zone)\(", generated)
        assert len(hp_decls) == total_apts
        assert len(zone_decls) == total_apts
        # Every HP has a matching zone of the same prefix.
        hp_prefixes = {name.removesuffix("_hp") for name in hp_decls}
        zone_prefixes = {name.removesuffix("_zone") for name in zone_decls}
        assert hp_prefixes == zone_prefixes

    def test_central_supply_chain_connects(self, generated: str):
        assert "connect(centralHp.port_b, mainSupply.port_a);" in generated
        assert "connect(mainSupply.port_b, floorTee.port_supplyIn);" in generated
        assert "connect(mainReturn.port_b, centralHp.port_a);" in generated

    def test_per_apartment_wiring(self, generated: str, topology: dict):
        for floor in topology["building"]["floors"]:
            f = floor["floor_number"]
            for idx, _ in enumerate(floor["apartments"], start=1):
                name = f"apt_{f}_{idx}"
                assert f"connect({name}_hp.heatPortCon, {name}_zone.heatPortInt);" in generated
                assert f"connect({name}_zone.TZone, {name}_hp.TZone);" in generated
                assert f"connect({name}_TSet.y, {name}_hp.TZoneSet);" in generated
                assert f"connect(weather.TDryBul, {name}_zone.TDryBul);" in generated
                assert f"connect(weather.HGloHor, {name}_zone.HGloHor);" in generated

    def test_floor_tee_branch_count(self, generated: str, topology: dict):
        n_floors = len(topology["building"]["floors"])
        assert f"FMUPlatform.Components.LoopTee floorTee(n_branches={n_floors});" in generated

    def test_apt_tee_branch_counts(self, generated: str, topology: dict):
        for floor in topology["building"]["floors"]:
            f = floor["floor_number"]
            n_apt = len(floor["apartments"])
            assert f"FMUPlatform.Components.LoopTee aptTee_{f}(n_branches={n_apt});" in generated


class TestDeterminism:
    def test_byte_identical_across_runs(self):
        topology = _load_example("small_building_2floors.json")
        first = generate(topology, model_name="SmallBuilding2Floors")
        second = generate(topology, model_name="SmallBuilding2Floors")
        assert first == second


class TestParameterSubstitution:
    def test_central_hp_power_kW_to_W(self, sample_topology):
        # sample_topology fixture has nominal_power_kW=120 at central HP
        topo = copy.deepcopy(sample_topology)
        generated = generate(topo, model_name="Sample")
        assert "Q_flow_nominal_W=120000" in generated

    def test_apartment_hp_power_kW_to_W(self, sample_topology):
        # First apartment in sample_topology has nominal_power_kW=5
        topo = copy.deepcopy(sample_topology)
        generated = generate(topo, model_name="Sample")
        assert "Q_flow_nominal_W=5000" in generated

    def test_pipe_dimensions_passed_through(self, sample_topology):
        topo = copy.deepcopy(sample_topology)
        generated = generate(topo, model_name="Sample")
        # Main pipe in sample_topology: length_m=40, diameter_mm=80, insulation=30
        assert "length_m=40" in generated
        assert "diameter_mm=80" in generated
        assert "insulation_thickness_mm=30" in generated

    def test_simulation_window_in_experiment_annotation(self, sample_topology):
        topo = copy.deepcopy(sample_topology)
        generated = generate(topo, model_name="Sample")
        assert "StartTime=0" in generated
        assert "StopTime=31536000" in generated
        assert "Interval=3600" in generated
