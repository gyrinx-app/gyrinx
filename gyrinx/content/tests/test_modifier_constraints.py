"""Tests for the ContentMod uniqueness constraints and the dedup migration
that backfills them (#1915).

The duplicate rows that motivated this were authored in the Django admin (the
"+ Add another" popup beside the ``modifiers`` M2M creates a fresh row with no
deduplication). The fix is a DB-level unique constraint on each mod subclass,
plus a one-off migration that merges the duplicates already in the database.
"""

import importlib

import pytest
from django.apps import apps as global_apps
from django.db import IntegrityError, connection, transaction

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentUpgrade,
    ContentModStat,
    ContentModTrait,
    ContentWeaponAccessory,
)
from gyrinx.content.models.modifier import ContentMod
from gyrinx.content.models.weapon import ContentWeaponTrait

# The migration module name starts with a digit, so import it dynamically.
_migration = importlib.import_module(
    "gyrinx.content.migrations.0176_contentmod_unique_constraints"
)


@pytest.mark.django_db
def test_contentmodstat_rejects_duplicate():
    ContentModStat.objects.create(stat="strength", mode="improve", value="1")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ContentModStat.objects.create(stat="strength", mode="improve", value="1")


@pytest.mark.django_db
def test_contentmodstat_allows_distinct_value():
    ContentModStat.objects.create(stat="strength", mode="improve", value="1")
    # Different value -> different row, allowed.
    ContentModStat.objects.create(stat="strength", mode="improve", value="2")
    assert ContentModStat.objects.filter(stat="strength", mode="improve").count() == 2


@pytest.mark.django_db
def test_contentmodtrait_rejects_duplicate():
    trait = ContentWeaponTrait.objects.create(name="Knockback")
    ContentModTrait.objects.create(trait=trait, mode="add")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ContentModTrait.objects.create(trait=trait, mode="add")


@pytest.mark.django_db(transaction=True)
def test_dedup_migration_merges_and_repoints_references():
    """The dedup migration must merge duplicate rows onto one canonical row and
    re-point every reference — never orphan a reference or delete a base row
    that something still points at."""
    constraint = next(
        c
        for c in ContentModStat._meta.constraints
        if c.name == "uniq_contentmodstat_stat_mode_value"
    )
    # Drop the constraint so we can seed the duplicates the migration cleans up.
    with connection.schema_editor(atomic=False) as se:
        se.remove_constraint(ContentModStat, constraint)
    try:
        rows = [
            ContentModStat.objects.create(stat="strength", mode="improve", value="2")
            for _ in range(3)
        ]
        # Canonical is the earliest by pk, matching the migration's ordering.
        rows.sort(key=lambda r: str(r.pk))
        canonical, redundant_a, redundant_b = rows

        # References spread across two different owner types, each pointing at a
        # *redundant* row — exactly the production shape.
        acc = ContentWeaponAccessory.objects.create(
            name="Dedup Acc", cost=5, rarity="C"
        )
        acc.modifiers.add(redundant_a)

        cat = ContentEquipmentCategory.objects.create(name="Dedup Cat")
        equip = ContentEquipment.objects.create(name="Dedup Equip", category=cat)
        upg = ContentEquipmentUpgrade.objects.create(
            equipment=equip, name="Dedup Upg", position=1, cost=0
        )
        upg.modifiers.add(redundant_b)

        # An owner that already references the canonical row (add must be idempotent).
        acc2 = ContentWeaponAccessory.objects.create(
            name="Dedup Acc 2", cost=5, rarity="C"
        )
        acc2.modifiers.add(canonical)

        _migration.dedup_mods(global_apps, None)

        remaining = ContentModStat.objects.filter(
            stat="strength", mode="improve", value="2"
        )
        assert remaining.count() == 1
        assert remaining.get().pk == canonical.pk
        # Redundant base ContentMod rows are gone — no orphans left behind.
        assert not ContentMod.objects.filter(
            pk__in=[redundant_a.pk, redundant_b.pk]
        ).exists()
        # Every reference now points at the canonical row.
        assert [m.pk for m in acc.modifiers.all()] == [canonical.pk]
        assert [m.pk for m in upg.modifiers.all()] == [canonical.pk]
        assert [m.pk for m in acc2.modifiers.all()] == [canonical.pk]
    finally:
        # Remove seeded data, then restore the constraint for the rest of the suite.
        ContentMod.objects.all().delete()
        with connection.schema_editor(atomic=False) as se:
            se.add_constraint(ContentModStat, constraint)
