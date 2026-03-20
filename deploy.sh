#!/usr/bin/env bash
#
# FMU Platform — Deploy / Update
#
# Run this on the VPS to pull the latest code and redeploy.
# First-time setup: run ./setup.sh first to generate .env
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

echo ""
echo "FMU Platform — Deploy"
echo "====================="
echo ""

# ── Pre-flight checks ───────────────────────────────────────────────────────

if [ ! -f ".env" ]; then
  echo "  ✗ No .env file found. Run ./setup.sh first."
  exit 1
fi

if ! command -v docker &>/dev/null; then
  echo "  ✗ Docker not found. Install Docker first:"
  echo "    curl -fsSL https://get.docker.com | sh"
  exit 1
fi

# ── Pull latest code ────────────────────────────────────────────────────────

echo "  Pulling latest code..."
git pull origin master 2>/dev/null || git pull origin main 2>/dev/null || {
  echo "  ⚠ Git pull failed — deploying from current local code"
}

# ── Build and deploy ─────────────────────────────────────────────────────────

echo "  Building and starting containers..."
docker compose up -d --build --remove-orphans

# ── Wait for health ──────────────────────────────────────────────────────────

echo "  Waiting for API to be healthy..."
for i in $(seq 1 30); do
  if docker compose exec -T api curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
    echo "  ✓ API is healthy"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "  ⚠ API not healthy after 30s — check logs with: docker compose logs api"
  fi
  sleep 1
done

# ── Status ───────────────────────────────────────────────────────────────────

echo ""
docker compose ps --format "table {{.Name}}\t{{.Status}}"
echo ""

DOMAIN=$(grep "^DOMAIN=" .env 2>/dev/null | cut -d= -f2)
if [ -n "$DOMAIN" ] && [ "$DOMAIN" != "localhost" ]; then
  echo "  ✓ Deployed at https://$DOMAIN"
  echo "    API docs: https://$DOMAIN/api/docs"
else
  echo "  ✓ Deployed locally"
  echo "    API docs: http://localhost:8000/api/docs"
fi

echo ""
