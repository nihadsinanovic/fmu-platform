# Modelica package & system-model generator

This directory holds the **Option B (native Modelica)** seed described in
`docs/simulation-backend-evaluation.md`. It is intentionally **additive** —
the existing FMU/SSP/PyFMI pipeline is untouched. Use this when you want to
prototype the LBNL Buildings-library path without disrupting the production
flow.

## What's here

```
modelica/
├── README.md                              ← you are here
└── FMUPlatform/                           ← Modelica package
    ├── package.mo                         ← top-level package (uses Buildings 11)
    ├── Components/                        ← per-component wrappers
    │   ├── WeatherSource.mo               ← wraps Buildings ReaderTMY3
    │   ├── CentralHeatPump.mo             ← Carnot HP + pump + ground source + PI
    │   ├── ApartmentHeatPump.mo           ← Carnot HP + condenser HeatPort + PI
    │   ├── AmbientLoopSegment.mo          ← wraps PlugFlowPipe
    │   ├── LoopTee.mo                     ← parametric N-branch manifold tee
    │   └── ApartmentThermalZone.mo        ← lumped RC zone
    └── Examples/
        └── SmallBuilding2Floors.mo        ← rendered example (also the test fixture)
```

The **Python generator** lives in the backend, parallel to the SSP generator:

```
backend/engine/modelica_generator.py   ← walks topology, emits a .mo file
backend/tests/test_modelica_generator.py
backend/tests/fixtures/small_building_2floors.mo   ← golden fixture
```

## Component wrappers — port and parameter map

Each wrapper hides Buildings library complexity behind ports and parameters
that match the platform's atomic-FMU vocabulary.

| Wrapper                | Wraps                             | Hydraulic ports         | Other ports                                      | Key params                                                      |
| ---------------------- | --------------------------------- | ----------------------- | ------------------------------------------------ | --------------------------------------------------------------- |
| `WeatherSource`        | `ReaderTMY3`                      | —                       | `TDryBul`, `HGloHor`, `vWin` (RealOutput)        | `filNam`                                                        |
| `CentralHeatPump`      | `Carnot_y` + pump + Boundary_pT   | `port_a`, `port_b`      | `TSet` (RealInput)                               | `Q_flow_nominal_W`, `COP_nominal`, `source_type`, `T_ground`    |
| `ApartmentHeatPump`    | `Carnot_y` + condenser HX + PI    | `port_a`, `port_b`      | `heatPortCon`, `TZoneSet`, `TZone`               | `Q_flow_nominal_W`, `COP_nominal`                               |
| `AmbientLoopSegment`   | `PlugFlowPipe`                    | `port_a`, `port_b`      | —                                                | `length_m`, `diameter_mm`, `insulation_thickness_mm`            |
| `LoopTee`              | cascaded `Junction`s              | `port_supplyIn/Out[]`, `port_returnIn/Out[]` | —                                | `n_branches`                                                    |
| `ApartmentThermalZone` | hand-rolled lumped RC             | —                       | `heatPortInt`, `TDryBul`, `HGloHor`, `TZone`     | `floor_area_m2`, `U_wall`, `U_window`, `window_area_m2`, ...    |

All hydraulic ports use `Buildings.Media.Water` (`replaceable package Medium`).
Heat ports use `Modelica.Thermal.HeatTransfer.Interfaces.HeatPort_a`.

## Generating a system model

```python
import json
from pathlib import Path
from engine.modelica_generator import generate, write

topology = json.loads(Path("fmu-library/examples/small_building_2floors.json").read_text())

# As a string:
src = generate(topology, model_name="SmallBuilding2Floors")

# Or write to disk:
write(topology, Path("modelica/FMUPlatform/Examples/SmallBuilding2Floors.mo"),
      model_name="SmallBuilding2Floors")
```

Output is **deterministic** (sorted iteration, no timestamps), so the rendered
file can be checked into git and used as a golden fixture.

## Topology → Modelica connection layout

```
                      ┌───────────────────┐
                      │  CentralHeatPump  │
                      │   (TSet input)    │
                      └───┬───────────────┘
              port_b ─────┘             port_a
                          ▼                 ▲
                     mainSupply         mainReturn
                          ▼                 ▲
                  ┌────────────────────────────┐
                  │   floorTee (n=#floors)     │
                  └─┬───────────────────┬──────┘
       supplyOut[f] │                   │ returnIn[f]
                    ▼                   ▲
              riserSupply_f       riserReturn_f
                    ▼                   ▲
              ┌─────────────────────────────┐
              │  aptTee_f (n=#apartments)   │
              └─┬─────────────────────┬─────┘
   supplyOut[a] │                     │ returnIn[a]
                ▼                     ▲
       apt_f_a_hp.port_a       apt_f_a_hp.port_b
                |
                | heatPortCon ───── apt_f_a_zone.heatPortInt
                | TZone     ◄────── apt_f_a_zone.TZone
                | TZoneSet  ◄────── apt_f_a_TSet (constant)
                |
        weather.TDryBul,HGloHor ───► apt_f_a_zone
```

Each topology pipe is rendered as **two** segments (supply + return) to model
the closed hydraulic loop realistically.

## Compiling the example (manual spike check)

The unit tests check generator output, but **don't** compile Modelica. To
verify the rendered example actually runs, install OpenModelica and Buildings
11.0.0, then:

```bash
# From the repo root, with omc on PATH:
omc \
  -d=initialization,backenddaeinfo \
  --simulate FMUPlatform.Examples.SmallBuilding2Floors \
  modelica/FMUPlatform/package.mo
```

Or via OMShell:

```
>> loadModel(Modelica)
>> loadModel(Buildings)        # requires Modelica Buildings 11 installed
>> loadFile("modelica/FMUPlatform/package.mo")
>> simulate(FMUPlatform.Examples.SmallBuilding2Floors, stopTime=86400)
```

The example's `experiment` annotation defaults to a one-year run
(`StopTime=31536000`); start with `stopTime=86400` (one day) to validate the
model first.

## Known v1 simplifications

These are intentional and called out so we can revisit deliberately:

- **No borefield** — `CentralHeatPump.T_ground` is a constant, not a borefield
  thermal model. Replace `TSouBou` with a borefield or a seasonal sinusoid for
  realism.
- **Lumped RC zone** — `ApartmentThermalZone` is a single-capacity model
  (envelope + window conductance + occupant gains + linear solar). Swap for
  `Buildings.ThermalZones.ReducedOrder.RC.OneElement` (or higher) when more
  fidelity is needed.
- **Constant zone setpoint** — each apartment's `TSet` is a 20 °C constant.
  Replace with a schedule for night/day setbacks.
- **No internal-gain schedule** — occupant gains are constant
  (80 W × `n_occupants`). Replace `Q_int_const` with a `CombiTimeTable` to get
  realistic diurnal patterns.
- **One TMY3 file** — generator currently embeds the LBNL San-Francisco TMY3
  shipped with Buildings library. Wire `topology.location.climate_zone` to a
  file picker to use site-appropriate weather.
- **Manifold caps** — `LoopTee` caps cascade ends with zero-flow boundaries
  (`MassFlowSource_T(m_flow=0)`). This is a clean Modelica primitive but means
  the supply and return manifolds are independent — check it doesn't break
  pressure balance for very imbalanced apartment sets.
- **No bypass valve** — real ambient loops have a building-level bypass that
  modulates against minimum pump flow. Not modelled; flow is set by the pump's
  constant `m_flow_nominal`.

## What to do next

When the spike compiles and runs, the natural follow-ups are:

1. Write a **BuildingsPy / OMPython driver** so simulations can be launched
   from Python (parallel to the existing PyFMI runner). This unblocks the
   "runner.py replacement" path described in the eval doc.
2. Replace `ApartmentThermalZone` with `Buildings.ThermalZones.ReducedOrder.RC.OneElement`
   for ISO 13790 compliance.
3. Add a `borefield` option to `CentralHeatPump` that activates when
   `source_type="ground"`.
4. Add schedule support to setpoints and internal gains.
