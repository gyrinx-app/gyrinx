import os

from .settings import *  # noqa: F403
from .settings import LOGGING as BASE_LOGGING

DEBUG = True
WHITENOISE_AUTOREFRESH = True

# Google's test reCAPTCHA keys
RECAPTCHA_PUBLIC_KEY = os.getenv(
    "RECAPTCHA_PUBLIC_KEY", "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"
)
RECAPTCHA_PRIVATE_KEY = os.getenv(
    "RECAPTCHA_PRIVATE_KEY", "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe"
)

SILENCED_SYSTEM_CHECKS = ["django_recaptcha.recaptcha_test_key_error"]

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
