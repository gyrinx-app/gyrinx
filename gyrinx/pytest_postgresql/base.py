"""Use unlogged tables only in disposable pytest databases.

Transactions, row locks, indexes and constraints use the normal PostgreSQL
backend. Test data needs no recovery across a PostgreSQL crash; each fresh
test run recreates it. Development and migration commands use the ordinary
backend, and even this schema editor keeps tables logged outside ``test_*``.
"""

from django.db.backends.postgresql.base import DatabaseWrapper as PostgreSQLWrapper
from django.db.backends.postgresql.schema import (
    DatabaseSchemaEditor as PostgreSQLSchemaEditor,
)


class DatabaseSchemaEditor(PostgreSQLSchemaEditor):
    @property
    def sql_create_table(self):
        sql = super().sql_create_table
        name = self.connection.settings_dict.get("NAME") or ""
        if name.startswith("test_"):
            return sql.replace("CREATE TABLE", "CREATE UNLOGGED TABLE", 1)
        return sql


class DatabaseWrapper(PostgreSQLWrapper):
    SchemaEditorClass = DatabaseSchemaEditor

    def get_connection_params(self):
        params = super().get_connection_params()
        name = self.settings_dict.get("NAME") or ""
        if name.startswith("test_"):
            # Acknowledging a test commit needs no disk recovery guarantee.
            # Scope this to the connection, including thread connections;
            # never change the shared server or an ordinary database.
            options = params.get("options", "")
            params["options"] = f"{options} -c synchronous_commit=off".strip()
        return params
