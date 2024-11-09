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
RUN pip install --editable .

# Install node dependencies
COPY package.json package-lock.json /app/
RUN nodeenv -p
RUN npm install

# Build frontend
RUN npm run build


# Collect static files for serving
RUN manage collectstatic --noinput

EXPOSE $PORT

CMD daphne -b 0.0.0.0 -p $PORT "gyrinx.asgi:application"
