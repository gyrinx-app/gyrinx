"""The migration graph may fork; the tools around it hold the line.

Three things are pinned here. Django's refusal to work on a forked graph is
switched off, and a generated migration joins every leaf. Django still routes
that refusal through the one method the switch replaces, so an upgrade that
moves it fails here rather than silently bringing the refusal back. And the
overlap reading tells an order-sensitive pair from a harmless one.
"""

import inspect

from django.core.management.commands import makemigrations, migrate
from django.db import migrations, models
from django.db.migrations import Migration
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.graph import MigrationGraph
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.questioner import NonInteractiveMigrationQuestioner
from django.db.migrations.state import ProjectState

from gyrinx.migration_graph import leaves_added_since
from gyrinx.migration_overlap import overlaps, touches


def _forked_graph():
    graph = MigrationGraph()
    for key in [
        ("orchard", "0001_initial"),
        ("orchard", "0002_a"),
        ("orchard", "0002_b"),
        ("other", "0001_initial"),
    ]:
        graph.add_node(key, None)
    graph.add_dependency(
        "orchard.0002_a", ("orchard", "0002_a"), ("orchard", "0001_initial")
    )
    graph.add_dependency(
        "orchard.0002_b", ("orchard", "0002_b"), ("orchard", "0001_initial")
    )
    return graph


def test_a_forked_graph_is_not_a_conflict():
    loader = MigrationLoader(None, load=False)
    loader.graph = _forked_graph()
    assert loader.graph.leaf_nodes("orchard") == [
        ("orchard", "0002_a"),
        ("orchard", "0002_b"),
    ]
    assert loader.detect_conflicts() == {}


def test_django_still_asks_the_loader_before_refusing():
    # Both commands consult detect_conflicts() and nothing else; if a Django
    # release moves the refusal, this fails and the switch needs following.
    # The modules are read, not the classes: pytest-django swaps the migrate
    # command for a subclass and the handle methods are wrapped by decorators.
    assert inspect.getsource(migrate).count("detect_conflicts()") == 1
    assert inspect.getsource(makemigrations).count("detect_conflicts()") == 1


def test_a_generated_migration_depends_on_every_leaf():
    detector = MigrationAutodetector(
        ProjectState(), ProjectState(), NonInteractiveMigrationQuestioner()
    )
    new = Migration("auto_1", "orchard")
    new.operations = [
        migrations.AddField("item", "weight", models.IntegerField(default=0))
    ]
    changes = detector.arrange_for_graph(
        {"orchard": [new]}, _forked_graph(), migration_name="weight"
    )
    (migration,) = changes["orchard"]
    assert migration.name == "0003_weight"
    assert set(migration.dependencies) == {("orchard", "0002_a"), ("orchard", "0002_b")}


def test_a_dependency_on_a_forked_app_names_every_tip():
    graph = _forked_graph()
    detector = MigrationAutodetector(
        ProjectState(), ProjectState(), NonInteractiveMigrationQuestioner()
    )
    new = Migration("auto_1", "other")
    new.dependencies = [
        ("orchard", "0002_a")
    ]  # what Django resolves a cross-app dep to
    new.operations = [
        migrations.AddField("thing", "item", models.IntegerField(default=0))
    ]
    changes = detector.arrange_for_graph({"other": [new]}, graph, migration_name="x")
    (migration,) = changes["other"]
    assert set(migration.dependencies) == {
        ("other", "0001_initial"),
        ("orchard", "0002_a"),
        ("orchard", "0002_b"),
    }


def test_a_branch_may_add_one_leaf():
    leaves = [("orchard", "0002_a"), ("orchard", "0002_b")]
    assert leaves_added_since(leaves, {"0001_initial", "0002_a"}) == [
        ("orchard", "0002_b")
    ]
    assert len(leaves_added_since(leaves, {"0001_initial"})) == 2


def _migration(app, name, *operations):
    m = Migration(name, app)
    m.operations = list(operations)
    return (app, name), m


def _backfill(apps, schema_editor):
    Item = apps.get_model("orchard", "Item")
    Item.objects.update(weight=1)


def test_two_additive_fields_do_not_overlap():
    base = dict(
        [
            _migration(
                "orchard",
                "0002_a",
                migrations.AddField("item", "price", models.IntegerField()),
            )
        ]
    )
    branch = dict(
        [
            _migration(
                "orchard",
                "0002_b",
                migrations.AddField("item", "colour", models.IntegerField()),
            )
        ]
    )
    assert overlaps(base, branch) == []


def test_a_rename_against_a_field_change_blocks():
    base = dict(
        [_migration("orchard", "0002_a", migrations.RenameModel("Item", "Product"))]
    )
    branch = dict(
        [
            _migration(
                "orchard",
                "0002_b",
                migrations.AddField("item", "colour", models.IntegerField()),
            )
        ]
    )
    (finding,) = overlaps(base, branch)
    assert finding.severity == "blocks"
    assert finding.base == ("orchard", "0002_a")
    assert finding.branch == ("orchard", "0002_b")


def test_the_same_field_changed_twice_blocks():
    base = dict(
        [
            _migration(
                "orchard",
                "0002_a",
                migrations.AlterField("item", "price", models.IntegerField()),
            )
        ]
    )
    branch = dict(
        [
            _migration(
                "orchard",
                "0002_b",
                migrations.AlterField("item", "price", models.FloatField()),
            )
        ]
    )
    (finding,) = overlaps(base, branch)
    assert finding.severity == "blocks"


def test_a_data_migration_on_a_changed_model_needs_review():
    base = dict(
        [
            _migration(
                "orchard",
                "0002_a",
                migrations.AddField("item", "weight", models.IntegerField()),
            )
        ]
    )
    branch = dict(
        [
            _migration(
                "orchard",
                "0002_b",
                migrations.RunPython(_backfill, migrations.RunPython.noop),
            )
        ]
    )
    (finding,) = overlaps(base, branch)
    assert finding.severity == "review"
    assert finding.branch_touch.model == "item"


def test_a_data_migration_on_another_app_is_left_alone():
    base = dict(
        [
            _migration(
                "orchard",
                "0002_a",
                migrations.AddField("item", "weight", models.IntegerField()),
            )
        ]
    )
    branch = dict(
        [
            _migration(
                "other",
                "0002_b",
                migrations.RunPython(_backfill, migrations.RunPython.noop),
            )
        ]
    )
    # The function fetches orchard.Item, so the app it lives in does not matter.
    assert len(overlaps(base, branch)) == 1
    unrelated = dict([_migration("other", "0002_c", migrations.RunSQL("select 1"))])
    assert overlaps(base, unrelated) == []


def test_separate_database_and_state_is_read_through():
    op = migrations.SeparateDatabaseAndState(
        state_operations=[migrations.AddField("item", "weight", models.IntegerField())],
        database_operations=[
            migrations.RunSQL("alter table orchard_item add weight int")
        ],
    )
    kinds = {t.kind for t in touches("orchard", op)}
    assert kinds == {"add", "data"}
