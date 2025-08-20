import logging
import os
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

from django.db import connections

from .settings import *  # noqa: F403
from .settings import BASE_DIR, STORAGES
from .settings import LOGGING as BASE_LOGGING

logger = logging.getLogger(__name__)

DEBUG = True
WHITENOISE_AUTOREFRESH = True

# Disable secure cookies for local development
CSRF_COOKIE_SECURE = False

# Allow local hosts for development
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

USE_REAL_EMAIL_IN_DEV = os.getenv("USE_REAL_EMAIL_IN_DEV", "False").lower() == "true"
if USE_REAL_EMAIL_IN_DEV:
    # Email configuration - all values from environment variables
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.sendgrid.net")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "apikey")
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
    """
    Writes slow SQL records and appends an EXPLAIN plan.
    - Only runs for SELECT statements (to avoid accidental mutations).
    - Uses the configured DB alias (default 'default').
    - By default uses plain EXPLAIN; set SQL_EXPLAIN_ANALYZE=True to include ANALYZE (executes the query!).
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
                # USE ANALYZE WITH CARE: it will execute the SELECT.
                prefix = "EXPLAIN ANALYZE " if analyze else "EXPLAIN "
                try:
                    with connections[alias].cursor() as cur:
                        # Django's logging already substitutes params into the SQL string
                        # The SQL we receive has literal values, not %s placeholders
                        # So we can directly execute EXPLAIN + sql
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
        "gyrinx": {
            "handlers": ["console"],
            "level": os.getenv("GYRINX_LOG_LEVEL", "DEBUG").upper(),
            "propagate": True,
        },
    },
}

# Media files configuration for development
# Check for environment variable to enable GCS testing
USE_GCS_IN_DEV = os.getenv("USE_GCS_IN_DEV", "False") == "True"

if USE_GCS_IN_DEV:
    # Use production GCS bucket for testing
    from .storage_settings import configure_gcs_storage

    # Apply GCS configuration (identical to production)
    gcs_config = configure_gcs_storage(STORAGES)

    # Extract settings to module namespace
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
