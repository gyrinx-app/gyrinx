"""Configure only the exploration's local Django environment before importing models."""

import os
import secrets
import sys
from pathlib import Path

import django
from django.conf import settings

HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get("EDITOR_PORT", "8765"))
sys.path.insert(0, str(HERE.parents[2]))

secret_file = HERE / ".local-secret"
if not secret_file.exists():
    secret_file.write_text(secrets.token_urlsafe(48))
    secret_file.chmod(0o600)
secret = secret_file.read_text().strip()

settings.configure(
    SECRET_KEY=secret,
    DEBUG=True,
    ALLOWED_HOSTS=["127.0.0.1", "localhost"],
    ROOT_URLCONF="server",
    DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
    INSTALLED_APPS=[
        "django.contrib.admin",
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.sessions",
        "django.contrib.messages",
        "django.contrib.staticfiles",
        "django.contrib.sites",
        "django.contrib.flatpages",
        "lab",
    ],
    SITE_ID=1,
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": HERE / "demo.sqlite3",
        }
    },
    MIDDLEWARE=[
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
    ],
    TEMPLATES=[
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "APP_DIRS": True,
            "OPTIONS": {
                "context_processors": [
                    "django.template.context_processors.request",
                    "django.contrib.auth.context_processors.auth",
                    "django.contrib.messages.context_processors.messages",
                ]
            },
        }
    ],
    STATIC_URL="/static/",
    STATICFILES_DIRS=[HERE / "public"],
    SESSION_COOKIE_NAME=f"gyrinx_editor_lab_session_{PORT}",
    CSRF_COOKIE_NAME=f"gyrinx_editor_lab_csrf_{PORT}",
    DATA_UPLOAD_MAX_MEMORY_SIZE=11 * 1024 * 1024,
)

django.setup()
