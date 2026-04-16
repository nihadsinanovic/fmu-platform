"""Stage 1 proof-of-concept: run a 2-apartment stack for 1 hour.

Usage (inside the api container):
    docker compose exec -T api python -m simulation.cosim_test

Writes a CSV of both apartments' room temperatures over time to
``/tmp/cosim_test.csv`` and prints a short summary. This is a standalone
sanity check for the subprocess worker + Jacobi master; it does not touch
the composition engine or the topology pipeline.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

from simulation.cosim_master import ApartmentSpec, CoSimMaster


def main(
    sim_duration_s: float = 3600.0,
    macro_step_s: float = 60.0,
    output_csv: Path = Path("/tmp/cosim_test.csv"),
) -> int:
    # Two apartments, stacked. A is the ground floor, B is on top of A.
    #   apt_A: floor = ground (10°C), roof = apt_B's room_temp
    #   apt_B: floor = apt_A's room_temp,  roof = sky (5°C)
    specs = [
        ApartmentSpec(
            id="apt_A",
            floor_temp_source=None,
            roof_temp_source="apt_B",
            supply_temp=35.0,
            ground_temp=10.0,
            initial_room_temp=20.0,
        ),
        ApartmentSpec(
            id="apt_B",
            floor_temp_source="apt_A",
            roof_temp_source=None,
            supply_temp=35.0,
            sky_temp=5.0,
            initial_room_temp=20.0,
        ),
    ]

    n_steps = int(sim_duration_s / macro_step_s)

    print(
        f"Cosim POC: {len(specs)} apartments, {n_steps} macro-steps of "
        f"{macro_step_s:.0f}s ({sim_duration_s:.0f}s total)"
    )
    wall_start = time.monotonic()

    with CoSimMaster(specs, macro_step_s=macro_step_s) as master:
        init_elapsed = time.monotonic() - wall_start
        print(f"  workers ready in {init_elapsed:.1f}s; starting macro-step loop")

        rows: list[tuple[float, float, float]] = []
        # t = 0 row: before any stepping, use the initial guesses.
        rows.append(
            (
                0.0,
                master.workers["apt_A"].last_room_temp,
                master.workers["apt_B"].last_room_temp,
            )
        )

        t = 0.0
        step_start = time.monotonic()
        for step_idx in range(n_steps):
            room_temps = master.step(t, macro_step_s)
            t += macro_step_s
            rows.append((t, room_temps["apt_A"], room_temps["apt_B"]))
            if step_idx % 10 == 0 or step_idx == n_steps - 1:
                elapsed = time.monotonic() - step_start
                print(
                    f"  step {step_idx + 1:4d}/{n_steps}  t={t:7.0f}s  "
                    f"apt_A={room_temps['apt_A']:6.2f}°C  "
                    f"apt_B={room_temps['apt_B']:6.2f}°C  "
                    f"(wall {elapsed:.1f}s)"
                )

    total_elapsed = time.monotonic() - wall_start

    # Write the CSV after shutdown so we don't hold workers open while doing disk IO.
    with output_csv.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["t_s", "apt_A_room_temp_C", "apt_B_room_temp_C"])
        writer.writerows(rows)

    # Simple sanity check: both temperatures should be bounded, non-NaN, and the
    # final values should be somewhere between the coldest boundary and the
    # supply temperature.
    final_a = rows[-1][1]
    final_b = rows[-1][2]
    ok = (
        -50.0 < final_a < 60.0
        and -50.0 < final_b < 60.0
        and all(-50.0 < r[1] < 60.0 and -50.0 < r[2] < 60.0 for r in rows)
    )

    print()
    print(f"  total wall time  : {total_elapsed:.1f}s")
    print(f"  final apt_A temp : {final_a:.2f}°C")
    print(f"  final apt_B temp : {final_b:.2f}°C")
    print(f"  CSV              : {output_csv} ({len(rows)} rows)")
    print(f"  sanity check     : {'PASS' if ok else 'FAIL'}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
