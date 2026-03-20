FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir "."

# Create storage directories
RUN mkdir -p /opt/fmu-platform/fmu-library \
             /opt/fmu-platform/projects \
             /opt/fmu-platform/temp

EXPOSE 8000

ENTRYPOINT ["sh", "entrypoint.sh"]
