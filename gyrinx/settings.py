"""
Django settings for gyrinx project.

This should contain safe defaults for production. The development settings
should be in a separate file.

Originally generated by 'django-admin startproject' using Django 5.1.2.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.1/ref/settings/
"""

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY
SECRET_KEY = os.getenv("SECRET_KEY")
CSRF_COOKIE_SECURE = True

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

try:
    ALLOWED_HOSTS = json.loads(os.getenv("ALLOWED_HOSTS", "[]"))
except Exception as e:
    logger.error(f"Error parsing ALLOWED_HOSTS: {e}")
    ALLOWED_HOSTS = []

try:
    CSRF_TRUSTED_ORIGINS = json.loads(os.getenv("CSRF_TRUSTED_ORIGINS", "[]"))
except Exception as e:
    logger.error(f"Error parsing CSRF_TRUSTED_ORIGINS: {e}")
    CSRF_TRUSTED_ORIGINS = []

CSRF_COOKIE_DOMAIN = os.environ.get("CSRF_COOKIE_DOMAIN", None)

logger.info(f"ALLOWED_HOSTS: {ALLOWED_HOSTS}")
logger.info(f"CSRF_TRUSTED_ORIGINS: {CSRF_TRUSTED_ORIGINS}")
logger.info(f"CSRF_COOKIE_DOMAIN: {CSRF_COOKIE_DOMAIN}")

# Email
# Use SMTP
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "hello@gyrinx.app"

# Analytics

GOOGLE_ANALYTICS_ID = os.getenv("GOOGLE_ANALYTICS_ID", "")

# Application definition

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.postgres",
    "django.contrib.admindocs",
    # Django allauth
    "allauth",
    "allauth.account",
    # simplehistory
    "simple_history",
    # Disable Django's static file handling in favour of WhiteNoise in dev
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "gyrinx.core",
    "gyrinx.content",
    "tinymce",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Django allauth
    "allauth.account.middleware.AccountMiddleware",
    # simplehistory
    "simple_history.middleware.HistoryRequestMiddleware",
]

ROOT_URLCONF = "gyrinx.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "gyrinx/core/templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "gyrinx.wsgi.application"
ASGI_APPLICATION = "gyrinx.asgi.application"


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

try:
    DB_CONFIG = json.loads(os.getenv("DB_CONFIG", "{}"))
except json.JSONDecodeError as e:
    logger.error(f"Error parsing DB_CONFIG: {e}")

if not DB_CONFIG.get("user"):
    logger.error("DB_CONFIG is missing 'user' key")
if not DB_CONFIG.get("password"):
    logger.error("DB_CONFIG is missing 'password' key")


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "gyrinx"),
        "USER": DB_CONFIG.get("user", "postgres"),
        "PASSWORD": DB_CONFIG.get("password", "postgres"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

# Caching
# https://docs.djangoproject.com/en/5.1/topics/cache/

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    },
    "content_page_ref_cache": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "content-page-ref-cache",
    },
}

# Authentication
# Using django-allauth for authentication
# https://django-allauth.readthedocs.io/en/latest/installation.html

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

LOGIN_REDIRECT_URL = "/"

# Allauth settings
# https://django-allauth.readthedocs.io/en/latest/configuration.html

ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 3
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[Gyrinx] "
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_SIGNUP_FORM_HONEYPOT_FIELD = "name"
ACCOUNT_USERNAME_BLACKLIST = ["admin", "superuser", "staff", "user", "gyrinx"]
ACCOUNT_CHANGE_EMAIL = True
ACCOUNT_ADAPTER = "gyrinx.core.adapter.CustomAccountAdapter"
# Custom setting to (dis)allow signups
ACCOUNT_ALLOW_SIGNUPS = os.getenv("ACCOUNT_ALLOW_SIGNUPS", "True") == "True"


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Storages

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Logging
# https://docs.djangoproject.com/en/5.1/topics/logging/

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "null": {
            "class": "logging.NullHandler",
        },
    },
    "loggers": {
        "django.security.DisallowedHost": {
            "handlers": ["null"],
            "propagate": False,
        },
    },
}

# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
