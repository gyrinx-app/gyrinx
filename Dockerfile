FROM python:3.14.7-slim

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
# The edition apps (n23.core / n23.content, n26.core / n26.library /
# n26.designsystem). Copied separately because the image is built from an
# explicit file list, not the whole tree — omit one and the container starts
# without that edition installed.
#
# These must be copied *before* `uv sync` below. The editable install writes a
# static `__editable___gyrinx_..._finder.py` whose module mapping is computed
# from whatever top-level packages exist at install time, so a directory that
# arrives after the sync is not importable however present its files are.
COPY n23/ /app/n23/
COPY n26/ /app/n26/
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

# Collect static into the image rather than on each container boot: the manifest
# and the gzip/brotli variants that CompressedManifestStaticFilesStorage writes
# are a pure function of the image's files, so a container recomputing them
# learns nothing and spends ~50s of its startup doing it.
#
# This must stay the LAST step that can see application files. The manifest only
# covers what exists when it runs, and ManifestStaticFilesStorage raises on a
# name it has no entry for — so a static asset added by a later COPY does not
# 404, it 500s every page that references it.
#
# settings_prod is required: it is what selects the WhiteNoise compressed-manifest
# storage, so building under plain `settings` would emit an unhashed tree that
# the manifest lookups then fail against at runtime. It needs no runtime
# environment — no database, no secrets, no GCP credentials; tracing init catches
# its own failure to reach GCP.
RUN DJANGO_SETTINGS_MODULE=gyrinx.settings_prod manage collectstatic --noinput

# Exec form: the script's shell becomes PID 1, so its `exec gunicorn` makes
# gunicorn PID 1 and SIGTERM from Cloud Run reaches it for graceful shutdown.
# (Shell form wraps the script in an outer `sh -c` that keeps PID 1 and dies
# on SIGTERM, taking the workers down hard.)
CMD ["./docker/entrypoint.sh"]
