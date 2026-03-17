# FMU Composition & Simulation Platform — Architecture

## 1. Problem Statement

Simulate ambient-loop heating systems in apartment complexes by composing parameterizable "atomic" AMESim FMUs (central heat pump, ambient loop segment, apartment heat pump, apartment thermal zone) into a building-scale simulation. Users define building topology through a web GUI; composition and simulation run on a license-managed VPS.

---

## 2. System Overview

```
┌─────────────────────────────────┐
│        Web Application          │
│  (React/Next.js, hosted sep.)   │
│                                 │
│  ┌───────────┐  ┌────────────┐  │
│  │ Topology  │  │  Project   │  │
│  │  Builder  │  │  Manager   │  │
│  │   (GUI)   │  │            │  │
│  └─────┬─────┘  └──────┬─────┘  │
│        │               │        │
│        ▼               ▼        │
│  ┌──────────────────────────┐   │
│  │    REST/WebSocket API    │   │
│  │    Client Layer          │   │
│  └────────────┬─────────────┘   │
└───────────────┼─────────────────┘
                │  HTTPS
                ▼
┌───────────────────────────────────────────────┐
│              VPS  (License Server)             │
│                                                │
│  ┌──────────────────────────────────────────┐  │
│  │          API Gateway (FastAPI)            │  │
│  │   /compose, /simulate, /projects, /jobs  │  │
│  └──────────┬──────────────┬────────────────┘  │
│             │              │                   │
│    ┌────────▼───────┐  ┌──▼──────────────┐    │
│    │  Job Queue &   │  │  Project &       │    │
│    │  License Mgr   │  │  FMU Storage     │    │
│    │  (Celery/Redis)│  │  (PostgreSQL +   │    │
│    │                │  │   Filesystem)    │    │
│    └────────┬───────┘  └─────────────────┘    │
│             │                                  │
│    ┌────────▼────────────────────────────┐     │
│    │      FMU Composition Engine         │     │
│    │  ┌──────────┐  ┌────────────────┐   │     │
│    │  │ Topology │  │  SSP Generator │   │     │
│    │  │ Resolver │  │  & Packager    │   │     │
│    │  └────┬─────┘  └───────┬────────┘   │     │
│    │       │                │            │     │
│    │  ┌────▼────────────────▼────────┐   │     │
│    │  │  FMU Parameterizer           │   │     │
│    │  │  (set params on atomic FMUs) │   │     │
│    │  └──────────────┬───────────────┘   │     │
│    └─────────────────┼───────────────────┘     │
│                      │                         │
│    ┌─────────────────▼───────────────────┐     │
│    │      Simulation Runner              │     │
│    │  PyFMI + Assimulo (ME solver)       │     │
│    │  Loads SSP → connects FMUs → runs   │     │
│    └─────────────────────────────────────┘     │
│                                                │
│    ┌─────────────────────────────────────┐     │
│    │   Atomic FMU Library                │     │
│    │   /fmu-library/                     │     │
│    │     central_heatpump.fmu            │     │
│    │     ambient_loop_segment.fmu        │     │
│    │     apartment_heatpump.fmu          │     │
│    │     apartment_thermal_zone.fmu      │     │
│    │     pipe_segment.fmu                │     │
│    │     ...                             │     │
│    └─────────────────────────────────────┘     │
└────────────────────────────────────────────────┘
```

---

## 3. Atomic FMU Design

Each atomic FMU is an AMESim-exported FMI 2.0 Model Exchange unit with a standardized port interface. The key is that ports follow naming conventions so the composition engine can wire them automatically.

### 3.1 Port Naming Convention

Ports follow the pattern: `{domain}_{direction}_{quantity}`

| Domain    | Direction | Quantities                        |
|-----------|-----------|-----------------------------------|
| `therm`   | `in/out`  | `T` (temperature), `Q` (heat flow), `mdot` (mass flow) |
| `hydr`    | `in/out`  | `p` (pressure), `mdot` (mass flow), `T` (temperature)  |
| `elec`    | `in/out`  | `P` (power), `V` (voltage)        |
| `ctrl`    | `in/out`  | `signal` (control signal)          |

### 3.2 Atomic FMU Catalog

#### `central_heatpump`
- **Parameters**: `nominal_power_kW`, `COP_nominal`, `source_type` (air/ground)
- **Inputs**: `hydr_in_T`, `hydr_in_mdot`, `hydr_in_p`, `ctrl_in_signal`
- **Outputs**: `hydr_out_T`, `hydr_out_mdot`, `hydr_out_p`, `elec_out_P`

#### `ambient_loop_segment`
- **Parameters**: `length_m`, `diameter_mm`, `insulation_thickness_mm`, `U_value`
- **Inputs**: `hydr_in_T`, `hydr_in_mdot`, `hydr_in_p`
- **Outputs**: `hydr_out_T`, `hydr_out_mdot`, `hydr_out_p`, `therm_out_Q_loss`

#### `loop_tee` (splitter/mixer)
- **Parameters**: `n_branches`
- **Inputs**: `hydr_in_T`, `hydr_in_mdot`, `hydr_in_p`
- **Outputs**: `hydr_out_T[i]`, `hydr_out_mdot[i]`, `hydr_out_p[i]` (per branch)

#### `apartment_heatpump`
- **Parameters**: `nominal_power_kW`, `COP_nominal`
- **Inputs**: `hydr_in_T`, `hydr_in_mdot`, `hydr_in_p` (from ambient loop), `therm_in_T_room`
- **Outputs**: `hydr_out_T`, `hydr_out_mdot`, `hydr_out_p`, `therm_out_Q_heating`

#### `apartment_thermal_zone`
- **Parameters**: `floor_area_m2`, `ceiling_height_m`, `U_wall`, `U_window`, `window_area_m2`, `n_occupants`, `orientation`
- **Inputs**: `therm_in_Q_heating`, `therm_in_T_ambient_outdoor`
- **Outputs**: `therm_out_T_room`, `therm_out_Q_demand`

#### `weather_source`
- **Parameters**: `location`, `climate_file_path`
- **Outputs**: `therm_out_T_ambient`, `ctrl_out_solar_radiation`

### 3.3 Interface Contracts

Each atomic FMU must ship with a **manifest file** (`manifest.json`) declaring:

```json
{
  "fmu_type": "central_heatpump",
  "fmi_version": "2.0",
  "fmi_type": "ModelExchange",
  "version": "1.2.0",
  "parameters": [
    { "name": "nominal_power_kW", "type": "Real", "default": 50.0, "unit": "kW", "min": 5, "max": 500 }
  ],
  "ports": {
    "inputs": [
      { "name": "hydr_in_T", "type": "Real", "unit": "K", "domain": "hydraulic" }
    ],
    "outputs": [
      { "name": "hydr_out_T", "type": "Real", "unit": "K", "domain": "hydraulic" }
    ]
  },
  "compatible_connections": {
    "hydr_in": ["ambient_loop_segment.hydr_out", "loop_tee.hydr_out"],
    "hydr_out": ["ambient_loop_segment.hydr_in", "loop_tee.hydr_in"]
  }
}
```

---

## 4. Topology Definition Schema

The GUI produces a JSON document describing the building. The composition engine translates this into FMU wiring.

### 4.1 Building Topology JSON

```json
{
  "project_id": "proj_abc123",
  "building": {
    "name": "Résidence Les Alpages",
    "location": { "lat": 45.19, "lon": 5.72, "climate_zone": "H1c" },
    "central_system": {
      "heatpump": {
        "type": "central_heatpump",
        "params": { "nominal_power_kW": 120, "COP_nominal": 3.8, "source_type": "ground" }
      }
    },
    "ambient_loop": {
      "main_pipe": { "length_m": 40, "diameter_mm": 80, "insulation_thickness_mm": 30 }
    },
    "floors": [
      {
        "floor_number": 0,
        "riser_length_m": 3.0,
        "apartments": [
          {
            "id": "apt_0_1",
            "label": "T2 - Ground Floor Left",
            "type_preset": "T2",
            "floor_area_m2": 45,
            "orientation": "south",
            "heatpump": { "nominal_power_kW": 5, "COP_nominal": 4.2 },
            "thermal_zone": {
              "U_wall": 0.25, "U_window": 1.4, "window_area_m2": 6,
              "n_occupants": 2, "ceiling_height_m": 2.5
            }
          },
          {
            "id": "apt_0_2",
            "label": "T3 - Ground Floor Right",
            "type_preset": "T3",
            "floor_area_m2": 65,
            "orientation": "north",
            "heatpump": { "nominal_power_kW": 8, "COP_nominal": 4.0 },
            "thermal_zone": {
              "U_wall": 0.25, "U_window": 1.4, "window_area_m2": 8,
              "n_occupants": 3, "ceiling_height_m": 2.5
            }
          }
        ]
      },
      {
        "floor_number": 1,
        "riser_length_m": 3.0,
        "apartments": [
          {
            "id": "apt_1_1",
            "label": "T2 - First Floor Left",
            "type_preset": "T2",
            "floor_area_m2": 45,
            "orientation": "south",
            "heatpump": { "nominal_power_kW": 5, "COP_nominal": 4.2 },
            "thermal_zone": {
              "U_wall": 0.25, "U_window": 1.4, "window_area_m2": 6,
              "n_occupants": 2, "ceiling_height_m": 2.5
            }
          }
        ]
      }
    ]
  },
  "simulation": {
    "start_time": 0,
    "end_time": 31536000,
    "step_size": 900,
    "solver": "CVode",
    "output_interval": 3600
  }
}
```

### 4.2 Topology → FMU Graph Translation

The composition engine walks the topology JSON and produces a **connection graph**:

```
weather_source
    └──► therm_out_T_ambient ──► [all apartment_thermal_zone.therm_in_T_ambient_outdoor]

central_heatpump
    └──► hydr_out ──► main_ambient_loop_segment.hydr_in

main_ambient_loop_segment
    └──► hydr_out ──► floor_0_tee.hydr_in

floor_0_tee
    ├──► hydr_out[0] ──► riser_0_segment.hydr_in
    │       └──► riser_0_segment.hydr_out ──► floor_0_branch_tee.hydr_in
    │               ├──► apt_0_1_heatpump.hydr_in
    │               └──► apt_0_2_heatpump.hydr_in
    └──► hydr_out[1] ──► riser_1_segment.hydr_in
            └──► ... (floor 1)

apt_0_1_heatpump
    ├──► therm_out_Q_heating ──► apt_0_1_zone.therm_in_Q_heating
    └──► hydr_out ──► (return to loop)

apt_0_1_zone
    └──► therm_out_T_room ──► apt_0_1_heatpump.therm_in_T_room
```

---

## 5. Composition Engine

### 5.1 Architecture

```python
# Composition pipeline
class CompositionEngine:
    """
    Transforms a building topology JSON into an executable simulation.
    """

    def compose(self, topology: dict) -> ComposedSystem:
        # Step 1: Parse topology
        building = TopologyParser.parse(topology)

        # Step 2: Instantiate atomic FMUs with parameters
        instances = self.instantiate_fmus(building)

        # Step 3: Generate connection graph
        connections = self.generate_connections(building, instances)

        # Step 4: Validate (port compatibility, no dangling ports)
        self.validate(instances, connections)

        # Step 5: Package as SSP or internal representation
        system = ComposedSystem(
            instances=instances,
            connections=connections,
            simulation_config=topology["simulation"]
        )

        # Step 6: Persist (save .ssp package or serialized system)
        system.save(path=f"/projects/{topology['project_id']}/system.ssp")

        return system
```

### 5.2 SSP Package as the "Composed FMU"

Rather than creating a single monolithic .fmu, the composed system is packaged as an **SSP (System Structure and Parameterization)** file. This is the Modelica Association's standard specifically designed for this purpose.

An `.ssp` file is a ZIP archive containing:

```
composed_system.ssp (ZIP)
├── SystemStructure.ssd          # XML: components, connections, parameters
├── resources/
│   ├── central_heatpump.fmu     # Atomic FMU (copy, parameterized)
│   ├── ambient_loop_seg_main.fmu
│   ├── floor_0_tee.fmu
│   ├── apt_0_1_heatpump.fmu
│   ├── apt_0_1_zone.fmu
│   ├── apt_0_2_heatpump.fmu
│   ├── apt_0_2_zone.fmu
│   └── weather.fmu
├── parameters/
│   ├── system_parameters.ssv    # Parameter values
│   └── parameter_mapping.ssm    # Name mappings
└── extra/
    └── topology.json            # Original topology for reference
```

**Why SSP over a monolithic wrapper FMU:**
- It is an open standard supported by many tools.
- It preserves the atomic FMU boundaries, so you can inspect/debug individual components.
- Parameter changes don't require recompilation — just update the .ssv file.
- You can swap out individual FMUs without recomposing the whole system.

### 5.3 SSP Generation (SystemStructure.ssd)

The engine generates an SSD (System Structure Description) XML like:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ssd:SystemStructureDescription name="AmbientLoopBuilding" version="1.0"
    xmlns:ssd="http://ssp-standard.org/SSP1/SystemStructureDescription">

  <ssd:System name="Building">

    <ssd:Elements>
      <ssd:Component name="CentralHP" type="application/x-fmu-sharedlibrary"
                     source="resources/central_heatpump.fmu">
        <ssd:Connectors>
          <ssd:Connector name="hydr_out_T" kind="output"/>
          <ssd:Connector name="hydr_out_mdot" kind="output"/>
          <ssd:Connector name="hydr_in_T" kind="input"/>
          <ssd:Connector name="hydr_in_mdot" kind="input"/>
        </ssd:Connectors>
      </ssd:Component>

      <ssd:Component name="Apt_0_1_HP" type="application/x-fmu-sharedlibrary"
                     source="resources/apt_0_1_heatpump.fmu">
        <!-- connectors... -->
      </ssd:Component>

      <!-- More components... -->
    </ssd:Elements>

    <ssd:Connections>
      <ssd:Connection startElement="CentralHP" startConnector="hydr_out_T"
                      endElement="MainLoopSegment" endConnector="hydr_in_T"/>
      <ssd:Connection startElement="CentralHP" startConnector="hydr_out_mdot"
                      endElement="MainLoopSegment" endConnector="hydr_in_mdot"/>
      <!-- More connections... -->
    </ssd:Connections>

  </ssd:System>

  <ssd:DefaultExperiment startTime="0" stopTime="31536000"/>

</ssd:SystemStructureDescription>
```

---

## 6. Simulation Runner

### 6.1 Approach: PyFMI with Assimulo Solver

Since all atomic FMUs are **FMI 2.0 Model Exchange**, they don't include their own solver. The simulation runner provides a unified solver across the entire composed system.

```python
from pyfmi import load_fmu
from pyfmi.master import Master

class SimulationRunner:
    def run(self, composed_system: ComposedSystem) -> SimulationResult:
        # 1. Load all FMU instances
        fmu_instances = {}
        for inst in composed_system.instances:
            fmu = load_fmu(inst.fmu_path)
            # Apply parameters from topology
            for param, value in inst.parameters.items():
                fmu.set(param, value)
            fmu_instances[inst.name] = fmu

        # 2. Define connections as PyFMI expects
        connections = []
        for conn in composed_system.connections:
            connections.append(
                (fmu_instances[conn.source_component], conn.source_port,
                 fmu_instances[conn.target_component], conn.target_port)
            )

        # 3. Create coupled system
        models = list(fmu_instances.values())
        master = Master(models, connections)

        # 4. Configure solver
        opts = master.simulate_options()
        opts["step_size"] = composed_system.config.step_size

        # 5. Run simulation
        result = master.simulate(
            start_time=composed_system.config.start_time,
            final_time=composed_system.config.end_time,
            options=opts
        )

        return self._package_results(result, composed_system)
```

### 6.2 Alternative: Use FMPy or CoFMPy

If PyFMI's master algorithm proves insufficient for ME FMUs (it's primarily designed for CS coupling), the fallback is:

- **FMPy** with its built-in CVode solver for ME FMUs, orchestrating the multi-FMU system manually.
- **CoFMPy** which handles algebraic loop resolution (likely needed since apartment heat pump temperature ↔ room temperature is a feedback loop).

---

## 7. Job Queue & License Management

### 7.1 Architecture

```
                  ┌──────────────┐
   API Request ──►│   FastAPI     │
                  │   Endpoint    │
                  └──────┬───────┘
                         │
                  ┌──────▼───────┐
                  │    Redis      │
                  │  (Broker)     │
                  └──────┬───────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Celery   │ │ Celery   │ │ Celery   │
        │ Worker 1 │ │ Worker 2 │ │ Worker 3 │
        │(1 license│ │(1 license│ │(1 license│
        │  each)   │ │  each)   │ │  each)   │
        └──────────┘ └──────────┘ └──────────┘
```

### 7.2 License-Aware Worker Pool

```python
# settings.py
LICENSE_POOL_SIZE = 3  # Number of AMESim licenses available

# celery_config.py
from celery import Celery

app = Celery('fmu_engine', broker='redis://localhost:6379/0')
app.conf.update(
    worker_concurrency=LICENSE_POOL_SIZE,  # One license per concurrent task
    task_acks_late=True,                   # Re-queue if worker dies
    worker_prefetch_multiplier=1,          # Don't prefetch (strict queuing)
)

# tasks.py
@app.task(bind=True, max_retries=3)
def compose_and_simulate(self, project_id: str, topology: dict):
    """Each invocation of this task consumes one AMESim license."""
    try:
        engine = CompositionEngine()
        system = engine.compose(topology)
        runner = SimulationRunner()
        result = runner.run(system)
        save_results(project_id, result)
        return {"status": "completed", "project_id": project_id}
    except LicenseError:
        # License unavailable — retry with backoff
        raise self.retry(countdown=60)
```

### 7.3 Job Status API

```
GET  /api/jobs/{job_id}/status
→ { "status": "queued", "position": 3, "estimated_wait_minutes": 12 }

GET  /api/jobs/{job_id}/status
→ { "status": "running", "progress": 0.45, "elapsed_seconds": 230 }

GET  /api/jobs/{job_id}/status
→ { "status": "completed", "result_url": "/api/projects/proj_abc/results" }
```

The web app polls this (or uses WebSocket) to show progress to the user.

---

## 8. API Design

### 8.1 Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/projects` | Create a new project |
| `GET` | `/api/projects/{id}` | Get project details |
| `PUT` | `/api/projects/{id}/topology` | Update building topology |
| `POST` | `/api/projects/{id}/compose` | Trigger FMU composition |
| `POST` | `/api/projects/{id}/simulate` | Trigger simulation run |
| `GET` | `/api/projects/{id}/results` | Get simulation results |
| `GET` | `/api/projects/{id}/ssp` | Download composed SSP package |
| `GET` | `/api/jobs/{id}/status` | Job status + queue position |
| `GET` | `/api/fmu-library` | List available atomic FMUs |
| `GET` | `/api/fmu-library/{type}/manifest` | Get FMU manifest (ports, params) |
| `WS` | `/ws/jobs/{id}` | Real-time job progress |

### 8.2 Typical Flow

```
1. User creates project          → POST /api/projects
2. User builds topology in GUI   → PUT  /api/projects/{id}/topology
3. User clicks "Compose & Run"   → POST /api/projects/{id}/compose
   API validates topology
   Queues composition job
   Returns job_id
4. Web app subscribes to updates → WS   /ws/jobs/{job_id}
5. Worker picks up job (if license available)
   - Composes SSP package
   - Runs simulation
   - Stores results
6. User sees results in GUI      → GET  /api/projects/{id}/results
```

---

## 9. Data Model

### 9.1 Database (PostgreSQL)

```sql
-- Projects
CREATE TABLE projects (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          VARCHAR(255) NOT NULL,
    owner_id      UUID NOT NULL REFERENCES users(id),
    topology      JSONB NOT NULL DEFAULT '{}',
    ssp_path      VARCHAR(500),        -- Path to composed .ssp file
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Simulation jobs
CREATE TABLE simulation_jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id    UUID NOT NULL REFERENCES projects(id),
    status        VARCHAR(20) DEFAULT 'queued',  -- queued/running/completed/failed
    topology_hash VARCHAR(64),          -- SHA256 of topology JSON (cache key)
    ssp_path      VARCHAR(500),
    result_path   VARCHAR(500),
    queued_at     TIMESTAMPTZ DEFAULT NOW(),
    started_at    TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ,
    error_message TEXT
);

-- Atomic FMU library
CREATE TABLE fmu_library (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type_name     VARCHAR(100) UNIQUE NOT NULL,  -- e.g. "central_heatpump"
    version       VARCHAR(20) NOT NULL,
    fmu_path      VARCHAR(500) NOT NULL,
    manifest      JSONB NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
```

### 9.2 File Storage Layout

```
/opt/fmu-platform/
├── fmu-library/                    # Atomic FMU templates
│   ├── central_heatpump/
│   │   ├── v1.2.0/
│   │   │   ├── central_heatpump.fmu
│   │   │   └── manifest.json
│   │   └── v1.1.0/
│   ├── ambient_loop_segment/
│   ├── apartment_heatpump/
│   └── apartment_thermal_zone/
├── projects/                       # Per-project storage
│   ├── proj_abc123/
│   │   ├── topology.json
│   │   ├── composed_system.ssp
│   │   └── results/
│   │       ├── run_001/
│   │       │   ├── timeseries.parquet
│   │       │   ├── summary.json
│   │       │   └── metadata.json
│   │       └── run_002/
│   └── proj_def456/
└── temp/                           # Working directory for active jobs
    └── job_xyz/
```

---

## 10. Web Application

### 10.1 Tech Stack

- **Framework**: React + TypeScript (Next.js or Vite)
- **State management**: Zustand or React Query
- **Topology builder**: Custom canvas component (React Flow / D3.js)
- **Charts**: Recharts or Plotly.js for simulation results
- **API client**: Generated from OpenAPI spec (the FastAPI auto-generates this)

### 10.2 Key Screens

1. **Dashboard** — List of projects, recent simulations, system status
2. **Topology Builder** — Visual building editor:
   - Left panel: building structure (floors, apartments)
   - Center canvas: schematic view of hydraulic connections
   - Right panel: parameter editor for selected component
3. **Simulation Monitor** — Job queue, progress, license availability
4. **Results Viewer** — Time-series charts, energy balance summaries, per-apartment analytics

### 10.3 Topology Builder UX Flow

```
┌─────────────────────────────────────────────────────────┐
│  Building Configurator                                  │
│                                                         │
│  ┌─── Building ──────────────────────────────────────┐  │
│  │  Name: [Résidence Les Alpages    ]                │  │
│  │  Location: [Grenoble, France     ] [Select Climate]│  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌─── Central System ───────────────────────────────┐   │
│  │  Heat Pump: [120 kW]  COP: [3.8]  Source: [Ground]│  │
│  │  Main Loop: Length [40m]  Diameter [80mm]          │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌─── Floors ────────────────────────────────────────┐  │
│  │  [+ Add Floor]                                    │  │
│  │                                                   │  │
│  │  ┌─ Floor 0 (Ground) ──────────────────────────┐  │  │
│  │  │  Riser length: [3.0 m]  [+ Add Apartment]   │  │  │
│  │  │                                              │  │  │
│  │  │  ┌─ Apt 0-1 (T2) ────┐ ┌─ Apt 0-2 (T3) ──┐ │  │  │
│  │  │  │ 45m² │ South      │ │ 65m² │ North     │ │  │  │
│  │  │  │ HP: 5kW           │ │ HP: 8kW          │ │  │  │
│  │  │  │ [Edit] [Remove]   │ │ [Edit] [Remove]  │ │  │  │
│  │  │  └───────────────────┘ └──────────────────┘ │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  │                                                   │  │
│  │  ┌─ Floor 1 ───────────────────────────────────┐  │  │
│  │  │  ...                                        │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌─── Schematic Preview ─────────────────────────────┐  │
│  │                                                   │  │
│  │   [Weather] ──────────────────────────────┐       │  │
│  │                                           │       │  │
│  │   [Central HP] ──► [Main Loop] ──► [Tee]──┤       │  │
│  │                                    │  │   │       │  │
│  │                    [Apt HP 0-1]◄───┘  │   │       │  │
│  │                     │                 │   │       │  │
│  │                    [Zone 0-1]         │   │       │  │
│  │                                       │   │       │  │
│  │                    [Apt HP 0-2]◄──────┘   │       │  │
│  │                     │                     │       │  │
│  │                    [Zone 0-2]    (Floor 1)│       │  │
│  │                                    ...    │       │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│            [ Compose & Simulate ]                       │
└─────────────────────────────────────────────────────────┘
```

---

## 11. Technology Stack Summary

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **VPS API** | Python + FastAPI | Async, auto-generates OpenAPI, great ecosystem |
| **Task Queue** | Celery + Redis | Mature, license-count = worker concurrency |
| **Database** | PostgreSQL | JSONB for topology, reliable |
| **Simulation** | PyFMI + Assimulo | Best Python lib for ME FMU coupling |
| **FMU Composition** | Custom SSP generator | Open standard, tool-independent |
| **File Storage** | Local filesystem (or S3-compatible) | SSP + results storage |
| **Web Frontend** | React + TypeScript | Rich interactive GUI |
| **Topology Canvas** | React Flow | Node-based visual editing |
| **Results Charts** | Plotly.js | Interactive time-series |
| **Auth** | JWT tokens | Stateless API auth |
| **WebSocket** | FastAPI WebSocket | Real-time job progress |

---

## 12. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| AMESim ME FMUs may need runtime license | Simulation fails without license | License pool management; consider upgrading to Amesim 2504+ for license-free export |
| Algebraic loops between apartment HP and thermal zone | Solver divergence | Use CoFMPy's algebraic loop resolution or add explicit delay/damping |
| Large buildings (100+ apartments) → many FMUs | Slow simulation, memory | Profile early; consider aggregating identical apartment types |
| SSP generation complexity | Bugs in wiring | Extensive validation step; visual preview before simulation |
| Network latency between web app and VPS | Slow UX | WebSocket for real-time updates; optimistic UI |

---

## 13. Development Phases

### Phase 1 — Foundation (4-6 weeks)
- Set up VPS with FastAPI + Celery + Redis + PostgreSQL
- Implement FMU library management (upload, version, manifest)
- Build composition engine: topology JSON → connection graph → SSP
- Manual testing with 2-3 atomic FMUs (one HP, one loop segment, one zone)

### Phase 2 — Simulation (3-4 weeks)
- Integrate PyFMI simulation runner
- Handle ME FMU coupling with Assimulo solver
- Implement results storage (Parquet time-series)
- License management and job queuing

### Phase 3 — Web Application (4-6 weeks)
- Project CRUD and API integration
- Topology builder GUI (building → floors → apartments)
- Schematic preview (auto-generated from topology)
- Job monitoring and results viewer

### Phase 4 — Polish & Scale (2-3 weeks)
- Apartment type presets (T1, T2, T3, T4, T5)
- Climate file integration
- Results comparison across runs
- Error handling and user feedback
- Performance optimization for large buildings
