# FMU Composition & Simulation Platform

## What This Project Is

A platform for composing parameterizable AMESim FMUs (Functional Mock-up Units) into building-scale energy simulations. The primary use case is simulating **ambient-loop heating systems in apartment complexes**: a centralized heat pump feeds an ambient loop, which distributes to per-apartment heat pumps, each heating a thermal zone.

Users define building topology through a web GUI (floors, apartments, sizes, orientations). The backend composes atomic FMUs into a connected system, runs the simulation on a license-managed VPS, and returns results.

## Monorepo Structure

```
fmu-platform/
├── CLAUDE.md              ← You are here. Project-wide context.
├── docker-compose.yml     ← Full stack: API, Celery, Postgres, Redis, Caddy
├── Caddyfile              ← Reverse proxy config (automatic HTTPS)
├── setup.sh               ← Generates .env with random passwords
├── deploy.sh              ← Pull + build + deploy in one command
├── backend/               ← Python (FastAPI + Celery). Runs on the VPS.
│   ├── CLAUDE.md          ← Backend-specific guidance
│   ├── app/               ← FastAPI application
│   ├── engine/            ← Composition engine + simulation runner
│   ├── workers/           ← Celery tasks
│   └── tests/
├── frontend/              ← React + TypeScript. Hosted separately.
│   ├── CLAUDE.md          ← Frontend-specific guidance
│   ├── src/
│   └── ...
└── docs/                  ← Shared architecture documentation
    └── architecture.md    ← Full architecture spec (source of truth)
```

## Core Concepts

### Atomic FMUs
Pre-built AMESim FMI 2.0 Model Exchange units, each representing one physical component. They have standardized ports so the composition engine can wire them together automatically.

Current catalog:
- `central_heatpump` — The building's main heat pump
- `ambient_loop_segment` — A pipe section of the ambient loop
- `loop_tee` — Splitter/mixer for branching the loop to floors/apartments
- `apartment_heatpump` — Per-apartment heat pump drawing from the ambient loop
- `apartment_thermal_zone` — Thermal model of an apartment
- `weather_source` — Outdoor conditions driver

### Port Naming Convention
All FMU ports follow: `{domain}_{direction}_{quantity}`

Domains: `therm` (thermal), `hydr` (hydraulic), `elec` (electrical), `ctrl` (control)
Directions: `in`, `out`
Quantities: `T` (temperature), `Q` (heat flow), `mdot` (mass flow), `p` (pressure), `P` (power), `signal`

Example: `hydr_out_T` = hydraulic domain, output, temperature

### FMU Manifest
Each atomic FMU has a `manifest.json` declaring its parameters, ports, and compatible connections. See `docs/architecture.md` §3.3 for the full schema.

### Composition via SSP
Composed systems are packaged as SSP (System Structure and Parameterization) files — an open standard. An `.ssp` is a ZIP containing:
- `SystemStructure.ssd` — XML describing components and connections
- `resources/` — All atomic FMU files
- `parameters/` — Parameter values (.ssv) and mappings (.ssm)
- `extra/topology.json` — Original topology for reference

### Simulation
PyFMI + Assimulo (CVode solver) loads the SSP, instantiates all ME FMUs, connects them, and runs a unified simulation. Results are stored as Parquet time-series.

### License Management
AMESim licenses are limited. The backend uses Celery with `worker_concurrency` set to the license count. Jobs queue in Redis; the web app shows queue position via WebSocket.

## Building Topology JSON Schema

This is the contract between frontend and backend. The GUI produces this; the composition engine consumes it.

```json
{
  "project_id": "string (UUID)",
  "building": {
    "name": "string",
    "location": { "lat": 0.0, "lon": 0.0, "climate_zone": "string" },
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
            "label": "string",
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

## API Contract (Backend ↔ Frontend)

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/projects | Create project |
| GET | /api/projects/{id} | Get project |
| PUT | /api/projects/{id}/topology | Update topology |
| POST | /api/projects/{id}/compose | Trigger composition → returns job_id |
| POST | /api/projects/{id}/simulate | Trigger simulation → returns job_id |
| GET | /api/projects/{id}/results | Get simulation results |
| GET | /api/projects/{id}/ssp | Download SSP package |
| GET | /api/jobs/{id}/status | Job status + queue position |
| GET | /api/fmu-library | List atomic FMUs |
| GET | /api/fmu-library/{type}/manifest | Get FMU manifest |
| WS | /ws/jobs/{id} | Real-time job progress |

## Data Model (PostgreSQL)

Three main tables:
- `projects` — id, name, owner_id, topology (JSONB), ssp_path
- `simulation_jobs` — id, project_id, status, topology_hash, ssp_path, result_path, timestamps
- `fmu_library` — id, type_name, version, fmu_path, manifest (JSONB)

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend API | Python 3.11+ / FastAPI |
| Task queue | Celery + Redis |
| Database | PostgreSQL 16 |
| Simulation | PyFMI + Assimulo |
| Composition | Custom SSP generator (Python) |
| Reverse proxy | Caddy 2 (automatic HTTPS via Let's Encrypt) |
| Frontend | React 18 + TypeScript (Vite) |
| Topology canvas | React Flow |
| Charts | Plotly.js |
| Auth | JWT |
| Real-time | WebSocket (FastAPI native) |

## Deployment

**No Coolify.** Deployment is plain Docker Compose on the VPS. Caddy handles HTTPS automatically.

### First-time setup on a fresh VPS:
```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Clone repo
git clone https://github.com/nihadsinanovic/fmu-platform.git /opt/fmu-platform
cd /opt/fmu-platform

# Generate .env with random passwords (interactive — asks for domain, license count)
./setup.sh

# Deploy
./deploy.sh
```

### Subsequent deploys:
```bash
cd /opt/fmu-platform && ./deploy.sh
```
deploy.sh pulls latest from git, rebuilds images, and restarts containers.

### Key env vars (auto-generated by setup.sh):
- `DOMAIN` — Used by Caddy for HTTPS cert (e.g. `fmu.example.com`)
- `DATABASE_URL` — Async (asyncpg) URL for FastAPI
- `DATABASE_URL_SYNC` — Sync (psycopg2) URL for Alembic migrations
- `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `SECRET_KEY` — Auto-generated secrets
- `LICENSE_POOL_SIZE` — Number of AMESim licenses = Celery worker concurrency
- `CORS_ORIGINS` — Comma-separated list of allowed frontend origins

### Staging environment:
Staging runs alongside production on the same VPS, with its own DB, Redis, and Celery worker. Caddy routes by subdomain.
```bash
./setup-staging.sh     # Generates .env.staging, adds STAGING_DOMAIN to .env
./deploy-staging.sh    # Builds and starts staging containers
```
Staging containers use project name `fmu-staging`. To check logs: `docker compose -f docker-compose.staging.yml -p fmu-staging logs`

### VPS access:
- Server: `root@194.163.143.24`
- **Change the root password** — the old one was exposed. Set up SSH key auth.

## Development Phases

Phase 1 (Foundation): VPS setup, FMU library management, composition engine, SSP generation
Phase 2 (Simulation): PyFMI integration, ME FMU coupling, results storage, license management
Phase 3 (Web App): Project CRUD, topology builder GUI, schematic preview, job monitoring, results viewer
Phase 4 (Polish): Apartment presets, climate files, run comparison, error handling, performance
