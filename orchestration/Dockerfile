# Dagster: one image for both Compose services (dagster-webserver, dagster-daemon).
# Build context is the repo root; orchestration/Dockerfile.dockerignore picks what goes in.
#   GIT_COMMIT=$(scripts/git-commit.sh) docker compose build dagster-webserver dagster-daemon
# Installs the `pipeline` (ingestion, dbt) and `orchestration` (Dagster) groups, not `api`.

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --group pipeline --group orchestration --no-install-project

FROM python:3.12-slim
RUN useradd --system --uid 10002 --create-home dagster
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY ingestion/ ./ingestion/
COPY transform/ ./transform/
COPY orchestration/ ./orchestration/
COPY scripts/git-commit.sh ./scripts/
ENV PATH=/app/.venv/bin:$PATH PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DAGSTER_HOME=/app/orchestration PIPELINE_TARGET=warehouse

# The dbt manifest, parsed now so the containers start without running dbt. profiles.yml
# needs these variables to render, but parsing never connects: placeholders, not secrets.
RUN POSTGRES_DB=parse PIPELINE_USER=parse PIPELINE_PASSWORD=parse \
    dbt parse --quiet --project-dir transform --profiles-dir transform \
      --target warehouse --target-path target-dagster-warehouse

# Writable at run time: dbt's target and logs, Dagster's local artifacts, and downloads
# (data/raw: a named volume, initialised from this directory with this ownership).
RUN mkdir -p data/raw orchestration/storage transform/logs \
 && chown -R dagster:dagster data orchestration/storage transform/logs transform/target-dagster-warehouse

# The commit this image was built from (no .git inside): scripts/git-commit.sh keeps it.
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=$GIT_COMMIT

USER dagster
EXPOSE 3000
CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "3000", "-m", "orchestration.definitions"]
