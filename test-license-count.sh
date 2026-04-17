#!/usr/bin/env bash
#
# FMU Platform — Empirical AMESim License Probe & Multi-Instance Safety Test
#
# Two modes:
#
# 1. License probe (default): spawns N parallel Python processes inside the
#    api container, each loads the given FMU and holds its license for a
#    fixed window. Reports peak concurrent hold to distinguish a true parallel
#    license pool from a serializing server.
#
# 2. Multi-instance test (`./test-license-count.sh multi-instance`): creates
#    an in-place copy of the FMU with ``canBeInstantiatedOnlyOncePerProcess``
#    flipped from true to false in modelDescription.xml, then attempts to
#    load two instances in ONE Python process. If both produce identical
#    outputs for identical inputs, the FMU is multi-instance-safe and the
#    singleton flag was only a conservative declaration.
#
# Usage:
#   ./test-license-count.sh                       # N=4, FMU=stackable_apartment, hold=5s
#   ./test-license-count.sh 8                     # 8 concurrent probes
#   ./test-license-count.sh 8 my_fmu_name         # custom FMU type name
#   ./test-license-count.sh 8 my_fmu_name 10      # hold each license for 10s
#   ./test-license-count.sh multi-instance        # load 2 instances in 1 process (default)
#   ./test-license-count.sh multi-instance my_fmu # same, custom FMU type
#   ./test-license-count.sh multi-instance my_fmu 10 # load 10 instances to probe per-process vs per-instance licensing
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

# Detect subcommand
MODE="license-probe"
if [ "${1:-}" = "multi-instance" ]; then
  MODE="multi-instance"
  shift
fi

if ! docker compose ps --status running --services 2>/dev/null | grep -q '^api$'; then
  echo "  ✗ The 'api' container is not running."
  exit 1
fi

# ════════════════════════════════════════════════════════════════════════════
# Mode: multi-instance safety test
# ════════════════════════════════════════════════════════════════════════════

if [ "$MODE" = "multi-instance" ]; then
  FMU_TYPE="${1:-stackable_apartment}"
  INSTANCE_COUNT="${2:-2}"

  echo ""
  echo "FMU Platform — Multi-Instance Safety Test"
  echo "========================================="
  echo ""
  echo "  FMU type       : $FMU_TYPE"
  echo "  Instance count : $INSTANCE_COUNT"
  echo ""
  echo "  Flipping canBeInstantiatedOnlyOncePerProcess to false in a copy of"
  echo "  the FMU and attempting to load N instances in one Python process."
  echo "  With N=2 this tests basic singleton-safety; with N=10+ it also probes"
  echo "  whether licensing is counted per-process or per-FMU-instance."
  echo ""

  PROBE=$(cat <<'PYEOF'
import logging
import os
import shutil
import sys
import tempfile
import zipfile
from functools import partial
from pathlib import Path

logging.disable(logging.CRITICAL)
pf = partial(print, flush=True)


def _is_license_err(exc_text: str, fmu_log: str) -> bool:
    bad = ("lic_init failed", "Checkout failed", "license", "License")
    return any(s in exc_text for s in bad) or any(s in fmu_log for s in bad)


def main():
    from sqlalchemy import create_engine, text

    from app.config import settings
    from engine.fmu_utils import (
        _normalize_data_file_for_injection,
        prepare_fmu_for_simulation,
        setup_amesim_environment,
    )

    fmu_type = sys.argv[1]
    n_instances = int(sys.argv[2])
    setup_amesim_environment(settings.TEMP_PATH, settings.AMESIM_LICENSE_SERVER)

    eng = create_engine(settings.sync_database_url)
    with eng.connect() as conn:
        row = conn.execute(
            text("SELECT fmu_path FROM fmu_library WHERE type_name = :n"),
            {"n": fmu_type},
        ).fetchone()
    if not row:
        pf(f"FAIL: FMU type '{fmu_type}' not registered in fmu_library")
        sys.exit(2)
    original_fmu = Path(row[0])
    if not original_fmu.exists():
        pf(f"FAIL: FMU file {original_fmu} does not exist on disk")
        sys.exit(2)
    pf(f"  original FMU : {original_fmu}")

    safe_cwd = Path("/")  # somewhere that won't vanish when we rmtree(work)
    work = Path(tempfile.mkdtemp(prefix="multi_inst_"))

    try:
        # ── 1. Patch modelDescription.xml ─────────────────────────────────
        patched = work / "patched.fmu"
        shutil.copy2(original_fmu, patched)

        with zipfile.ZipFile(patched, "r") as zin:
            md_raw = zin.read("modelDescription.xml").decode("utf-8")
        if 'canBeInstantiatedOnlyOncePerProcess="true"' not in md_raw:
            pf("FAIL: 'canBeInstantiatedOnlyOncePerProcess=\"true\"' not found in XML.")
            sys.exit(2)
        md_new = md_raw.replace(
            'canBeInstantiatedOnlyOncePerProcess="true"',
            'canBeInstantiatedOnlyOncePerProcess="false"',
            1,
        )
        patched_tmp = work / "patched_tmp.fmu"
        with (
            zipfile.ZipFile(patched, "r") as zin,
            zipfile.ZipFile(patched_tmp, "w", zipfile.ZIP_DEFLATED) as zout,
        ):
            for info in zin.infolist():
                if info.filename == "modelDescription.xml":
                    zout.writestr(info, md_new.encode("utf-8"))
                else:
                    zout.writestr(info, zin.read(info.filename))
        shutil.move(patched_tmp, patched)
        pf("  XML patch    : canBeInstantiatedOnlyOncePerProcess → false")

        # ── 2. Prepare N distinct ready-to-load FMUs, each in its own dir ─
        inst_dirs: list[Path] = []
        ready_paths: list[Path] = []
        for i in range(n_instances):
            fmu_i = work / f"inst_{i:02d}.fmu"
            shutil.copy2(patched, fmu_i)
            dir_i = work / f"work_{i:02d}"
            dir_i.mkdir()
            ready_paths.append(prepare_fmu_for_simulation(fmu_i, dir_i))
            inst_dirs.append(dir_i)

        data_dir = original_fmu.parent / "data"
        if data_dir.exists():
            for f in data_dir.iterdir():
                if not f.is_file():
                    continue
                for wd in inst_dirs:
                    dest = wd / f.name
                    if f.suffix == ".data":
                        _normalize_data_file_for_injection(f, dest)
                    else:
                        shutil.copy2(f, dest)

        # ── 3. Load all N in ONE process. Watch for license errors. ───────
        from pyfmi import load_fmu  # type: ignore[import]

        models = []
        load_license_fail_at: int | None = None
        for i, (ready, wd) in enumerate(zip(ready_paths, inst_dirs)):
            os.chdir(wd)
            try:
                m = load_fmu(str(ready), log_level=0)
                models.append(m)
                pf(f"  load inst {i:2d} : ok")
            except Exception as exc:  # noqa: BLE001
                fmu_log = ""
                if models:
                    try:
                        fmu_log = "\n".join(models[-1].get_log()[-10:])
                    except Exception:
                        pass
                exc_text = str(exc)
                if _is_license_err(exc_text, fmu_log):
                    pf(f"  load inst {i:2d} : LICENSE FAIL — {exc_text[:200]}")
                    load_license_fail_at = i
                    break
                pf(f"  load inst {i:2d} : FAIL (non-license) — {exc_text[:200]}")
                os.chdir(safe_cwd)
                raise

        os.chdir(safe_cwd)
        loaded = len(models)
        pf(f"  summary      : {loaded}/{n_instances} instances loaded into one process")

        if load_license_fail_at is not None:
            pf("")
            pf(f"  VERDICT: licensing is PER-INSTANCE. Hit a license cap at "
               f"instance #{load_license_fail_at} within a single process.")
            pf("  Total simultaneous FMU instances (across all processes) is "
               "bounded by the license pool.")
            return 0  # informative outcome, not a failure of the test itself

        # ── 4. Initialize all N ──────────────────────────────────────────
        for i, (m, wd) in enumerate(zip(models, inst_dirs)):
            os.chdir(wd)
            m.setup_experiment(start_time=0.0)
            m.enter_initialization_mode()
            m.exit_initialization_mode()
        os.chdir(safe_cwd)
        pf(f"  initialize   : all {loaded} ok")

        # ── 5. Drive all with identical inputs; compare outputs ───────────
        inputs = {
            "amesim_interface.floor_temp": 15.0,
            "amesim_interface.roof_temp": 10.0,
            "amesim_interface.supply": 35.0,
        }
        names = list(inputs.keys())
        values = list(inputs.values())

        def _quiet(model):
            opts = model.simulate_options()
            opts["ncp"] = 1
            opts["initialize"] = False
            if "silent_mode" in opts:
                opts["silent_mode"] = True
            if "result_handling" in opts:
                opts["result_handling"] = "memory"
            cv = opts.get("CVode_options")
            if isinstance(cv, dict):
                cv["verbosity"] = 50
            return opts

        pf(f"  simulate     : 60s with identical inputs, all {loaded} instances...")
        room_temps: list[float] = []
        for i, (m, wd) in enumerate(zip(models, inst_dirs)):
            m.set(names, values)
            os.chdir(wd)
            res = m.simulate(start_time=0.0, final_time=60.0, options=_quiet(m))
            room_temps.append(float(res["amesim_interface.room_temp"][-1]))
        os.chdir(safe_cwd)

        for i, rt in enumerate(room_temps):
            pf(f"  inst {i:2d} room  : {rt:.4f} °C")
        spread = max(room_temps) - min(room_temps)
        pf(f"  max spread   : {spread:.6f} °C")

        tolerance = 0.001
        pf("")
        if spread < tolerance:
            pf(f"  VERDICT: PASS — all {loaded} instances in one process produced")
            pf(f"  identical results (spread {spread:.6f} °C < {tolerance} °C).")
            if loaded >= 10:
                pf("  No license errors despite loading 10+ instances in a single")
                pf("  Python process. This strongly suggests the license server is")
                pf("  counting PER PROCESS, not per instance — a huge win. Combined")
                pf("  with the XML singleton flip, we could run many apartments on")
                pf("  one license without needing Martti's state-save re-export.")
            else:
                pf("  The singleton-per-process flag is conservative; flipping it in")
                pf("  the XML is safe for this FMU. Try a larger N to test whether")
                pf("  licensing is per-process or per-instance.")
            return 0
        pf(f"  VERDICT: FAIL — outputs differ by {spread:.4f} °C > {tolerance} °C.")
        pf("  Instances appear to share state through static globals. A real")
        pf("  re-export from Martti is needed; editing the XML alone is not safe.")
        return 1
    finally:
        # Get out of any directory we might be about to delete so the shell
        # we return to isn't left pointing at a vanished cwd.
        try:
            os.chdir(safe_cwd)
        except Exception:
            pass
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        pf(f"FAIL: unexpected exception: {exc}")
        raise
PYEOF
)

  # Run the probe. If Python segfaults or exits non-zero, capture it.
  set +e
  docker compose exec -T api python -c "$PROBE" "$FMU_TYPE" "$INSTANCE_COUNT"
  rc=$?
  set -e
  echo ""
  if [ "$rc" -eq 0 ]; then
    echo "  ─────────────────────────────────────────────"
    echo "  Test passed — see verdict above for the licensing implication."
  elif [ "$rc" -eq 139 ] || [ "$rc" -eq 134 ]; then
    echo "  ─────────────────────────────────────────────"
    echo "  ✗ Python crashed (exit $rc — likely segfault/abort)."
    echo "  The FMU is definitely NOT safe to run this many in one process."
  else
    echo "  ─────────────────────────────────────────────"
    echo "  ✗ Test failed (exit $rc). See output above."
  fi
  echo ""
  exit "$rc"
fi

# ════════════════════════════════════════════════════════════════════════════
# Mode: license probe (default)
# ════════════════════════════════════════════════════════════════════════════

N="${1:-4}"
FMU_TYPE="${2:-stackable_apartment}"
HOLD_SECONDS="${3:-5}"

echo ""
echo "FMU Platform — License Probe"
echo "============================"
echo ""
echo "  Concurrent loads : $N"
echo "  FMU type         : $FMU_TYPE"
echo "  License hold     : ${HOLD_SECONDS}s per probe"
echo ""

# The probe itself runs inside the container. One small Python program that
# loads the FMU, runs 1s of simulation (long enough to force license checkout),
# and prints exactly one of: SUCCESS, LICENSE_FAILURE, OTHER_ERROR:<msg>.
PROBE=$(cat <<'PYEOF'
import os, sys, time, tempfile, shutil, logging
from pathlib import Path

logging.disable(logging.CRITICAL)

try:
    from sqlalchemy import create_engine, text
    from app.config import settings
    from engine.fmu_utils import setup_amesim_environment, prepare_fmu_for_simulation

    fmu_type = sys.argv[1]
    hold_seconds = float(sys.argv[2])
    setup_amesim_environment(settings.TEMP_PATH, settings.AMESIM_LICENSE_SERVER)

    engine = create_engine(settings.DATABASE_URL_SYNC)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT fmu_path FROM fmu_library WHERE type_name = :n"),
            {"n": fmu_type},
        ).fetchone()
    if not row:
        print(f"OTHER_ERROR: FMU type '{fmu_type}' not in library")
        sys.exit(0)
    fmu_path = Path(row[0])

    from pyfmi import load_fmu

    with tempfile.TemporaryDirectory(prefix="licprobe_") as tmp:
        work = Path(tmp)
        ready = prepare_fmu_for_simulation(fmu_path, work)
        data_dir = fmu_path.parent / "data"
        if data_dir.exists():
            from engine.fmu_utils import _normalize_data_file_for_injection
            for f in data_dir.iterdir():
                if f.is_file():
                    dest = work / f.name
                    if f.suffix == ".data":
                        _normalize_data_file_for_injection(f, dest)
                    else:
                        shutil.copy2(f, dest)
        os.chdir(work)

        model = load_fmu(str(ready), log_level=0)
        opts = model.simulate_options()
        opts["ncp"] = 2
        try:
            model.simulate(start_time=0.0, final_time=1.0, options=opts)
        except Exception as sim_exc:
            # Inspect FMU log for license-specific errors
            fmu_log = ""
            try:
                fmu_log = "\n".join(model.get_log())
            except Exception:
                pass
            if "lic_init failed" in fmu_log or "Checkout failed" in fmu_log:
                print("LICENSE_FAILURE")
                sys.exit(0)
            raise
        # License is checked out here. Hold it for the requested window.
        held_start = time.time()
        print(f"HELD_START {held_start:.3f}", flush=True)
        time.sleep(hold_seconds)
        held_end = time.time()
        print(f"HELD_END {held_end:.3f}", flush=True)
        print("SUCCESS")
except Exception as exc:
    msg = str(exc).replace("\n", " ")[:200]
    print(f"OTHER_ERROR: {msg}")
PYEOF
)

echo "  Launching $N parallel probes..."
echo ""

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

WALL_START=$(date +%s.%N)

for i in $(seq 1 "$N"); do
  (
    output=$(docker compose exec -T api python -c "$PROBE" "$FMU_TYPE" "$HOLD_SECONDS" 2>&1 || true)
    # Save full output for analysis; pull out the result tag for display.
    echo "$output" > "$TMPDIR/probe-$i.out"
    result=$(echo "$output" | grep -E '^(SUCCESS|LICENSE_FAILURE|OTHER_ERROR)' | tail -n 1)
    [ -z "$result" ] && result="OTHER_ERROR: no-result-tag (output: $(echo "$output" | tail -c 200))"
    printf "    probe %2d: %s\n" "$i" "$result"
  ) &
done

wait

WALL_END=$(date +%s.%N)
WALL_ELAPSED=$(awk -v s="$WALL_START" -v e="$WALL_END" 'BEGIN { printf "%.2f", e - s }')

echo ""
echo "  ─────────────────────────────────────────────"
echo "  Summary"
echo "  ─────────────────────────────────────────────"

SUCCESS=$(grep -lE '^SUCCESS$' "$TMPDIR"/probe-*.out 2>/dev/null | wc -l || true)
LIC_FAIL=$(grep -lE '^LICENSE_FAILURE$' "$TMPDIR"/probe-*.out 2>/dev/null | wc -l || true)
OTHER=$(grep -lE '^OTHER_ERROR' "$TMPDIR"/probe-*.out 2>/dev/null | wc -l || true)

printf "    successful checkouts : %d\n" "$SUCCESS"
printf "    license failures     : %d\n" "$LIC_FAIL"
printf "    other errors         : %d\n" "$OTHER"
printf "    total wall time      : %ss\n" "$WALL_ELAPSED"
echo ""

# Concurrency analysis: look at HELD_START / HELD_END timestamps from each
# probe. If two probes' hold windows overlap, at least two licenses were
# simultaneously checked out. Count the maximum overlap across time.
START_TIMES=$(grep -h '^HELD_START ' "$TMPDIR"/probe-*.out 2>/dev/null | awk '{print $2}')
END_TIMES=$(grep -h '^HELD_END ' "$TMPDIR"/probe-*.out 2>/dev/null | awk '{print $2}')
N_STARTS=$(echo "$START_TIMES" | grep -c . || true)

if [ "$N_STARTS" -ge 2 ]; then
  # Maximum overlap = at any instant, how many hold windows contain that instant?
  # Sweep-line algorithm: sort events, +1 on start, -1 on end, track max.
  MAX_OVERLAP=$(
    {
      echo "$START_TIMES" | awk '{ print $1, "+1" }'
      echo "$END_TIMES"   | awk '{ print $1, "-1" }'
    } | sort -k1,1n | awk '
      { cur += $2; if (cur > max) max = cur }
      END { print max }
    '
  )
  # Also compute the narrowest overlap window (for intuition).
  MAX_START=$(echo "$START_TIMES" | sort -n | tail -1)
  MIN_END=$(echo "$END_TIMES" | sort -n | head -1)
  ALL_OVERLAP=$(awk -v s="$MAX_START" -v e="$MIN_END" 'BEGIN { print (s < e) ? "yes" : "no" }')

  printf "    peak concurrent hold : %d / %d\n" "$MAX_OVERLAP" "$SUCCESS"
  printf "    all N simultaneously : %s\n" "$ALL_OVERLAP"
  echo ""

  if [ "$MAX_OVERLAP" -eq "$N" ] && [ "$LIC_FAIL" -eq 0 ]; then
    echo "  ✓ All $N licenses were held simultaneously. True parallel checkout."
    echo "    Try a higher N to find the ceiling."
  elif [ "$MAX_OVERLAP" -lt "$N" ] && [ "$LIC_FAIL" -eq 0 ]; then
    echo "  ⚠ Only $MAX_OVERLAP / $N held licenses simultaneously (despite all succeeding)."
    echo "    The license server may be serializing — probes checked out, released,"
    echo "    and the next one then checked out. Capacity likely = $MAX_OVERLAP."
  fi
fi

if [ "$LIC_FAIL" -gt 0 ]; then
  echo "  ⚠ Hit a license ceiling at N=$N."
  echo "    Effective parallel capacity is between $((N - LIC_FAIL)) and $((N - 1))."
fi

if [ "$OTHER" -gt 0 ]; then
  echo ""
  echo "  ⚠ Non-license errors occurred. First one:"
  grep -h '^OTHER_ERROR' "$TMPDIR"/probe-*.out | head -n 1 | sed 's/^/    /'
fi
echo ""
