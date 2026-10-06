"""Authored status conditions and the standard-content upgrade."""

from importlib import import_module
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import connection

from n26.core.status import Status
from n26.library.authoring import (
    attach_modifiers_to,
    create_gang_type,
    create_pack,
    create_pickable,
    create_slot_type,
    ef_adds,
    has_status,
    modifier,
    revise,
    targets_every_model,
    targets_model,
)
from n26.library.models import (
    AddsAssignable,
    GangType,
    HasStatus,
    Modifier,
    Pickable,
    Slot,
    TargetsMiniature,
)
from n26.library.standard_content import GANG_TYPES, STANDARD_CONTENT

pytestmark = pytest.mark.django_db


def test_status_condition_is_authored_and_compiled(default_pack, gang_type):
    from n26.core import select

    condition = has_status(Status.CAPTURED)
    scope = targets_every_model(condition)
    assert HasStatus.objects.get(scope=scope).status == Status.CAPTURED
    selector = scope.as_selector()
    assert selector.matches(select.Matchable(thing=None, status=Status.CAPTURED))
    assert not selector.matches(select.Matchable(thing=None, status=Status.RECOVERY))


def test_standard_upgrade_is_idempotent_and_leaves_other_packs(default_pack, gang_type):
    STANDARD_CONTENT["lasting-effect-tables"].create()
    escape = Slot.objects.get(name="Escape")
    captured = Pickable.objects.get(name="Captured", slot_type__name="Lasting Injury")
    revise(captured, record_only=False)
    revise(escape, follows_status=False)
    modifier(
        "Old capture grant", targets_every_model(), ef_adds(escape), attach_to=captured
    )
    homebrew = create_pack("Homebrew")
    other = create_pickable(
        "Captured", create_slot_type("Lasting Injury", pack=homebrew), pack=homebrew
    )
    upgrade = import_module(
        "n26.library.migrations.0120_status_follow_up_choices"
    ).update_standard_choices
    editor = SimpleNamespace(connection=connection)
    upgrade(apps, editor)
    count = Modifier.objects.count()
    upgrade(apps, editor)
    assert Modifier.objects.count() == count
    captured.refresh_from_db()
    escape.refresh_from_db()
    other.refresh_from_db()
    assert captured.record_only and escape.follows_status
    assert not other.record_only
    assert not captured.modifiers.filter(adds_assignable__slot=escape).exists()
    grant = gang_type.modifiers.get(name="Captured models: Escape")
    assert grant.targets_miniature.has_status.get().status == Status.CAPTURED


def test_standard_upgrade_reverse_restores_the_result_grant(default_pack, gang_type):
    STANDARD_CONTENT["lasting-effect-tables"].create()
    migration = import_module("n26.library.migrations.0120_status_follow_up_choices")
    grant = Modifier.objects.get(name="Captured models: Escape")
    scope_id, effect_id = grant.targets_miniature_id, grant.adds_assignable_id
    migration.restore_standard_choices(apps, SimpleNamespace(connection=connection))
    assert not TargetsMiniature.objects.filter(pk=scope_id).exists()
    assert not HasStatus.objects.filter(scope_id=scope_id).exists()
    assert not AddsAssignable.objects.filter(pk=effect_id).exists()
    parts_before = (TargetsMiniature.objects.count(), AddsAssignable.objects.count())
    escape = Slot.objects.get(name="Escape")
    captures = Pickable.objects.filter(name="Captured")
    assert not escape.follows_status
    assert not Modifier.objects.filter(name="Captured models: Escape").exists()
    for result in captures:
        assert not result.record_only
        grant = result.modifiers.get(adds_assignable__slot=escape)
        assert grant.targets_miniature.reach == "bearer"
    migration.update_standard_choices(apps, SimpleNamespace(connection=connection))
    assert gang_type.modifiers.filter(name="Captured models: Escape").exists()
    assert not captures.filter(modifiers__adds_assignable__slot=escape).exists()
    renewed = Modifier.objects.get(name="Captured models: Escape")
    scope_id, effect_id = renewed.targets_miniature_id, renewed.adds_assignable_id
    migration.restore_standard_choices(apps, SimpleNamespace(connection=connection))
    assert (
        TargetsMiniature.objects.count(),
        AddsAssignable.objects.count(),
    ) == parts_before
    assert not TargetsMiniature.objects.filter(pk=scope_id).exists()
    assert not HasStatus.objects.filter(scope_id=scope_id).exists()
    assert not AddsAssignable.objects.filter(pk=effect_id).exists()
    assert all(
        result.modifiers.filter(adds_assignable__slot=escape).exists()
        for result in captures
    )


def test_reverse_reuses_the_original_shared_escape_grant(default_pack, gang_type):
    STANDARD_CONTENT["lasting-effect-tables"].create()
    escape = Slot.objects.get(name="Escape")
    captures = list(Pickable.objects.filter(name="Captured"))
    assert len(captures) == 2
    legacy = modifier(
        "Captured: rolls on the Escape table", targets_model(), ef_adds(escape)
    )
    for result in captures:
        attach_modifiers_to(result, [legacy])
    migration = import_module("n26.library.migrations.0120_status_follow_up_choices")
    editor = SimpleNamespace(connection=connection)
    migration.update_standard_choices(apps, editor)
    assert not any(
        result.modifiers.filter(pk=legacy.pk).exists() for result in captures
    )
    before = Modifier.objects.count()
    migration.restore_standard_choices(apps, editor)
    assert Modifier.objects.count() == before - 1
    for result in captures:
        assert list(
            result.modifiers.filter(adds_assignable__slot=escape).values_list(
                "pk", flat=True
            )
        ) == [legacy.pk]
        # The old standard-content seed finds this exact existing name, so
        # seeding after rollback leaves a single grant on each result.
        name = f"{result}: rolls on the {escape.choice_label} table"
        assert result.modifiers.filter(name=name).get().pk == legacy.pk


@pytest.mark.parametrize("tables_first", [False, True])
def test_standard_gang_types_offer_escape_in_either_seed_order(
    default_pack, tables_first
):
    homebrew = create_pack("Homebrew")
    custom = create_gang_type("Custom gang", pack=homebrew)
    keys = ["lasting-effect-tables", "gang-types"]
    if not tables_first:
        keys.reverse()
    for key in keys:
        STANDARD_CONTENT[key].create()
    grant = Modifier.objects.get(name="Captured models: Escape", pack=default_pack)
    standard = GangType.objects.filter(pack=default_pack, name__in=GANG_TYPES)
    assert standard.count() == len(GANG_TYPES)
    assert all(gang.modifiers.filter(pk=grant.pk).exists() for gang in standard)
    assert not custom.modifiers.filter(pk=grant.pk).exists()
    before = Modifier.objects.count()
    for key in keys:
        STANDARD_CONTENT[key].create()
    assert Modifier.objects.count() == before
    assert all(gang.modifiers.filter(pk=grant.pk).count() == 1 for gang in standard)


@pytest.mark.parametrize("reverse", [False, True])
def test_standard_upgrade_preserves_custom_results_in_the_default_pack(
    default_pack, gang_type, reverse
):
    STANDARD_CONTENT["lasting-effect-tables"].create()
    escape = Slot.objects.get(name="Escape")
    injury_kind = Pickable.objects.get(name="Captured", qualifier="").slot_type
    custom = [
        create_pickable("Captured", injury_kind, qualifier="custom"),
        create_pickable(
            "Captured",
            Pickable.objects.get(name="Captured", qualifier="vehicle").slot_type,
            qualifier="custom damage",
        ),
        create_pickable("Executed", escape.slot_type, qualifier="custom"),
        create_pickable("Released unharmed", escape.slot_type),
    ]
    for result in custom:
        revise(result, record_only=reverse)
        modifier(
            f"Custom grant {result.pk}",
            targets_model(),
            ef_adds(escape),
            attach_to=result,
        )
    before = {
        result.pk: (
            result.record_only,
            set(result.modifiers.values_list("pk", flat=True)),
        )
        for result in custom
    }
    migration = import_module("n26.library.migrations.0120_status_follow_up_choices")
    action = (
        migration.restore_standard_choices
        if reverse
        else migration.update_standard_choices
    )
    action(apps, SimpleNamespace(connection=connection))
    for result in custom:
        result.refresh_from_db()
        assert (
            result.record_only,
            set(result.modifiers.values_list("pk", flat=True)),
        ) == before[result.pk]
