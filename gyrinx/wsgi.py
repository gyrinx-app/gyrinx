"""Django WSGI application with a database-free readiness endpoint."""

import os
import warnings

# Suppress the Google namespace package's pkg_resources deprecation warning.
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API",
    category=UserWarning,
)

from django.core.wsgi import get_wsgi_application  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gyrinx.settings")

# Initialise trace propagation before loading Django.
import gyrinx.tracing  # noqa: F401, E402

# The readiness path Cloud Run's startup probe hits. Keep it in sync with the
# --startup-probe flags in cloudbuild.yaml.
HEALTHZ_PATH = "/healthz"


def _healthz(start_response):
    """Answer the readiness probe."""
    body = b"ok\n"
    start_response(
        "200 OK",
        [
            ("Content-Type", "text/plain; charset=utf-8"),
            ("Content-Length", str(len(body))),
            # Never let a proxy or the probe itself serve a stale 200.
            ("Cache-Control", "no-store"),
        ],
    )
    return [body]


def make_application(django_application):
    """Wrap Django with a readiness endpoint outside its routing and middleware.

    The probe skips host validation and database work. Module initialisation
    finishes get_wsgi_application before exposing the wrapper, so the probe
    can respond only after a worker finishes Django startup.
    """

    def app(environ, start_response):
        if environ.get("PATH_INFO") == HEALTHZ_PATH:
            return _healthz(start_response)
        return django_application(environ, start_response)

    return app


application = make_application(get_wsgi_application())
