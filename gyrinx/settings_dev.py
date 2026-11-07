import logging
import os
import sys
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

from debug_toolbar.settings import PANELS_DEFAULTS as _TOOLBAR_PANELS_DEFAULTS
from django.core.exceptions import ImproperlyConfigured
from django.db import connections

from .settings import *  # noqa: F403
from .settings import (
    APP_LOGGER_ROOTS,
    BASE_DIR,
    DATABASES,
    INSTALLED_APPS,
    MIDDLEWARE,
    STORAGES,
)
from .settings import LOGGING as BASE_LOGGING

logger = logging.getLogger(__name__)

DEBUG = True
WHITENOISE_AUTOREFRESH = True

# Keep Cotton component guards enabled under pytest, which forces DEBUG=False.
COTTON_STRICT_COMPONENTS = True

# Adjust loaders after Cotton's AppConfig installs them; settings-level changes
# would be overwritten. See gyrinx/cotton_dev.py.
if "django_cotton" not in INSTALLED_APPS:
    raise ImproperlyConfigured(
        "Expected 'django_cotton' in INSTALLED_APPS so development could swap in "
        "gyrinx.cotton_dev.DevCottonConfig; it isn't there."
    )
# Install the development toolbar cache wrappers through its AppConfig.
# See gyrinx/toolbar_dev.py.
if "debug_toolbar" not in INSTALLED_APPS:
    raise ImproperlyConfigured(
        "Expected 'debug_toolbar' in INSTALLED_APPS so development could swap in "
        "gyrinx.toolbar_dev.ToolbarDevConfig; it isn't there."
    )
_DEV_APP_CONFIGS = {
    "django_cotton": "gyrinx.cotton_dev.DevCottonConfig",
    "debug_toolbar": "gyrinx.toolbar_dev.ToolbarDevConfig",
}
INSTALLED_APPS = [_DEV_APP_CONFIGS.get(app, app) for app in INSTALLED_APPS]
INSTALLED_APPS += ["gyrinx.devserver.apps.DevServerConfig"]

# Detect pytest before settings load; PYTEST_CURRENT_TEST is not set this early.
_UNDER_PYTEST = "pytest" in sys.modules

# Disposable test rows need constraints and transactions, but no crash
# recovery. Keep the shared PostgreSQL server's durability settings intact.
# The schema editor also checks the database name before creating an unlogged
# table. Set False for a controlled comparison with ordinary logged tables.
if _UNDER_PYTEST and os.getenv("GYRINX_TEST_UNLOGGED_TABLES") != "False":
    DATABASES["default"]["ENGINE"] = "gyrinx.pytest_postgresql"

# Keep compiled templates cached; runserver autoreload clears them after edits.
# Set GYRINX_CACHE_TEMPLATES=False when a process without autoreload needs
# to read template changes directly.
CACHE_TEMPLATES = _UNDER_PYTEST or os.getenv("GYRINX_CACHE_TEMPLATES") != "False"

# Watch template directories for additions and removals that autoreload
# does not track. Tests keep the ordinary cached loader.
WATCH_TEMPLATE_DIRECTORIES = not _UNDER_PYTEST

# Start collapsed when localStorage has no toolbar preference.
DEBUG_TOOLBAR_CONFIG = {
    "SHOW_COLLAPSED": True,
    # Encode each panel's data for the History panel when it is first read, not
    # as every request ends. See gyrinx/toolbar_store.py.
    "TOOLBAR_STORE_CLASS": "gyrinx.toolbar_store.LazyMemoryStore",
}

# The toolbar's default panels, with a Templates panel that keeps each context
# layer once instead of once per template. See gyrinx/toolbar_panels.py.
_TOOLBAR_TEMPLATES_PANEL = "debug_toolbar.panels.templates.TemplatesPanel"
if _TOOLBAR_TEMPLATES_PANEL not in _TOOLBAR_PANELS_DEFAULTS:
    raise ImproperlyConfigured(
        f"Expected {_TOOLBAR_TEMPLATES_PANEL} in the debug toolbar's default "
        "panels so development could swap in "
        "gyrinx.toolbar_panels.SharedContextTemplatesPanel; it isn't there."
    )
DEBUG_TOOLBAR_PANELS = [
    "gyrinx.toolbar_panels.SharedContextTemplatesPanel"
    if panel == _TOOLBAR_TEMPLATES_PANEL
    else panel
    for panel in _TOOLBAR_PANELS_DEFAULTS
]

# Disable debug toolbar in tests - prevents 'djdt' namespace errors when tests
# use @override_settings(DEBUG=True). pytest-xdist workers set RUN_MAIN env var.
if _UNDER_PYTEST:
    DEBUG_TOOLBAR_CONFIG["SHOW_TOOLBAR_CALLBACK"] = lambda request: False

# Use the durable worker queue under runserver. Other commands retain
# the inherited eager mode. TASKS_FAULT_* configures optional delivery faults.
if "runserver" in sys.argv and not _UNDER_PYTEST:
    TASKS = {  # noqa: F405
        "default": {
            "BACKEND": "gyrinx.tasks.local_backend.DatabaseBackend",
            "OPTIONS": {
                "mode": "worker",
                "num_workers": int(os.getenv("TASKS_WORKERS", "2")),
            },
        }
    }

# Restart after the memory limit; agent-owned servers also stop on owner exit
# or idle timeout. Zero disables the corresponding numeric limit.
DEV_SERVER_GUARD = "runserver" in sys.argv and not _UNDER_PYTEST
DEV_SERVER_MEMORY_LIMIT_MB = int(os.getenv("GYRINX_DEV_MEMORY_LIMIT_MB", "2048"))
DEV_SERVER_IDLE_MINUTES = int(os.getenv("GYRINX_DEV_IDLE_MINUTES", "120"))

# Disable secure cookies for local development
CSRF_COOKIE_SECURE = False

# Disable the admin MFA gate by default under pytest, which forces DEBUG=False.
# Tests of the gate override this setting explicitly.
if _UNDER_PYTEST and os.getenv("ADMIN_REQUIRE_MFA") is None:
    ADMIN_REQUIRE_MFA = False

# Allow local hosts for development
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

# Per-worktree dynamic CSRF origins — DJANGO_PORT is set by dev.sh / session hook
_dev_port = os.getenv("DJANGO_PORT", "8000")
CSRF_TRUSTED_ORIGINS = [
    f"http://localhost:{_dev_port}",
    f"http://127.0.0.1:{_dev_port}",
]

# Cookies share a domain across localhost ports. Include the worktree port
# in cookie names so separate databases retain independent login sessions.
SESSION_COOKIE_NAME = f"gyrinx_sessionid_{_dev_port}"
CSRF_COOKIE_NAME = f"gyrinx_csrftoken_{_dev_port}"

# Use console tracing in development by default
# Set TRACING_MODE=gcp in environment to test with GCP Cloud Trace
TRACING_MODE = os.getenv("TRACING_MODE", "console")

# Add trace URL logging middleware (only active when TRACING_MODE="gcp")
MIDDLEWARE = [
    *MIDDLEWARE,
    "gyrinx.tracing.TraceURLLoggingMiddleware",
]

USE_REAL_EMAIL_IN_DEV = os.getenv("USE_REAL_EMAIL_IN_DEV", "False").lower() == "true"
if USE_REAL_EMAIL_IN_DEV:
    # Email configuration - all values from environment variables
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.getenv("EMAIL_HOST")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")


# Ensure logs dir exists (fallback to tmp if not writable)
logs_dir = BASE_DIR / "logs"
try:
    logs_dir.mkdir(exist_ok=True)
except OSError:
    logs_dir = Path(tempfile.gettempdir()) / "gyrinx_logs"
    logs_dir.mkdir(exist_ok=True)
    print(f"SQL_DEBUG: {logs_dir}")


# --- Custom filter: only keep queries above a duration threshold ---
class SlowQueryFilter(logging.Filter):
    def filter(self, record):
        # Django attaches record.duration (seconds) on django.db.backends logs
        try:
            threshold = float(os.getenv("SQL_MIN_DURATION", "0.01"))  # default 10 ms
        except ValueError:
            threshold = 0.1
        return getattr(record, "duration", 0.0) >= threshold


# --- Custom handler: write slow queries + EXPLAIN plan to file ---
class ExplainFileHandler(RotatingFileHandler):
    """Append EXPLAIN output for logged statements starting with SELECT.

    Use SQL_EXPLAIN_DB_ALIAS to select the connection. SQL_EXPLAIN_ANALYZE=True
    executes the statement while collecting the plan.
    """

    def emit(self, record):
        try:
            base_msg = self.format(record)

            sql = getattr(record, "sql", None)
            explain_lines = []
            # Skip EXPLAIN queries themselves to avoid recursion
            if isinstance(sql, str) and sql.strip().upper().startswith("EXPLAIN"):
                explain_lines.append("[EXPLAIN SKIPPED: recursive EXPLAIN]")
            elif isinstance(sql, str) and sql.strip().upper().startswith("SELECT"):
                alias = os.getenv("SQL_EXPLAIN_DB_ALIAS", "default")
                analyze = os.getenv("SQL_EXPLAIN_ANALYZE", "False") == "True"
                # EXPLAIN ANALYZE executes the SELECT.
                prefix = "EXPLAIN ANALYZE " if analyze else "EXPLAIN "
                try:
                    with connections[alias].cursor() as cur:
                        # The logged SQL already contains substituted parameters.
                        cur.execute(prefix + sql)
                        rows = cur.fetchall()
                        # Postgres returns one text column per line; MySQL returns tabular rows
                        for row in rows:
                            explain_lines.append(" | ".join(str(col) for col in row))
                except Exception as ex:
                    explain_lines.append(f"[EXPLAIN ERROR: {ex}]")
            else:
                explain_lines.append("[EXPLAIN SKIPPED: non-SELECT or no SQL]")

            combined = (
                base_msg + "\n" + "\n".join(explain_lines) + "\n" + ("-" * 80) + "\n"
            )
            # Write combined message
            if self.stream is None:
                self.stream = self._open()
            self.stream.write(combined)
            self.flush()
        except Exception:
            self.handleError(record)


LOGGING = {
    **BASE_LOGGING,
    "filters": {
        **BASE_LOGGING.get("filters", {}),
        "slow_sql": {"()": SlowQueryFilter},
    },
    "handlers": {
        **BASE_LOGGING["handlers"],
        # All-SQL rotating file (keeps a full archive)
        "sql_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": logs_dir / "sql.log",
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
            "formatter": "verbose",
        },
        # Slow-SQL file with EXPLAIN
        "slow_sql_file": {
            "()": ExplainFileHandler,  # custom handler defined above
            "filename": logs_dir / "slow_sql.log",
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
            "filters": ["slow_sql"],  # only records >= SQL_MIN_DURATION
        },
    },
    "loggers": {
        **BASE_LOGGING["loggers"],
        # Django SQL logger
        "django.db.backends": {
            # Always log to files only, no console output
            "handlers": ["sql_file", "slow_sql_file"],
            "level": "DEBUG" if os.getenv("SQL_DEBUG") == "True" else "INFO",
            "propagate": False,  # don't bubble into root
        },
        # Configure every first-party package root so edition debug logs reach the console.
        **{
            _root: {
                "handlers": ["console"],
                "level": os.getenv("GYRINX_LOG_LEVEL", "DEBUG").upper(),
                "propagate": False,
            }
            for _root in APP_LOGGER_ROOTS
        },
    },
}

# Media files configuration for development
# Check for environment variable to enable GCS testing
USE_GCS_IN_DEV = os.getenv("USE_GCS_IN_DEV", "False") == "True"

if USE_GCS_IN_DEV:
    # Use the configured GCS bucket when testing storage integration.
    from .storage_settings import configure_gcs_storage

    gcs_config = configure_gcs_storage(STORAGES)

    DEFAULT_FILE_STORAGE = gcs_config["DEFAULT_FILE_STORAGE"]
    GS_BUCKET_NAME = gcs_config["GS_BUCKET_NAME"]
    GS_PROJECT_ID = gcs_config["GS_PROJECT_ID"]
    GS_DEFAULT_ACL = gcs_config["GS_DEFAULT_ACL"]
    GS_QUERYSTRING_AUTH = gcs_config["GS_QUERYSTRING_AUTH"]
    GS_OBJECT_PARAMETERS = gcs_config["GS_OBJECT_PARAMETERS"]
    CDN_DOMAIN = gcs_config["CDN_DOMAIN"]
    MEDIA_URL = gcs_config["MEDIA_URL"]
else:
    # Default local filesystem storage
    MEDIA_URL = "/media/"
    MEDIA_ROOT = BASE_DIR / "media"  # noqa: F405
