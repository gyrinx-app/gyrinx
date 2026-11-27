"""Historical model state for tests that run with --nomigrations.

pytest-django replaces ``MIGRATION_MODULES`` with a mapping that reports
every app as having no migrations. ``MigrationLoader`` then never reads the
files, and the test database is created from the current models.
``django.apps.apps`` therefore already includes a field a migration is about
to add, and a different field order. A data migration exercised through that
registry cannot see the declaration it will run against.
"""

from __future__ import annotations

from collections.abc import Sequence


def historical_state(targets: Sequence[tuple[str, str]]):
    """Return the project state at the named migration nodes.

    The migrations are not applied. Pass ``.apps`` into the migration
    function. ``django.apps.apps`` stays the current models.

    ``targets`` is a list of ``(app_label, migration_name)`` nodes. Name
    every node the state should include when an app has more than one leaf.
    """
    nodes = [_migration_node(target) for target in targets]
    if not nodes:
        raise ValueError("name at least one (app_label, migration_name) node")

    from django.db.migrations.loader import MigrationLoader
    from django.test import override_settings

    # An empty mapping restores disk discovery for this load only.
    with override_settings(MIGRATION_MODULES={}):
        return MigrationLoader(None).project_state(nodes)


def _migration_node(target) -> tuple[str, str]:
    if (
        isinstance(target, tuple)
        and len(target) == 2
        and all(isinstance(part, str) and part for part in target)
    ):
        return target
    raise ValueError(
        f"historical_state expects (app_label, migration_name) nodes, not {target!r}"
    )
