FROM python:3.12.13-slim

ENV PYTHONUNBUFFERED=1 \
    # prevents python creating .pyc files
    PYTHONDONTWRITEBYTECODE=1

# Pinned so the image resolves with the same uv as CI and scripts/dev.sh.
# Dependabot's docker ecosystem keeps this tag current.
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

WORKDIR /app
# UV_PROJECT_ENVIRONMENT tells `uv sync` which environment to manage; VIRTUAL_ENV
# and PATH make it the default interpreter for the rest of the build and at
# runtime. `uv sync` creates the environment itself, so there is no `uv venv`.
ENV UV_PROJECT_ENVIRONMENT="/opt/venv" \
    VIRTUAL_ENV="/opt/venv" \
    PATH="/opt/venv/bin:$PATH"

# Set application settings
ENV DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-gyrinx.settings}

# Install python dependencies
COPY pyproject.toml uv.lock /app/
COPY scripts/ /app/scripts/
COPY gyrinx/ /app/gyrinx/
# The n23 edition apps (n23.core / n23.content). Copied separately because the
# image is built from an explicit file list, not the whole tree — omit this and
# the container starts without the edition installed, which no test catches.
COPY n23/ /app/n23/
# Game data files, unrelated to the n23 Python package above.
COPY content/ /app/content/
# Root-level static assets (favicon.ico) served by WhiteNoise via
# WHITENOISE_ROOT — without this the container warns "No directory at:
# /app/static/" and /favicon.ico falls through to the page router.
COPY static/ /app/static/
# Set a version for setuptools-scm when .git is not available
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_GYRINX=1.0.0
# --locked installs exactly what uv.lock pins and fails if the lock is stale, so
# the image can never be built from a lock that has drifted from pyproject.toml.
RUN uv sync --locked --no-dev

# Install system dependencies for Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    libatomic1 \
    && rm -rf /var/lib/apt/lists/*

# Install node dependencies
COPY package.json package-lock.json /app/
RUN nodeenv -p
RUN npm install

# Build frontend
RUN npm run build

COPY docker/ /app/docker/

EXPOSE $PORT

# Exec form: the script's shell becomes PID 1, so its `exec gunicorn` makes
# gunicorn PID 1 and SIGTERM from Cloud Run reaches it for graceful shutdown.
# (Shell form wraps the script in an outer `sh -c` that keeps PID 1 and dies
# on SIGTERM, taking the workers down hard.)
CMD ["./docker/entrypoint.sh"]
