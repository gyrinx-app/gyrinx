"""Test schemas skip WAL writes while ordinary databases remain logged."""

from types import SimpleNamespace

import pytest
from django.db import connection
from django.db.backends.postgresql.schema import (
    DatabaseSchemaEditor as PostgreSQLSchemaEditor,
)

from gyrinx.pytest_postgresql.base import DatabaseSchemaEditor


@pytest.mark.parametrize("name", ["gyrinx_main", "gyrinx_wt_example", "postgres", None])
def test_non_test_database_tables_stay_logged(name):
    editor = DatabaseSchemaEditor.__new__(DatabaseSchemaEditor)
    editor.connection = SimpleNamespace(settings_dict={"NAME": name})
    assert editor.sql_create_table == PostgreSQLSchemaEditor.sql_create_table


@pytest.mark.django_db
def test_the_test_schema_has_no_logged_tables():
    if not isinstance(connection.schema_editor(), DatabaseSchemaEditor):
        pytest.skip("Ordinary logged tables selected for a performance comparison")
    with connection.cursor() as cursor:
        cursor.execute("SHOW synchronous_commit")
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
