"""Generate AMESim-compatible weather data files.

AMESim .data file format for tables:
- Comment lines start with ';'
- First non-comment line: N [M]
  N = number of data points (rows)
  M = number of value columns (optional, defaults to 1)
- Data rows: whitespace-separated numbers
  First column is always the independent variable (time in seconds)
  Remaining columns are signal values

This module generates synthetic weather data suitable for testing
AMESim FMUs that reference external weather/ambient condition files.
"""

from __future__ import annotations

import math
from pathlib import Path


def generate_weather_data(
    filename: str,
    output_dir: Path,
    *,
    days: int = 30,
    step_seconds: int = 3600,
    latitude: float = 45.78,
    t_min: float = 14.0,
    t_max: float = 26.0,
) -> Path:
    """Generate an AMESim-format weather data file with realistic daily cycles.

    Produces a multi-column table with:
      Column 1: Time (seconds)
      Column 2: Outdoor temperature (°C)
      Column 3: Direct horizontal solar radiation (W/m²)
      Column 4: Diffuse horizontal radiation (W/m²)
      Column 5: Cloud cover (0–1)

    Args:
        filename: Output filename (e.g. 'HeatingAmbientLoop_TwoBuldnings_.june.data')
        output_dir: Directory to write the file into.
        days: Number of days of data to generate.
        step_seconds: Time step in seconds (default 3600 = hourly).
        latitude: Site latitude for solar calculations.
        t_min: Minimum daily temperature (°C), occurs ~05:00.
        t_max: Maximum daily temperature (°C), occurs ~15:00.

    Returns:
        Path to the generated file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / filename

    total_seconds = days * 86400
    n_points = total_seconds // step_seconds + 1

    # Number of value columns (excluding the time/x column)
    n_cols = 4

    lines: list[str] = []
    lines.append(f"; AMESim weather data — synthetic {days}-day profile")
    lines.append(f"; Location: lat={latitude}")
    lines.append("; Columns: Time(s)  Temperature(degC)  DirectSolar(W/m2)  DiffuseSolar(W/m2)  CloudCover(0-1)")
    lines.append(f"{n_points} {n_cols}")

    t_mid = (t_max + t_min) / 2.0
    t_amp = (t_max - t_min) / 2.0

    for i in range(n_points):
        t = i * step_seconds
        hour_of_day = (t % 86400) / 3600.0

        # Temperature: sinusoidal with min at 05:00, max at 15:00
        temp = t_mid - t_amp * math.cos(2.0 * math.pi * (hour_of_day - 15.0) / 24.0)

        # Solar radiation: bell curve during daylight (06:00–20:00)
        sunrise = 6.0
        sunset = 20.0
        if sunrise < hour_of_day < sunset:
            solar_frac = math.sin(math.pi * (hour_of_day - sunrise) / (sunset - sunrise))
            direct = 800.0 * solar_frac
            diffuse = 150.0 * solar_frac
        else:
            direct = 0.0
            diffuse = 0.0

        # Cloud cover: lower midday, higher at night
        if sunrise < hour_of_day < sunset:
            cloud = 0.3 + 0.1 * math.cos(2.0 * math.pi * (hour_of_day - 13.0) / 24.0)
        else:
            cloud = 0.6 + 0.1 * math.sin(2.0 * math.pi * hour_of_day / 24.0)

        cloud = max(0.0, min(1.0, cloud))

        lines.append(f"{t:.1f}\t{temp:.2f}\t{direct:.2f}\t{diffuse:.2f}\t{cloud:.3f}")

    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest
