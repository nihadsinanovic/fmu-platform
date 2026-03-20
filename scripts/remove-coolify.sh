#!/usr/bin/env bash
#
# Remove Coolify from this server
#
# This stops all Coolify containers, removes its data, and frees up
# ports 80/443/8080 for the FMU platform's own Caddy reverse proxy.
#
# Run this ON THE VPS as root.
#
set -euo pipefail

echo ""
echo "Remove Coolify"
echo "=============="
echo ""
echo "This will:"
echo "  1. Stop all Coolify-managed containers (including the FMU platform ones)"
echo "  2. Remove Coolify's own containers (coolify, coolify-db, coolify-redis, etc.)"
echo "  3. Remove Coolify's data from /data/coolify"
echo "  4. Free up ports 80, 443, and 8080"
echo ""
echo "Your FMU platform code and database volumes will NOT be deleted."
echo "You'll redeploy using plain docker compose after this."
echo ""
read -rp "Continue? [y/N] " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
  echo "Aborted."
  exit 0
fi

echo ""

# ── Step 1: Stop Coolify-managed application containers ──────────────────────

echo "  Stopping Coolify-managed app containers..."
APP_CONTAINERS=$(docker ps -a --filter "label=coolify.managed=true" --format "{{.Names}}" 2>/dev/null || true)
FMU_CONTAINERS=$(docker ps -a --format "{{.Names}}" | grep "f1r37fkfx3fsrc4anzr7ksxu" 2>/dev/null || true)

for container in $APP_CONTAINERS $FMU_CONTAINERS; do
  echo "    Stopping $container"
  docker stop "$container" 2>/dev/null || true
  docker rm "$container" 2>/dev/null || true
done

# ── Step 2: Stop Coolify's own containers ────────────────────────────────────

echo "  Stopping Coolify core containers..."
COOLIFY_DIR="/data/coolify/source"
if [ -d "$COOLIFY_DIR" ] && [ -f "$COOLIFY_DIR/docker-compose.yml" ]; then
  cd "$COOLIFY_DIR"
  docker compose down --remove-orphans 2>/dev/null || true
fi

# Also catch any stragglers
for name in coolify coolify-db coolify-redis coolify-realtime coolify-soketi; do
  if docker ps -a --format "{{.Names}}" | grep -q "^${name}$"; then
    echo "    Removing $name"
    docker stop "$name" 2>/dev/null || true
    docker rm "$name" 2>/dev/null || true
  fi
done

# ── Step 3: Remove Coolify proxy (Traefik/Caddy) ────────────────────────────

echo "  Removing Coolify proxy..."
PROXY_DIR="/data/coolify/proxy"
if [ -d "$PROXY_DIR" ] && [ -f "$PROXY_DIR/docker-compose.yml" ]; then
  cd "$PROXY_DIR"
  docker compose down --remove-orphans 2>/dev/null || true
fi

# ── Step 4: Clean up Coolify data ────────────────────────────────────────────

echo "  Removing Coolify data..."
rm -rf /data/coolify/source
rm -rf /data/coolify/proxy
rm -rf /data/coolify/ssh
rm -rf /data/coolify/applications

# Keep /data/coolify briefly in case we missed something
# The user can rm -rf /data/coolify manually later

# ── Step 5: Remove Coolify volumes ───────────────────────────────────────────

echo "  Removing Coolify Docker volumes..."
for vol in $(docker volume ls --format "{{.Name}}" | grep coolify); do
  echo "    Removing volume $vol"
  docker volume rm "$vol" 2>/dev/null || true
done

# ── Step 6: Clean up unused Docker resources ─────────────────────────────────

echo "  Pruning unused Docker resources..."
docker network prune -f 2>/dev/null || true
docker image prune -f 2>/dev/null || true

# ── Step 7: Verify ports are free ────────────────────────────────────────────

echo ""
echo "  Checking ports..."
for port in 80 443 8080; do
  if ss -tlnp | grep -q ":$port "; then
    echo "    ⚠ Port $port still in use — check with: ss -tlnp | grep :$port"
  else
    echo "    ✓ Port $port is free"
  fi
done

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo "  ✓ Coolify removed"
echo ""
echo "  Next steps:"
echo "    1. Clone your repo:   git clone https://github.com/nihadsinanovic/fmu-platform.git /opt/fmu-platform"
echo "    2. Run setup:         cd /opt/fmu-platform && ./setup.sh"
echo "    3. Deploy:            ./deploy.sh"
echo ""
echo "  To fully remove Coolify remnants later:"
echo "    rm -rf /data/coolify"
echo ""
