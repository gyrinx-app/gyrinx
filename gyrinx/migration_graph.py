"""An app's migration graph may carry more than one leaf.

Django refuses to ``migrate`` or ``makemigrations`` while an app has two leaf
migrations, and offers a no-op merge migration as the cure. Neither the refusal
nor the merge file is needed for correctness: ``migrate`` already applies every
unapplied node in dependency order, and the project state is built from every
leaf. What correctness does need is that a migration made on a tree with several
leaves depends on all of them, so its operations can never run before the state
they were generated against. That is the one change made here.

With it, two branches that each add a migration to the same app merge in any
order and deploy in any order, with no renaming and no repointing. The next
migration anyone generates joins the leaves.

The refusal lives at exactly two call sites in Django, both a policy check on
``MigrationLoader.detect_conflicts()``; a test pins that so a Django upgrade
that moves it is noticed.
"""

from __future__ import annotations

from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.loader import MigrationLoader

_django_arrange_for_graph = MigrationAutodetector.arrange_for_graph


def detect_conflicts(self):
    """Several leaves in one app are allowed; report none."""
    return {}


def arrange_for_graph(self, changes, graph, migration_name=None):
    """Name the new migrations as Django does, then depend on every leaf.

    Django appends the first leaf it finds for the app; the rest are added
    here, so a migration generated on a forked tree joins the fork.
    """
    changes = _django_arrange_for_graph(self, changes, graph, migration_name)
    for app_label, migrations in changes.items():
        if not migrations:
            continue
        first = migrations[0]
        for leaf in graph.leaf_nodes(app_label):
            if leaf not in first.dependencies:
                first.dependencies.append(leaf)
        # A dependency on another app's leaf means "that app as it stands";
        # when that app is forked, Django names one tip. Name them all.
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
    """Install the policy. Idempotent; called from an AppConfig.ready()."""
    MigrationLoader.detect_conflicts = detect_conflicts
    MigrationAutodetector.arrange_for_graph = arrange_for_graph


def leaves_added_since(leaves, base_names):
    """The leaves of an app that are not migrations the base already has.

    ``leaves`` are ``(app_label, name)`` keys; ``base_names`` the migration
    names the base tree holds for that app. A branch may bring one new leaf
    per app: its own chain's tip. Two means a migration was written by hand
    on a tree whose other leaf it ignored, and its operations may run before
    the state they assume.
    """
    return [leaf for leaf in leaves if leaf[1] not in base_names]
