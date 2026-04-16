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
#   ./test-license-count.sh               # default: N=4, FMU=stackable_apartment
#   ./test-license-count.sh 8             # try 8 concurrent
#   ./test-license-count.sh 8 my_fmu_name # custom FMU type name
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

N="${1:-4}"
FMU_TYPE="${2:-stackable_apartment}"

echo ""
echo "FMU Platform — License Probe"
echo "============================"
echo ""
echo "  Concurrent loads : $N"
echo "  FMU type         : $FMU_TYPE"
echo ""

if ! docker compose ps --status running --services 2>/dev/null | grep -q '^api$'; then
  echo "  ✗ The 'api' container is not running."
  exit 1
fi

# The probe itself runs inside the container. One small Python program that
# loads the FMU, runs 1s of simulation (long enough to force license checkout),
# and prints exactly one of: SUCCESS, LICENSE_FAILURE, OTHER_ERROR:<msg>.
PROBE=$(cat <<'PYEOF'
import os, sys, tempfile, shutil, logging
from pathlib import Path

logging.disable(logging.CRITICAL)

try:
    from sqlalchemy import create_engine, text
    from app.config import settings
    from engine.fmu_utils import setup_amesim_environment, prepare_fmu_for_simulation

    fmu_type = sys.argv[1]
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

for i in $(seq 1 "$N"); do
  (
    output=$(docker compose exec -T api python -c "$PROBE" "$FMU_TYPE" 2>&1 || true)
    # Keep only the last non-empty line (the result tag), in case anything
    # leaked to stdout despite our logging.disable.
    result=$(echo "$output" | grep -E '^(SUCCESS|LICENSE_FAILURE|OTHER_ERROR)' | tail -n 1)
    [ -z "$result" ] && result="OTHER_ERROR: no-result-tag (output: $(echo "$output" | tail -c 200))"
    echo "$result" > "$TMPDIR/probe-$i.out"
    printf "    probe %2d: %s\n" "$i" "$result"
  ) &
done

wait

echo ""
echo "  ─────────────────────────────────────────────"
echo "  Summary"
echo "  ─────────────────────────────────────────────"

SUCCESS=$(grep -l '^SUCCESS$' "$TMPDIR"/probe-*.out 2>/dev/null | wc -l || true)
LIC_FAIL=$(grep -l '^LICENSE_FAILURE$' "$TMPDIR"/probe-*.out 2>/dev/null | wc -l || true)
OTHER=$(grep -l '^OTHER_ERROR' "$TMPDIR"/probe-*.out 2>/dev/null | wc -l || true)

printf "    successful checkouts : %d\n" "$SUCCESS"
printf "    license failures     : %d\n" "$LIC_FAIL"
printf "    other errors         : %d\n" "$OTHER"
echo ""

if [ "$LIC_FAIL" -eq 0 ] && [ "$OTHER" -eq 0 ]; then
  echo "  ✓ All $N succeeded. Try a higher N to find the ceiling."
elif [ "$LIC_FAIL" -gt 0 ]; then
  echo "  ⚠ Hit a license ceiling at N=$N."
  echo "    Effective parallel capacity is between $((N - LIC_FAIL)) and $N-1."
  echo "    Re-run with lower N to confirm."
fi

if [ "$OTHER" -gt 0 ]; then
  echo ""
  echo "  ⚠ Non-license errors occurred. First one:"
  grep -h '^OTHER_ERROR' "$TMPDIR"/probe-*.out | head -n 1 | sed 's/^/    /'
fi
echo ""
