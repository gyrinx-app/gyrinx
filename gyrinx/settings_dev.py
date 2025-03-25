import os

from .settings import LOGGING as BASE_LOGGING
from .settings import *  # noqa: F403

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
