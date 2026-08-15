"""
WSGI config for gyrinx project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

import os
import warnings

# Filter deprecation warning from Google namespace packages using pkg_resources.
# This is a third-party issue that we can't fix directly.
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API",
    category=UserWarning,
)

from django.core.wsgi import get_wsgi_application  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gyrinx.settings")

# Initialize OpenTelemetry tracing before Django loads
# This ensures trace context propagation is configured for all requests
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
    """
    Wrap the Django WSGI app with the readiness endpoint.

    The probe is answered *before* Django's routing and middleware, for two
    reasons. It cannot 400 on ALLOWED_HOSTS — Cloud Run probes the container by
    its instance IP, which is not a name we can list — and it does no database
    work, so a probe can never be held up behind a slow query or a saturated
    connection pool.

    Readiness is carried by the fact that this callable exists at all. Gunicorn
    imports this module in each worker, and that import is what runs
    `get_wsgi_application()` (app registry, model loading, checks). So nothing
    answers on this path until a worker has fully booted and can serve real
    requests too — which is exactly the signal the startup probe needs. The old
    TCP probe went green when the gunicorn *master* bound the socket, ~47s
    before any worker could respond, and Cloud Run routed live traffic into the
    gap.
    """

    def app(environ, start_response):
        if environ.get("PATH_INFO") == HEALTHZ_PATH:
            return _healthz(start_response)
        return django_application(environ, start_response)

    return app


application = make_application(get_wsgi_application())
