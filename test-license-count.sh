#!/usr/bin/env bash
#
# FMU Platform — Empirical AMESim License Probe
#
# Spawns N parallel Python processes inside the api container, each of which
# loads the given FMU and runs a brief simulation. Reports how many succeed
# vs. fail due to license checkout. Since each docker-exec call creates a
# fresh Python process, this bypasses the FMU's
# canBeInstantiatedOnlyOncePerProcess="true" constraint and actually exercises
# the license server the way a multi-process co-simulation would.
#
# Usage:
#   ./test-license-count.sh                  # default: N=4, FMU=stackable_apartment, hold=5s
#   ./test-license-count.sh 8                # try 8 concurrent
#   ./test-license-count.sh 8 my_fmu_name    # custom FMU type name
#   ./test-license-count.sh 8 my_fmu_name 10 # hold each license for 10s
#
# Each probe explicitly holds its license for HOLD_SECONDS (default 5s) after
# FMU instantiation. This way, if licenses are truly being checked out in
# parallel, total wall time stays ~= HOLD_SECONDS + startup overhead regardless
# of N. If the license server is serializing, total wall time grows with N.
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

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

if ! docker compose ps --status running --services 2>/dev/null | grep -q '^api$'; then
  echo "  ✗ The 'api' container is not running."
  exit 1
fi

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
