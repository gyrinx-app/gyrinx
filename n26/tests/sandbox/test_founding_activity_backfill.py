"""Backfill one founding activity for each unarchived gang with no founding-activity
history. Reuse the domain operation and batched maintenance runner; completed
activities, repeated runs and redelivery must not create another.
"""

import pytest
from django.contrib.auth.models import User

from gyrinx.maintenance.models import Backfill
from n26.core.models import Activity, Gang, LedgerEvent
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.maintenance import (
    Operation,
    gangs_without_a_founding_action,
    open_founding_actions,
)
from n26.tests.sandbox.actions import found_gang, open_founding

pytestmark = pytest.mark.django_db

FOUNDING = Activity.Kind.FOUNDING


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
    """Construct a gang with no founding activity or activity events."""

    def _found(name="Before The Activity", **kwargs):
        gang = found_gang(name, gang_type, owner=player, budget=1000, **kwargs)
        LedgerEvent.objects.filter(
            gang=gang,
            kind__in=[LedgerEvent.Kind.ACTION_OPENED, LedgerEvent.Kind.ACTION_CLOSED],
        ).delete()
        assert not Activity.objects.filter(gang=gang).exists()
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
    """Qualify gangs with no founding-activity history, excluding completed and archived
    gangs.
    """

    def test_a_gang_founded_before_the_action_qualifies(self, old_gang):
        gang = old_gang()

        assert list(gangs_without_a_founding_action()) == [gang]

    def test_a_gang_that_started_the_action_does_not(
        self, gang_type, player, default_pack
    ):
        open_founding(found_gang("Founded Today", gang_type, owner=player, budget=1000))

        assert not gangs_without_a_founding_action().exists()

    def test_a_gang_that_completed_its_founding_does_not(self, old_gang, player):
        gang = old_gang()
        with operation(gang, actor=player) as op:
            op.open_activity(FOUNDING)
        with operation(gang, actor=player) as op:
            op.close_activity(gang.open_activity(FOUNDING))

        assert gang.open_activity(FOUNDING) is None
        assert not gangs_without_a_founding_action().exists()

    def test_an_archived_gang_does_not(self, old_gang):
        gang = old_gang()
        gang.archive()

        assert not gangs_without_a_founding_action().exists()


class TestOpeningTheAction:
    """Create one activity and opening event through the standard operation."""

    def test_each_qualifying_gang_gets_one_action_and_one_event(self, old_gang, record):
        first = old_gang("First")
        second = old_gang("Second")

        run(record)

        for gang in (first, second):
            action = gang.open_activity(FOUNDING)
            assert action is not None
            assert action.trade_points is None
            assert action.opened.kind == LedgerEvent.Kind.ACTION_OPENED
            assert opened_events(gang) == 1
            gang.refresh_from_db()
            assert_reconciled(gang)

    def test_nobody_is_named_as_having_started_it(self, old_gang, record):
        """System-created activity events have no actor; the admin triggering the repair
        must not appear as the gang's player.
        """
        boss = User.objects.create_superuser("chief", "chief@example.com", "password")
        record.triggered_by = boss
        record.save()
        gang = old_gang()

        run(record)

        assert gang.open_activity(FOUNDING).opened.actor_id is None

    def test_the_gang_history_says_the_action_was_started(self, old_gang, record):
        from n26.core.history import build

        gang = old_gang()

        run(record)

        told = " ".join(line.search for line in build(gang))
        assert "started the spend founding tp action" in told

    def test_the_history_line_carries_no_subject(self, old_gang, record):
        """Display system-created history without an actor label."""
        from n26.core.history import build

        gang = old_gang()

        run(record)

        started = [
            line
            for line in build(gang)
            if "started the Spend founding TP action"
            in "".join(span.text for span in line.spans)
        ]
        assert len(started) == 1
        assert started[0].actor == ""

    def test_a_gang_that_already_has_one_keeps_the_one_it_has(
        self, old_gang, player, record
    ):
        gang = old_gang()
        with operation(gang, actor=player) as op:
            already = op.open_activity(FOUNDING)

        run(record)

        assert gang.open_activity(FOUNDING).pk == already.pk
        assert Activity.objects.filter(gang=gang, kind=FOUNDING).count() == 1
        assert opened_events(gang) == 1

    def test_a_completed_founding_is_not_opened_again(self, old_gang, player, record):
        """Preserve completed founding rather than opening another activity."""
        gang = old_gang()
        with operation(gang, actor=player) as op:
            op.open_activity(FOUNDING)
        with operation(gang, actor=player) as op:
            op.close_activity(gang.open_activity(FOUNDING))

        run(record)

        assert gang.open_activity(FOUNDING) is None
        assert Activity.objects.filter(gang=gang, kind=FOUNDING).count() == 1

    def test_a_gang_that_gained_one_at_the_last_moment_is_counted(
        self, old_gang, record, monkeypatch
    ):
        """Treat the open-activity refusal as an already-completed repair if another
        transaction opened it before the gang lock was acquired.
        """
        from n26.core.operations import Operation as GangOperation
        from n26.core.operations import Refusal

        slipped_in = old_gang("Slipped In")
        plain = old_gang("Straightforward")
        really_open = GangOperation.open_activity

        def open_activity(self, kind, trade_points=None):
            if self.gang.pk == slipped_in.pk:
                raise Refusal(
                    "Complete the open Spend founding TP action before "
                    "starting another."
                )
            return really_open(self, kind, trade_points)

        monkeypatch.setattr(GangOperation, "open_activity", open_activity)

        run(record)

        assert record.status == Backfill.Status.DONE
        assert record.summary["failures"] == {}
        assert record.summary["totals"]["already_had_one"] == 1
        assert record.summary["totals"]["opened"] == 1
        assert plain.open_activity(FOUNDING) is not None

    def test_an_archived_gang_is_left_alone(self, old_gang, record):
        gang = old_gang()
        gang.archive()

        run(record)

        assert not Activity.objects.filter(gang=gang).exists()
        assert opened_events(gang) == 0


class TestTheRecord:
    """Persist final status and operation counts on the backfill record."""

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
        open_founding(found_gang("Founded Today", gang_type, owner=player, budget=1000))

        run(record)

        assert record.summary["totals"]["opened"] == 1
        assert record.summary["totals"]["already_had_one"] == 1

    def test_a_run_over_nothing_still_ends_done(
        self, gang_type, player, default_pack, record
    ):
        open_founding(found_gang("Founded Today", gang_type, owner=player, budget=1000))

        run(record)

        assert record.status == Backfill.Status.DONE
        assert "opened" not in record.summary["totals"]


class TestRunningItTwice:
    """Keep both explicit reruns and duplicate delivery idempotent."""

    def test_a_rerun_changes_nothing(self, old_gang, record):
        gang = old_gang()
        run(record)
        again = Backfill.objects.create(
            operation=Operation.OPEN_FOUNDING_ACTIONS,
            status=Backfill.Status.RUNNING,
            summary={"attempts": 0},
        )

        run(again)

        assert Activity.objects.filter(gang=gang, kind=FOUNDING).count() == 1
        assert opened_events(gang) == 1
        assert again.status == Backfill.Status.DONE
        assert again.summary["totals"]["already_had_one"] == 1
        assert "opened" not in again.summary["totals"]

    def test_a_redelivered_message_opens_nothing_more(
        self, old_gang, record, task_queue
    ):
        """An active run uses a single-flight lock, and a terminal backfill rejects another
        claim. Neither delivery path may open a second activity.
        """
        gang = old_gang()

        with task_queue.capture():
            open_founding_actions.enqueue(backfill_id=str(record.pk))
        task_queue.deliver_all()
        task_queue.redeliver_last()

        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE
        assert Activity.objects.filter(gang=gang, kind=FOUNDING).count() == 1
        assert opened_events(gang) == 1


class TestTheEstate:
    """Walk every unarchived gang rather than a shrinking eligible subset so the batch
    cursor remains stable.
    """

    def test_the_walk_counts_every_unarchived_gang(
        self, old_gang, gang_type, player, default_pack, record
    ):
        old_gang("Qualifies")
        open_founding(found_gang("Founded Today", gang_type, owner=player, budget=1000))
        archived = old_gang("Gone")
        archived.archive()

        run(record)

        assert record.summary["total"] == Gang.objects.filter(archived=False).count()
        assert record.summary["total"] == 2
