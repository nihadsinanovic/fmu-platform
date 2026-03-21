FROM condaforge/miniforge3:latest AS base

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

COPY . .

# Install the rest of the app dependencies via pip
# (FastAPI, SQLAlchemy, Celery, etc.)
RUN pip install --no-cache-dir "."

# Create storage directories
RUN mkdir -p /opt/fmu-platform/fmu-library \
             /opt/fmu-platform/projects \
             /opt/fmu-platform/temp

EXPOSE 8000

ENTRYPOINT ["sh", "entrypoint.sh"]
