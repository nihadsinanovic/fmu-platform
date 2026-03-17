"""Tests for the connection resolver."""

from engine.connection_resolver import ConnectionResolver
from engine.topology_parser import TopologyParser


class TestConnectionResolver:
    def test_creates_weather_source(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)
        names = [inst.name for inst in graph.instances]
        assert "weather_source" in names

    def test_creates_central_hp(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)
        names = [inst.name for inst in graph.instances]
        assert "central_hp" in names

    def test_creates_main_loop(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)
        names = [inst.name for inst in graph.instances]
        assert "main_loop_segment" in names

    def test_creates_floor_riser(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)
        names = [inst.name for inst in graph.instances]
        assert "riser_floor_0" in names
        assert "riser_floor_1" in names

    def test_creates_apartment_components(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)
        names = [inst.name for inst in graph.instances]
        assert "apt_0_1_heatpump" in names
        assert "apt_0_1_zone" in names
        assert "apt_0_2_heatpump" in names
        assert "apt_0_2_zone" in names
        assert "apt_1_1_heatpump" in names
        assert "apt_1_1_zone" in names

    def test_creates_branch_tee_for_multi_apartment_floor(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)
        names = [inst.name for inst in graph.instances]
        # Floor 0 has 2 apartments → needs a branch tee
        assert "branch_tee_floor_0" in names
        # Floor 1 has 1 apartment → no branch tee
        assert "branch_tee_floor_1" not in names

    def test_connections_exist(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)
        assert len(graph.connections) > 0

    def test_central_hp_to_main_loop_connection(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)
        hp_to_loop = [
            c for c in graph.connections
            if c.source_instance == "central_hp" and c.target_instance == "main_loop_segment"
        ]
        # Should have T, mdot, p connections
        assert len(hp_to_loop) == 3

    def test_weather_to_zone_connections(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)
        weather_conns = [
            c for c in graph.connections
            if c.source_instance == "weather_source"
        ]
        # One weather→zone connection per apartment (3 apartments total)
        assert len(weather_conns) == 3

    def test_hp_zone_feedback_loop(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)
        # Check apt_0_1: HP→Zone and Zone→HP feedback
        hp_to_zone = [
            c for c in graph.connections
            if c.source_instance == "apt_0_1_heatpump" and c.target_instance == "apt_0_1_zone"
        ]
        zone_to_hp = [
            c for c in graph.connections
            if c.source_instance == "apt_0_1_zone" and c.target_instance == "apt_0_1_heatpump"
        ]
        assert len(hp_to_zone) == 1  # therm_out_Q_heating
        assert len(zone_to_hp) == 1  # therm_out_T_room

    def test_instance_parameters(self, sample_topology):
        parsed = TopologyParser.parse(sample_topology)
        graph = ConnectionResolver().resolve(parsed.building)
        central = next(i for i in graph.instances if i.name == "central_hp")
        assert central.parameters["nominal_power_kW"] == 120
        assert central.parameters["COP_nominal"] == 3.8
