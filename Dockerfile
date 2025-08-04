FROM python:3.12.7-slim

ENV PYTHONUNBUFFERED=1 \
    # prevents python creating .pyc files
    PYTHONDONTWRITEBYTECODE=1 \
    \
    # pip
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /app
RUN python -m venv /opt/venv
# Enable venv
ENV PATH="/opt/venv/bin:$PATH"

# Set application settings
ENV DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-gyrinx.settings}

# Install python dependencies
COPY pyproject.toml requirements.txt /app/
COPY scripts/ /app/scripts/
COPY gyrinx/ /app/gyrinx/
COPY content/ /app/content/
# Set a version for setuptools-scm when .git is not available
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_GYRINX=1.0.0
RUN pip install --editable .

# Install node dependencies
COPY package.json package-lock.json /app/
RUN nodeenv -p
RUN npm install

# Build frontend
RUN npm run build

COPY docker/ /app/docker/

EXPOSE $PORT

CMD ./docker/entrypoint.sh
