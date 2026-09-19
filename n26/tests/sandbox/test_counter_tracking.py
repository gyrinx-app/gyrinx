"""Deploying the counter journal leaves ordinary counter editing available."""

import pytest

from n26.core.counter_tracking import is_active
from n26.core.models import CounterValue, Gang, LedgerEvent
from n26.core.operations import Refusal, operation
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

    @pytest.mark.parametrize("archived", [False, True])
    def test_history_with_a_missing_balance_is_reported(
        self, archived, gang, counter_tracking
    ):
        with operation(gang, actor=gang.owner) as op:
            held = op.assign(create_counter("Kill Count"), gang=gang)
            op.tally(held, 6)
        held.archived = archived
        held.save(update_fields=["archived", "modified"])
        CounterValue.objects.filter(assignment=held).delete()

        assert any(
            str(held.pk) in problem and "history has no counter value" in problem
            for problem in check_gang(gang)
        )

    @pytest.mark.parametrize("writer", ["tally", "open_counter"])
    def test_missing_balance_with_history_cannot_be_reopened(
        self, writer, gang, counter_tracking
    ):
        with operation(gang, actor=gang.owner) as op:
            held = op.assign(create_counter("Kill Count"), gang=gang)
            op.tally(held, 6)
        CounterValue.objects.filter(assignment=held).delete()
        events = list(gang.ledger_events.order_by("pk").values())

        with pytest.raises(Refusal, match="Its value is missing"):
            with operation(gang, actor=gang.owner) as op:
                getattr(op, writer)(held, 2)

        assert not CounterValue.objects.filter(assignment=held).exists()
        assert list(gang.ledger_events.order_by("pk").values()) == events

    def test_an_untouched_counter_needs_no_balance(self, gang, counter_tracking):
        with operation(gang, actor=gang.owner) as op:
            held = op.assign(create_counter("Kill Count"), gang=gang)

        assert not CounterValue.objects.filter(assignment=held).exists()
        assert check_gang(gang) == []

    def test_deleting_an_assignment_removes_its_balance_and_history(
        self, gang, counter_tracking
    ):
        with operation(gang, actor=gang.owner) as op:
            held = op.assign(create_counter("Kill Count"), gang=gang)
            op.tally(held, 6)
        assignment_id = held.pk
        held.delete()

        assert not CounterValue.objects.filter(assignment_id=assignment_id).exists()
        assert not LedgerEvent.objects.filter(assignment_id=assignment_id).exists()
        assert check_gang(gang) == []
