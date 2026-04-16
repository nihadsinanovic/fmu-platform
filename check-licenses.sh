#!/usr/bin/env bash
#
# FMU Platform — AMESim License Check
#
# Queries the configured license server and reports how many licenses
# exist for each feature, how many are in use, and how many are free.
#
# Usage:
#   ./check-licenses.sh                 # uses AMESIM_LICENSE_SERVER from .env
#   ./check-licenses.sh 27000@hostname  # override server
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

echo ""
echo "FMU Platform — License Check"
echo "============================"
echo ""

# ── Load server from .env if not given as arg ────────────────────────────────

if [ -f ".env" ]; then
  # shellcheck disable=SC1091
  set -a && source .env && set +a
fi

SERVER="${1:-${AMESIM_LICENSE_SERVER:-}}"
if [ -z "$SERVER" ]; then
  echo "  ✗ No license server configured."
  echo "    Set AMESIM_LICENSE_SERVER in .env, or pass it as an argument:"
  echo "      $0 27000@hostname"
  exit 1
fi

echo "  License server: $SERVER"
echo ""

# ── Make sure the api container is running ───────────────────────────────────

if ! docker compose ps --status running --services 2>/dev/null | grep -q '^api$'; then
  echo "  ✗ The 'api' container is not running."
  echo "    Start it first with: docker compose up -d api"
  exit 1
fi

# ── Run the query inside the api container ──────────────────────────────────
#
# AMESim's licensing tool (lmutil / splm_lmutil) is installed alongside
# AMESim itself. We search common locations inside the container.

TMP_OUTPUT=$(mktemp)
trap 'rm -f "$TMP_OUTPUT"' EXIT

echo "  Querying license server..."
echo ""

docker compose exec -T api bash -s "$SERVER" <<'INNER' | tee "$TMP_OUTPUT"
set -eu
SERVER="$1"

# Candidate locations for the license query tool.
# Order: most specific first, so a bundled tool wins over anything on PATH.
CANDIDATES=(
  "${AME:-}/sys/bin/lmutil"
  "${AME:-}/licensing/bin/lmutil"
  "${AME:-}/licensing/bin/splm_lmutil"
  "/opt/Siemens/AMESim/2025.1/licensing/bin/splm_lmutil"
  "/opt/Siemens/AMESim/2025.1/licensing/bin/lmutil"
  "/opt/Siemens/SimcenterAMESim/licensing/bin/splm_lmutil"
  "/opt/Siemens/SimcenterAMESim/licensing/bin/lmutil"
  "splm_lmutil"
  "lmutil"
)

TOOL=""
for path in "${CANDIDATES[@]}"; do
  [ -z "$path" ] && continue
  # Expand globs (if any) and take the first executable match.
  for expanded in $path; do
    if [ -x "$expanded" ]; then
      TOOL="$expanded"
      break 2
    fi
    if command -v "$expanded" >/dev/null 2>&1; then
      TOOL="$(command -v "$expanded")"
      break 2
    fi
  done
done

if [ -z "$TOOL" ]; then
  echo "ERROR: Could not find lmutil or splm_lmutil inside the container."
  echo "Search these locations manually:"
  echo "  docker compose exec api find / -name 'lmutil' -o -name 'splm_lmutil' 2>/dev/null"
  exit 2
fi

echo "Tool: $TOOL"
echo "--- lmstat output ---"
# -a shows all features. -c points at the license server.
"$TOOL" lmstat -c "$SERVER" -a 2>&1 || true
echo "--- end lmstat output ---"
INNER

echo ""
echo "  ─────────────────────────────────────────────"
echo "  Summary"
echo "  ─────────────────────────────────────────────"

# Parse FlexLM-style lines: "Users of FEATURE:  (Total of N licenses issued;  Total of M licenses in use)"
if ! grep -qE "Users of .+Total of [0-9]+ licenses? issued" "$TMP_OUTPUT"; then
  echo "  ⚠ No license features detected in the output."
  echo "    Check that the license server is reachable and serving AMESim features."
  exit 1
fi

grep -E "Users of .+Total of [0-9]+ licenses? issued" "$TMP_OUTPUT" | \
  sed -E 's/.*Users of ([^:]+):[[:space:]]*\(Total of ([0-9]+) licenses? issued;[[:space:]]+Total of ([0-9]+) licenses? in use.*/\1|\2|\3/' | \
  awk -F'|' '
    {
      feature = $1; issued = $2; in_use = $3; free = issued - in_use;
      printf "  %-40s %2d issued  %2d in use  %2d free\n", feature, issued, in_use, free;
    }
  '

echo ""
echo "  Tip: for running the stackable apartment FMU, you need one license"
echo "  of the AMESim runtime feature per concurrent FMU instance."
echo ""
