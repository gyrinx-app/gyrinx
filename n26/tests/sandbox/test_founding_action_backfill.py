"""The founding-action backfill: every existing gang gets the act it
was founded without.

Founding a gang opens a Found and equip gang action, but gangs founded
before that existed have none — nothing on their page says the act is
still to be completed. The backfill walks the estate on the batched
runner and opens one for each, through the same operation a founding
uses, so the gang's history reads as it would have.

Proven here: which gangs qualify, that each gets exactly one action and
one event, that a gang already holding one — open or completed — is
stepped past, that archived gangs are untouched, that the outcome lands
on the record, and that a rerun and a redelivered message both change
nothing.
"""

import pytest
from django.contrib.auth.models import User

from gyrinx.maintenance.models import Backfill
from n26.core.models import Action, Gang, LedgerEvent
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.maintenance import (
    Operation,
    gangs_without_a_founding_action,
    open_founding_actions,
)
from n26.tests.sandbox.actions import found_gang

pytestmark = pytest.mark.django_db

FOUNDING = Action.Kind.FOUNDING


@pytest.fixture
def player():
    return User.objects.create_user("founder")


@pytest.fixture
def record(db):
    return Backfill.objects.create(
        operation=Operation.OPEN_FOUNDING_ACTIONS,
        status=Backfill.Status.RUNNING,
        summary={"attempts": 0},
    )


@pytest.fixture
def old_gang(gang_type, player, person_type, default_pack):
    """A gang as one founded before the action existed: no action row,
    and no event saying one was ever started."""

    def _found(name="Before The Action", **kwargs):
        gang = found_gang(name, gang_type, owner=player, budget=1000, **kwargs)
        LedgerEvent.objects.filter(
            gang=gang,
            kind__in=[LedgerEvent.Kind.ACTION_OPENED, LedgerEvent.Kind.ACTION_CLOSED],
        ).delete()
        assert not Action.objects.filter(gang=gang).exists()
        return gang

    return _found


def run(record):
    open_founding_actions.func(backfill_id=str(record.pk))
    record.refresh_from_db()
    return record


def opened_events(gang):
    return LedgerEvent.objects.filter(
        gang=gang, kind=LedgerEvent.Kind.ACTION_OPENED
    ).count()


class TestWhichGangsQualify:
    """Never had one, rather than has not got one now: an owner who has
    completed the act is done with it."""

    def test_a_gang_founded_before_the_action_qualifies(self, old_gang):
        gang = old_gang()

        assert list(gangs_without_a_founding_action()) == [gang]

    def test_a_gang_founded_since_does_not(self, gang_type, player, default_pack):
        found_gang("Founded Today", gang_type, owner=player, budget=1000)

        assert not gangs_without_a_founding_action().exists()

    def test_a_gang_that_completed_its_founding_does_not(self, old_gang, player):
        gang = old_gang()
        with operation(gang, actor=player) as op:
            op.open_action(FOUNDING)
        with operation(gang, actor=player) as op:
            op.close_action(gang.open_action(FOUNDING))

        assert gang.open_action(FOUNDING) is None
        assert not gangs_without_a_founding_action().exists()

    def test_an_archived_gang_does_not(self, old_gang):
        gang = old_gang()
        gang.archive()

        assert not gangs_without_a_founding_action().exists()


class TestOpeningTheAction:
    """One action per qualifying gang, opened the way a founding opens
    it — so the event is there and the history reads the same."""

    def test_each_qualifying_gang_gets_one_action_and_one_event(self, old_gang, record):
        first = old_gang("First")
        second = old_gang("Second")

        run(record)

        for gang in (first, second):
            action = gang.open_action(FOUNDING)
            assert action is not None
            assert action.trade_points is None
            assert action.opened.kind == LedgerEvent.Kind.ACTION_OPENED
            assert opened_events(gang) == 1
            gang.refresh_from_db()
            assert_reconciled(gang)

    def test_the_event_is_filed_against_whoever_asked_for_the_run(
        self, old_gang, record
    ):
        """A repair that hands a gang something says who asked for it;
        an act filed against nobody reads as the gang's own."""
        boss = User.objects.create_superuser("chief", "chief@example.com", "password")
        record.triggered_by = boss
        record.save()
        gang = old_gang()

        run(record)

        assert gang.open_action(FOUNDING).opened.actor_id == boss.pk

    def test_the_gang_history_says_the_action_was_started(self, old_gang, record):
        from n26.core.history import build

        gang = old_gang()

        run(record)

        told = " ".join(line.search for line in build(gang))
        assert "started the found and equip gang action" in told

    def test_a_gang_that_already_has_one_keeps_the_one_it_has(
        self, old_gang, player, record
    ):
        gang = old_gang()
        with operation(gang, actor=player) as op:
            already = op.open_action(FOUNDING)

        run(record)

        assert gang.open_action(FOUNDING).pk == already.pk
        assert Action.objects.filter(gang=gang, kind=FOUNDING).count() == 1
        assert opened_events(gang) == 1

    def test_a_completed_founding_is_not_opened_again(self, old_gang, player, record):
        """Completing the act is the owner saying they are done. A
        backfill that reopened it would put them back at the start."""
        gang = old_gang()
        with operation(gang, actor=player) as op:
            op.open_action(FOUNDING)
        with operation(gang, actor=player) as op:
            op.close_action(gang.open_action(FOUNDING))

        run(record)

        assert gang.open_action(FOUNDING) is None
        assert Action.objects.filter(gang=gang, kind=FOUNDING).count() == 1

    def test_an_archived_gang_is_left_alone(self, old_gang, record):
        gang = old_gang()
        gang.archive()

        run(record)

        assert not Action.objects.filter(gang=gang).exists()
        assert opened_events(gang) == 0


class TestTheRecord:
    """Every ending is written onto the record rather than raised."""

    def test_a_finished_run_says_what_it_opened(self, old_gang, record):
        old_gang("First")
        old_gang("Second")

        run(record)

        assert record.status == Backfill.Status.DONE
        assert record.summary["totals"]["opened"] == 2
        assert record.summary["done"] == 2
        assert record.summary["failures"] == {}

    def test_a_gang_stepped_past_is_counted_too(
        self, old_gang, gang_type, player, default_pack, record
    ):
        old_gang("Qualifies")
        found_gang("Founded Today", gang_type, owner=player, budget=1000)

        run(record)

        assert record.summary["totals"]["opened"] == 1
        assert record.summary["totals"]["already_had_one"] == 1

    def test_a_run_over_nothing_still_ends_done(
        self, gang_type, player, default_pack, record
    ):
        found_gang("Founded Today", gang_type, owner=player, budget=1000)

        run(record)

        assert record.status == Backfill.Status.DONE
        assert "opened" not in record.summary["totals"]


class TestRunningItTwice:
    """Delivery is at-least-once and an operator may run a repair again;
    neither may open a second action."""

    def test_a_rerun_changes_nothing(self, old_gang, record):
        gang = old_gang()
        run(record)
        again = Backfill.objects.create(
            operation=Operation.OPEN_FOUNDING_ACTIONS,
            status=Backfill.Status.RUNNING,
            summary={"attempts": 0},
        )

        run(again)

        assert Action.objects.filter(gang=gang, kind=FOUNDING).count() == 1
        assert opened_events(gang) == 1
        assert again.status == Backfill.Status.DONE
        assert again.summary["totals"]["already_had_one"] == 1
        assert "opened" not in again.summary["totals"]

    def test_a_redelivered_message_opens_nothing_more(
        self, old_gang, record, task_queue
    ):
        """The run holds its own lock, so a copy arriving while it works
        stands down. A copy arriving after it has finished gets no
        further: the record has reached an ending, endings are final,
        and the claim refuses to start a second walk over it."""
        gang = old_gang()

        with task_queue.capture():
            open_founding_actions.enqueue(backfill_id=str(record.pk))
        task_queue.deliver_all()
        task_queue.redeliver_last()

        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE
        assert Action.objects.filter(gang=gang, kind=FOUNDING).count() == 1
        assert opened_events(gang) == 1


class TestTheEstate:
    """The walk is every unarchived gang, so the set it steps through
    does not shrink as it works — the cursor a batched run keeps is only
    sound over a set that stays put."""

    def test_the_walk_counts_every_unarchived_gang(
        self, old_gang, gang_type, player, default_pack, record
    ):
        old_gang("Qualifies")
        found_gang("Founded Today", gang_type, owner=player, budget=1000)
        archived = old_gang("Gone")
        archived.archive()

        run(record)

        assert record.summary["total"] == Gang.objects.filter(archived=False).count()
        assert record.summary["total"] == 2
