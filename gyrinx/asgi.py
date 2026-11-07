"""Django ASGI application with tracing initialised before startup."""

import os
import warnings

# Suppress the Google namespace package's pkg_resources deprecation warning.
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API",
    category=UserWarning,
)

from django.core.asgi import get_asgi_application  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gyrinx.settings")

# Initialise trace propagation before loading Django.
import gyrinx.tracing  # noqa: F401, E402

application = get_asgi_application()
