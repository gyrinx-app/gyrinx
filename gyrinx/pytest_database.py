"""Whether this pytest session will create a test database.

pytest-django's ``django_db_setup`` only calls ``setup_databases`` for tests
that request the database. A session of plain tests leaves the connection on
``DB_NAME``, the worktree's dev database. An autouse session fixture that
queries then writes into the dev database, or fails on a fresh one with
``relation content_contentstat does not exist``.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest


def session_creates_test_database(items: Sequence[pytest.Item]) -> bool:
    """True when pytest-django will point connections at a test database.

    This is the same predicate ``django_db_setup`` uses. An empty alias set
    means ``setup_databases`` returns without renaming the connection, so
    any later query hits the dev database. The predicate is private to
    pytest-django, so an upgrade can move it; gyrinx/tests/test_pytest_database.py
    fails if it does.
    """
    from pytest_django.fixtures import _get_databases_for_setup

    aliases, _serialized = _get_databases_for_setup(items)
    return bool(aliases)
