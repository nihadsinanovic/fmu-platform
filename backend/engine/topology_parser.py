"""Parse building topology JSON into internal dataclass model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Location:
    lat: float
    lon: float
    climate_zone: str = ""


@dataclass
class HeatPumpConfig:
    nominal_power_kW: float
    COP_nominal: float
    source_type: str = "ground"


@dataclass
class ThermalZoneConfig:
    floor_area_m2: float
    ceiling_height_m: float
    U_wall: float
    U_window: float
    window_area_m2: float
    n_occupants: int
    orientation: str = "south"


@dataclass
class AmbientLoopConfig:
    length_m: float
    diameter_mm: float
    insulation_thickness_mm: float = 0


@dataclass
class Apartment:
    id: str
    label: str
    floor_area_m2: float
    orientation: str
    heatpump: HeatPumpConfig
    thermal_zone: ThermalZoneConfig
    type_preset: str = ""


@dataclass
class Floor:
    floor_number: int
    riser_length_m: float
    apartments: list[Apartment] = field(default_factory=list)


@dataclass
class Building:
    name: str
    location: Location
    central_heatpump: HeatPumpConfig
    ambient_loop: AmbientLoopConfig
    floors: list[Floor] = field(default_factory=list)


@dataclass
class SimulationConfig:
    start_time: float = 0
    end_time: float = 31536000
    step_size: float = 900
    solver: str = "CVode"
    output_interval: float = 3600


@dataclass
class ParsedTopology:
    building: Building
    simulation: SimulationConfig


class TopologyParser:
    """Parse raw topology JSON dict into typed dataclass model."""

    @staticmethod
    def parse(topology: dict[str, Any]) -> ParsedTopology:
        bldg = topology["building"]

        location = Location(
            lat=bldg["location"]["lat"],
            lon=bldg["location"]["lon"],
            climate_zone=bldg["location"].get("climate_zone", ""),
        )

        hp_params = bldg["central_system"]["heatpump"]["params"]
        central_hp = HeatPumpConfig(
            nominal_power_kW=hp_params["nominal_power_kW"],
            COP_nominal=hp_params["COP_nominal"],
            source_type=hp_params.get("source_type", "ground"),
        )

        pipe = bldg["ambient_loop"]["main_pipe"]
        ambient_loop = AmbientLoopConfig(
            length_m=pipe["length_m"],
            diameter_mm=pipe["diameter_mm"],
            insulation_thickness_mm=pipe.get("insulation_thickness_mm", 0),
        )

        floors = []
        for floor_data in bldg.get("floors", []):
            apartments = []
            for apt_data in floor_data.get("apartments", []):
                apt_hp = HeatPumpConfig(
                    nominal_power_kW=apt_data["heatpump"]["nominal_power_kW"],
                    COP_nominal=apt_data["heatpump"]["COP_nominal"],
                )
                tz = apt_data["thermal_zone"]
                thermal_zone = ThermalZoneConfig(
                    floor_area_m2=apt_data["floor_area_m2"],
                    ceiling_height_m=tz.get("ceiling_height_m", 2.5),
                    U_wall=tz["U_wall"],
                    U_window=tz["U_window"],
                    window_area_m2=tz["window_area_m2"],
                    n_occupants=tz["n_occupants"],
                    orientation=apt_data.get("orientation", "south"),
                )
                apartments.append(
                    Apartment(
                        id=apt_data["id"],
                        label=apt_data.get("label", ""),
                        floor_area_m2=apt_data["floor_area_m2"],
                        orientation=apt_data.get("orientation", "south"),
                        heatpump=apt_hp,
                        thermal_zone=thermal_zone,
                        type_preset=apt_data.get("type_preset", ""),
                    )
                )
            floors.append(
                Floor(
                    floor_number=floor_data["floor_number"],
                    riser_length_m=floor_data.get("riser_length_m", 3.0),
                    apartments=apartments,
                )
            )

        building = Building(
            name=bldg["name"],
            location=location,
            central_heatpump=central_hp,
            ambient_loop=ambient_loop,
            floors=floors,
        )

        sim_data = topology.get("simulation", {})
        simulation = SimulationConfig(
            start_time=sim_data.get("start_time", 0),
            end_time=sim_data.get("end_time", 31536000),
            step_size=sim_data.get("step_size", 900),
            solver=sim_data.get("solver", "CVode"),
            output_interval=sim_data.get("output_interval", 3600),
        )

        return ParsedTopology(building=building, simulation=simulation)
