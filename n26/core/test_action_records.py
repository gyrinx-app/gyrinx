import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

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
    with pytest.raises(ValidationError, match="another fighter"):
        allowance.full_clean()


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
    assert reconcile.check_counter_value(held.counter_value) == []


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
