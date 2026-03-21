# Build context is the repo root (set in docker-compose.yml).
# This lets us reference both admin/ and backend/ in one build.

# ── Stage 1: Build admin panel ────────────────────────────────────────────────
FROM node:20-alpine AS admin-builder

WORKDIR /admin-src

# Install dependencies (layer-cached unless package.json changes)
COPY admin/package*.json ./
RUN npm ci --prefer-offline

# Copy source and build
COPY admin/ ./
RUN npm run build
# Output is at /admin-src/dist

# ── Stage 2: Python backend ───────────────────────────────────────────────────
FROM condaforge/miniforge3:latest

# Install system dependencies needed by psycopg2, lxml, and curl (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install simulation stack from conda-forge (pre-built, compatible binaries)
RUN conda install -y -c conda-forge \
    python=3.11 \
    pyfmi \
    assimulo \
    numpy \
    && conda clean -afy

WORKDIR /app

# Copy only the backend source (not the whole repo)
COPY backend/ .

# Install the rest of the app dependencies via pip
RUN pip install --no-cache-dir "."

# Create storage directories
RUN mkdir -p /opt/fmu-platform/fmu-library \
             /opt/fmu-platform/projects \
             /opt/fmu-platform/temp

# Copy built admin panel from stage 1
COPY --from=admin-builder /admin-src/dist /app/admin-dist

EXPOSE 8000

ENTRYPOINT ["sh", "entrypoint.sh"]
