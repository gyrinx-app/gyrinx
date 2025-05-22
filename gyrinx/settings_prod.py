import os

import google.cloud.logging

from .settings import *  # noqa: F403
from .settings import STORAGES

client = google.cloud.logging.Client()
client.setup_logging()

DEBUG = False
CSRF_COOKIE_SECURE = True
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.sendgrid.net"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
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
