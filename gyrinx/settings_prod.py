import json
import logging
import os
import sys

from .settings import *  # noqa: F403

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

logger = logging.getLogger(__name__)

try:
    DB_CONFIG = json.loads(os.getenv("DB_CONFIG", "{}"))
except json.JSONDecodeError as e:
    logger.error(f"Error parsing DB_CONFIG: {e}")
    sys.exit(1)

if not DB_CONFIG.get("user"):
    logger.error("DB_CONFIG is missing 'user' key")
    sys.exit(1)
if not DB_CONFIG.get("password"):
    logger.error("DB_CONFIG is missing 'password' key")
    sys.exit(1)


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "gyrinx"),
        "USER": DB_CONFIG.get("user", ""),
        "PASSWORD": DB_CONFIG.get("password", ""),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}
