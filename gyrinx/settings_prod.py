import os

from .settings import *  # noqa: F403
from .settings import APP_LOGGER_ROOTS, LOGGING, STORAGES, TASKS
from .storage_settings import configure_gcs_storage

# Use GCP tracing in production
TRACING_MODE = "gcp"

# Use the project ID for trace correlation, with an environment override.
GCP_PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or "windy-ellipse-440618-p9"

# Emit structured JSON for Cloud Run logging with the project ID for trace correlation.
LOGGING["handlers"]["structured_console"] = {
    "class": "google.cloud.logging_v2.handlers.StructuredLogHandler",
    "project_id": GCP_PROJECT_ID,
}

# Disable propagation to avoid duplicate structured log entries.
LOGGING["loggers"]["django.request"]["handlers"] = ["structured_console"]
LOGGING["loggers"]["django.request"]["propagate"] = False

for _logger_root in APP_LOGGER_ROOTS:
    LOGGING["loggers"][_logger_root]["handlers"] = ["structured_console"]
    LOGGING["loggers"][_logger_root]["propagate"] = False

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

# The load balancer appends client and forwarding-rule addresses. Earlier
# X-Forwarded-For entries may be supplied by the caller.
TRUSTED_X_FORWARDED_FOR_HOPS = 2
ALLAUTH_TRUSTED_PROXY_COUNT = 2

# Use a bounded per-process pool instead of per-thread persistent connections.
# Keep CONN_MAX_AGE at zero and CONN_HEALTH_CHECKS enabled so checkout
# replaces dropped connections. Pool limits multiply by worker processes and
# Cloud Run instances, including overlapping revisions during deployment;
# review those settings together in docker/entrypoint.sh and cloudbuild.yaml.
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True  # noqa: F405
DATABASES["default"]["OPTIONS"] = {  # noqa: F405
    **DATABASES["default"].get("OPTIONS", {}),  # noqa: F405
    "pool": {
        "min_size": 1,
        "max_size": 6,
        # Limit checkout waits so saturation does not accumulate blocked requests.
        "timeout": 5,
        # Release idle burst connections promptly while old revisions drain.
        "max_idle": 60,
    },
}

STORAGES = {
    **STORAGES,
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Django hashes ordinary static assets; Vite hashes the React module graph.
# Module imports keep Vite's URLs so the browser shares one React instance.
WHITENOISE_IMMUTABLE_FILE_TEST = (
    r"\.[0-9a-f]{12}\."
    r"|/n26/react/assets/[^/]+-[A-Za-z0-9_-]{8}\.(?:js|css)$"
)

gcs_config = configure_gcs_storage(STORAGES)

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
