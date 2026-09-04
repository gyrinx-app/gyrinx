"""The player-data repair that frees the retired Affiliation rows."""

import pytest

from n26.core.capture import gang_state
from n26.core.legacy_affiliation_assignments import (
    ARCHIVED_NONE,
    LIVE_SPARE,
    Refused,
    apply,
    find,
)
from n26.core.models import Assignment, LedgerEntry, LedgerEvent
from n26.core.reconcile import assert_reconciled
from n26.tests.sandbox.actions import (
    assign,
    create_affiliation,
    create_gang_type,
    create_hidden,
    create_pickable,
    create_picklist,
    create_slot,
    create_slot_type,
    ef_adds,
    found_gang,
    modifier,
    targets_gang_alone,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def legacy_world(default_pack, owner):
    gang_type = create_gang_type("Legacy repair gang", starting_credits=1000)

    variant_type = create_slot_type(
        "Variant", plural_name="Variants", allows_repeats=False
    )
    variant_slot = create_slot(
        "Variant",
        variant_type,
        create_picklist("Variants", variant_type),
        assigned_to="gang",
        min_picks=0,
        max_picks=1,
    )

    affiliation_type = create_slot_type(
        "Affiliation", plural_name="Affiliations", allows_repeats=False
    )
    mutant_pickable = create_pickable("Mutant", affiliation_type)
    clanless_pickable = create_pickable("Clanless", affiliation_type)
    affiliation_slot = create_slot(
        "Affiliation",
        affiliation_type,
        create_picklist(
            "Affiliations",
            affiliation_type,
            members=[mutant_pickable, clanless_pickable],
        ),
        assigned_to="gang",
        min_picks=0,
        max_picks=1,
    )
    modifier(
        "Variants: the gang is asked its Variant",
        targets_gang_alone(),
        ef_adds(variant_slot),
        carried_by=gang_type,
    )

    none_gang = found_gang("The None", gang_type, owner=owner, budget=1000)
    none_cause = none_gang.founding
    none = assign(
        create_affiliation("None"),
        gang=none_gang,
        caused_by=none_cause,
    )
    none.archive()

    spare_gang = found_gang("The Spare", gang_type, owner=owner, budget=1000)
    marker = assign(
        create_hidden("Affiliation"),
        gang=spare_gang,
        caused_by=spare_gang.founding,
    )
    mutant = assign(
        create_affiliation("Mutant"),
        gang=spare_gang,
        caused_by=marker,
    )
    old_pick = assign(
        mutant_pickable,
        gang=spare_gang,
        caused_by=marker,
        chosen_for=marker,
        chosen_for_slot=affiliation_slot,
    )
    old_pick.archive()
    current_pick = assign(
        clanless_pickable,
        gang=spare_gang,
        caused_by=marker,
        chosen_for=marker,
        chosen_for_slot=affiliation_slot,
    )

    assert_reconciled(none_gang)
    assert_reconciled(spare_gang)
    return none_gang, none, spare_gang, mutant, old_pick, current_pick


def test_it_finds_only_the_two_measured_shapes(legacy_world):
    none_gang, none, spare_gang, mutant, *_ = legacy_world

    plan = find()

    assert plan.ok and not plan.nothing_here
    assert dict(plan.gangs) == {
        none_gang.pk: ((none.pk, ARCHIVED_NONE),),
        spare_gang.pk: ((mutant.pk, LIVE_SPARE),),
    }
    said = "\n".join(plan.preview())
    assert "1 archived None assignment" in said
    assert "1 live spare" in said
    assert "ledger entries and history events are deleted too" in said


def test_it_deletes_the_legacy_rows_and_their_empty_books_without_changing_pages(
    legacy_world,
):
    none_gang, none, spare_gang, mutant, old_pick, current_pick = legacy_world
    before = {gang.pk: gang_state(gang) for gang in (none_gang, spare_gang)}
    deleted_ids = (none.pk, mutant.pk)
    kept_event = current_pick.ledger_events.get().pk

    report = apply(find())

    assert any("deleted 1 legacy assignment" in line for line in report)
    assert not Assignment.objects.filter(pk__in=deleted_ids).exists(), report
    assert not LedgerEntry.objects.filter(assignment_id__in=deleted_ids).exists()
    assert not LedgerEvent.objects.filter(assignment_id__in=deleted_ids).exists()
    assert Assignment.objects.filter(pk__in=(old_pick.pk, current_pick.pk)).count() == 2
    assert LedgerEvent.objects.filter(pk=kept_event).exists()
    none_gang.refresh_from_db()
    assert gang_state(none_gang) == before[none_gang.pk]
    assert_reconciled(none_gang)
    spare_gang.refresh_from_db()
    after_spare = gang_state(spare_gang)
    assert after_spare["rows"] == [
        row for row in before[spare_gang.pk]["rows"] if row != "Mutant"
    ]
    assert {**after_spare, "rows": before[spare_gang.pk]["rows"]} == before[
        spare_gang.pk
    ]
    assert_reconciled(spare_gang)
    assert find().nothing_here
    assert apply(find()) == ["no legacy affiliation assignments remain"]


def test_it_refuses_a_non_zero_ledger_entry(legacy_world):
    _, none, *_ = legacy_world
    entry = none.ledger_entry
    entry.paid = 1
    entry.save(update_fields=["paid"])

    plan = find()

    assert not plan.ok
    assert any("non-zero ledger entry" in problem for problem in plan.problems)
    with pytest.raises(Refused, match="cannot run"):
        apply(plan)


def test_it_refuses_history_pinned_to_another_gang(legacy_world):
    _, none, other_gang, *_ = legacy_world
    event = none.ledger_events.get()
    event.gang = other_gang
    event.save(update_fields=["gang"])

    plan = find()

    assert not plan.ok
    assert any("history event pinned to another gang" in p for p in plan.problems)


def test_it_refuses_a_live_none_assignment(legacy_world):
    _, none, *_ = legacy_world
    none.unarchive()

    plan = find()

    assert not plan.ok
    assert any("live None assignment" in problem for problem in plan.problems)


def test_it_refuses_a_spare_without_one_current_converted_pick(legacy_world):
    *_, current_pick = legacy_world
    current_pick.archive()

    plan = find()

    assert not plan.ok
    assert any("one live pick" in problem for problem in plan.problems)


def test_a_changed_plan_is_skipped_without_deleting_anything(legacy_world):
    _, none, *_ = legacy_world
    plan = find()
    none.unarchive()

    report = apply(plan)

    assert Assignment.objects.filter(pk=none.pk).exists()
    assert any("changed since the plan was read" in line for line in report)
