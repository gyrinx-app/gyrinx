import os

from .settings import *  # noqa: F403
from .settings import LOGGING as BASE_LOGGING
from .settings import STORAGES

DEBUG = True
WHITENOISE_AUTOREFRESH = True

# Disable secure cookies for local development
CSRF_COOKIE_SECURE = False

# Allow local hosts for development
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

USE_REAL_EMAIL_IN_DEV = os.getenv("USE_REAL_EMAIL_IN_DEV", "False").lower() == "true"
if USE_REAL_EMAIL_IN_DEV:
    # Email configuration - all values from environment variables
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.sendgrid.net")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "apikey")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")


LOGGING = {
    **BASE_LOGGING,
    "handlers": {
        **BASE_LOGGING["handlers"],
    },
    "loggers": {
        **BASE_LOGGING["loggers"],
        "django.db.backends": {
            "handlers": ["console"],
            "level": "DEBUG" if os.getenv("SQL_DEBUG") == "True" else "INFO",
            "propagate": False,
        },
        "gyrinx": {
            "handlers": ["console"],
            "level": os.getenv("GYRINX_LOG_LEVEL", "DEBUG").upper(),
            "propagate": True,
        },
    },
}

# Media files configuration for development
# Check for environment variable to enable GCS testing
USE_GCS_IN_DEV = os.getenv("USE_GCS_IN_DEV", "False") == "True"

if USE_GCS_IN_DEV:
    # Use production GCS bucket for testing
    from .storage_settings import configure_gcs_storage

    # Apply GCS configuration (identical to production)
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
else:
    # Default local filesystem storage
    MEDIA_URL = "/media/"
    MEDIA_ROOT = BASE_DIR / "media"  # noqa: F405
