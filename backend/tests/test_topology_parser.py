"""Tests for the topology parser."""

from engine.topology_parser import TopologyParser


class TestTopologyParser:
    def test_parse_building_name(self, sample_topology):
        result = TopologyParser.parse(sample_topology)
        assert result.building.name == "Test Building"

    def test_parse_location(self, sample_topology):
        result = TopologyParser.parse(sample_topology)
        assert result.building.location.lat == 45.19
        assert result.building.location.lon == 5.72
        assert result.building.location.climate_zone == "H1c"

    def test_parse_central_heatpump(self, sample_topology):
        result = TopologyParser.parse(sample_topology)
        hp = result.building.central_heatpump
        assert hp.nominal_power_kW == 120
        assert hp.COP_nominal == 3.8
        assert hp.source_type == "ground"

    def test_parse_ambient_loop(self, sample_topology):
        result = TopologyParser.parse(sample_topology)
        loop = result.building.ambient_loop
        assert loop.length_m == 40
        assert loop.diameter_mm == 80
        assert loop.insulation_thickness_mm == 30

    def test_parse_floors(self, sample_topology):
        result = TopologyParser.parse(sample_topology)
        assert len(result.building.floors) == 2

    def test_parse_apartments(self, sample_topology):
        result = TopologyParser.parse(sample_topology)
        floor_0 = result.building.floors[0]
        assert len(floor_0.apartments) == 2
        assert floor_0.apartments[0].id == "apt_0_1"
        assert floor_0.apartments[0].floor_area_m2 == 45
        assert floor_0.apartments[0].orientation == "south"

    def test_parse_apartment_heatpump(self, sample_topology):
        result = TopologyParser.parse(sample_topology)
        apt = result.building.floors[0].apartments[0]
        assert apt.heatpump.nominal_power_kW == 5
        assert apt.heatpump.COP_nominal == 4.2

    def test_parse_thermal_zone(self, sample_topology):
        result = TopologyParser.parse(sample_topology)
        tz = result.building.floors[0].apartments[0].thermal_zone
        assert tz.U_wall == 0.25
        assert tz.U_window == 1.4
        assert tz.window_area_m2 == 6
        assert tz.n_occupants == 2

    def test_parse_simulation_config(self, sample_topology):
        result = TopologyParser.parse(sample_topology)
        sim = result.simulation
        assert sim.start_time == 0
        assert sim.end_time == 31536000
        assert sim.step_size == 900
        assert sim.solver == "CVode"

    def test_parse_floor_1_single_apartment(self, sample_topology):
        result = TopologyParser.parse(sample_topology)
        floor_1 = result.building.floors[1]
        assert len(floor_1.apartments) == 1
        assert floor_1.apartments[0].id == "apt_1_1"
