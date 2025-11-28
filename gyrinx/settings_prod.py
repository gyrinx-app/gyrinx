import os

from .settings import *  # noqa: F403
from .settings import LOGGING, STORAGES
from .storage_settings import configure_gcs_storage

# Configure Django logging for production using StructuredLogHandler
# This writes JSON to stdout, which Cloud Run captures and sends to Cloud Logging
# Note: RequestMiddleware in settings.py handles trace correlation
# The project_id is required for proper trace correlation formatting
GCP_PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("GCP_PROJECT_ID", ""))
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
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.sendgrid.net")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "apikey")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")

# This is handled by the load balancer
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 60
SESSION_COOKIE_SECURE = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = True

BASE_URL = "https://gyrinx.app"

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
