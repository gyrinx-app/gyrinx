import uuid
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import RestrictedError

from n26.core import reconcile
from n26.core.models import (
    ActionAllowance,
    ActionRecord,
    Gang,
    LedgerEvent,
)
from n26.core.operations import operation
from n26.library.models import Action, Counter, RankTable

pytestmark = [pytest.mark.django_db, pytest.mark.core]


@pytest.fixture
def gang(user, gang_type):
    return Gang.objects.create(name="The Long Hunt", owner=user, gang_type=gang_type)


@pytest.fixture
def fighter(user, gang, make_profile, make_statline):
    profile = make_profile("Hunter", price=100)
    make_statline(profile)
    with operation(gang, actor=user) as op:
        return op.hire(profile, "Kara", paid=100)


@pytest.fixture
def action():
    return Action.objects.create(name="Maintain suit", timing=Action.Timing.POST_CYCLE)


def recruitment_allowance(fighter, action):
    return ActionAllowance.objects.create(
        action=action,
        fighter=fighter,
        recruitment=fighter.membership,
        source_kind=ActionAllowance.Source.RECRUITMENT,
    )


def test_allowance_source_shape_is_enforced(fighter, action):
    with pytest.raises(IntegrityError), transaction.atomic():
        ActionAllowance.objects.create(
            action=action,
            fighter=fighter,
            recruitment=fighter.membership,
            source_kind=ActionAllowance.Source.RANK,
            threshold=6,
        )


def test_rank_allowances_are_unique_per_threshold(fighter, action):
    xp = Counter.objects.create(name="XP")
    ranks = RankTable.objects.create(name="Standard ranks", counter=xp)
    fields = {
        "action": action,
        "fighter": fighter,
        "recruitment": fighter.membership,
        "source_kind": ActionAllowance.Source.RANK,
        "threshold": 6,
        "rank_table": ranks,
    }
    ActionAllowance.objects.create(**fields)
    with pytest.raises(IntegrityError), transaction.atomic():
        ActionAllowance.objects.create(**fields)


def test_allowance_must_name_its_fighters_recruitment(
    user, gang, fighter, action, make_profile, make_statline
):
    profile = make_profile("Other hunter", price=100)
    make_statline(profile)
    with operation(gang, actor=user) as op:
        other = op.hire(profile, "Rika", paid=100)
    allowance = ActionAllowance(
        action=action,
        fighter=fighter,
        recruitment=other.membership,
        source_kind=ActionAllowance.Source.RECRUITMENT,
    )
    with pytest.raises(ValidationError, match="another model"):
        allowance.full_clean()


def test_rank_allowance_threshold_must_be_positive(fighter, action):
    xp = Counter.objects.create(name="XP")
    ranks = RankTable.objects.create(name="Standard ranks", counter=xp)
    with pytest.raises(IntegrityError), transaction.atomic():
        ActionAllowance.objects.create(
            action=action,
            fighter=fighter,
            recruitment=fighter.membership,
            source_kind=ActionAllowance.Source.RANK,
            threshold=0,
            rank_table=ranks,
        )


def test_request_keys_are_idempotent_within_a_gang(gang, fighter, action):
    request_key = uuid.uuid4()
    ActionRecord.objects.create(
        gang=gang, fighter=fighter, action=action, request_key=request_key
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        ActionRecord.objects.create(
            gang=gang, fighter=fighter, action=action, request_key=request_key
        )


def test_active_record_reserves_an_allowance_until_cancelled(gang, fighter, action):
    allowance = recruitment_allowance(fighter, action)
    first = ActionRecord.objects.create(
        gang=gang,
        fighter=fighter,
        action=action,
        allowance=allowance,
        request_key=uuid.uuid4(),
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        ActionRecord.objects.create(
            gang=gang,
            fighter=fighter,
            action=action,
            allowance=allowance,
            request_key=uuid.uuid4(),
        )

    first.state = ActionRecord.State.CANCELLED
    first.save(update_fields=["state", "modified"])
    ActionRecord.objects.create(
        gang=gang,
        fighter=fighter,
        action=action,
        allowance=allowance,
        request_key=uuid.uuid4(),
    )


@pytest.mark.parametrize("delete", ["fighter", "gang"])
def test_a_consumed_allowance_leaves_with_its_fighter_graph(
    delete, gang, fighter, action
):
    allowance = recruitment_allowance(fighter, action)
    ActionRecord.objects.create(
        gang=gang,
        fighter=fighter,
        action=action,
        allowance=allowance,
        request_key=uuid.uuid4(),
    )

    (fighter if delete == "fighter" else gang).delete()

    assert not ActionAllowance.objects.filter(pk=allowance.pk).exists()
    assert not ActionRecord.objects.filter(allowance_id=allowance.pk).exists()


def test_a_consumed_allowance_cannot_be_deleted_on_its_own(gang, fighter, action):
    allowance = recruitment_allowance(fighter, action)
    ActionRecord.objects.create(
        gang=gang,
        fighter=fighter,
        action=action,
        allowance=allowance,
        request_key=uuid.uuid4(),
    )

    with pytest.raises(RestrictedError):
        allowance.delete()


def test_exact_action_selections_persist_and_leave_with_the_record(
    user, gang, fighter, action
):
    from n26.core.models import (
        AdvancementSelection,
        AugmentationSelection,
        SkillSelection,
    )
    from n26.library.models import Category, Pickable, Section, Skill, SlotType

    record = ActionRecord.objects.create(
        gang=gang, fighter=fighter, action=action, request_key=uuid.uuid4()
    )
    slot_type = SlotType.objects.create(name="Selection")
    intended = Pickable.objects.create(name="Exact result", slot_type=slot_type)
    section = Section.objects.create(name="Selection skills")
    skill_set = Category.objects.create(name="Selection set", section=section)
    skill = Skill.objects.create(name="Exact skill", category=skill_set)
    event = LedgerEvent.objects.create(
        gang=gang, actor=user, kind=LedgerEvent.Kind.ROLLED, miniature=fighter
    )
    assignment = fighter.membership

    augmentation = AugmentationSelection.objects.create(
        action_record=record,
        item_assignment=assignment,
        slot_assignment=assignment,
        previous_pick=assignment,
        intended_pick=intended,
        new_pick=assignment,
    )
    advancement = AdvancementSelection.objects.create(
        action_record=record,
        slot_assignment=assignment,
        roll_event=event,
        intended_pick=intended,
        pick_assignment=assignment,
    )
    selected = SkillSelection.objects.create(
        action_record=record,
        mode=SkillSelection.Mode.SELECT,
        access=SkillSelection.Access.PRIMARY,
        skill_set=skill_set,
        selected_skill=skill,
        skill_assignment=assignment,
    )

    assert augmentation.intended_pick_id == intended.pk
    assert advancement.roll_event_id == event.pk
    assert selected.selected_skill_id == skill.pk

    record.delete()
    assert not AugmentationSelection.objects.filter(pk=augmentation.pk).exists()
    assert not AdvancementSelection.objects.filter(pk=advancement.pk).exists()
    assert not SkillSelection.objects.filter(pk=selected.pk).exists()


def test_tally_writes_a_structured_chain(user, gang, fighter):
    xp = Counter.objects.create(name="XP")
    with operation(gang, actor=user) as op:
        held = op.assign(xp, miniature=fighter)
        op.tally(held, 7)
        op.tally(held, -10)

    events = list(
        held.ledger_events.filter(counter_before__isnull=False).order_by("created")
    )
    assert [
        (event.kind, event.counter_before, event.counter_delta, event.counter_after)
        for event in events
    ] == [
        (LedgerEvent.Kind.COUNTER_OPENED, 0, 0, 0),
        (LedgerEvent.Kind.TALLIED, 0, 7, 7),
        (LedgerEvent.Kind.TALLIED, 7, -7, 0),
    ]
    counter_value = held.counter_value
    counter_value.refresh_from_db()
    assert reconcile.check_counter_value(counter_value) == []


def test_counter_event_arithmetic_is_enforced(user, gang, fighter):
    xp = Counter.objects.create(name="XP")
    with operation(gang, actor=user) as op:
        held = op.assign(xp, miniature=fighter)

    with pytest.raises(IntegrityError), transaction.atomic():
        LedgerEvent.objects.create(
            assignment=held,
            gang=gang,
            actor=user,
            kind=LedgerEvent.Kind.TALLIED,
            counter_before=0,
            counter_delta=2,
            counter_after=3,
        )


def test_counter_fields_are_refused_on_another_event_kind(user, gang, fighter):
    with pytest.raises(IntegrityError), transaction.atomic():
        LedgerEvent.objects.create(
            gang=gang,
            actor=user,
            kind=LedgerEvent.Kind.STATUS_SET,
            miniature=fighter,
            counter_before=0,
            counter_delta=1,
            counter_after=1,
        )


def test_legacy_tally_without_structured_counter_fields_is_kept(user, gang, fighter):
    event = LedgerEvent.objects.create(
        gang=gang,
        actor=user,
        kind=LedgerEvent.Kind.TALLIED,
        miniature=fighter,
    )
    assert event.counter_before is None
    assert event.counter_delta is None
    assert event.counter_after is None


def test_events_with_the_same_timestamp_have_stable_primary_key_order(
    user, gang, fighter
):
    first = LedgerEvent.objects.create(
        gang=gang, actor=user, kind=LedgerEvent.Kind.STATUS_SET, miniature=fighter
    )
    second = LedgerEvent.objects.create(
        gang=gang, actor=user, kind=LedgerEvent.Kind.STATUS_SET, miniature=fighter
    )
    timestamp = first.created - timedelta(seconds=1)
    LedgerEvent.objects.filter(pk__in=[first.pk, second.pk]).update(created=timestamp)

    assert list(
        LedgerEvent.objects.filter(pk__in=[first.pk, second.pk]).values_list(
            "pk", flat=True
        )
    ) == sorted([first.pk, second.pk])


def test_tally_ignores_a_counter_value_cached_before_the_lock(user, gang, fighter):
    counter = Counter.objects.create(name="XP")
    with operation(gang, actor=user) as op:
        held = op.assign(counter, miniature=fighter)
        op.tally(held, 2)
    stale = held.counter_value
    assert stale.value == 2
    with operation(gang, actor=user) as op:
        op.tally(held, 3)
    assert stale.value == 2
    with operation(gang, actor=user) as op:
        assert op.tally(held, 4) == 9
    stale.refresh_from_db()
    assert stale.value == 9


def test_counter_chain_requires_an_opening(user, gang, fighter):
    with operation(gang, actor=user) as op:
        held = op.assign(Counter.objects.create(name="XP"), miniature=fighter)
        op.tally(held, 3)
    held.ledger_events.filter(kind=LedgerEvent.Kind.COUNTER_OPENED).delete()
    assert any(
        "no counter opening event" in problem
        for problem in reconcile.check_counter_value(held.counter_value)
    )


def test_gang_reconciliation_reads_counter_chains_together(user, gang, fighter):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with operation(gang, actor=user) as op:
        for index in range(6):
            held = op.assign(
                Counter.objects.create(name=f"Counter {index}"), miniature=fighter
            )
            op.tally(held, index)
    with CaptureQueriesContext(connection) as queries:
        assert reconcile.check_gang(Gang.objects.get(pk=gang.pk)) == []
    chain_reads = [
        query for query in queries if '"counter_before" IS NOT NULL' in query["sql"]
    ]
    assert len(chain_reads) == 1
