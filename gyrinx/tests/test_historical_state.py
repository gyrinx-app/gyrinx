"""--nomigrations hides the declaration a data migration will run against.

The test database is built from the current models. ``django.apps.apps``
already has fields a later migration adds, so a function that reads
``_meta.concrete_fields`` sees the live order. ``historical_state`` loads
the migration files for one call and returns the project state at the
named nodes. It does not apply those migrations.

Not marked core: that suite is capped. CI still runs this file when a
pull request changes it.
"""

import pytest
from django.apps import apps
from django.conf import settings

from gyrinx.historical_state import historical_state

SLOT_RATING = ("library", "0129_slot_pick_rating_override")
BEFORE_SLOT_RATING = (
    ("library", "0128_battle_xp_action_allowances"),
    ("library", "0128_randomises_skill_advancements"),
)


def _field_names(model):
    return [field.name for field in model._meta.concrete_fields]


def test_the_live_slot_already_has_the_field_its_migration_adds():
    live = apps.get_model("library", "Slot")
    before = historical_state(BEFORE_SLOT_RATING).apps.get_model("library", "Slot")
    added = historical_state([SLOT_RATING]).apps.get_model("library", "Slot")

    assert "pick_rating_override" in _field_names(live)
    assert "pick_rating_override" not in _field_names(before)
    assert "pick_rating_override" in _field_names(added)
    assert _field_names(before) != _field_names(live)


def test_nomigrations_loader_does_not_read_the_slot_migration():
    from django.db.migrations.loader import MigrationLoader

    loader = MigrationLoader(None)
    assert SLOT_RATING not in loader.graph.nodes


def test_historical_state_restores_the_disabled_migration_modules():
    historical_state([SLOT_RATING])
    assert settings.MIGRATION_MODULES["library"] is None


def test_historical_state_rejects_a_bare_node_and_an_empty_list():
    with pytest.raises(ValueError, match="app_label, migration_name"):
        historical_state(SLOT_RATING)
    with pytest.raises(ValueError, match="at least one"):
        historical_state(())
