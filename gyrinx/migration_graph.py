"""Allow multiple migration leaves and join them when generating migrations.

Suppress Django's conflict policy while preserving dependency order. Add
every existing app leaf to generated dependencies, including dependencies
on another app's leaf. Tests pin Django's conflict-check call sites so
upgrades that change the integration are detected.
"""

from __future__ import annotations

from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.loader import MigrationLoader

_django_arrange_for_graph = MigrationAutodetector.arrange_for_graph


def detect_conflicts(self):
    """Several leaves in one app are allowed; report none."""
    return {}


def arrange_for_graph(self, changes, graph, migration_name=None):
    """Apply Django's naming, then add dependencies on every relevant app leaf."""
    changes = _django_arrange_for_graph(self, changes, graph, migration_name)
    for app_label, migrations in changes.items():
        if not migrations:
            continue
        first = migrations[0]
        for leaf in graph.leaf_nodes(app_label):
            if leaf not in first.dependencies:
                first.dependencies.append(leaf)
        # A dependency on one tip of another app must include that app's other leaves.
        for migration in migrations:
            for dep in list(migration.dependencies):
                if dep[0] == app_label or dep[1] in ("__first__", "__latest__"):
                    continue
                other_leaves = graph.leaf_nodes(dep[0])
                if dep in other_leaves:
                    for leaf in other_leaves:
                        if leaf not in migration.dependencies:
                            migration.dependencies.append(leaf)
    return changes


def allow_many_leaves():
    """Install the migration policy patches; safe to call repeatedly from ready()."""
    MigrationLoader.detect_conflicts = detect_conflicts
    MigrationAutodetector.arrange_for_graph = arrange_for_graph


def leaves_added_since(leaves, base_names):
    """Return leaf keys whose migration names are absent from the base tree.

    Callers enforce the project's one-new-leaf-per-app branch rule.
    """
    return [leaf for leaf in leaves if leaf[1] not in base_names]
