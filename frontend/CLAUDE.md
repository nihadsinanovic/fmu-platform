# Frontend — FMU Platform Web Application

Read the root `../CLAUDE.md` first for full project context. This file covers frontend-specific guidance.

## Role

This is the React web application hosted separately from the VPS. It provides:
1. **Project management** — Create, list, edit simulation projects
2. **Topology builder** — GUI for defining building structure (floors, apartments, parameters)
3. **Job monitoring** — Queue position, simulation progress via WebSocket
4. **Results viewer** — Time-series charts, energy summaries, per-apartment analytics

## Directory Structure

```
frontend/
├── CLAUDE.md
├── package.json
├── tsconfig.json
├── vite.config.ts
├── index.html
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/                        ← API client (generated or hand-written)
│   │   ├── client.ts               ← Axios/fetch base config
│   │   ├── projects.ts             ← Project CRUD
│   │   ├── jobs.ts                 ← Job status polling
│   │   ├── fmu-library.ts          ← Atomic FMU catalog
│   │   └── websocket.ts            ← WebSocket connection for job progress
│   ├── types/                      ← TypeScript types
│   │   ├── topology.ts             ← Building topology schema types
│   │   ├── project.ts
│   │   ├── job.ts
│   │   └── fmu.ts                  ← FMU manifest types
│   ├── stores/                     ← Zustand stores
│   │   ├── project-store.ts
│   │   ├── topology-store.ts       ← Current topology being edited
│   │   └── job-store.ts
│   ├── pages/
│   │   ├── Dashboard.tsx           ← Project list, recent sims, system status
│   │   ├── ProjectPage.tsx         ← Single project view (tabs below)
│   │   ├── TopologyBuilder.tsx     ← Main building editor
│   │   ├── SimulationMonitor.tsx   ← Job queue, progress
│   │   └── ResultsViewer.tsx       ← Charts, summaries
│   ├── components/
│   │   ├── topology/
│   │   │   ├── BuildingConfig.tsx      ← Name, location, climate zone
│   │   │   ├── CentralSystemPanel.tsx  ← Central HP + main loop params
│   │   │   ├── FloorEditor.tsx         ← Add/remove/reorder floors
│   │   │   ├── ApartmentCard.tsx       ← Single apartment config
│   │   │   ├── ApartmentDialog.tsx     ← Detailed apartment parameter editor
│   │   │   ├── SchematicPreview.tsx    ← Auto-generated system diagram
│   │   │   └── PresetSelector.tsx      ← T1/T2/T3/T4/T5 apartment presets
│   │   ├── simulation/
│   │   │   ├── JobStatusBadge.tsx
│   │   │   ├── QueuePosition.tsx
│   │   │   └── ProgressBar.tsx
│   │   ├── results/
│   │   │   ├── TimeSeriesChart.tsx     ← Plotly wrapper for temperature/power curves
│   │   │   ├── EnergyBalance.tsx       ← Summary metrics
│   │   │   └── ApartmentHeatmap.tsx    ← Per-apartment comfort analysis
│   │   └── common/
│   │       ├── Layout.tsx
│   │       ├── Sidebar.tsx
│   │       └── LoadingState.tsx
│   ├── hooks/
│   │   ├── useProject.ts
│   │   ├── useTopology.ts
│   │   ├── useJobStatus.ts        ← WebSocket hook for real-time updates
│   │   └── useFmuLibrary.ts
│   └── utils/
│       ├── topology-defaults.ts    ← Default values for apartment presets
│       ├── topology-validator.ts   ← Client-side validation before submit
│       └── schematic-layout.ts     ← Auto-layout logic for the schematic preview
├── public/
└── tests/
```

## Key Dependencies

```json
{
  "dependencies": {
    "react": "^18",
    "react-dom": "^18",
    "react-router-dom": "^6",
    "zustand": "^4",
    "@tanstack/react-query": "^5",
    "reactflow": "^11",
    "plotly.js": "^2",
    "react-plotly.js": "^2",
    "axios": "^1",
    "zod": "^3"
  },
  "devDependencies": {
    "typescript": "^5",
    "vite": "^5",
    "@vitejs/plugin-react": "^4",
    "tailwindcss": "^3",
    "vitest": "^1"
  }
}
```

## Topology Builder — The Core Screen

This is the most complex piece of the frontend. It has three sections:

### Left Panel: Building Structure
A form-based tree editor:
```
Building: [Résidence Les Alpages]
├── Central System
│   ├── Heat Pump: [120 kW] [COP 3.8] [Ground source]
│   └── Main Loop: [40m] [80mm] [30mm insulation]
├── Floor 0 (Ground)                    [+ Add Apartment]
│   ├── Apt 0-1: T2, 45m², South       [Edit] [Delete]
│   └── Apt 0-2: T3, 65m², North       [Edit] [Delete]
├── Floor 1                             [+ Add Apartment]
│   └── Apt 1-1: T2, 45m², South       [Edit] [Delete]
└── [+ Add Floor]
```

### Center: Schematic Preview
Auto-generated using React Flow (or a simpler SVG renderer). Shows the hydraulic topology:
- Central HP → Main loop → Floor tees → Apartment HPs → Thermal zones
- Color-coded by domain (blue = hydraulic, red = thermal)
- Updates live as the user edits the building structure

### Right Panel: Parameter Editor
When a component is selected, shows its editable parameters with:
- Labels and units
- Min/max validation (from FMU manifest)
- Default values
- Tooltips explaining each parameter

## Apartment Presets

Quick-fill templates to speed up topology definition:

```typescript
const APARTMENT_PRESETS = {
  T1: { floor_area_m2: 30, n_occupants: 1, window_area_m2: 4, heatpump_kW: 3 },
  T2: { floor_area_m2: 45, n_occupants: 2, window_area_m2: 6, heatpump_kW: 5 },
  T3: { floor_area_m2: 65, n_occupants: 3, window_area_m2: 8, heatpump_kW: 8 },
  T4: { floor_area_m2: 85, n_occupants: 4, window_area_m2: 10, heatpump_kW: 10 },
  T5: { floor_area_m2: 110, n_occupants: 5, window_area_m2: 14, heatpump_kW: 14 },
};
```

User picks a preset, then can override individual values.

## Topology TypeScript Types

These must stay in sync with the backend Pydantic schemas (see root CLAUDE.md for the JSON schema):

```typescript
interface BuildingTopology {
  project_id: string;
  building: Building;
  simulation: SimulationConfig;
}

interface Building {
  name: string;
  location: { lat: number; lon: number; climate_zone: string };
  central_system: {
    heatpump: { type: string; params: CentralHeatPumpParams };
  };
  ambient_loop: {
    main_pipe: { length_m: number; diameter_mm: number; insulation_thickness_mm: number };
  };
  floors: Floor[];
}

interface Floor {
  floor_number: number;
  riser_length_m: number;
  apartments: Apartment[];
}

interface Apartment {
  id: string;
  label: string;
  type_preset: string;
  floor_area_m2: number;
  orientation: 'north' | 'south' | 'east' | 'west';
  heatpump: { nominal_power_kW: number; COP_nominal: number };
  thermal_zone: ThermalZoneParams;
}
```

## API Integration

Use `@tanstack/react-query` for data fetching and caching. The backend (FastAPI) auto-generates an OpenAPI spec, so you can use `openapi-typescript` to generate types, or hand-write the API client.

```typescript
// Example: Trigger composition
const useCompose = (projectId: string) => {
  return useMutation({
    mutationFn: () => api.post(`/projects/${projectId}/compose`),
    onSuccess: (data) => {
      // data.job_id → subscribe to WebSocket for progress
      jobStore.subscribeToJob(data.job_id);
    }
  });
};
```

## WebSocket for Job Progress

```typescript
// hooks/useJobStatus.ts
const useJobStatus = (jobId: string | null) => {
  const [status, setStatus] = useState<JobStatus | null>(null);

  useEffect(() => {
    if (!jobId) return;
    const ws = new WebSocket(`${WS_BASE}/ws/jobs/${jobId}`);
    ws.onmessage = (event) => {
      setStatus(JSON.parse(event.data));
    };
    return () => ws.close();
  }, [jobId]);

  return status;
};
```

Status shape from backend:
```typescript
interface JobStatus {
  status: 'queued' | 'running' | 'completed' | 'failed';
  position?: number;          // Queue position (if queued)
  progress?: number;          // 0.0 to 1.0 (if running)
  elapsed_seconds?: number;
  estimated_remaining?: number;
  error_message?: string;     // If failed
  result_url?: string;        // If completed
}
```

## Code Style

- TypeScript strict mode
- Functional components only
- Zustand for global state, React Query for server state
- Tailwind CSS for styling
- Vitest for unit tests
- ESLint + Prettier
