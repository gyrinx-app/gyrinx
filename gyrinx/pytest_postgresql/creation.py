"""Serialize disposable test schema creation across PostgreSQL workers."""

from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.postgresql.creation import (
    DatabaseCreation as PostgreSQLCreation,
)

# All workers use the same postgres database and two-integer key namespace.
# Schema DDL shares the server's lock table even across separate test databases.
_SCHEMA_CREATION_LOCK = (0x47595258, 0x50595453)  # GYRX / PYTS


class DatabaseCreation(PostgreSQLCreation):
    def create_test_db(self, *args, **kwargs):
        # This dedicated, unpooled session survives the main connection closing.
        # Avoid the PostgreSQL fallback: workers must all lock on postgres.
        with BaseDatabaseWrapper._nodb_cursor(self.connection) as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s, %s)", _SCHEMA_CREATION_LOCK)
            try:
                return super().create_test_db(*args, **kwargs)
            finally:
                cursor.execute(
                    "SELECT pg_advisory_unlock(%s, %s)", _SCHEMA_CREATION_LOCK
                )
