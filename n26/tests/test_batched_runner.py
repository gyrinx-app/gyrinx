"""The batched runner: large work as many short, resumable deliveries.

``run_batched`` walks an ordered work-list committing each row alone,
writes its position onto the ``Backfill`` record as it goes, and picks
up from that position on the next delivery. Proven here with a plain
work-list and a recording ``do_one``: a run finishes and records DONE;
a spent budget hands the rest to a fresh delivery and nothing is done
twice; a failing row is recorded and stepped past; a cancel between
batches stops the run where it stands; and the attempt count forgives
deliveries that moved the cursor while refusing ones stuck in place.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User

from gyrinx.maintenance.models import Backfill
from n26.maintenance import MAX_ATTEMPTS, _claim_batched, run_batched

pytestmark = pytest.mark.django_db

LOCK_KEY = 999_826_031


@pytest.fixture
def record(db):
    return Backfill.objects.create(
        operation="n26_test_batched_runner",
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
        lock_key=LOCK_KEY,
        what="Batched runner under test",
        items=rows,
        do_one=do_one,
        again=again or (lambda: None),
        **kwargs,
    )


class TestARunThatFits:
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
    def test_the_rest_is_handed_to_fresh_deliveries_and_nothing_repeats(
        self, record, rows
    ):
        """A zero budget ends every attempt after its first batch, so
        the run only finishes if each delivery continues exactly where
        the last one stopped."""
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


class TestAFailingRow:
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
        assert record.summary["done"] == 25
        assert len(seen) == 24


class TestCancel:
    def test_a_cancel_lands_between_batches_and_the_settled_stay_settled(
        self, record, rows
    ):
        """The operator cancels while a batch is mid-flight; the next
        progress write is refused and the run stops where it stands,
        keeping the ending the operator wrote."""
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
    def test_a_moved_cursor_forgives_and_a_stuck_one_exhausts(self, record):
        for _attempt in range(MAX_ATTEMPTS):
            may_start, _ = _claim_batched(record.pk)
            assert may_start
        may_start, why_not = _claim_batched(record.pk)
        assert not may_start
        assert "same place" in why_not

        Backfill.objects.filter(pk=record.pk).update(
            summary={**record.summary, "cursor": "somewhere-new", "attempts": 99}
        )
        record.refresh_from_db()
        may_start, _ = _claim_batched(record.pk)
        assert may_start
        record.refresh_from_db()
        assert record.summary["attempts"] == 1

    def test_a_record_already_ended_refuses_the_claim(self, record):
        Backfill.objects.filter(pk=record.pk).update(status=Backfill.Status.DONE)
        may_start, why_not = _claim_batched(record.pk)
        assert not may_start
        assert "already" in why_not
