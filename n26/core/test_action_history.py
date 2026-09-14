import uuid

import pytest

from n26.core import history
from n26.core.models import Gang, LedgerEvent
from n26.core.operations import operation
from n26.core.test_action_checkout import configured_action, start_and_review

pytestmark = [pytest.mark.django_db, pytest.mark.core]


@pytest.fixture
def gang(user, gang_type):
    return Gang.objects.create(
        name="The Long Hunt",
        owner=user,
        gang_type=gang_type,
        starting_credits=1000,
        credits=1000,
    )


@pytest.fixture
def fighter(user, gang, make_profile, make_statline):
    profile = make_profile("Hunter", price=100)
    make_statline(profile)
    with operation(gang, actor=user) as op:
        return op.hire(profile, "Kara", paid=100)


def sentence(act):
    return "".join(span.text for span in act.spans)


def is_action_use(act):
    return sentence(act).startswith(
        ("started ", "paid to use ", "completed ", "cancelled ", "corrected ")
    )


def test_action_lifecycle_history_names_the_action_and_fighter(user, gang, fighter):
    action, outcome, _, _ = configured_action(user, gang, fighter)
    record = start_and_review(user, gang, fighter, action, outcome)
    with operation(gang, actor=user) as op:
        op.complete_action(
            record,
            revision=record.revision,
            review=record.review,
            outcome=outcome,
        )

    acts = [
        act
        for act in history.build(gang, viewer=user)
        if is_action_use(act) and "Maintain suit" in sentence(act)
    ]
    assert [(sentence(act), act.category, act.note) for act in acts] == [
        ("started Maintain suit for Kara", "model", ""),
        ("paid to use Maintain suit for Kara", "money", ""),
        ("completed Maintain suit for Kara — Clear glitches", "model", ""),
    ]


def test_cancelled_and_corrected_actions_have_plain_sentences(user, gang, fighter):
    action, _, _, _ = configured_action(user, gang, fighter)
    with operation(gang, actor=user) as op:
        cancelled = op.start_action(fighter, action, uuid.uuid4())
        op.cancel_action(cancelled)
        corrected = op.start_action(fighter, action, uuid.uuid4())
        op.event(
            fighter,
            LedgerEvent.Kind.ACTION_USE_CORRECTED,
            action_record=corrected,
            note="A better result",
        )

    told = [
        (sentence(act), act.category, act.note)
        for act in history.build(gang)
        if is_action_use(act) and "Maintain suit" in sentence(act)
    ]
    assert ("cancelled Maintain suit for Kara", "model", "") in told
    assert ("corrected Maintain suit for Kara — A better result", "model", "") in told


def test_action_history_queries_do_not_grow_with_events(
    user, gang, fighter, django_assert_num_queries
):
    action, _, _, _ = configured_action(user, gang, fighter)
    for _ in range(10):
        with operation(gang, actor=user) as op:
            record = op.start_action(fighter, action, uuid.uuid4())
            op.cancel_action(record)

    history.build(gang)
    with django_assert_num_queries(3):
        acts = history.build(gang)
    assert len([act for act in acts if is_action_use(act)]) == 20
