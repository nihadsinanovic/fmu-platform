"""Generate FMU connection graph from parsed building topology."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.topology_parser import Building


@dataclass
class FMUInstance:
    name: str
    fmu_type: str
    parameters: dict[str, Any] = field(default_factory=dict)
    fmu_path: str = ""


@dataclass
class Connection:
    source_instance: str
    source_port: str
    target_instance: str
    target_port: str


@dataclass
class ConnectionGraph:
    instances: list[FMUInstance] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)

    def add_instance(self, instance: FMUInstance) -> None:
        self.instances.append(instance)

    def add_connection(
        self,
        source_instance: str,
        source_port: str,
        target_instance: str,
        target_port: str,
    ) -> None:
        self.connections.append(
            Connection(source_instance, source_port, target_instance, target_port)
        )


class ConnectionResolver:
    """Walk the building model and produce FMU instances + connections."""

    def resolve(self, building: Building) -> ConnectionGraph:
        graph = ConnectionGraph()

        # 1. Weather source
        weather = FMUInstance(
            name="weather_source",
            fmu_type="weather_source",
            parameters={
                "lat": building.location.lat,
                "lon": building.location.lon,
                "climate_zone": building.location.climate_zone,
            },
        )
        graph.add_instance(weather)

        # 2. Central heat pump
        central_hp = FMUInstance(
            name="central_hp",
            fmu_type="central_heatpump",
            parameters={
                "nominal_power_kW": building.central_heatpump.nominal_power_kW,
                "COP_nominal": building.central_heatpump.COP_nominal,
                "source_type": building.central_heatpump.source_type,
            },
        )
        graph.add_instance(central_hp)

        # 3. Main ambient loop segment
        main_loop = FMUInstance(
            name="main_loop_segment",
            fmu_type="ambient_loop_segment",
            parameters={
                "length_m": building.ambient_loop.length_m,
                "diameter_mm": building.ambient_loop.diameter_mm,
                "insulation_thickness_mm": building.ambient_loop.insulation_thickness_mm,
            },
        )
        graph.add_instance(main_loop)

        # Connect central HP output to main loop input
        for qty in ("T", "mdot", "p"):
            graph.add_connection("central_hp", f"hydr_out_{qty}", "main_loop_segment", f"hydr_in_{qty}")

        # 4. Floor-level tee to split among floors
        floor_tee = FMUInstance(
            name="floor_tee",
            fmu_type="loop_tee",
            parameters={"n_branches": len(building.floors)},
        )
        graph.add_instance(floor_tee)

        # Connect main loop output to floor tee input
        for qty in ("T", "mdot", "p"):
            graph.add_connection("main_loop_segment", f"hydr_out_{qty}", "floor_tee", f"hydr_in_{qty}")

        # 5. For each floor
        for floor in building.floors:
            fn = floor.floor_number
            riser_name = f"riser_floor_{fn}"

            # Riser segment for this floor
            riser = FMUInstance(
                name=riser_name,
                fmu_type="ambient_loop_segment",
                parameters={
                    "length_m": floor.riser_length_m,
                    "diameter_mm": building.ambient_loop.diameter_mm,
                    "insulation_thickness_mm": building.ambient_loop.insulation_thickness_mm,
                },
            )
            graph.add_instance(riser)

            # Connect floor tee branch to riser
            for qty in ("T", "mdot", "p"):
                graph.add_connection("floor_tee", f"hydr_out_{qty}[{fn}]", riser_name, f"hydr_in_{qty}")

            # Branch tee to split among apartments on this floor
            if len(floor.apartments) > 1:
                branch_tee_name = f"branch_tee_floor_{fn}"
                branch_tee = FMUInstance(
                    name=branch_tee_name,
                    fmu_type="loop_tee",
                    parameters={"n_branches": len(floor.apartments)},
                )
                graph.add_instance(branch_tee)

                for qty in ("T", "mdot", "p"):
                    graph.add_connection(riser_name, f"hydr_out_{qty}", branch_tee_name, f"hydr_in_{qty}")

                source_for_apts = branch_tee_name
            else:
                source_for_apts = riser_name

            # 6. For each apartment
            for apt_idx, apt in enumerate(floor.apartments):
                apt_hp_name = f"{apt.id}_heatpump"
                apt_zone_name = f"{apt.id}_zone"

                # Apartment heat pump
                apt_hp = FMUInstance(
                    name=apt_hp_name,
                    fmu_type="apartment_heatpump",
                    parameters={
                        "nominal_power_kW": apt.heatpump.nominal_power_kW,
                        "COP_nominal": apt.heatpump.COP_nominal,
                    },
                )
                graph.add_instance(apt_hp)

                # Connect loop to apartment HP
                if len(floor.apartments) > 1:
                    for qty in ("T", "mdot", "p"):
                        graph.add_connection(
                            source_for_apts, f"hydr_out_{qty}[{apt_idx}]",
                            apt_hp_name, f"hydr_in_{qty}",
                        )
                else:
                    for qty in ("T", "mdot", "p"):
                        graph.add_connection(
                            source_for_apts, f"hydr_out_{qty}",
                            apt_hp_name, f"hydr_in_{qty}",
                        )

                # Apartment thermal zone
                tz = apt.thermal_zone
                apt_zone = FMUInstance(
                    name=apt_zone_name,
                    fmu_type="apartment_thermal_zone",
                    parameters={
                        "floor_area_m2": tz.floor_area_m2,
                        "ceiling_height_m": tz.ceiling_height_m,
                        "U_wall": tz.U_wall,
                        "U_window": tz.U_window,
                        "window_area_m2": tz.window_area_m2,
                        "n_occupants": tz.n_occupants,
                        "orientation": tz.orientation,
                    },
                )
                graph.add_instance(apt_zone)

                # HP heating output → zone heating input
                graph.add_connection(
                    apt_hp_name, "therm_out_Q_heating",
                    apt_zone_name, "therm_in_Q_heating",
                )

                # Zone room temp feedback → HP
                graph.add_connection(
                    apt_zone_name, "therm_out_T_room",
                    apt_hp_name, "therm_in_T_room",
                )

                # Weather → zone outdoor temperature
                graph.add_connection(
                    "weather_source", "therm_out_T_ambient",
                    apt_zone_name, "therm_in_T_ambient_outdoor",
                )

            # Connect return paths: apartment HPs back through riser to floor tee
            for apt_idx, apt in enumerate(floor.apartments):
                apt_hp_name = f"{apt.id}_heatpump"
                if len(floor.apartments) > 1:
                    for qty in ("T", "mdot", "p"):
                        graph.add_connection(
                            apt_hp_name, f"hydr_out_{qty}",
                            source_for_apts, f"hydr_in_{qty}[{apt_idx}]",
                        )
                else:
                    for qty in ("T", "mdot", "p"):
                        graph.add_connection(
                            apt_hp_name, f"hydr_out_{qty}",
                            riser_name, f"hydr_in_{qty}",
                        )

        # Return path: floor tee back to central HP
        for qty in ("T", "mdot", "p"):
            graph.add_connection("floor_tee", f"hydr_return_{qty}", "central_hp", f"hydr_in_{qty}")

        return graph
