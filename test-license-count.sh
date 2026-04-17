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
#   ./test-license-count.sh multi-instance        # multi-instance safety test, default FMU
#   ./test-license-count.sh multi-instance my_fmu # same, custom FMU type
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

  echo ""
  echo "FMU Platform — Multi-Instance Safety Test"
  echo "========================================="
  echo ""
  echo "  FMU type : $FMU_TYPE"
  echo ""
  echo "  Flipping canBeInstantiatedOnlyOncePerProcess to false in a copy of"
  echo "  the FMU and attempting to load two instances in one Python process."
  echo "  If both produce identical outputs for identical inputs, the flag"
  echo "  was conservative and we can skip that part of the re-export."
  echo ""

  PROBE=$(cat <<'PYEOF'
import logging
import os
import re
import shutil
import sys
import tempfile
import zipfile
from functools import partial
from pathlib import Path

logging.disable(logging.CRITICAL)
pf = partial(print, flush=True)


def main():
    from sqlalchemy import create_engine, text

    from app.config import settings
    from engine.fmu_utils import (
        _normalize_data_file_for_injection,
        prepare_fmu_for_simulation,
        setup_amesim_environment,
    )

    fmu_type = sys.argv[1]
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

    work = Path(tempfile.mkdtemp(prefix="multi_inst_"))
    try:
        # ── 1. Patch modelDescription.xml ─────────────────────────────────
        patched = work / "patched.fmu"
        shutil.copy2(original_fmu, patched)

        with zipfile.ZipFile(patched, "r") as zin:
            md_raw = zin.read("modelDescription.xml").decode("utf-8")
        if 'canBeInstantiatedOnlyOncePerProcess="true"' not in md_raw:
            pf("FAIL: 'canBeInstantiatedOnlyOncePerProcess=\"true\"' not found in XML.")
            pf("  The FMU may already be multi-instance, or uses a different syntax.")
            sys.exit(2)
        md_new = md_raw.replace(
            'canBeInstantiatedOnlyOncePerProcess="true"',
            'canBeInstantiatedOnlyOncePerProcess="false"',
            1,
        )

        # Rewrite the zip: only modelDescription.xml changes; everything else
        # is copied byte-for-byte from the original.
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

        # ── 2. Make two copies with distinct names so prepare_fmu_for_simulation
        #      doesn't overwrite its own output on the second call.
        fmu_a = work / "inst_a.fmu"
        fmu_b = work / "inst_b.fmu"
        shutil.copy2(patched, fmu_a)
        shutil.copy2(patched, fmu_b)

        dir_a = work / "work_a"
        dir_b = work / "work_b"
        dir_a.mkdir()
        dir_b.mkdir()
        ready_a = prepare_fmu_for_simulation(fmu_a, dir_a)
        ready_b = prepare_fmu_for_simulation(fmu_b, dir_b)

        # Also drop data files directly in each work dir, matching what
        # _run_fmu_test_sync does — belt and suspenders.
        data_dir = original_fmu.parent / "data"
        if data_dir.exists():
            for f in data_dir.iterdir():
                if not f.is_file():
                    continue
                for wd in (dir_a, dir_b):
                    dest = wd / f.name
                    if f.suffix == ".data":
                        _normalize_data_file_for_injection(f, dest)
                    else:
                        shutil.copy2(f, dest)

        # ── 3. Load both in ONE process ───────────────────────────────────
        from pyfmi import load_fmu  # type: ignore[import]

        os.chdir(dir_a)
        pf("  load inst A  : attempting...")
        model_a = load_fmu(str(ready_a), log_level=0)
        pf("  load inst A  : ok")

        os.chdir(dir_b)
        pf("  load inst B  : attempting (critical test)...")
        try:
            model_b = load_fmu(str(ready_b), log_level=0)
        except Exception as exc:  # noqa: BLE001
            pf(f"  load inst B  : FAILED — {exc}")
            pf("")
            pf("  VERDICT: FMU cannot be loaded twice even with the flag flipped.")
            pf("  Need a real re-export from Martti with the singleton flag off.")
            sys.exit(1)
        pf("  load inst B  : ok")

        # ── 4. Initialize both ────────────────────────────────────────────
        os.chdir(dir_a)
        model_a.setup_experiment(start_time=0.0)
        model_a.enter_initialization_mode()
        model_a.exit_initialization_mode()

        os.chdir(dir_b)
        model_b.setup_experiment(start_time=0.0)
        model_b.enter_initialization_mode()
        model_b.exit_initialization_mode()
        pf("  initialize   : both ok")

        # ── 5. Drive both with identical inputs ───────────────────────────
        inputs = {
            "amesim_interface.floor_temp": 15.0,
            "amesim_interface.roof_temp": 10.0,
            "amesim_interface.supply": 35.0,
        }
        names = list(inputs.keys())
        values = list(inputs.values())
        model_a.set(names, values)
        model_b.set(names, values)

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

        pf("  simulate     : 60s with identical inputs, both instances...")
        os.chdir(dir_a)
        res_a = model_a.simulate(start_time=0.0, final_time=60.0, options=_quiet(model_a))
        os.chdir(dir_b)
        res_b = model_b.simulate(start_time=0.0, final_time=60.0, options=_quiet(model_b))

        room_a = float(res_a["amesim_interface.room_temp"][-1])
        room_b = float(res_b["amesim_interface.room_temp"][-1])
        diff = abs(room_a - room_b)
        pf(f"  inst A result: room_temp @ t=60s = {room_a:.4f} °C")
        pf(f"  inst B result: room_temp @ t=60s = {room_b:.4f} °C")
        pf(f"  |A - B|      : {diff:.6f} °C")

        pf("")
        tolerance = 0.001
        if diff < tolerance:
            pf("  VERDICT: PASS — two instances in one process produced identical")
            pf(f"  results (difference {diff:.6f} °C < {tolerance} °C tolerance).")
            pf("  The singleton-per-process flag appears to be a conservative")
            pf("  declaration; flipping it in the XML is safe for this FMU.")
            pf("  (State flags canGetAndSetFMUstate still require a re-export.)")
            return 0
        else:
            pf(f"  VERDICT: FAIL — outputs differ by {diff:.4f} °C > {tolerance} °C.")
            pf("  Instances appear to share state through static globals. A real")
            pf("  re-export from Martti is needed; editing the XML alone is not safe.")
            return 1
    finally:
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
  docker compose exec -T api python -c "$PROBE" "$FMU_TYPE"
  rc=$?
  set -e
  echo ""
  if [ "$rc" -eq 0 ]; then
    echo "  ─────────────────────────────────────────────"
    echo "  Test passed. The singleton flag can safely be flipped in the XML."
    echo "  Still need Martti's re-export for canGetAndSetFMUstate."
  elif [ "$rc" -eq 139 ] || [ "$rc" -eq 134 ]; then
    echo "  ─────────────────────────────────────────────"
    echo "  ✗ Python crashed (exit $rc — likely segfault/abort)."
    echo "  The FMU is definitely NOT safe to run twice in one process."
    echo "  Need Martti's re-export."
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
