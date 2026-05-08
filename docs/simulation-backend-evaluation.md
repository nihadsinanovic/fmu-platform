# Simulation Backend Evaluation

**Status:** Research / decision support. No code changes proposed.
**Audience:** Project owner deciding whether to continue with AMESim FMUs or pivot.
**Date:** 2026-05-08

---

## 1. Executive summary

The current architecture is built around composing AMESim FMUs into SSP packages and solving them via PyFMI. The motivating concerns are real: AMESim licensing constrains Celery concurrency by design (`LICENSE_POOL_SIZE` in `backend/CLAUDE.md`), license servers are operationally fragile, and the FMU binaries currently in `fmu-library/` are stubs from `fmu-library/generate_stub_fmus.py` — there is no sunk cost in real AMESim physics yet.

Three viable backends exist. **Opinion, not a decision:** LBNL's Modelica Buildings Library is the strongest fit because `Buildings.Experimental.DHC` already contains 5th-generation district heating models that match the project's ambient-loop-with-per-apartment-heat-pumps topology almost one-to-one. The principal risk is OpenModelica's solver maturity for stiff thermo-hydraulic systems; Dymola removes that risk but reintroduces a commercial license (without the runtime license-server pattern AMESim uses).

| Dimension | AMESim FMU (current) | LBNL Modelica Buildings | EnergyPlus + OpenStudio |
|---|---|---|---|
| Licensing cost | High; runtime license server | None (BSD) with OpenModelica; Dymola optional | None (DOE, public domain) |
| Component fit for ambient loops | Build-it-yourself | Pre-modeled in `Experimental.DHC` | Plant loops are rigid; awkward fit |
| Python integration | PyFMI (working today) | BuildingsPy (BSD) | OpenStudio SDK / EnergyPlus API |
| Solver maturity | AMESim mature; PyFMI master OK | Dymola excellent, OpenModelica fair | Mature, but fixed solver semantics |
| Learning curve from here | Already invested | Modelica + Buildings package | EnergyPlus IDF / OpenStudio model |
| Vendor lock-in | High (AMESim) | None (BSD) or Dymola optional | None |

---

## 2. What's already built around FMUs

The FMU coupling is concentrated in a few places. Migration cost depends on which option below is chosen.

| Surface | Path | Notes |
|---|---|---|
| Composition entry | `backend/engine/composition.py` | `CompositionEngine.compose(topology, output_path)` |
| Topology → graph | `backend/engine/connection_resolver.py` | **Deepest coupling.** Hardcoded port-name patterns at lines 90–91 and 102–103: `for qty in ("T", "mdot", "p"): graph.add_connection(..., f"hydr_out_{qty}", ..., f"hydr_in_{qty}")`. FMU type strings hardcoded throughout. |
| SSP package | `backend/engine/ssp_generator.py` | Emits `SystemStructure.ssd` XML, copies FMU binaries to `resources/`, writes `parameters/system_parameters.ssv` |
| Manifest schema | `backend/engine/manifest.py` | `FMUManifest`, `PortDefinition`, `ParameterDefinition` |
| Simulation runner | `backend/simulation/runner.py` | PyFMI `Master` + Assimulo CVode; calls `setup_amesim_environment()` for license server |
| DB | `backend/app/models/project.py`, `backend/app/models/job.py` | `ssp_path` columns assume the SSP artifact pattern |
| Frontend types | `admin/src/types.ts` | `FMUPort`, `FMUManifest`, `FMUTestRunStats` |
| Atomic FMU catalog | `fmu-library/{type}/v1.0.0/*.fmu` | All six are stubs from `fmu-library/generate_stub_fmus.py` |

Honest accounting: the composition pipeline, validator, and SSP packaging are real engineering effort that would be wasted if the FMU paradigm is dropped. The FMU binaries themselves are throwaway stubs — no waste there. Celery dispatch is still a TODO (see `backend/app/routes/projects.py` ~line 84), so the runtime path has not been hardened against real licensing pressure yet.

---

## 3. LBNL Modelica Buildings Library

### What it is
- **Maintainer:** Lawrence Berkeley National Laboratory, repo `lbl-srg/modelica-buildings`.
- **License:** 3-clause BSD (library and BuildingsPy). Commercial-use OK; no license server.
- **Version:** 13.0.0, released 4 May 2026, actively developed.
- **Top-level packages:** `Fluid`, `HeatTransfer`, `ThermalZones`, `BoundaryConditions`, `Controls`, `Electrical`, `Airflow`, `Media`, `Utilities`, **`Experimental.DHC`**.

### Why it fits this project specifically
`Buildings.Experimental.DHC` is the package for district heating/cooling, including 5th-generation networks: ambient-temperature loops (5–35 °C) with per-building Energy Transfer Stations containing water-to-water heat pumps. That is a near-exact match for the project's topology — central heat pump → ambient loop → apartment heat pumps → thermal zones. Reference component:
`Buildings.Experimental.DHC.EnergyTransferStations.Combined.Generation5`.

The `Buildings.Experimental.DHC.Examples` sub-package contains worked example systems — a starting point for the composition engine to emit, rather than building everything from primitives.

### Tooling around it
- **Compilers:** Dymola (commercial, considered the gold standard for stiff thermo-hydraulic systems), **OpenModelica** (open-source, ~86% of Buildings models compile cleanly per OpenModelica's published test stats), OPTIMICA (commercial).
- **Python integration:** **BuildingsPy** (BSD) drives Dymola, OpenModelica, and OPTIMICA from Python — runs simulations, parses `.mat` results, regression tests.
- **FMI export:** All three compilers export FMI 2.0 FMUs. With OpenModelica, `--fmuRuntimeDepends=modelica` is needed to bundle CVode runtime dependencies into a portable FMU.

---

## 4. Component mapping

For every atomic FMU in `fmu-library/`, an equivalent Buildings model exists. This is what makes a migration tractable rather than a from-scratch rebuild.

| Current FMU type | Buildings library equivalent | Parameter mapping notes |
|---|---|---|
| `central_heatpump` | `Buildings.Fluid.HeatPumps.ScrollWaterToWater` or `EquationFitWaterToWater` | `nominal_power_kW` → `QCon_flow_nominal` (in W). `COP_nominal` → `dpEva_nominal`/`dpCon_nominal` plus performance record. `source_type="ground"` → ground-source ETS variant. |
| `apartment_heatpump` | Same family, smaller capacity; or `Buildings.Experimental.DHC.EnergyTransferStations.Combined.Generation5HeatPump` | Same parameter shape as central, smaller `QCon_flow_nominal`. |
| `ambient_loop_segment` | `Buildings.Fluid.FixedResistances.Pipe` or `PlugFlowPipe` | `length_m` → `length`. `diameter_mm` → `dh` (m). `insulation_thickness_mm` → wall-layer record (`Insulation`/`thicknessIns`). `PlugFlowPipe` adds transport-delay and ground heat loss. |
| `loop_tee` | `Buildings.Fluid.FixedResistances.Junction` | `n_branches` constrains topology — Junction is 3-port; multi-way splits become daisy-chained junctions or a custom block. |
| `apartment_thermal_zone` | `Buildings.ThermalZones.ReducedOrder.RC` (ISO 13790) or `Buildings.ThermalZones.Detailed.MixedAir` | `floor_area_m2`, `ceiling_height_m` → zone geometry. `U_wall`, `U_window`, `window_area_m2` → envelope parameters. `n_occupants` → internal-gains profile. `orientation` → solar-aperture orientation in the RC reduced-order model. |
| `weather_source` | `Buildings.BoundaryConditions.WeatherData.ReaderTMY3` | TMY3 weather files (.mos format). `location.lat/lon` → file selection rather than parameter. |

The shape of a `Connection` (source/target instance + port) is preserved either way; only the port name conventions change. Buildings uses Modelica's `fluid_a`/`fluid_b` connectors, which carry T, mdot, p as a bundle — fewer per-component connections than the current `(T, mdot, p)` triple-wiring at `connection_resolver.py:90-91`.

---

## 5. Three architectural options

### A. Hybrid — keep SSP/PyFMI, swap FMU source
Replace stub AMESim FMUs with FMUs exported from Modelica Buildings models via OpenModelica (or Dymola). Composition engine, runner, SSP pipeline, DB schema, and frontend types all stay.

**Pros:** Smallest blast radius. Existing investment in composition + SSP + manifest validation is preserved. Migration is mostly a content swap (new FMU binaries + new port names + new parameter schemas in `connection_resolver.py`).

**Cons:** Inherits SSP/FMU master complexity forever. Two solver layers: PyFMI master coordinating internally-CVode-solved Modelica FMUs is suboptimal numerically vs. a single integrator over the full DAE. Loses access to Modelica's algebraic solver advantages for stiff coupled systems.

### B. Native Modelica — generate `.mo` from topology JSON
Composition engine emits a Modelica model file using `Buildings.Experimental.DHC` components, BuildingsPy compiles and runs it. Drop PyFMI, Assimulo, SSP, `manifest.py`, `ssp_generator.py`. Results come back as `.mat`, post-processed to Parquet.

**Pros:** Single integrator over the full DAE — better numerics for stiff thermo-hydraulic systems with many heat pumps. Smaller surface area: the composition engine becomes a Modelica code generator, no FMU master, no SSP. Direct access to Buildings library's parameter records and connector bundles.

**Cons:** Larger refactor: `connection_resolver.py`, `ssp_generator.py`, `runner.py`, `manifest.py` are reworked or deleted. DB schema: `ssp_path` becomes `model_path` or similar. Frontend types lose `FMUPort`/`FMUManifest` shape. Port-introspection UX (current `FMULibrary.tsx`) needs a Modelica-aware equivalent.

### C. EnergyPlus + OpenStudio SDK — different paradigm
EnergyPlus is mature, free (DOE), and battle-tested for whole-building energy simulation. The OpenStudio SDK provides a Ruby/C++/Python API to build and run models.

**Cons (decisive for this project):** EnergyPlus's plant-loop topology is rigid — ambient-loop networks with novel branching patterns are awkward to express. Per-apartment heat pumps drawing from a shared ambient loop is closer to what the Modelica DHC package was built for. EnergyPlus would force the topology into a shape the project has explicitly tried to avoid. Included for completeness; not a serious contender here.

---

## 6. Risks and unknowns

- **OpenModelica compatibility cliff.** The 14% of Buildings models that fail to compile under OpenModelica have not been audited for this project's needs. Concretely: do `Buildings.Experimental.DHC.EnergyTransferStations.Combined.Generation5*` and `Buildings.Fluid.HeatPumps.ScrollWaterToWater` compile cleanly? Unknown until tested.
- **Solver convergence on year-long simulations.** A building with 30+ apartment heat pumps each with their own controller is a stiff system. Dymola handles this routinely; OpenModelica's CVode integration may need tolerance tuning, event handling adjustments, or fall over entirely on some configurations.
- **Dymola fallback economics.** If OpenModelica proves unreliable, Dymola is ~€5–15k/seat (rough order, varies) — significantly cheaper than AMESim and licensed per-seat (no runtime license server). This trades open-source for reliability but still removes the operational pain point.
- **Frontend re-modeling.** Option B forces the frontend's FMU-aware types and components in `admin/src/pages/FMULibrary.tsx` to be reconceived. Not a blocker, but real UI work.
- **Data file injection coupling.** `runner.py`'s AMESim `.data` file injection (cited in `backend/simulation/runner.py` and `fmu_utils.py`) becomes irrelevant in either A or B — code to delete, not migrate.

---

## 7. Suggested next step

Before committing to A or B, run a **time-boxed spike (1–2 days)** answering one question: *does a 5GDHC example from `Buildings.Experimental.DHC.Examples` compile under OpenModelica and run a year-long simulation reliably from BuildingsPy?*

Concrete spike steps:
1. Install OpenModelica + the Buildings library locally.
2. Pick the closest example to this project's topology (single ambient loop, multiple buildings/apartments with heat pumps).
3. Drive it from BuildingsPy: compile, run for 31,536,000 s with 900 s step, dump `.mat`, parse to a DataFrame.
4. Note: compile time, simulation wall-clock, peak memory, any solver failures or warnings.

If the spike passes, Option B becomes the recommendation. If it fails on Buildings library models specifically (rather than on the user's setup), Option A becomes a safer bet, or Dymola enters the picture.

---

## Sources

- LBNL Modelica overview & BuildingsPy: <https://simulationresearch.lbl.gov/modelica/>
- Repo, releases, BSD license: <https://github.com/lbl-srg/modelica-buildings>
- 5GDHC examples roadmap: <https://github.com/lbl-srg/modelica-buildings/issues/1769>
- Generation 5 ETS reference: <https://simulationresearch.lbl.gov/modelica/releases/v8.0.0/help/Buildings_Experimental_DHC_EnergyTransferStations_Combined_Generation5.html>
- DOE peer review on Spawn + MBL: <https://www.energy.gov/sites/default/files/2024-11/bto-peer-2024-35511-35512-35517-35527-spawn-modelica-bldgs-library-wetter.pdf>
- OpenModelica FMI export: <https://openmodelica.org/doc/OpenModelicaUsersGuide/latest/fmitlm.html>
