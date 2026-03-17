"""Package simulation results as Parquet + summary JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SimulationResult:
    """Container for simulation output data."""

    time: list[float] = field(default_factory=list)
    variables: dict[str, list[float]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        if not self.time:
            return 0
        return self.time[-1] - self.time[0]


def save_results(result: SimulationResult, output_dir: Path) -> Path:
    """Save simulation results as Parquet time-series and summary JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save time-series as Parquet
    parquet_path = output_dir / "timeseries.parquet"
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        columns = {"time": result.time}
        columns.update(result.variables)
        table = pa.table(columns)
        pq.write_table(table, parquet_path)
    except ImportError:
        # Fallback: save as JSON if pyarrow not available
        parquet_path = output_dir / "timeseries.json"
        data = {"time": result.time, **result.variables}
        with open(parquet_path, "w") as f:
            json.dump(data, f)

    # Save summary
    summary = {
        "n_timesteps": len(result.time),
        "duration_seconds": result.duration_seconds,
        "variables": list(result.variables.keys()),
        "metadata": result.metadata,
    }
    summary_path = output_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    # Save metadata
    metadata_path = output_dir / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(result.metadata, f, indent=2)

    return output_dir
