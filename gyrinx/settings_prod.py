from .settings import *  # noqa: F403

DEBUG = False
CSRF_COOKIE_SECURE = True
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
