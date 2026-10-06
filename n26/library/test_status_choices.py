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
    op_sets_status,
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
        "Captured: rolls on the Escape table",
        targets_model(),
        ef_adds(escape),
        attach_to=captured,
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
    custom_default = create_gang_type("Authored default-pack gang")
    qualified = create_gang_type("Escher", qualifier="Custom")
    keys = ["lasting-effect-tables", "gang-types"]
    if not tables_first:
        keys.reverse()
    for key in keys:
        STANDARD_CONTENT[key].create()
    grant = Modifier.objects.get(name="Captured models: Escape", pack=default_pack)
    standard = GangType.objects.filter(
        pack=default_pack, name__in=GANG_TYPES, qualifier=""
    )
    assert standard.count() == len(GANG_TYPES)
    assert STANDARD_CONTENT["gang-types"].check() == (len(GANG_TYPES), len(GANG_TYPES))
    assert all(gang.modifiers.filter(pk=grant.pk).exists() for gang in standard)
    assert not custom.modifiers.filter(pk=grant.pk).exists()
    assert not custom_default.modifiers.filter(pk=grant.pk).exists()
    assert not qualified.modifiers.filter(pk=grant.pk).exists()
    before = Modifier.objects.count()
    for key in keys:
        STANDARD_CONTENT[key].create()
    assert Modifier.objects.count() == before
    assert all(gang.modifiers.filter(pk=grant.pk).count() == 1 for gang in standard)
    assert not custom_default.modifiers.filter(pk=grant.pk).exists()
    assert not qualified.modifiers.filter(pk=grant.pk).exists()


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


def test_standard_upgrade_does_not_grant_escape_to_authored_default_pack_gangs(
    default_pack, gang_type
):
    STANDARD_CONTENT["lasting-effect-tables"].create()
    custom = create_gang_type("Authored default-pack gang")
    qualified = create_gang_type("Escher", qualifier="Custom")
    grant = Modifier.objects.get(name="Captured models: Escape", pack=default_pack)
    assert not custom.modifiers.filter(pk=grant.pk).exists()
    upgrade = import_module(
        "n26.library.migrations.0120_status_follow_up_choices"
    ).update_standard_choices
    upgrade(apps, SimpleNamespace(connection=connection))
    assert gang_type.modifiers.filter(pk=grant.pk).exists()
    assert not custom.modifiers.filter(pk=grant.pk).exists()
    assert not qualified.modifiers.filter(pk=grant.pk).exists()


@pytest.mark.parametrize("source", ["migration", "seed"])
def test_upgrading_capture_detaches_only_the_legacy_seeded_escape_grant(
    default_pack, gang_type, source
):
    STANDARD_CONTENT["lasting-effect-tables"].create()
    escape = Slot.objects.get(name="Escape", qualifier="")
    captures = list(Pickable.objects.filter(name="Captured"))
    legacy = modifier(
        "Captured: rolls on the Escape table", targets_model(), ef_adds(escape)
    )
    custom = modifier("Authored prisoner choice", targets_model(), ef_adds(escape))
    for result in captures:
        attach_modifiers_to(result, [legacy, custom])
    custom_parts = (custom.targets_miniature_id, custom.adds_assignable_id)
    migration = import_module("n26.library.migrations.0120_status_follow_up_choices")
    if source == "migration":
        migration.update_standard_choices(apps, SimpleNamespace(connection=connection))
    else:
        STANDARD_CONTENT["lasting-effect-tables"].create()
    for result in captures:
        assert not result.modifiers.filter(pk=legacy.pk).exists()
        assert result.modifiers.filter(pk=custom.pk).exists()
    custom.refresh_from_db()
    assert (custom.targets_miniature_id, custom.adds_assignable_id) == custom_parts
    if source == "migration":
        migration.restore_standard_choices(apps, SimpleNamespace(connection=connection))
        for result in captures:
            assert result.modifiers.filter(pk=legacy.pk).exists()
            assert result.modifiers.filter(pk=custom.pk).exists()


@pytest.mark.parametrize("source", ["migration", "seed", "rollback"])
def test_a_conflicting_escape_modifier_fails_without_changing_authored_content(
    default_pack, gang_type, source
):
    from django.db import transaction

    STANDARD_CONTENT["lasting-effect-tables"].create()
    seeded = Modifier.objects.get(name="Captured models: Escape")
    revise(seeded, name="Existing standard grant")
    custom = modifier(
        "Captured models: Escape", targets_model(), op_sets_status(Status.DEAD)
    )
    scope_id, effect_id = custom.targets_miniature_id, custom.op_sets_status_id
    escape = Slot.objects.get(name="Escape", qualifier="")
    captured = Pickable.objects.get(name="Captured", qualifier="")
    revise(escape, follows_status=False)
    revise(captured, record_only=False)
    migration = import_module("n26.library.migrations.0120_status_follow_up_choices")
    with pytest.raises(RuntimeError, match="different scope or effect"):
        with transaction.atomic():
            if source == "seed":
                STANDARD_CONTENT["lasting-effect-tables"].create()
            else:
                action = (
                    migration.restore_standard_choices
                    if source == "rollback"
                    else migration.update_standard_choices
                )
                action(apps, SimpleNamespace(connection=connection))
    custom.refresh_from_db()
    assert (custom.targets_miniature_id, custom.op_sets_status_id) == (
        scope_id,
        effect_id,
    )
    assert not custom.library_gangtype_set.exists()
    assert gang_type.modifiers.filter(pk=seeded.pk).exists()
    escape.refresh_from_db()
    captured.refresh_from_db()
    assert not escape.follows_status and not captured.record_only


@pytest.mark.parametrize("tables_exist", [False, True])
def test_the_gang_seed_rejects_an_unrelated_escape_modifier(default_pack, tables_exist):
    if tables_exist:
        STANDARD_CONTENT["lasting-effect-tables"].create()
        revise(
            Modifier.objects.get(name="Captured models: Escape"), name="Standard grant"
        )
    custom = modifier(
        "Captured models: Escape", targets_model(), op_sets_status(Status.DEAD)
    )
    with pytest.raises(RuntimeError, match="different scope or effect"):
        STANDARD_CONTENT["gang-types"].create()
    assert not custom.library_gangtype_set.exists()


@pytest.mark.parametrize("content", ["clean", "renamed", "authored", "missing-table"])
def test_schema_rollback_refuses_surviving_status_conditions(
    default_pack, content, monkeypatch
):
    from unittest.mock import Mock

    from django.db import transaction
    from django.db.migrations.executor import MigrationExecutor
    from django.test import override_settings

    if content == "missing-table":
        modifier(
            "Authored status grant",
            targets_every_model(has_status(Status.CAPTURED)),
            op_sets_status(Status.RECOVERY),
        )
    else:
        STANDARD_CONTENT["lasting-effect-tables"].create()
        if content == "renamed":
            revise(
                Modifier.objects.get(name="Captured models: Escape"),
                name="Renamed grant",
            )
        elif content == "authored":
            modifier(
                "Authored status grant",
                targets_model(has_status(Status.CAPTURED)),
                op_sets_status(Status.RECOVERY),
            )
    before = (
        list(Modifier.objects.values_list("pk", "name")),
        list(HasStatus.objects.values_list("pk", "scope_id", "status")),
        list(Slot.objects.values_list("pk", "follows_status")),
        list(Pickable.objects.values_list("pk", "record_only")),
    )
    migration = import_module("n26.library.migrations.0120_status_follow_up_choices")
    with override_settings(MIGRATION_MODULES={}):
        state = MigrationExecutor(connection).loader.project_state(
            [("library", "0119_hide_equipment_categories")]
        )

    class ReachedSchemaRemoval(Exception):
        pass

    delete_model = Mock(side_effect=ReachedSchemaRemoval)
    expected = ReachedSchemaRemoval if content == "clean" else RuntimeError
    with pytest.raises(expected) as raised:
        with transaction.atomic(), connection.schema_editor() as editor:
            monkeypatch.setattr(editor, "delete_model", delete_model)
            migration.Migration("0120_status_follow_up_choices", "library").unapply(
                state, editor
            )
    if content != "clean":
        message = str(raised.value)
        assert 'Restore the standard modifier name "Captured models: Escape"' in message
        assert "remove the affected authored modifiers in full" in message
        assert "Do not delete status conditions alone" in message
    assert delete_model.call_count == (1 if content == "clean" else 0)
    assert before == (
        list(Modifier.objects.values_list("pk", "name")),
        list(HasStatus.objects.values_list("pk", "scope_id", "status")),
        list(Slot.objects.values_list("pk", "follows_status")),
        list(Pickable.objects.values_list("pk", "record_only")),
    )
