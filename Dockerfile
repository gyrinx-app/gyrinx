FROM python:3.14.6-slim

ENV PYTHONUNBUFFERED=1 \
    # prevents python creating .pyc files
    PYTHONDONTWRITEBYTECODE=1 \
    \
    # pip
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

# Pinned so the image resolves with the same uv as CI and scripts/dev.sh.
# Dependabot's docker ecosystem keeps this tag current.
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

WORKDIR /app
RUN uv venv /opt/venv
# Enable venv. VIRTUAL_ENV is what uv reads to pick an install target; PATH
# alone is not enough.
ENV VIRTUAL_ENV="/opt/venv" \
    PATH="/opt/venv/bin:$PATH"

# Set application settings
ENV DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-gyrinx.settings}

# Install python dependencies
COPY pyproject.toml requirements.txt /app/
COPY scripts/ /app/scripts/
COPY gyrinx/ /app/gyrinx/
COPY content/ /app/content/
# Set a version for setuptools-scm when .git is not available
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_GYRINX=1.0.0
RUN uv pip install --editable .

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

CMD ./docker/entrypoint.sh
