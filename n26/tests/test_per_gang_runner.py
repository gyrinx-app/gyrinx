"""The per-gang runner: a gang-by-gang repair as many short deliveries.

``run_per_gang`` reads a plan once, under the lock, and walks its gangs
through the batched runner: each gang settles on its own commit, its
line lands on the record's report, and a spent budget hands the rest to
a fresh delivery that walks the same list. Proven here with a plan
built by hand over real gangs: a plan with problems refuses and touches
nothing; a plan with nothing to do ends DONE with its preview; a plan
of gangs is walked once with every gang's line recorded; and the plan
is read exactly once, so a gang appearing mid-run is not visited by
this run.
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
def gangs(owner, gang_type):
    return [
        Gang.objects.create(name=f"Gang {n:02d}", owner=owner, gang_type=gang_type)
        for n in range(7)
    ]


@dataclass
class Plan:
    """The shape every gang-by-gang plan shares: gangs to visit, problems
    that refuse the run, and whether there is anything to do."""

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
        assert record.summary["report"][0] == "what the plan would do"
        assert sorted(record.summary["report"][1:]) == sorted(
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
    """The plan is read once and its gangs recorded; every later delivery
    walks that list from where the last one stopped."""

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

        # A gang appearing after the plan was read belongs to the next
        # run, not this one: where it fell against the cursor would
        # depend on nothing but its id.
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
