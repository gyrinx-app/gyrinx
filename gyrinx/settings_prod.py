import os

from .settings import *  # noqa: F403
from .settings import LOGGING, STORAGES, TASKS
from .storage_settings import configure_gcs_storage

# Use GCP tracing in production
TRACING_MODE = "gcp"

# GCP Project ID - required for trace correlation in logging
# Uses env var with hardcoded fallback (same approach as storage_settings.py)
GCP_PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or "windy-ellipse-440618-p9"

# Configure Django logging for production using StructuredLogHandler
# This writes JSON to stdout, which Cloud Run captures and sends to Cloud Logging
# Note: RequestMiddleware in settings.py handles trace correlation
# The project_id is required for proper trace correlation formatting
LOGGING["handlers"]["structured_console"] = {
    "class": "google.cloud.logging_v2.handlers.StructuredLogHandler",
    "project_id": GCP_PROJECT_ID,
}

# Update loggers to use structured logging with propagate: False to prevent duplicates
LOGGING["loggers"]["django.request"]["handlers"] = ["structured_console"]
LOGGING["loggers"]["django.request"]["propagate"] = False

LOGGING["loggers"]["gyrinx"]["handlers"] = ["structured_console"]
LOGGING["loggers"]["gyrinx"]["propagate"] = False

LOGGING["root"]["handlers"] = ["structured_console"]

DEBUG = False
CSRF_COOKIE_SECURE = True
# Email configuration - all values from environment variables
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")

# This is handled by the load balancer
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 31536000  # 1 year
SESSION_COOKIE_SECURE = True
# includeSubDomains is left off: we cannot verify that every subdomain serves
# HTTPS only, so asserting it could break a plain-HTTP subdomain.
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
# Preload requires includeSubDomains (and is a one-way commitment that is hard
# to undo), so it stays disabled until that is a deliberate, verified decision.
SECURE_HSTS_PRELOAD = False

BASE_URL = "https://gyrinx.app"

# Database connection pooling (psycopg_pool via Django's `pool` option).
#
# Persistent connections (CONN_MAX_AGE > 0) must stay OFF here: they are
# per-thread, and under an ASGI server (daphne) Django runs each request's
# sync ORM work on a fresh single-use thread (ThreadSensitiveContext →
# one ThreadPoolExecutor(max_workers=1) per request). The thread dies with
# its connection still open — close_old_connections declines to close a
# connection younger than the max age — so nothing is ever reused and the
# socket lingers until cyclic GC. In production this leaked idle
# connections until Cloud SQL's max_connections (50 on db-g1-small) was
# exhausted, while delivering zero of the reuse it was meant to buy.
#
# The pool gives the reuse benefit for real (no per-request TLS + auth
# handshake) with a hard per-process cap and is safe under ASGI:
# connections return to the pool at the end of every request regardless
# of which thread ran it. CONN_HEALTH_CHECKS must stay True — it is what
# makes Django pass check=ConnectionPool.check_connection, so a
# connection dropped by the server or the Cloud SQL proxy is verified
# (and replaced) on checkout instead of failing the request.
#
# Sizing: the live service runs at most 3 instances (one daphne process
# each), so max_size 8 caps steady state at 24 connections — and at most
# 48 in the worst case during a rolling deploy, when old and new
# revisions briefly overlap and both serve traffic. That stays under the
# 50-connection limit with room for cloudsqladmin, prodshell, and
# deploy-time migrations. Requests beyond the cap queue for a connection
# for up to `timeout` seconds rather than failing the database.
#
# Dev/tests intentionally keep the Django default (no pool) — short-lived
# processes and pytest don't benefit, and the pool complicates teardown.
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True  # noqa: F405
DATABASES["default"]["OPTIONS"] = {  # noqa: F405
    **DATABASES["default"].get("OPTIONS", {}),  # noqa: F405
    "pool": {
        "min_size": 1,
        "max_size": 8,
        "timeout": 10,
    },
}

STORAGES = {
    **STORAGES,
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Google Cloud Storage configuration for media files
# Apply GCS configuration
gcs_config = configure_gcs_storage(STORAGES)

# Extract settings to module namespace
DEFAULT_FILE_STORAGE = gcs_config["DEFAULT_FILE_STORAGE"]
GS_BUCKET_NAME = gcs_config["GS_BUCKET_NAME"]
GS_PROJECT_ID = gcs_config["GS_PROJECT_ID"]
GS_DEFAULT_ACL = gcs_config["GS_DEFAULT_ACL"]
GS_QUERYSTRING_AUTH = gcs_config["GS_QUERYSTRING_AUTH"]
GS_OBJECT_PARAMETERS = gcs_config["GS_OBJECT_PARAMETERS"]
CDN_DOMAIN = gcs_config["CDN_DOMAIN"]
MEDIA_URL = gcs_config["MEDIA_URL"]

# Background tasks - use Pub/Sub backend in production
TASKS["default"] = {
    "BACKEND": "gyrinx.tasks.backend.PubSubBackend",
    "OPTIONS": {
        "project_id": GCP_PROJECT_ID,
    },
}
TASKS_ENVIRONMENT = "prod"

# Cloud Scheduler location for scheduled tasks
SCHEDULER_LOCATION = os.getenv("SCHEDULER_LOCATION", "europe-west2")
