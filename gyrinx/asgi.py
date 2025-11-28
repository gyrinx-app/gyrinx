"""
ASGI config for gyrinx project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gyrinx.settings")

# Initialize OpenTelemetry tracing before Django loads
# This ensures trace context propagation is configured for all requests
import gyrinx.tracing  # noqa: F401, E402

application = get_asgi_application()
