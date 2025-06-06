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

# Google Cloud Storage configuration for media files
DEFAULT_FILE_STORAGE = "storages.backends.gcloud.GoogleCloudStorage"
GS_BUCKET_NAME = os.environ.get("GS_BUCKET_NAME", "gyrinx-app-bootstrap-uploads")
GS_PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
# With Uniform bucket-level access, ACLs are not used
GS_DEFAULT_ACL = None  # ACLs are disabled with uniform access
# Files are served based on bucket IAM policies
GS_QUERYSTRING_AUTH = False
# Set proper cache headers for CDN
GS_OBJECT_PARAMETERS = {
    "CacheControl": "public, max-age=2592000",  # 30 days for uploaded images
}

# Media URL configuration
# Use CDN domain if available, otherwise fall back to direct GCS access
CDN_DOMAIN = os.environ.get("CDN_DOMAIN", None)
if CDN_DOMAIN:
    MEDIA_URL = f"https://{CDN_DOMAIN}/"
else:
    # Fall back to direct GCS access
    MEDIA_URL = f"https://storage.googleapis.com/{GS_BUCKET_NAME}/"
