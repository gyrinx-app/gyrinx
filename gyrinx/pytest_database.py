"""Whether this pytest session will create a test database.

pytest-django's ``django_db_setup`` only calls ``setup_databases`` for tests
that request the database. A session of plain tests leaves the connection on
``DB_NAME``, the worktree's dev database. oriole hit this on #lessons
(7 Oct 2026): the autouse ``content_stat_definitions`` fixture then wrote
ContentStat rows there, and a fresh empty worktree failed every test with
``relation content_contentstat does not exist``.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest


def session_creates_test_database(items: Sequence[pytest.Item]) -> bool:
    """True when pytest-django will point connections at a test database.

    This is the same predicate ``django_db_setup`` uses. An empty alias set
    means ``setup_databases`` returns without renaming the connection, so
    any later query hits the dev database.
    """
    from pytest_django.fixtures import _get_databases_for_setup

    aliases, _serialized = _get_databases_for_setup(items)
    return bool(aliases)
