"""The batched runner: large work as many short, resumable deliveries.

``run_batched`` walks an ordered work-list committing each row alone,
writes its position onto the ``Backfill`` record after every batch, and
picks up from that position on the next delivery. Proven here with a
plain work-list and a recording ``do_one``: a run finishes and records
DONE; a spent budget hands the rest to a fresh delivery — after the
lock is released — and nothing is done twice; a failing row is recorded
and stepped past, and struck off if a later walk settles it; a cancel
between batches stops the run where it stands; and the attempt count is
reset by every recorded batch, so only attempts that die before getting
anywhere exhaust it.
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
    """The runner looks its lock up in the one auditable registry, so
    the test operation registers its key there like any real one."""
    monkeypatch.setitem(maintenance.LOCK_KEYS, OPERATION, LOCK_KEY)


@pytest.fixture
def record(db):
    return Backfill.objects.create(
        operation=OPERATION,
        status=Backfill.Status.RUNNING,
    )


@pytest.fixture
def rows(db):
    """Twenty-five rows with unique, orderable primary keys. Any table
    serves; the runner only ever reads pks."""
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
    """One delivery is enough: everything settles once and the record
    ends DONE with the counts telling the whole story."""

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
    """An attempt past its budget records the cursor and summons a
    fresh delivery, which continues exactly where it stopped — so the
    run finishes without any row being settled twice."""

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
        """The delivery the hand-back summons must never find the lock
        still held — it would stand down, acknowledge its message, and
        leave the record RUNNING with nothing left to finish it."""
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
    """A broken row is written down and stepped past — and struck off
    again if a later walk settles it."""

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
        """A crash can replay a batch whose failure was already
        recorded; the replay settling the row must clear the entry, or
        the run ends FAILED over a row that is actually fine."""
        bad = sorted(rows.values_list("pk", flat=True))[3]
        Backfill.objects.filter(pk=record.pk).update(
            summary={"failures": {str(bad): "broke last time"}}
        )

        run(record, rows, lambda pk: None)

        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE
        assert record.summary["failures"] == {}


class TestCancel:
    """An operator's cancel is an ending, endings are final, and the
    run finds out at its next progress write — stopping where it
    stands, with everything already settled staying settled."""

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


class TestTheAttemptCount:
    """``_claim`` serves both run shapes: every recorded batch resets
    the count, so only attempts dying before any progress exhaust it,
    and a record that has ended refuses the claim outright."""

    def test_attempts_without_progress_exhaust_the_cap(self, record):
        for _attempt in range(MAX_ATTEMPTS):
            may_start, _ = _claim(record.pk)
            assert may_start
        may_start, why_not = _claim(record.pk)
        assert not may_start
        assert "without getting anywhere" in why_not

    def test_a_recorded_batch_starts_the_count_over(self, record, rows):
        """A long run is many deliveries; each one claims afresh, and
        the progress its predecessor recorded is what keeps the run
        from reading as stuck."""
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
