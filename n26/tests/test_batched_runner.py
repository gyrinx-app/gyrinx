"""Verify resumable maintenance batches, cursor persistence, retry accounting and
cancellation. Each item commits independently, and follow-up deliveries start only after
releasing the run lock.
"""

from contextlib import contextmanager
from datetime import timedelta

import pytest
from django.contrib.auth.models import User

from gyrinx.maintenance.models import Backfill
from n26 import maintenance
from n26.maintenance import MAX_ATTEMPTS, _claim, run_batched

pytestmark = pytest.mark.django_db

OPERATION = "n26_test_batched_runner"
LOCK_KEY = 999_826_031


@pytest.fixture(autouse=True)
def lock_key(monkeypatch):
    """Register the test operation's advisory lock in the runner's lock registry."""
    monkeypatch.setitem(maintenance.LOCK_KEYS, OPERATION, LOCK_KEY)


@pytest.fixture
def record(db):
    return Backfill.objects.create(
        operation=OPERATION,
        status=Backfill.Status.RUNNING,
    )


@pytest.fixture
def rows(db):
    """Provide 25 uniquely ordered primary keys; the runner does not depend on the model
    type.
    """
    User.objects.bulk_create(
        User(username=f"batched-runner-row-{n:03d}") for n in range(25)
    )
    return User.objects.filter(username__startswith="batched-runner-row-")


def run(record, rows, do_one, again=None, **kwargs):
    kwargs.setdefault("batch_size", 10)
    return run_batched(
        record.pk,
        operation=OPERATION,
        what="Batched runner under test",
        items=rows,
        do_one=do_one,
        again=again or (lambda: None),
        **kwargs,
    )


class TestARunThatFits:
    """Complete all work in one delivery and record final counts."""

    def test_it_settles_everything_once_and_records_done(self, record, rows):
        seen = []
        run(record, rows, seen.append)

        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE
        assert record.summary["done"] == 25
        assert record.summary["total"] == 25
        assert record.summary["failures"] == {}
        assert sorted(seen) == sorted(rows.values_list("pk", flat=True))


class TestASpentBudget:
    """Persist progress before scheduling another delivery, without repeating completed
    items.
    """

    def test_the_rest_is_handed_to_fresh_deliveries_and_nothing_repeats(
        self, record, rows
    ):
        seen = []
        handed_back = []

        def deliver():
            run(
                record,
                rows,
                seen.append,
                again=lambda: handed_back.append(True),
                budget=timedelta(0),
            )

        deliver()
        record.refresh_from_db()
        assert record.status == Backfill.Status.RUNNING
        assert record.summary["done"] == 10
        assert record.summary["cursor"]

        while record.status == Backfill.Status.RUNNING:
            deliver()
            record.refresh_from_db()

        assert record.status == Backfill.Status.DONE
        assert len(seen) == 25
        assert len(set(seen)) == 25
        assert len(handed_back) == 2

    def test_the_fresh_delivery_is_summoned_only_after_the_lock_is_freed(
        self, record, rows, monkeypatch
    ):
        """Release the lock before enqueueing the continuation; otherwise it can skip a
        locked run and leave no delivery to finish it.
        """
        order = []
        real_lock = maintenance._single_flight

        @contextmanager
        def watched_lock(key):
            order.append("locked")
            with real_lock(key) as mine:
                yield mine
            order.append("unlocked")

        monkeypatch.setattr(maintenance, "_single_flight", watched_lock)
        run(
            record,
            rows,
            lambda pk: None,
            again=lambda: order.append("summoned"),
            budget=timedelta(0),
        )
        assert order == ["locked", "unlocked", "summoned"]


class TestAFailingRow:
    """Record item failures while continuing; clear an earlier failure when replay
    succeeds.
    """

    def test_it_is_recorded_and_the_rest_still_settle(self, record, rows):
        bad = sorted(rows.values_list("pk", flat=True))[12]
        seen = []

        def do_one(pk):
            if pk == bad:
                raise RuntimeError("this row is broken")
            seen.append(pk)

        run(record, rows, do_one)

        record.refresh_from_db()
        assert record.status == Backfill.Status.FAILED
        assert list(record.summary["failures"]) == [str(bad)]
        assert "1 of 25" in record.error
        assert record.summary["done"] == 24
        assert len(seen) == 24

    def test_a_row_that_settles_on_a_later_walk_is_struck_off(self, record, rows):
        """Clear a recorded failure when a replay succeeds so the run can finish DONE."""
        bad = sorted(rows.values_list("pk", flat=True))[3]
        Backfill.objects.filter(pk=record.pk).update(
            summary={"failures": {str(bad): "broke last time"}}
        )

        run(record, rows, lambda pk: None)

        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE
        assert record.summary["failures"] == {}


class TestCancel:
    """Observe cancellation between batches and preserve completed work."""

    def test_a_cancel_lands_between_batches_and_the_settled_stay_settled(
        self, record, rows
    ):
        seen = []

        def do_one(pk):
            seen.append(pk)
            if len(seen) == 12:
                Backfill.objects.filter(pk=record.pk).update(
                    status=Backfill.Status.CANCELLED
                )

        run(record, rows, do_one)

        record.refresh_from_db()
        assert record.status == Backfill.Status.CANCELLED
        assert len(seen) == 20

    def test_a_cancel_while_handed_back_stops_the_next_delivery_at_the_claim(
        self, record, rows
    ):
        """Reject the next delivery after cancellation while preserving the previous
        batch's work.
        """
        seen = []
        run(record, rows, seen.append, budget=timedelta(0))
        assert len(seen) == 10

        Backfill.objects.filter(pk=record.pk).update(status=Backfill.Status.CANCELLED)
        run(record, rows, seen.append, budget=timedelta(0))

        record.refresh_from_db()
        assert record.status == Backfill.Status.CANCELLED
        assert len(seen) == 10


class TestTheAttemptCount:
    """Reset attempt accounting on recorded progress and reject terminal runs."""

    def test_attempts_without_progress_exhaust_the_cap(self, record):
        for _attempt in range(MAX_ATTEMPTS):
            may_start, _ = _claim(record.pk)
            assert may_start
        may_start, why_not = _claim(record.pk)
        assert not may_start
        assert "without getting anywhere" in why_not

    def test_a_recorded_batch_starts_the_count_over(self, record, rows):
        """Recorded batch progress allows more deliveries than the no-progress attempt
        limit.
        """
        for _delivery in range(MAX_ATTEMPTS + 2):
            run(record, rows, lambda pk: None, budget=timedelta(0))
            record.refresh_from_db()
            if record.status != Backfill.Status.RUNNING:
                break
        assert record.status == Backfill.Status.DONE

    def test_a_record_already_ended_refuses_the_claim(self, record):
        Backfill.objects.filter(pk=record.pk).update(status=Backfill.Status.DONE)
        may_start, why_not = _claim(record.pk)
        assert not may_start
        assert "already" in why_not


class TestACallableWorkList:
    """Evaluate callable work lists under the run lock and retain item report lines. A
    callable may refuse work or record a terminal result itself.
    """

    def test_it_is_read_under_the_lock_and_walked(self, record, rows, monkeypatch):
        order = []
        real_lock = maintenance._single_flight

        @contextmanager
        def watched_lock(key):
            order.append("locked")
            with real_lock(key) as mine:
                yield mine

        def work_list():
            order.append("read")
            return rows

        monkeypatch.setattr(maintenance, "_single_flight", watched_lock)
        seen = []
        run(record, work_list, seen.append)

        record.refresh_from_db()
        assert order == ["locked", "read"]
        assert record.status == Backfill.Status.DONE
        assert len(seen) == 25

    def test_a_refusal_ends_the_record_failed_in_its_own_words(self, record):
        class Refused(Exception):
            pass

        def refuse():
            raise Refused("the world is not the one the plan described")

        run(record, refuse, lambda pk: None, refusals=(Refused,))

        record.refresh_from_db()
        assert record.status == Backfill.Status.FAILED
        assert record.error == "the world is not the one the plan described"

    def test_nothing_to_walk_leaves_the_ending_the_work_list_wrote(self, record):
        def nothing():
            Backfill.objects.filter(pk=record.pk).update(
                status=Backfill.Status.DONE, summary={"report": ["nothing here"]}
            )
            return None

        touched = []
        run(record, nothing, touched.append)

        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE
        assert record.summary == {"report": ["nothing here"]}
        assert touched == []

    def test_nothing_to_walk_with_no_ending_written_fails_the_record(self, record):
        """Fail a callable that returns no work without recording a terminal state."""
        run(record, lambda: None, lambda pk: None)

        record.refresh_from_db()
        assert record.status == Backfill.Status.FAILED
        assert "wrote no ending" in record.error

    def test_what_a_row_says_is_a_line_of_the_report(self, record, rows):
        def say(pk):
            return f"row {pk}: settled"

        run(record, rows, say, budget=timedelta(0))
        record.refresh_from_db()
        assert record.status == Backfill.Status.RUNNING
        assert len(record.summary["report"]) == 10

        while record.status == Backfill.Status.RUNNING:
            run(record, rows, say, budget=timedelta(0))
            record.refresh_from_db()

        assert record.status == Backfill.Status.DONE
        assert len(record.summary["report"]) == 25
        assert all(line.endswith(": settled") for line in record.summary["report"])
