# Three stages: a shared base, a dev image with hot reload, and a runtime image
# that carries no build toolchain.
#
# The split matters. `build-essential` used to live in the shared base, so the
# production image shipped a C compiler and its headers — a few hundred MB of
# attack surface for something only needed while installing wheels.

# --- Base: the Python runtime, nothing else -------------------------------
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# `curl` is the healthcheck; `libpq5` is the client library asyncpg links
# against, and `postgresql-client` provides pg_dump/pg_restore for
# scripts/backup.py. All runtime, none of them compilers.
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl libpq5 postgresql-client \
    && rm -rf /var/lib/apt/lists/*


# --- Builder: compiles wheels, then is discarded --------------------------
FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
    && rm -rf /var/lib/apt/lists/*
# `app` as well as the manifest: `pyproject.toml` names it under
# `[tool.setuptools] packages`, so `pip install .` fails with "package
# directory 'app' does not exist" without it. Before that setting was added
# the install quietly succeeded here by finding no packages at all and
# building an empty distribution — the dependencies came from the later
# `COPY . .` shadowing it.
#
# The cost is that a source change invalidates the dependency install. That is
# the right trade against an image whose contents depend on which layer won.
COPY pyproject.toml ./
COPY app ./app
# Into a virtualenv so the whole dependency tree can be copied as one
# self-contained directory, leaving the compiler behind.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install .


# --- Dev: hot reload, dev dependencies, source mounted over the top -------
FROM base AS dev
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
    && rm -rf /var/lib/apt/lists/*
# Same reason as the builder stage: an editable install still resolves the
# package directory named in pyproject.toml, so `app` has to be here first.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && pip install -e ".[dev]"
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# --- Prod -----------------------------------------------------------------
FROM base AS prod
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Ownership is set during the copy rather than by a later `chown -R`, which
# would duplicate the whole tree into another layer.
RUN useradd --create-home --shell /bin/bash appuser
COPY --chown=appuser:appuser . .
USER appuser

EXPOSE 8000

# Distinguishes "the process is up" from "it can serve", and is what compose
# and most orchestrators use to decide whether to route traffic here.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/v1/healthz || exit 1

# Worker count belongs to the deployment, not the image: it depends on the
# host's cores and on how many replicas are running.
ENV WEB_CONCURRENCY=2
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY}"]
