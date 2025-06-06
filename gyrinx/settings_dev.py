import os

from .settings import LOGGING as BASE_LOGGING
from .settings import *  # noqa: F403
from .settings import STORAGES

DEBUG = True
WHITENOISE_AUTOREFRESH = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        **BASE_LOGGING["handlers"],
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        **BASE_LOGGING["loggers"],
        "django.db.backends": {
            "handlers": ["console"],
            "level": "DEBUG",
        }
        if os.getenv("SQL_DEBUG") == "True"
        else {"level": "INFO"},
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
