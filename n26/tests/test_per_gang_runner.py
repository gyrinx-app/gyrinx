"""Verify per-gang runner plans, refusals, reports and continuation. Record the initial
gang list once and resume it across deliveries so gangs created mid-run are excluded.
"""

from dataclasses import dataclass, field
from datetime import timedelta

import pytest

from gyrinx.maintenance.models import Backfill
from n26 import maintenance
from n26.core.models import Gang
from n26.maintenance import run_per_gang

pytestmark = pytest.mark.django_db

OPERATION = "n26_test_per_gang_runner"
LOCK_KEY = 999_826_032


@pytest.fixture(autouse=True)
def lock_key(monkeypatch):
    """Register a distinct operation lock for this runner fixture."""
    monkeypatch.setitem(maintenance.LOCK_KEYS, OPERATION, LOCK_KEY)


@pytest.fixture
def record(db):
    return Backfill.objects.create(
        operation=OPERATION,
        status=Backfill.Status.RUNNING,
    )


@pytest.fixture
def gangs(owner, gang_type):
    return [
        Gang.objects.create(name=f"Gang {n:02d}", owner=owner, gang_type=gang_type)
        for n in range(7)
    ]


@dataclass
class Plan:
    """Minimal per-gang plan contract: gang IDs, refusal reasons, an empty-plan flag and
    preview lines.
    """

    gangs: tuple = ()
    problems: tuple = ()
    nothing_here: bool = False
    said: list = field(default_factory=lambda: ["what the plan would do"])

    def preview(self):
        return list(self.said)


def run(record, find, apply_one, again=None, **kwargs):
    kwargs.setdefault("batch_size", 3)
    return run_per_gang(
        record.pk,
        operation=OPERATION,
        what="Per-gang runner under test",
        find=find,
        apply_one=apply_one,
        again=again or (lambda: None),
        **kwargs,
    )


class TestAPlanThatRefuses:
    def test_the_record_fails_in_the_plans_words_and_no_gang_is_touched(
        self, record, gangs
    ):
        plan = Plan(
            gangs=tuple((gang.pk, ()) for gang in gangs),
            problems=("gang 3 holds a pick nobody made",),
        )
        touched = []

        run(record, lambda: plan, touched.append)

        record.refresh_from_db()
        assert record.status == Backfill.Status.FAILED
        assert "gang 3 holds a pick nobody made" in record.error
        assert record.error.startswith("Per-gang runner under test cannot run")
        assert touched == []


class TestAPlanThatRaisesItsOwnRefusal:
    def test_the_callers_refusal_ends_the_record_in_its_words(self, record):
        class Refused(Exception):
            pass

        def find():
            raise Refused("the library is not the one the plan expects")

        run(record, find, lambda pk: None, refusals=(Refused,))

        record.refresh_from_db()
        assert record.status == Backfill.Status.FAILED
        assert record.error == "the library is not the one the plan expects"


class TestAPlanWithNothingToDo:
    def test_the_record_ends_done_with_the_preview(self, record):
        plan = Plan(nothing_here=True, said=["nothing left to move"])
        touched = []

        run(record, lambda: plan, touched.append)

        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE
        assert record.summary["report"] == ["nothing left to move"]
        assert touched == []


class TestAPlanOfGangs:
    def test_every_gang_is_visited_once_and_its_line_recorded(self, record, gangs):
        plan = Plan(gangs=tuple((gang.pk, ("some", "detail")) for gang in gangs))
        seen = []

        def apply_one(gang_id):
            seen.append(gang_id)
            return f"gang {gang_id}: settled"

        run(record, lambda: plan, apply_one)

        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE
        assert sorted(seen) == sorted(gang.pk for gang in gangs)
        assert len(set(seen)) == len(gangs)
        assert record.summary["gang_ids"] == [str(gang.pk) for gang in gangs]
        # The view records the preview separately; the report contains only completed
        # work.
        assert sorted(record.summary["report"]) == sorted(
            f"gang {gang.pk}: settled" for gang in gangs
        )
        assert record.summary["done"] == len(gangs)

    def test_a_gang_that_cannot_settle_is_recorded_and_the_rest_go_on(
        self, record, gangs
    ):
        plan = Plan(gangs=tuple((gang.pk, ()) for gang in gangs))
        bad = gangs[2].pk

        def apply_one(gang_id):
            if gang_id == bad:
                raise RuntimeError("its books do not reconcile")
            return f"gang {gang_id}: settled"

        run(record, lambda: plan, apply_one)

        record.refresh_from_db()
        assert record.status == Backfill.Status.FAILED
        assert list(record.summary["failures"]) == [str(bad)]
        assert record.summary["done"] == len(gangs) - 1


class TestASpentBudget:
    """Resume the recorded gang list from its saved cursor on every delivery."""

    def test_the_plan_is_read_once_and_later_deliveries_walk_the_same_list(
        self, record, gangs, owner, gang_type
    ):
        reads = []
        seen = []
        handed_back = []

        def find():
            reads.append(True)
            return Plan(gangs=tuple((gang.pk, ()) for gang in gangs))

        def deliver():
            run(
                record,
                find,
                seen.append,
                again=lambda: handed_back.append(True),
                budget=timedelta(0),
            )

        deliver()
        record.refresh_from_db()
        assert record.status == Backfill.Status.RUNNING
        assert len(seen) == 3

        # A newly created gang is outside the recorded plan, regardless of where its ID
        # sorts.
        late = Gang.objects.create(name="Latecomer", owner=owner, gang_type=gang_type)
        planned = list(gangs)
        gangs.append(late)

        while record.status == Backfill.Status.RUNNING:
            deliver()
            record.refresh_from_db()

        assert record.status == Backfill.Status.DONE
        assert len(reads) == 1
        assert late.pk not in seen
        assert sorted(seen) == sorted(gang.pk for gang in planned)
        assert len(set(seen)) == len(seen)
        assert handed_back
