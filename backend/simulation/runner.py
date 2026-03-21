"""PyFMI + Assimulo simulation execution.

This module handles loading SSP packages, instantiating FMUs,
connecting them, and running the simulation.
"""

from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path
from typing import Any

from simulation.results import SimulationResult
from simulation.solver_config import SolverConfig

logger = logging.getLogger(__name__)


class SimulationError(Exception):
    pass


class SimulationRunner:
    """Load an SSP package and run the composed FMU simulation."""

    def __init__(self, solver_config: SolverConfig | None = None):
        self.solver_config = solver_config or SolverConfig()

    def run(
        self,
        ssp_path: Path,
        work_dir: Path,
        start_time: float = 0,
        end_time: float = 31536000,
        step_size: float = 900,
        output_interval: float = 3600,
    ) -> SimulationResult:
        """Run simulation from an SSP package.

        This requires PyFMI to be installed. The method:
        1. Unpacks the SSP archive
        2. Parses the SSD to find components and connections
        3. Loads each FMU with PyFMI
        4. Sets parameters from the SSV file
        5. Builds a coupled system
        6. Runs the simulation with Assimulo CVode solver
        7. Extracts and returns results
        """
        work_dir.mkdir(parents=True, exist_ok=True)

        # 1. Unpack SSP
        unpack_dir = work_dir / "unpacked"
        with zipfile.ZipFile(ssp_path, "r") as zf:
            zf.extractall(unpack_dir)

        # 2. Parse SSD to get components and connections
        ssd_path = unpack_dir / "SystemStructure.ssd"
        if not ssd_path.exists():
            raise SimulationError("SSP package missing SystemStructure.ssd")

        components, connections = self._parse_ssd(ssd_path)

        # 3. Load parameters from SSV
        ssv_path = unpack_dir / "parameters" / "system_parameters.ssv"
        parameters = self._parse_ssv(ssv_path) if ssv_path.exists() else {}

        # 4. Load FMUs and run simulation
        try:
            return self._run_with_pyfmi(
                unpack_dir, components, connections, parameters,
                start_time, end_time, step_size, output_interval,
            )
        except ImportError:
            logger.warning("PyFMI not available — returning empty result")
            return SimulationResult(
                metadata={"error": "PyFMI not installed", "ssp_path": str(ssp_path)}
            )

    def _parse_ssd(self, ssd_path: Path) -> tuple[list[dict], list[dict]]:
        """Parse SystemStructure.ssd XML to extract components and connections."""
        from lxml import etree

        tree = etree.parse(str(ssd_path))
        ns = {"ssd": "http://ssp-standard.org/SSP1/SystemStructureDescription"}

        components = []
        for comp in tree.xpath("//ssd:Component", namespaces=ns):
            components.append({
                "name": comp.get("name"),
                "source": comp.get("source"),
                "type": comp.get("type"),
            })

        connections = []
        for conn in tree.xpath("//ssd:Connection", namespaces=ns):
            connections.append({
                "start_element": conn.get("startElement"),
                "start_connector": conn.get("startConnector"),
                "end_element": conn.get("endElement"),
                "end_connector": conn.get("endConnector"),
            })

        return components, connections

    def _parse_ssv(self, ssv_path: Path) -> dict[str, Any]:
        """Parse SSV XML to extract parameter values."""
        from lxml import etree

        tree = etree.parse(str(ssv_path))
        parameters: dict[str, Any] = {}

        for param in tree.xpath("//Parameter"):
            name = param.get("name")
            real_el = param.find("Real")
            int_el = param.find("Integer")
            str_el = param.find("String")

            if real_el is not None:
                parameters[name] = float(real_el.get("value"))
            elif int_el is not None:
                parameters[name] = int(int_el.get("value"))
            elif str_el is not None:
                parameters[name] = str_el.get("value")

        return parameters

    def _run_with_pyfmi(
        self,
        unpack_dir: Path,
        components: list[dict],
        connections: list[dict],
        parameters: dict[str, Any],
        start_time: float,
        end_time: float,
        step_size: float,
        output_interval: float,
    ) -> SimulationResult:
        """Run simulation using PyFMI's CoupledFMUModelME2."""
        from pyfmi import load_fmu

        from engine.fmu_utils import prepare_fmu_for_simulation

        # Prepare and load FMU instances
        fmu_instances: dict[str, Any] = {}
        patch_dir = unpack_dir / "_patched"
        patch_dir.mkdir(exist_ok=True)

        for comp in components:
            fmu_path = unpack_dir / comp["source"]
            if not fmu_path.exists():
                raise SimulationError(f"FMU file not found: {fmu_path}")
            # Patch needsExecutionTool and other AMESim quirks
            ready_path = prepare_fmu_for_simulation(fmu_path, patch_dir)
            fmu = load_fmu(str(ready_path))
            fmu_instances[comp["name"]] = fmu

        # Apply parameters
        for param_key, value in parameters.items():
            parts = param_key.split(".", 1)
            if len(parts) == 2:
                instance_name, param_name = parts
                if instance_name in fmu_instances:
                    try:
                        fmu_instances[instance_name].set(param_name, value)
                    except Exception as e:
                        logger.warning(f"Could not set {param_key}={value}: {e}")

        # Build connection tuples for PyFMI
        pyfmi_connections = []
        for conn in connections:
            src_fmu = fmu_instances.get(conn["start_element"])
            tgt_fmu = fmu_instances.get(conn["end_element"])
            if src_fmu and tgt_fmu:
                pyfmi_connections.append(
                    (src_fmu, conn["start_connector"], tgt_fmu, conn["end_connector"])
                )

        # Create coupled model and simulate
        from pyfmi.master import Master

        models = list(fmu_instances.values())
        master = Master(models, pyfmi_connections)

        opts = master.simulate_options()
        opts["step_size"] = step_size

        res = master.simulate(
            start_time=start_time,
            final_time=end_time,
            options=opts,
        )

        # Extract results
        time_data = list(res["time"])
        variables = {}
        for comp_name, fmu in fmu_instances.items():
            for var_name in fmu.get_model_variables():
                key = f"{comp_name}.{var_name}"
                try:
                    variables[key] = list(res[key])
                except (KeyError, Exception):
                    pass

        return SimulationResult(
            time=time_data,
            variables=variables,
            metadata={
                "start_time": start_time,
                "end_time": end_time,
                "step_size": step_size,
                "n_components": len(components),
                "n_connections": len(connections),
            },
        )
