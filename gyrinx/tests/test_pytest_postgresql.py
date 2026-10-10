"""Test schemas skip WAL writes while ordinary databases remain logged."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from django.db import connection
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.postgresql.creation import (
    DatabaseCreation as PostgreSQLCreation,
)
from django.db.backends.postgresql.schema import (
    DatabaseSchemaEditor as PostgreSQLSchemaEditor,
)

from gyrinx.pytest_postgresql.base import DatabaseSchemaEditor
from gyrinx.pytest_postgresql.creation import DatabaseCreation


@pytest.mark.parametrize("name", ["gyrinx_main", "gyrinx_wt_example", "postgres", None])
def test_non_test_database_tables_stay_logged(name):
    editor = DatabaseSchemaEditor.__new__(DatabaseSchemaEditor)
    editor.connection = SimpleNamespace(settings_dict={"NAME": name})
    assert editor.sql_create_table == PostgreSQLSchemaEditor.sql_create_table


@pytest.mark.django_db
def test_the_test_schema_has_no_logged_tables():
    if not isinstance(connection.schema_editor(), DatabaseSchemaEditor):
        pytest.skip("Ordinary logged tables selected for a performance comparison")
    assert isinstance(connection.creation, DatabaseCreation)
    with connection.cursor() as cursor:
        cursor.execute("SHOW synchronous_commit")
        assert cursor.fetchone() == ("off",)
        cursor.execute("SHOW jit")
        assert cursor.fetchone() == ("off",)
        cursor.execute(
            "SELECT relname, relpersistence FROM pg_class "
            "WHERE relnamespace = current_schema()::regnamespace "
            "AND relkind = 'r'"
        )
        tables = dict(cursor.fetchall())
    assert "auth_user" in tables
    assert "core_list" in tables
    assert "n26_gang" in tables
    assert set(tables.values()) == {"u"}


@pytest.mark.parametrize("failure_type", [RuntimeError, SystemExit, KeyboardInterrupt])
def test_failed_schema_creation_releases_the_maintenance_session(
    monkeypatch, failure_type
):
    maintenance = SimpleNamespace(locked=False, closed=False)
    application = SimpleNamespace(closed=False)
    failure = failure_type("schema creation interrupted")

    class Cursor:
        def execute(self, sql, params):
            if "pg_advisory_unlock" in sql:
                maintenance.locked = False
            else:
                maintenance.locked = True

    @contextmanager
    def maintenance_cursor(connection):
        assert connection is application
        try:
            yield Cursor()
        finally:
            maintenance.closed = True

    def interrupted_creation(self, *args, **kwargs):
        assert maintenance.locked
        # Django closes the main connection before building the schema.
        application.closed = True
        assert maintenance.locked
        raise failure

    monkeypatch.setattr(BaseDatabaseWrapper, "_nodb_cursor", maintenance_cursor)
    monkeypatch.setattr(PostgreSQLCreation, "create_test_db", interrupted_creation)

    with pytest.raises(failure_type) as raised:
        DatabaseCreation(application).create_test_db(verbosity=0, autoclobber=True)

    assert raised.value is failure
    assert application.closed
    assert not maintenance.locked
    assert maintenance.closed
