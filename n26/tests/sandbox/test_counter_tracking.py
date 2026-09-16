"""Deploying the counter journal leaves ordinary counter editing available."""

import pytest

from n26.core.counter_tracking import is_active
from n26.core.models import Gang, LedgerEvent
from n26.core.operations import operation
from n26.core.reconcile import check_counter_value, check_gang
from n26.library.authoring import create_counter

pytestmark = [pytest.mark.django_db, pytest.mark.core]


@pytest.fixture
def gang(owner, gang_type):
    return Gang.objects.create(name="The Hunt", owner=owner, gang_type=gang_type)


class TestCounterTrackingBeforeActivation:
    """Schema delivery does not begin a journal halfway through a counter's life."""

    def test_counter_edits_keep_the_balance_and_the_existing_history(self, gang):
        counter = create_counter("Kill Count")
        with operation(gang, actor=gang.owner) as op:
            held = op.assign(counter, gang=gang)
            op.tally(held, 6)
            op.tally(held, -4)

        assert not is_active()
        held.counter_value.refresh_from_db()
        assert held.counter_value.value == 2
        events = list(held.ledger_events.filter(kind=LedgerEvent.Kind.TALLIED))
        assert len(events) == 2
        assert all(event.counter_before is None for event in events)
        assert any("-4 → 2" in event.note for event in events)
        assert not held.ledger_events.filter(
            kind=LedgerEvent.Kind.COUNTER_OPENED
        ).exists()
        assert check_gang(gang) == []

    def test_the_other_reconciliation_checks_still_run(self, gang):
        Gang.objects.filter(pk=gang.pk).update(rating=42)
        gang.refresh_from_db()

        assert any("rating pinned 42" in problem for problem in check_gang(gang))

    def test_an_explicit_counter_audit_still_requires_an_opening(self, gang):
        with operation(gang, actor=gang.owner) as op:
            held = op.assign(create_counter("Kill Count"), gang=gang)
            op.tally(held, 6)

        assert any(
            "no counter opening event" in problem
            for problem in check_counter_value(held.counter_value)
        )


class TestCounterTrackingAfterActivation:
    """New counters and every movement have a structured history."""

    def test_new_counter_history_reconciles(self, gang, counter_tracking):
        with operation(gang, actor=gang.owner) as op:
            held = op.assign(create_counter("Kill Count"), gang=gang)
            op.tally(held, 6)
            op.tally(held, -4)

        assert is_active()
        held.counter_value.refresh_from_db()
        assert check_counter_value(held.counter_value) == []
        assert check_gang(gang) == []
