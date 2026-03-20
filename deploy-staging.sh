#!/usr/bin/env bash
#
# FMU Platform — Deploy Staging
#
# Deploys the staging stack alongside production.
# Run ./setup-staging.sh first to generate .env.staging
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

echo ""
echo "FMU Platform — Deploy Staging"
echo "============================="
echo ""

# ── Pre-flight checks ───────────────────────────────────────────────────

if [ ! -f ".env.staging" ]; then
  echo "  ✗ No .env.staging file found. Run ./setup-staging.sh first."
  exit 1
fi

if [ ! -f ".env" ]; then
  echo "  ✗ No .env file found. Run ./setup.sh first (production must be set up)."
  exit 1
fi

# ── Pull latest code ────────────────────────────────────────────────────

echo "  Pulling latest code..."
git pull origin master 2>/dev/null || git pull origin main 2>/dev/null || {
  echo "  ⚠ Git pull failed — deploying from current local code"
}

# ── Ensure the shared network exists ─────────────────────────────────────

docker network inspect fmu-platform_default >/dev/null 2>&1 || {
  echo "  ⚠ Production network not found. Start production first: ./deploy.sh"
  exit 1
}

# ── Restart Caddy to pick up staging domain ──────────────────────────────

echo "  Reloading Caddy with staging config..."
docker compose restart caddy 2>/dev/null || true

# ── Build and deploy staging ─────────────────────────────────────────────

echo "  Building and starting staging containers..."
docker compose -f docker-compose.staging.yml --env-file .env.staging -p fmu-staging up -d --build --remove-orphans

# ── Wait for health ──────────────────────────────────────────────────────

echo "  Waiting for staging API to be healthy..."
for i in $(seq 1 30); do
  if docker compose -f docker-compose.staging.yml -p fmu-staging exec -T api-staging curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
    echo "  ✓ Staging API is healthy"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "  ⚠ Staging API not healthy after 30s — check logs:"
    echo "    docker compose -f docker-compose.staging.yml -p fmu-staging logs api-staging"
  fi
  sleep 1
done

# ── Status ───────────────────────────────────────────────────────────────

echo ""
docker compose -f docker-compose.staging.yml -p fmu-staging ps --format "table {{.Name}}\t{{.Status}}"
echo ""

STAGING_DOMAIN=$(grep "^STAGING_DOMAIN=" .env.staging 2>/dev/null | cut -d= -f2)
if [ -n "$STAGING_DOMAIN" ] && [ "$STAGING_DOMAIN" != ":8080" ]; then
  echo "  ✓ Staging deployed at https://$STAGING_DOMAIN"
else
  echo "  ✓ Staging deployed"
fi

echo ""
