# Backend — FMU Composition & Simulation Engine

Read the root `../CLAUDE.md` first for full project context. This file covers backend-specific guidance.

## Role

This is the Python backend running on a VPS with AMESim licenses. It handles:
1. **API layer** — FastAPI endpoints for projects, jobs, FMU library
2. **Composition engine** — Transforms building topology JSON into wired SSP packages
3. **Simulation runner** — Loads SSP, runs coupled ME FMU simulation via PyFMI
4. **Job queue** — Celery workers, one per license slot

## Directory Structure

```
backend/
├── CLAUDE.md
├── pyproject.toml              ← Poetry or pip, Python 3.11+
├── app/
│   ├── __init__.py
│   ├── main.py                 ← FastAPI app, CORS, lifespan
│   ├── config.py               ← Settings (license count, paths, DB URL)
│   ├── models/                 ← SQLAlchemy / Pydantic models
│   │   ├── project.py
│   │   ├── job.py
│   │   └── fmu_library.py
│   ├── routes/
│   │   ├── projects.py         ← CRUD + topology update
│   │   ├── jobs.py             ← Status, queue position
│   │   ├── fmu_library.py      ← List FMUs, get manifests
│   │   └── websocket.py        ← Real-time job progress
│   ├── schemas/                ← Pydantic request/response schemas
│   │   ├── topology.py         ← Building topology validation
│   │   ├── project.py
│   │   └── job.py
│   └── database.py             ← DB session, engine
├── engine/
│   ├── __init__.py
│   ├── topology_parser.py      ← Parse topology JSON into internal model
│   ├── connection_resolver.py  ← Generate FMU connection graph from topology
│   ├── ssp_generator.py        ← Build SSP package (SSD XML + FMU copies + params)
│   ├── parameterizer.py        ← Apply parameter values to FMU instances
│   ├── validator.py            ← Validate connections, ports, no dangling wires
│   └── manifest.py             ← Load/parse FMU manifest files
├── simulation/
│   ├── __init__.py
│   ├── runner.py               ← PyFMI + Assimulo simulation execution
│   ├── results.py              ← Package results as Parquet + summary JSON
│   └── solver_config.py        ← CVode options, tolerances
├── workers/
│   ├── __init__.py
│   ├── celery_app.py           ← Celery config (concurrency = license count)
│   ├── tasks.py                ← compose_and_simulate task
│   └── license_manager.py      ← License acquisition/release logic
├── tests/
│   ├── test_topology_parser.py
│   ├── test_connection_resolver.py
│   ├── test_ssp_generator.py
│   ├── test_validator.py
│   └── test_api/
│       ├── test_projects.py
│       └── test_jobs.py
└── alembic/                    ← DB migrations
    └── versions/
```

## Key Dependencies

```
fastapi
uvicorn
celery[redis]
sqlalchemy
alembic
psycopg2-binary
pydantic>=2.0
PyFMI
FMPy                # For FMU inspection/validation
lxml                # SSP/SSD XML generation
pyarrow             # Parquet results
python-multipart    # File uploads
websockets
```

## Composition Engine — How It Works

### Step 1: Parse Topology
`topology_parser.py` takes the building topology JSON and produces an internal object model:
```python
@dataclass
class Building:
    name: str
    location: Location
    central_heatpump: HeatPumpConfig
    ambient_loop: AmbientLoopConfig
    floors: list[Floor]

@dataclass
class Floor:
    floor_number: int
    riser_length_m: float
    apartments: list[Apartment]

@dataclass
class Apartment:
    id: str
    label: str
    floor_area_m2: float
    orientation: str
    heatpump: HeatPumpConfig
    thermal_zone: ThermalZoneConfig
```

### Step 2: Resolve Connections
`connection_resolver.py` walks the building model and produces a list of FMU instances + connections:

```python
@dataclass
class FMUInstance:
    name: str                    # e.g. "apt_0_1_heatpump"
    fmu_type: str                # e.g. "apartment_heatpump"
    parameters: dict[str, Any]   # e.g. {"nominal_power_kW": 5}
    fmu_path: str                # Path to atomic .fmu file

@dataclass
class Connection:
    source_instance: str    # e.g. "central_hp"
    source_port: str        # e.g. "hydr_out_T"
    target_instance: str    # e.g. "main_loop_segment"
    target_port: str        # e.g. "hydr_in_T"
```

The resolver follows this logic:
1. Create `weather_source` instance
2. Create `central_heatpump` instance → connect output to `main_ambient_loop_segment`
3. For each floor:
   - Create `ambient_loop_segment` (riser) for that floor
   - Create `loop_tee` to split flow among apartments on this floor
   - For each apartment:
     - Create `apartment_heatpump` → connect ambient loop input
     - Create `apartment_thermal_zone` → connect to HP output
     - Connect zone temperature feedback to HP
4. Connect return paths back to central HP

### Step 3: Generate SSP
`ssp_generator.py` creates the `.ssp` ZIP archive:
- Generate `SystemStructure.ssd` XML from instances + connections
- Copy atomic FMU files into `resources/`
- Generate `.ssv` parameter file from instance parameters
- Include original `topology.json` in `extra/`

### Step 4: Validate
`validator.py` checks:
- Every input port is connected to exactly one output
- Port types match (Real→Real, etc.)
- No orphan FMU instances
- All referenced FMU types exist in the library
- Parameter values are within manifest-declared min/max

## Simulation Runner

```python
# Simplified flow in runner.py
def run_simulation(ssp_path: str) -> SimulationResult:
    # 1. Unpack SSP, parse SSD
    # 2. Load each FMU with PyFMI: load_fmu(path)
    # 3. Set parameters on each FMU instance
    # 4. Build coupled system using PyFMI's CoupledFMUModelME2
    # 5. Configure Assimulo CVode solver
    # 6. Simulate
    # 7. Extract results, write to Parquet
```

Important: PyFMI's `CoupledFMUModelME2` class is what aggregates multiple ME FMUs into a single ODE system solved by Assimulo. This is different from the co-simulation master algorithm.

## Celery Configuration

```python
# celery_app.py
from celery import Celery
from app.config import settings

app = Celery('fmu_engine', broker=settings.REDIS_URL)
app.conf.update(
    worker_concurrency=settings.LICENSE_POOL_SIZE,  # KEY: matches license count
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_backend=settings.REDIS_URL,
    task_track_started=True,
)
```

## Environment Variables

```
DATABASE_URL=postgresql://user:pass@localhost/fmu_platform
REDIS_URL=redis://localhost:6379/0
LICENSE_POOL_SIZE=3
FMU_LIBRARY_PATH=/opt/fmu-platform/fmu-library
PROJECTS_PATH=/opt/fmu-platform/projects
AMESIM_LICENSE_SERVER=port@hostname    # FlexLM server
```

## Testing Strategy

- **Unit tests**: topology parser, connection resolver, SSP generator, validator — these can run without FMUs or licenses
- **Integration tests**: Use simple test FMUs (can create mock ME FMUs with PythonFMU) to test the full compose → simulate pipeline
- **API tests**: FastAPI TestClient with test database

## Code Style

- Python 3.11+, type hints everywhere
- Pydantic v2 for all schemas
- async endpoints in FastAPI (but Celery tasks are sync)
- pytest for testing
- Ruff for linting
