"""Generate a Modelica system model from a parsed building topology.

Walks the topology and emits a self-contained ``.mo`` file that instantiates
the wrappers in ``FMUPlatform.Components`` (defined under ``modelica/`` at the
repo root) and wires them according to the building's hydraulic and control
graph.

Design notes
------------
* Output is deterministic: sorted iteration, stable instance names, no
  timestamps. Required for golden-file testing.
* Emits Modelica source as a string; ``write()`` persists to disk.
* Each ambient-loop pipe section is rendered as two segments (supply + return)
  to keep the closed hydraulic loop physically realistic. The topology JSON's
  ``length_m`` is used for both segments.
* Flow direction:
  ``centralHp.port_b -> mainSupply -> floorTee.port_supplyIn``
  ``floorTee.port_supplyOut[f] -> riserSupply_f -> aptTee_f.port_supplyIn``
  ``aptTee_f.port_supplyOut[a] -> apt_*_hp.port_a``
  ``apt_*_hp.port_b -> aptTee_f.port_returnIn[a]``
  ``aptTee_f.port_returnOut -> riserReturn_f -> floorTee.port_returnIn[f]``
  ``floorTee.port_returnOut -> mainReturn -> centralHp.port_a``
* The floor-level LoopTee uses ``n_branches = number of floors``. When there
  is only one floor it still emits a 1-branch tee (cleanest invariant).
"""

from __future__ import annotations

from pathlib import Path

from engine.topology_parser import (
    Apartment,
    Floor,
    ParsedTopology,
    SimulationConfig,
    TopologyParser,
)


_DEFAULT_TMY3 = (
    'Modelica.Utilities.Files.loadResource("modelica://Buildings/Resources/'
    'weatherdata/USA_CA_San.Francisco.Intl.AP.724940_TMY3.mos")'
)


def _fmt(value: float | int) -> str:
    """Render a numeric Modelica literal without trailing zeros for ints."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) or (isinstance(value, float) and value.is_integer()):
        return str(int(value))
    return repr(float(value))


def _apt_instance_name(floor_number: int, apt_idx: int) -> str:
    return f"apt_{floor_number}_{apt_idx}"


def _floor_branch_index(floors: list[Floor], floor_number: int) -> int:
    """Position of a floor in the sorted floors list (1-indexed for Modelica)."""
    sorted_numbers = sorted(f.floor_number for f in floors)
    return sorted_numbers.index(floor_number) + 1


def _emit_header(model_name: str, building_name: str) -> list[str]:
    return [
        "within FMUPlatform.Examples;",
        f'model {model_name}',
        f'  "Auto-generated system model for: {building_name}"',
        "  extends Modelica.Icons.Example;",
    ]


def _emit_central(central_hp, ambient_loop, n_floors: int) -> list[str]:
    Q_W = int(central_hp.nominal_power_kW * 1000)
    lines = [
        "  // --- Central plant ---",
        f"  FMUPlatform.Components.WeatherSource weather(",
        f"    filNam={_DEFAULT_TMY3});",
        f"  FMUPlatform.Components.CentralHeatPump centralHp(",
        f"    Q_flow_nominal_W={Q_W},",
        f"    COP_nominal={_fmt(central_hp.COP_nominal)},",
        f'    source_type="{central_hp.source_type}");',
        f"  Modelica.Blocks.Sources.Constant TSet_loop(k=308.15)",
        f'    "Loop supply temperature setpoint (35 degC)";',
        "  // --- Main ambient loop pipes ---",
        f"  FMUPlatform.Components.AmbientLoopSegment mainSupply(",
        f"    length_m={_fmt(ambient_loop.length_m)},",
        f"    diameter_mm={_fmt(ambient_loop.diameter_mm)},",
        f"    insulation_thickness_mm={_fmt(ambient_loop.insulation_thickness_mm)});",
        f"  FMUPlatform.Components.AmbientLoopSegment mainReturn(",
        f"    length_m={_fmt(ambient_loop.length_m)},",
        f"    diameter_mm={_fmt(ambient_loop.diameter_mm)},",
        f"    insulation_thickness_mm={_fmt(ambient_loop.insulation_thickness_mm)});",
        "  // --- Floor distribution tee ---",
        f"  FMUPlatform.Components.LoopTee floorTee(n_branches={n_floors});",
    ]
    return lines


def _emit_floor(floor: Floor) -> list[str]:
    n_apt = len(floor.apartments)
    f = floor.floor_number
    lines = [
        f"  // --- Floor {f} ---",
        f"  FMUPlatform.Components.AmbientLoopSegment riserSupply_{f}(",
        f"    length_m={_fmt(floor.riser_length_m)},",
        "    diameter_mm=50,",
        "    insulation_thickness_mm=20);",
        f"  FMUPlatform.Components.AmbientLoopSegment riserReturn_{f}(",
        f"    length_m={_fmt(floor.riser_length_m)},",
        "    diameter_mm=50,",
        "    insulation_thickness_mm=20);",
        f"  FMUPlatform.Components.LoopTee aptTee_{f}(n_branches={n_apt});",
    ]
    for idx, apt in enumerate(floor.apartments, start=1):
        lines.extend(_emit_apartment(f, idx, apt))
    return lines


def _emit_apartment(floor_number: int, apt_idx: int, apt: Apartment) -> list[str]:
    name = _apt_instance_name(floor_number, apt_idx)
    Q_W = int(apt.heatpump.nominal_power_kW * 1000)
    return [
        f"  FMUPlatform.Components.ApartmentHeatPump {name}_hp(",
        f"    Q_flow_nominal_W={Q_W},",
        f"    COP_nominal={_fmt(apt.heatpump.COP_nominal)});",
        f"  FMUPlatform.Components.ApartmentThermalZone {name}_zone(",
        f"    floor_area_m2={_fmt(apt.thermal_zone.floor_area_m2)},",
        f"    ceiling_height_m={_fmt(apt.thermal_zone.ceiling_height_m)},",
        f"    U_wall={_fmt(apt.thermal_zone.U_wall)},",
        f"    U_window={_fmt(apt.thermal_zone.U_window)},",
        f"    window_area_m2={_fmt(apt.thermal_zone.window_area_m2)},",
        f"    n_occupants={apt.thermal_zone.n_occupants},",
        f'    orientation="{apt.thermal_zone.orientation}");',
        f"  Modelica.Blocks.Sources.Constant {name}_TSet(k=293.15)",
        f'    "Zone setpoint for {apt.id} (20 degC)";',
    ]


def _emit_connections(topo: ParsedTopology) -> list[str]:
    floors = sorted(topo.building.floors, key=lambda f: f.floor_number)
    lines = [
        "equation",
        "  // --- Central plant supply chain ---",
        "  connect(TSet_loop.y, centralHp.TSet);",
        "  connect(centralHp.port_b, mainSupply.port_a);",
        "  connect(mainSupply.port_b, floorTee.port_supplyIn);",
        "  connect(floorTee.port_returnOut, mainReturn.port_a);",
        "  connect(mainReturn.port_b, centralHp.port_a);",
    ]
    for floor in floors:
        f = floor.floor_number
        b = _floor_branch_index(floors, f)
        lines.append(f"  // --- Floor {f} branch ---")
        lines.append(f"  connect(floorTee.port_supplyOut[{b}], riserSupply_{f}.port_a);")
        lines.append(f"  connect(riserSupply_{f}.port_b, aptTee_{f}.port_supplyIn);")
        lines.append(f"  connect(aptTee_{f}.port_returnOut, riserReturn_{f}.port_a);")
        lines.append(f"  connect(riserReturn_{f}.port_b, floorTee.port_returnIn[{b}]);")
        for idx, apt in enumerate(floor.apartments, start=1):
            name = _apt_instance_name(f, idx)
            lines.extend(
                [
                    f"  // {apt.id}",
                    f"  connect(aptTee_{f}.port_supplyOut[{idx}], {name}_hp.port_a);",
                    f"  connect({name}_hp.port_b, aptTee_{f}.port_returnIn[{idx}]);",
                    f"  connect({name}_hp.heatPortCon, {name}_zone.heatPortInt);",
                    f"  connect({name}_zone.TZone, {name}_hp.TZone);",
                    f"  connect({name}_TSet.y, {name}_hp.TZoneSet);",
                    f"  connect(weather.TDryBul, {name}_zone.TDryBul);",
                    f"  connect(weather.HGloHor, {name}_zone.HGloHor);",
                ]
            )
    return lines


def _emit_footer(model_name: str, sim: SimulationConfig) -> list[str]:
    return [
        "  annotation (",
        "    experiment(",
        f"      StartTime={_fmt(sim.start_time)},",
        f"      StopTime={_fmt(sim.end_time)},",
        f"      Interval={_fmt(sim.output_interval)},",
        "      Tolerance=1e-6),",
        '    __OpenModelica_simulationFlags(s="cvode"));',
        f"end {model_name};",
    ]


def generate(topology: dict, model_name: str = "GeneratedSystem") -> str:
    """Render Modelica source for a topology dict.

    Parameters
    ----------
    topology : dict
        Raw topology JSON (matches the schema in ``backend/app/schemas/topology.py``).
    model_name : str
        Name of the generated Modelica class (also the filename stem).
    """
    parsed = TopologyParser.parse(topology)
    return generate_from_parsed(parsed, model_name)


def generate_from_parsed(topology: ParsedTopology, model_name: str = "GeneratedSystem") -> str:
    """Render Modelica source for an already-parsed topology."""
    floors = sorted(topology.building.floors, key=lambda f: f.floor_number)
    n_floors = max(len(floors), 1)

    parts: list[str] = []
    parts.extend(_emit_header(model_name, topology.building.name))
    parts.extend(
        _emit_central(
            topology.building.central_heatpump,
            topology.building.ambient_loop,
            n_floors,
        )
    )
    for floor in floors:
        parts.extend(_emit_floor(floor))
    parts.extend(_emit_connections(topology))
    parts.extend(_emit_footer(model_name, topology.simulation))

    return "\n".join(parts) + "\n"


def write(topology: dict, out_path: Path, model_name: str = "GeneratedSystem") -> Path:
    """Generate Modelica source and write it to ``out_path``."""
    source = generate(topology, model_name)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(source)
    return out_path
