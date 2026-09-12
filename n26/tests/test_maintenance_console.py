"""This edition's repairs, as the maintenance console offers them.

A seam test: the console is the platform's, the repair is ours, and what
is proven here is that the two meet — the operation is registered and
gated, the page shows the plan without writing, applying records what
happened, and a repair that has been run keeps its name without keeping
its page.

Each repair's own discipline is proven beside it; this file cares only
about the door it is triggered through.
"""

import ast
import importlib
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.maintenance.models import Backfill
from gyrinx.maintenance.registry import (
    all_operations,
    operation_label,
    operations,
    resolve_operation,
)
from n26 import maintenance
from n26.core.reconcile import assert_reconciled
from n26.maintenance import (
    LOCK_KEYS,
    ONE_ATTEMPT_DEADLINE,
    Operation,
    clear_item_restrictions_view,
    convert_chaos_god_view,
    convert_outcast_affiliation_view,
    convert_variant_view,
    delete_empty_affiliations_view,
    delete_legacy_affiliation_assignments_view,
    delete_nameless_gang_type_view,
    open_founding_actions_view,
    order_collections_view,
    task_routes,
)

pytestmark = pytest.mark.django_db


def _is_atomic(call):
    """``transaction.atomic(...)`` or a bare ``atomic(...)``."""
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr == "atomic"
    return isinstance(func, ast.Name) and func.id == "atomic"


def _is_atomic_decorator(decorator):
    """``@transaction.atomic``, ``@atomic``, or either called."""
    if isinstance(decorator, ast.Call):
        return _is_atomic(decorator)
    if isinstance(decorator, ast.Attribute):
        return decorator.attr == "atomic"
    return isinstance(decorator, ast.Name) and decorator.id == "atomic"


def _opens_a_transaction(function):
    """True when the function begins a transaction of its own — as a
    decorator, or as a ``with`` anywhere in its body."""
    if any(_is_atomic_decorator(d) for d in function.decorator_list):
        return True
    return any(
        isinstance(node, ast.With)
        and any(_is_atomic(item.context_expr) for item in node.items)
        for node in ast.walk(function)
    )


LOOPS = (
    ast.For,
    ast.While,
    ast.AsyncFor,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


def commits_row_by_row(module_name):
    """Whether any loop in the module commits per iteration — directly,
    or by calling a function of the module that opens its own
    transaction. That is the batched shape, and a run of it under the
    one-transaction runner has no budget and no cursor."""
    module = importlib.import_module(module_name)
    here = Path(module.__file__)
    # A package is read whole: the conversions live in its files, not
    # in the file that names it.
    files = sorted(here.parent.rglob("*.py")) if here.name == "__init__.py" else [here]
    trees = [ast.parse(path.read_text()) for path in files]
    functions = [
        node
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    owners = {fn.name for fn in functions if _opens_a_transaction(fn)}
    for tree in trees:
        for loop in ast.walk(tree):
            if not isinstance(loop, LOOPS):
                continue
            for node in ast.walk(loop):
                if isinstance(node, ast.With) and any(
                    _is_atomic(item.context_expr) for item in node.items
                ):
                    return True
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in owners
                ):
                    return True
    return False


def _calls(function):
    return {
        call.func.id
        for call in ast.walk(function)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }


def tasks_run_in_one_transaction():
    """Every function in ``n26/maintenance.py`` that calls the
    one-transaction runner itself, with the modules it imports to do so.
    Discovered from the source, so a new task is checked without anyone
    listing it. A task that reaches the runner through a wrapper is
    covered by the wrapper's own entry. A function calling the runner
    with no import of its own is listed with no modules, so the check
    fails on it rather than passing it by."""
    tree = ast.parse(Path(maintenance.__file__).read_text())
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if "_run_recorded" not in _calls(node):
            continue
        modules = tuple(
            imported.module
            for imported in ast.walk(node)
            if isinstance(imported, ast.ImportFrom) and imported.module
        )
        found.append((node.name, modules))
    return found


def one_transaction_route_names():
    """The routed task names that end in the one-transaction runner,
    directly or through a wrapper."""
    tree = ast.parse(Path(maintenance.__file__).read_text())
    functions = {
        node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    reaches = {}

    def reaches_runner(name, seen=()):
        if name in reaches:
            return reaches[name]
        function = functions.get(name)
        if function is None or name in seen:
            return False
        calls = _calls(function)
        answer = "_run_recorded" in calls or any(
            reaches_runner(called, (*seen, name)) for called in calls
        )
        reaches[name] = answer
        return answer

    return {route.name for route in task_routes if reaches_runner(route.name)}


class TestTheRunnerDiscipline:
    """A run through the one-transaction runner must finish inside one
    delivery. A repair that walks gangs and commits each on its own has
    outgrown that runner however few gangs it names today: a gang's
    proof is many queries, and the plan on the day it is run is not the
    plan on the day it was written. Such repairs go through
    ``run_per_gang``, whose budget hands the rest to a fresh delivery."""

    def test_there_is_something_to_check(self):
        assert tasks_run_in_one_transaction()
        assert one_transaction_route_names()
        assert task_routes

    @pytest.mark.parametrize(
        "task_name,modules",
        tasks_run_in_one_transaction(),
        ids=lambda value: value if isinstance(value, str) else "",
    )
    def test_no_one_transaction_task_commits_gang_by_gang(self, task_name, modules):
        assert modules, (
            f"{task_name} calls _run_recorded but imports nothing inside the "
            "function, so what it runs cannot be read from here. Import the "
            "repair's module inside the task, as the other tasks do."
        )
        offenders = [name for name in modules if commits_row_by_row(name)]
        assert not offenders, (
            f"{task_name} runs through _run_recorded but {', '.join(offenders)} "
            "commits inside a loop. Route it through run_per_gang (or "
            "run_batched), which records how far it got and hands the rest "
            "to a fresh delivery before the acknowledgement deadline."
        )

    def test_the_guard_reads_the_shapes_it_is_for(self):
        """The guard is only worth having if it tells the two shapes
        apart: a module that commits inside a loop, and one that holds
        everything inside one transaction."""
        assert commits_row_by_row("n26.core.legacy_affiliation_assignments")
        assert commits_row_by_row("n26.core.rehost_picks")
        assert not commits_row_by_row("n26.library.empty_affiliations")
        assert not commits_row_by_row("n26.library.conversion")

    def test_every_route_declares_the_one_attempt_deadline(self):
        """The warning ``_run_recorded`` writes is measured against this
        constant, so a route with a different deadline would be judged
        against the wrong clock. Every routed task that ends in the
        one-transaction runner is checked, wrappers followed."""
        seconds = int(ONE_ATTEMPT_DEADLINE.total_seconds())
        one_transaction = one_transaction_route_names()
        assert len(one_transaction) > 2
        astray = [
            route.name
            for route in task_routes
            if route.name in one_transaction and route.ack_deadline != seconds
        ]
        assert not astray, (
            f"{', '.join(astray)}: ack_deadline is not {seconds}s. Change "
            "ONE_ATTEMPT_DEADLINE with it, or the run-time warning is measured "
            "against the wrong clock."
        )

    def test_a_long_one_transaction_run_is_written_up_on_its_record(self, monkeypatch):
        operation = Operation.DELETE_EMPTY_AFFILIATIONS
        record = Backfill.objects.create(
            operation=operation.value, status=Backfill.Status.RUNNING
        )
        # The runner reads the clock through its own module, so only it
        # sees a run that took most of the deadline; the record's own
        # timestamps keep the real clock.
        start = maintenance.timezone.now()
        reads = []

        class SlowClock:
            @staticmethod
            def now():
                reads.append(True)
                if len(reads) == 1:
                    return start
                return start + ONE_ATTEMPT_DEADLINE * 0.9

        monkeypatch.setattr(maintenance, "timezone", SlowClock)

        maintenance._run_recorded(
            record.pk, operation, "A slow repair", lambda: ["done"], ()
        )

        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE
        assert record.summary["report"] == ["done"]
        assert record.summary["seconds"] == 540
        assert "540 of the 600 seconds" in record.summary["warning"]
        assert "run_per_gang" in record.summary["warning"]

    def test_a_per_gang_record_page_reads_as_progress_until_it_is_done(
        self, client, superuser
    ):
        """A gang-by-gang run commits as it goes, so its page says what
        it has done so far while it runs, and only calls that the whole
        of what it did once it has ended."""
        client.force_login(superuser)
        record = Backfill.objects.create(
            operation=Operation.REPAIR_DOUBLED_REFUNDS.value,
            status=Backfill.Status.RUNNING,
            summary={
                "preview": ["gang 1: drop 2 surplus events"],
                "report": ["gang 1: dropped 2 events; credits now 990"],
                "done": 1,
                "total": 3,
                "attempts": 1,
            },
        )
        address = reverse("admin:maintenance_backfill_detail", args=[record.id])

        page = client.get(address).content.decode()
        assert "What it has done so far" in page
        assert "1 of 3 gangs settled" in page
        assert "gang 1: dropped 2 events" in page

        Backfill.objects.filter(pk=record.pk).update(status=Backfill.Status.DONE)
        page = client.get(address).content.decode()
        assert "What it did" in page
        assert "What it has done so far" not in page

    def test_a_quick_one_transaction_run_records_only_how_long_it_took(self):
        operation = Operation.DELETE_EMPTY_AFFILIATIONS
        record = Backfill.objects.create(
            operation=operation.value, status=Backfill.Status.RUNNING
        )

        maintenance._run_recorded(
            record.pk, operation, "A quick repair", lambda: ["done"], ()
        )

        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE
        assert record.summary["seconds"] == 0
        assert "warning" not in record.summary


class TestTheCollectionOrdering:
    """The repair that sinks the variant equipment lists: every
    collection on the page with how it reaches a card, one column
    written, one transaction."""

    @pytest.fixture
    def variant_world(self, default_pack):
        """A house list a gang type grants, and a variant's list a pick
        of a slot type that is not a gang archetype grants."""
        from n26.library.authoring import (
            create_collection,
            create_gang_type,
            create_pickable,
            create_slot_type,
            ef_adds,
            modifier,
            targets_every_model,
        )

        house = create_collection("Escher Equipment List")
        escher = create_gang_type("Escher")
        modifier(
            "Escher: its fighters buy from the Escher list",
            targets_every_model(),
            ef_adds(house),
            attach_to=escher,
        )
        variant = create_collection("Chaos Corrupted Equipment List")
        corrupted = create_pickable("Chaos Corrupted", create_slot_type("Variant"))
        modifier(
            "Chaos Corrupted: its fighters buy from the Chaos Corrupted list",
            targets_every_model(),
            ef_adds(variant),
            attach_to=corrupted,
        )
        return {"house": house, "variant": variant}

    def test_its_lock_is_not_shared(self):
        keys = list(LOCK_KEYS.values())
        assert len(keys) == len(set(keys))
        assert LOCK_KEYS[Operation.ORDER_COLLECTIONS] == 826_020_625
        assert Operation.ORDER_COLLECTIONS.value == "n26_order_collections"

    def test_the_operation_is_registered_and_named(self):
        registered = {op.operation for op in operations()}

        assert Operation.ORDER_COLLECTIONS.value in registered
        found = resolve_operation(Operation.ORDER_COLLECTIONS.value)
        assert found.name == Operation.ORDER_COLLECTIONS.label
        assert found.view is order_collections_view

    def test_only_a_superuser_may_reach_it(self, client, staffer):
        client.force_login(staffer)

        response = client.get(reverse("admin:maintenance_n26_order_collections"))

        assert response.status_code in (302, 403)

    def test_its_page_lists_every_collection_and_writes_nothing(
        self, client, superuser, variant_world
    ):
        client.force_login(superuser)

        response = client.get(reverse("admin:maintenance_n26_order_collections"))

        page = response.content.decode()
        assert response.status_code == 200
        assert "Escher Equipment List" in page
        assert "granted by gang type Escher" in page
        assert "Chaos Corrupted Equipment List" in page
        assert "granted by pickable Chaos Corrupted (Variant)" in page
        assert "set to 100" in page
        assert "1 list would be set to 100" in page
        assert "Set position 100 on the variant lists" in page
        assert not Backfill.objects.exists()
        variant_world["variant"].refresh_from_db()
        assert variant_world["variant"].position == 0

    def test_applying_records_what_it_set(self, client, superuser, variant_world):
        client.force_login(superuser)

        response = client.post(reverse("admin:maintenance_n26_order_collections"))

        assert response.status_code == 302
        run = Backfill.objects.get(operation=Operation.ORDER_COLLECTIONS)
        assert run.status == Backfill.Status.DONE
        assert run.triggered_by == superuser
        assert run.summary["preview"] == [
            "Chaos Corrupted Equipment List (N26): granted by pickable "
            "Chaos Corrupted (Variant) — set to 100"
        ]
        assert run.summary["report"] == [
            "Chaos Corrupted Equipment List (N26): set to 100",
            "Set 1 list.",
        ]
        variant_world["variant"].refresh_from_db()
        variant_world["house"].refresh_from_db()
        assert variant_world["variant"].position == 100
        assert variant_world["house"].position == 0

        page = client.get(response["Location"]).content.decode()
        assert "What it did" in page
        assert "Chaos Corrupted Equipment List (N26): set to 100" in page

    def test_its_page_says_when_there_is_nothing_to_set(
        self, client, superuser, variant_world
    ):
        from n26.library.models import Collection

        Collection.objects.filter(pk=variant_world["variant"].pk).update(position=100)
        client.force_login(superuser)

        page = client.get(reverse("admin:maintenance_n26_order_collections"))
        assert "Nothing to set" in page.content.decode()
        assert "left at 100, already set" in page.content.decode()

        response = client.post(reverse("admin:maintenance_n26_order_collections"))
        assert response.status_code == 302
        assert not Backfill.objects.exists()


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser("boss", "boss@example.com", "password")


@pytest.fixture
def staffer(db):
    return User.objects.create_user(
        "clerk", "clerk@example.com", "password", is_staff=True
    )


class TestARepairThatHasBeenRun:
    """A repair whose work cannot recur keeps its slug and loses its
    page. The slug is what a historical record carries, so dropping the
    registration would leave old runs reading as a bare slug."""

    RETIRED = (
        Operation.CONVERT_SPECIALISATION,
        Operation.CONVERT_SKILL_TREE,
        Operation.CONVERT_GANG_LEGACY,
        Operation.RETIRE_GANG_LEGACY_PILOT,
        Operation.CONVERT_ARCHETYPE,
        Operation.SWEEP_ARCHIVED,
        Operation.CLEAR_SPARE_ANSWERS,
        Operation.DELETE_RETIRED_KINDS,
        Operation.MERGE_WARGEAR_INTO_WEAPON,
    )

    def test_there_is_something_to_check(self):
        assert self.RETIRED

    @pytest.mark.parametrize("operation", RETIRED, ids=lambda op: op.value)
    def test_its_record_still_reads_as_a_name(self, operation):
        assert operation_label(operation.value) == operation.label
        assert operation.value in {op.operation for op in all_operations()}

    @pytest.mark.parametrize("operation", RETIRED, ids=lambda op: op.value)
    def test_it_is_no_longer_offered_or_reachable(self, operation):
        assert operation.value not in {op.operation for op in operations()}
        assert resolve_operation(operation.value).view is None

    def test_a_run_of_one_still_names_itself_on_the_console(self, client, superuser):
        """The reason the slug stays: the index lists past runs, and a
        retired repair's run must not read as a bare slug."""
        Backfill.objects.create(operation=Operation.SWEEP_ARCHIVED.value)
        client.force_login(superuser)

        page = client.get(reverse("admin:maintenance_index")).content.decode()

        assert Operation.SWEEP_ARCHIVED.label in page


class TestTheNamelessGangTypeRetirement:
    """The repair still on offer: an empty-named gang type an ingest
    founded from a blank Gang cell, the gang of nothing founded on it,
    and — where somebody played one — a repoint instead."""

    @pytest.fixture
    def nameless_world(self, owner, default_pack):
        from n26.library.models import GangType
        from n26.tests.sandbox.actions import create_gang_type, found_gang

        nameless = GangType.objects.create(name="")
        create_gang_type("Escher", starting_credits=1000)
        return found_gang("A Gang Of Nothing", nameless, owner=owner)

    def test_the_operation_is_registered_and_named(self):
        registered = {op.operation for op in operations()}

        assert Operation.DELETE_NAMELESS_GANG_TYPE.value in registered
        found = resolve_operation(Operation.DELETE_NAMELESS_GANG_TYPE.value)
        assert found.name == Operation.DELETE_NAMELESS_GANG_TYPE.label
        assert found.view is delete_nameless_gang_type_view

    def test_only_a_superuser_may_reach_it(self, client, staffer):
        client.force_login(staffer)

        response = client.get(
            reverse("admin:maintenance_n26_delete_nameless_gang_type")
        )

        assert response.status_code in (302, 403)

    def test_a_stranger_is_sent_to_the_login(self, client):
        response = client.get(
            reverse("admin:maintenance_n26_delete_nameless_gang_type")
        )

        assert response.status_code in (302, 401, 403)

    def test_its_page_shows_the_plan_and_writes_nothing(
        self, client, superuser, nameless_world
    ):
        from n26.library.models import GangType

        client.force_login(superuser)

        response = client.get(
            reverse("admin:maintenance_n26_delete_nameless_gang_type")
        )

        page = response.content.decode()
        assert response.status_code == 200
        assert "delete 1 untouched gang founded on a nameless type" in page
        assert not Backfill.objects.exists()
        assert GangType.objects.filter(name="").exists()

    def test_applying_records_what_it_retired(self, client, superuser, nameless_world):
        from n26.core.models import Gang
        from n26.library.models import GangType

        client.force_login(superuser)

        response = client.post(
            reverse("admin:maintenance_n26_delete_nameless_gang_type")
        )

        assert response.status_code == 302
        run = Backfill.objects.get(operation=Operation.DELETE_NAMELESS_GANG_TYPE)
        assert run.status == Backfill.Status.DONE
        assert any("deleted" in line for line in run.summary["report"])
        assert not GangType.objects.filter(name="").exists()
        assert not Gang.objects.filter(pk=nameless_world.pk).exists()
        assert GangType.objects.filter(name="Escher").exists()

    def test_a_played_gang_is_repointed_rather_than_deleted(
        self, client, superuser, nameless_world, person_type
    ):
        """The whole point of the operation running at all: a gang
        somebody has played keeps everything, and stops naming nothing."""
        from n26.core.models import Gang
        from n26.library.models import GangType
        from n26.tests.sandbox.actions import create_profile, hire

        escher = GangType.objects.get(name="Escher")
        profile = create_profile("Ganger", person_type, escher, price=50)
        hire(nameless_world, profile, "Somebody At All", paid=50)
        client.force_login(superuser)

        client.post(reverse("admin:maintenance_n26_delete_nameless_gang_type"))

        run = Backfill.objects.get(operation=Operation.DELETE_NAMELESS_GANG_TYPE)
        assert run.status == Backfill.Status.DONE
        assert Gang.objects.get(pk=nameless_world.pk).gang_type_id == escher.pk
        assert not GangType.objects.filter(name="").exists()
        assert_reconciled(Gang.objects.get(pk=nameless_world.pk))

    def test_a_gang_nobody_can_read_stops_the_type_going(
        self, client, superuser, nameless_world, person_type
    ):
        """Two lists in one gang and nobody can say what it is, so the
        gang and the type it names are both left standing."""
        from n26.core.models import Gang
        from n26.library.models import GangType
        from n26.tests.sandbox.actions import create_gang_type, create_profile, hire

        for house in ("Escher", "Goliath"):
            gang_type = GangType.objects.filter(name=house).first() or create_gang_type(
                house, starting_credits=1000
            )
            hire(
                nameless_world,
                create_profile(f"{house} Ganger", person_type, gang_type, price=50),
                f"From {house}",
                paid=50,
            )
        client.force_login(superuser)

        client.post(reverse("admin:maintenance_n26_delete_nameless_gang_type"))

        run = Backfill.objects.get(operation=Operation.DELETE_NAMELESS_GANG_TYPE)
        assert run.status == Backfill.Status.DONE
        assert GangType.objects.filter(name="").exists()
        assert Gang.objects.get(pk=nameless_world.pk).gang_type.name == ""
        assert_reconciled(Gang.objects.get(pk=nameless_world.pk))


class TestTheOutcastAffiliationConversion:
    """The repair still on offer: the Outcast affiliations become picks."""

    def test_the_operation_is_registered_and_named(self):
        registered = {op.operation for op in operations()}

        assert Operation.CONVERT_OUTCAST_AFFILIATION.value in registered
        found = resolve_operation(Operation.CONVERT_OUTCAST_AFFILIATION.value)
        assert found.name == Operation.CONVERT_OUTCAST_AFFILIATION.label
        assert found.view is convert_outcast_affiliation_view

    def test_proof_words_count_holders_when_the_plan_omits_reaches(self):
        """The confirm dialog must not say “0 gangs” just because a
        future conversion leaves ``Plan.reaches`` at its default."""
        from n26.library.conversion.base import Plan
        from n26.maintenance import _proof_words

        words = _proof_words(
            Plan(
                system="outcast_affiliation",
                holder_ids=(1, 2, 3),
                gang_ids=(1,),
            )
        )

        assert "It reaches 3 gangs" in words["reach_words"]
        assert "Convert 3 gang(s)" in words["confirm_words"]
        assert "0 gang" not in words["reach_words"]
        assert "0 gang" not in words["confirm_words"]

    def test_only_a_superuser_may_reach_it(self, client, staffer):
        client.force_login(staffer)

        response = client.get(
            reverse("admin:maintenance_n26_convert_outcast_affiliation")
        )

        assert response.status_code in (302, 403)

    def test_its_page_shows_nothing_to_convert_when_the_system_is_absent(
        self, client, superuser, default_pack
    ):
        client.force_login(superuser)

        response = client.get(
            reverse("admin:maintenance_n26_convert_outcast_affiliation")
        )

        page = response.content.decode()
        assert response.status_code == 200
        assert "Nothing to convert" in page
        assert not Backfill.objects.exists()

    def test_its_page_shows_the_plan_and_writes_nothing(
        self, client, superuser, default_pack, person_type, owner
    ):
        from n26.tests.sandbox.test_conversion_affiliation import (
            build_prod_shape,
            build_world,
        )

        build_world(build_prod_shape(person_type), owner)
        client.force_login(superuser)

        response = client.get(
            reverse("admin:maintenance_n26_convert_outcast_affiliation")
        )

        page = response.content.decode()
        assert response.status_code == 200
        assert "create slot type “Affiliation”" in page
        assert not Backfill.objects.exists()

    def test_applying_records_what_it_converted(
        self, client, superuser, default_pack, person_type, owner
    ):
        from n26.library.models import Pickable, Slot
        from n26.tests.sandbox.test_conversion_affiliation import (
            build_prod_shape,
            build_world,
        )

        build_world(build_prod_shape(person_type), owner)
        client.force_login(superuser)

        response = client.post(
            reverse("admin:maintenance_n26_convert_outcast_affiliation")
        )

        assert response.status_code == 302
        run = Backfill.objects.get(operation=Operation.CONVERT_OUTCAST_AFFILIATION)
        assert run.status == Backfill.Status.DONE
        assert any("applied" in line for line in run.summary["report"])
        assert Slot.objects.filter(name="Affiliation").exists()
        assert Pickable.objects.filter(
            name="Clanless Outcast", slot_type__name="Affiliation"
        ).exists()


class TestTheChaosGodConversion:
    """The repair still on offer: the Chaos Gods become picks."""

    def test_its_lock_is_not_shared(self):
        keys = list(LOCK_KEYS.values())
        assert len(keys) == len(set(keys))
        assert (
            LOCK_KEYS[Operation.CONVERT_CHAOS_GOD]
            != LOCK_KEYS[Operation.REPAIR_DOUBLED_REFUNDS]
        )

    def test_the_operation_is_registered_and_named(self):
        registered = {op.operation for op in operations()}

        assert Operation.CONVERT_CHAOS_GOD.value in registered
        found = resolve_operation(Operation.CONVERT_CHAOS_GOD.value)
        assert found.name == Operation.CONVERT_CHAOS_GOD.label
        assert found.view is convert_chaos_god_view

    def test_it_is_not_retired(self):
        assert Operation.CONVERT_CHAOS_GOD not in TestARepairThatHasBeenRun.RETIRED
        assert resolve_operation(Operation.CONVERT_CHAOS_GOD.value).view is not None

    def test_only_a_superuser_may_reach_it(self, client, staffer):
        client.force_login(staffer)

        response = client.get(reverse("admin:maintenance_n26_convert_chaos_god"))

        assert response.status_code in (302, 403)

    def test_its_page_shows_nothing_to_convert_when_the_system_is_absent(
        self, client, superuser, default_pack
    ):
        client.force_login(superuser)

        response = client.get(reverse("admin:maintenance_n26_convert_chaos_god"))

        page = response.content.decode()
        assert response.status_code == 200
        assert "Nothing to convert" in page
        assert not Backfill.objects.exists()

    def test_its_page_shows_the_plan_and_writes_nothing(
        self, client, superuser, default_pack, owner
    ):
        from n26.tests.sandbox.test_conversion_chaos_god import (
            build_prod_shape,
            build_world,
        )

        build_world(build_prod_shape(), owner)
        client.force_login(superuser)

        response = client.get(reverse("admin:maintenance_n26_convert_chaos_god"))

        page = response.content.decode()
        assert response.status_code == 200
        assert "create slot type “Chaos God”" in page
        assert not Backfill.objects.exists()

    def test_applying_records_what_it_converted(
        self, client, superuser, default_pack, owner
    ):
        from n26.library.models import Pickable, Slot
        from n26.tests.sandbox.test_conversion_chaos_god import (
            build_prod_shape,
            build_world,
        )

        build_world(build_prod_shape(), owner)
        client.force_login(superuser)

        response = client.post(reverse("admin:maintenance_n26_convert_chaos_god"))

        assert response.status_code == 302
        run = Backfill.objects.get(operation=Operation.CONVERT_CHAOS_GOD)
        assert run.status == Backfill.Status.DONE
        assert any("applied" in line for line in run.summary["report"])
        assert Slot.objects.filter(name="Chaos God").count() == 2
        assert Pickable.objects.filter(
            name="Blood God", slot_type__name="Chaos God"
        ).exists()


class TestTheVariantConversion:
    """The repair still on offer: the Variants become picks."""

    def test_its_lock_is_not_shared(self):
        keys = list(LOCK_KEYS.values())
        assert len(keys) == len(set(keys))
        assert (
            LOCK_KEYS[Operation.CONVERT_VARIANT]
            != LOCK_KEYS[Operation.CONVERT_CHAOS_GOD]
        )

    def test_the_operation_is_registered_and_named(self):
        registered = {op.operation for op in operations()}

        assert Operation.CONVERT_VARIANT.value in registered
        found = resolve_operation(Operation.CONVERT_VARIANT.value)
        assert found.name == Operation.CONVERT_VARIANT.label
        assert found.view is convert_variant_view

    def test_it_is_not_retired(self):
        assert Operation.CONVERT_VARIANT not in TestARepairThatHasBeenRun.RETIRED
        assert resolve_operation(Operation.CONVERT_VARIANT.value).view is not None

    def test_only_a_superuser_may_reach_it(self, client, staffer):
        client.force_login(staffer)

        response = client.get(reverse("admin:maintenance_n26_convert_variant"))

        assert response.status_code in (302, 403)

    def test_its_page_shows_nothing_to_convert_when_the_system_is_absent(
        self, client, superuser, default_pack
    ):
        client.force_login(superuser)

        response = client.get(reverse("admin:maintenance_n26_convert_variant"))

        page = response.content.decode()
        assert response.status_code == 200
        assert "Nothing to convert" in page
        assert not Backfill.objects.exists()

    def test_its_page_shows_the_plan_and_writes_nothing(
        self, client, superuser, default_pack, owner
    ):
        from n26.tests.sandbox.test_conversion_variant import (
            build_prod_shape,
            build_world,
        )

        build_world(build_prod_shape(), owner)
        client.force_login(superuser)

        response = client.get(reverse("admin:maintenance_n26_convert_variant"))

        page = response.content.decode()
        assert response.status_code == 200
        assert "create slot type “Variant”" in page
        assert not Backfill.objects.exists()

    def test_applying_records_what_it_converted(
        self, client, superuser, default_pack, owner
    ):
        from n26.library.models import Pickable, Slot
        from n26.tests.sandbox.test_conversion_variant import (
            build_prod_shape,
            build_world,
        )

        build_world(build_prod_shape(), owner)
        client.force_login(superuser)

        response = client.post(reverse("admin:maintenance_n26_convert_variant"))

        assert response.status_code == 302
        run = Backfill.objects.get(operation=Operation.CONVERT_VARIANT)
        assert run.status == Backfill.Status.DONE
        assert any("applied" in line for line in run.summary["report"])
        assert Slot.objects.filter(name="Variant").count() == 1
        assert Pickable.objects.filter(
            name="Chaos Corrupted", slot_type__name="Variant"
        ).exists()
        assert not Pickable.objects.filter(name="None").exists()


class TestTheEmptyAffiliationDeletion:
    """The repair still on offer: emptied Affiliation library rows go."""

    def test_its_lock_is_not_shared(self):
        keys = list(LOCK_KEYS.values())
        assert len(keys) == len(set(keys))
        assert LOCK_KEYS[Operation.DELETE_EMPTY_AFFILIATIONS] == 826_020_616
        assert (
            LOCK_KEYS[Operation.DELETE_EMPTY_AFFILIATIONS]
            != LOCK_KEYS[Operation.BACKFILL_BUILT_INS]
        )
        assert (
            LOCK_KEYS[Operation.DELETE_EMPTY_AFFILIATIONS]
            != LOCK_KEYS[Operation.DROP_DUPLICATE_GRANTS]
        )
        assert Operation.DELETE_EMPTY_AFFILIATIONS.value == (
            "n26_delete_empty_affiliations"
        )

    def test_the_operation_is_registered_and_named(self):
        registered = {op.operation for op in operations()}

        assert Operation.DELETE_EMPTY_AFFILIATIONS.value in registered
        found = resolve_operation(Operation.DELETE_EMPTY_AFFILIATIONS.value)
        assert found.name == Operation.DELETE_EMPTY_AFFILIATIONS.label
        assert found.view is delete_empty_affiliations_view

    def test_it_is_not_retired(self):
        assert (
            Operation.DELETE_EMPTY_AFFILIATIONS not in TestARepairThatHasBeenRun.RETIRED
        )
        assert (
            resolve_operation(Operation.DELETE_EMPTY_AFFILIATIONS.value).view
            is not None
        )

    def test_only_a_superuser_may_reach_it(self, client, staffer):
        client.force_login(staffer)

        response = client.get(
            reverse("admin:maintenance_n26_delete_empty_affiliations")
        )

        assert response.status_code in (302, 403)

    def test_its_page_shows_nothing_to_delete_when_the_rows_are_gone(
        self, client, superuser, default_pack
    ):
        client.force_login(superuser)

        response = client.get(
            reverse("admin:maintenance_n26_delete_empty_affiliations")
        )

        page = response.content.decode()
        assert response.status_code == 200
        assert "Nothing to delete" in page
        assert "No Affiliation leftovers are selected for deletion" in page
        assert not Backfill.objects.exists()

    def test_its_page_shows_the_plan_and_writes_nothing(
        self, client, superuser, leftover_world
    ):
        client.force_login(superuser)

        response = client.get(
            reverse("admin:maintenance_n26_delete_empty_affiliations")
        )

        page = response.content.decode()
        assert response.status_code == 200
        assert "delete the emptied affiliation" in page
        assert "those are the new system" in page
        assert not Backfill.objects.exists()

    def test_applying_records_what_it_deleted(self, client, superuser, leftover_world):
        from n26.library.models import Affiliation

        gang, *_ = leftover_world
        client.force_login(superuser)

        response = client.post(
            reverse("admin:maintenance_n26_delete_empty_affiliations")
        )

        assert response.status_code == 302
        run = Backfill.objects.get(operation=Operation.DELETE_EMPTY_AFFILIATIONS)
        assert run.status == Backfill.Status.DONE
        assert any("Deleted" in line for line in run.summary["report"])
        assert not Affiliation.objects.exists()
        assert_reconciled(gang)

    def test_its_page_refuses_while_an_assignment_still_names_one(
        self, client, superuser, leftover_world
    ):
        from n26.core.models import Assignment
        from n26.library.models import Affiliation

        gang, names, _, _, _ = leftover_world
        Assignment.objects.create(
            affiliation=names["Mutant"],
            gang=gang,
            gang_root=gang,
        )
        client.force_login(superuser)
        address = reverse("admin:maintenance_n26_delete_empty_affiliations")

        page = client.get(address).content.decode()
        posted = client.post(address)

        assert "The deletion cannot run" in page
        assert "assignment" in page and "Mutant" in page
        assert posted.status_code == 302
        assert not Backfill.objects.exists()
        assert Affiliation.objects.filter(pk=names["Mutant"].pk).exists()


class TestTheLegacyAffiliationAssignmentDeletion:
    def test_its_lock_is_unique_and_its_slug_is_permanent(self):
        keys = list(LOCK_KEYS.values())
        assert len(keys) == len(set(keys))
        assert LOCK_KEYS[Operation.DELETE_LEGACY_AFFILIATION_ASSIGNMENTS] == 826_020_618
        assert Operation.DELETE_LEGACY_AFFILIATION_ASSIGNMENTS.value == (
            "n26_delete_legacy_affiliation_assignments"
        )

    def test_the_operation_is_registered_and_offered(self):
        registered = {op.operation for op in operations()}

        assert Operation.DELETE_LEGACY_AFFILIATION_ASSIGNMENTS.value in registered
        found = resolve_operation(Operation.DELETE_LEGACY_AFFILIATION_ASSIGNMENTS.value)
        assert found.name == Operation.DELETE_LEGACY_AFFILIATION_ASSIGNMENTS.label
        assert found.view is delete_legacy_affiliation_assignments_view

    def test_only_a_superuser_may_reach_it(self, client, staffer):
        client.force_login(staffer)

        response = client.get(
            reverse("admin:maintenance_n26_delete_legacy_affiliation_assignments")
        )

        assert response.status_code in (302, 403)

    def test_get_shows_the_empty_plan_without_writing(
        self, client, superuser, default_pack
    ):
        client.force_login(superuser)

        response = client.get(
            reverse("admin:maintenance_n26_delete_legacy_affiliation_assignments")
        )

        page = response.content.decode()
        assert response.status_code == 200
        assert "Nothing to delete" in page
        assert "No legacy affiliation assignments remain" in page
        assert not Backfill.objects.exists()


@pytest.fixture
def leftover_world(default_pack, person_type, owner):
    from n26.tests.sandbox.test_empty_affiliations import build_leftover_world

    return build_leftover_world(person_type, owner)


class TestTheFoundingActionBackfill:
    """The repair still on offer: gangs founded before the Found and
    equip gang action existed are given one."""

    @pytest.fixture
    def old_gang(self, owner, default_pack, gang_type):
        """A gang as one founded before the action existed."""
        from n26.core.models import LedgerEvent
        from n26.tests.sandbox.actions import found_gang

        gang = found_gang("Before The Action", gang_type, owner=owner, budget=1000)
        LedgerEvent.objects.filter(
            gang=gang, kind=LedgerEvent.Kind.ACTION_OPENED
        ).delete()
        return gang

    def test_its_lock_is_not_shared(self):
        keys = list(LOCK_KEYS.values())
        assert len(keys) == len(set(keys))
        assert (
            LOCK_KEYS[Operation.OPEN_FOUNDING_ACTIONS]
            != LOCK_KEYS[Operation.REPOINT_CHAMPION_PICKS]
        )

    def test_the_operation_is_registered_and_named(self):
        registered = {op.operation for op in operations()}

        assert Operation.OPEN_FOUNDING_ACTIONS.value in registered
        found = resolve_operation(Operation.OPEN_FOUNDING_ACTIONS.value)
        assert found.name == Operation.OPEN_FOUNDING_ACTIONS.label
        assert found.view is open_founding_actions_view

    def test_only_a_superuser_may_reach_it(self, client, staffer):
        client.force_login(staffer)

        response = client.get(reverse("admin:maintenance_n26_open_founding_actions"))

        assert response.status_code in (302, 403)

    def test_its_page_counts_the_gangs_and_writes_nothing(
        self, client, superuser, old_gang
    ):
        from n26.core.models import Action

        client.force_login(superuser)

        response = client.get(reverse("admin:maintenance_n26_open_founding_actions"))

        page = response.content.decode()
        assert response.status_code == 200
        assert "1 of 1 unarchived gang would get the action" in page
        assert not Backfill.objects.exists()
        assert not Action.objects.filter(gang=old_gang).exists()

    def test_its_page_says_when_there_is_nothing_to_open(
        self, client, superuser, owner, default_pack, gang_type
    ):
        from n26.tests.sandbox.actions import found_gang

        found_gang("Founded Today", gang_type, owner=owner, budget=1000)
        client.force_login(superuser)

        response = client.get(reverse("admin:maintenance_n26_open_founding_actions"))

        page = response.content.decode()
        assert response.status_code == 200
        assert "Nothing to open" in page

    def test_applying_records_what_it_opened(self, client, superuser, old_gang):
        from n26.core.models import Action

        client.force_login(superuser)

        response = client.post(reverse("admin:maintenance_n26_open_founding_actions"))

        assert response.status_code == 302
        run = Backfill.objects.get(operation=Operation.OPEN_FOUNDING_ACTIONS)
        assert run.status == Backfill.Status.DONE
        assert run.summary["preview"] == [
            "1 of 1 unarchived gang has never had a Found and equip gang action.",
            "Every unarchived gang is walked, so this run's total counts "
            "gangs walked, not gangs changed.",
        ]
        assert run.summary["totals"]["opened"] == 1
        assert old_gang.open_action(Action.Kind.FOUNDING) is not None
        old_gang.refresh_from_db()
        assert_reconciled(old_gang)

    def test_the_record_page_labels_what_the_run_walked_and_opened(
        self, client, superuser, old_gang
    ):
        """The walk and the totals differ, so the page says which is
        which rather than dumping the summary as it was stored."""
        client.force_login(superuser)
        client.post(reverse("admin:maintenance_n26_open_founding_actions"))
        run = Backfill.objects.get(operation=Operation.OPEN_FOUNDING_ACTIONS)

        page = client.get(
            reverse("admin:maintenance_backfill_detail", args=[run.id])
        ).content.decode()

        assert "gang walked" in page or "gangs walked" in page
        assert "Gangs given a Found and equip gang action" in page
        assert "Gangs skipped: they already had one, open or completed" in page
        assert "never had a Found and equip gang action." in page
        assert "{'opened'" not in page

    def test_applying_with_nothing_to_open_records_no_run(
        self, client, superuser, owner, default_pack, gang_type
    ):
        from n26.tests.sandbox.actions import found_gang

        found_gang("Founded Today", gang_type, owner=owner, budget=1000)
        client.force_login(superuser)

        response = client.post(reverse("admin:maintenance_n26_open_founding_actions"))

        assert response.status_code == 302
        assert not Backfill.objects.exists()


@pytest.fixture
def restricted_world(default_pack, make_profile):
    """What the equipment-lists upload left behind, beside what it did
    not write and must not touch.

    The long las carries a "Van Saar only" bracket on the item, and two
    collections list it — the shape the upload wrote. The lasgun carries
    the same kind of bracket but no collection lists it, so it was
    written by hand. The carapace armour is narrowed to a subtype, which
    the upload never resolved. And the Van Saar list's own line for the
    armour is narrowed on the entry, which is the right place.
    """
    from n26.library.authoring import (
        add_entry,
        create_category,
        create_collection,
        create_subtype,
        create_wargear,
        create_weapon,
        restrict_use,
    )

    leader = make_profile("Van Saar Leader", price=120)
    champion = make_profile("Van Saar Champion", price=95)
    lasguns = create_category("Ranged weapons", "Lasguns")
    long_las = create_weapon("Long las", profiles=[("", 0)], price=60, category=lasguns)
    restrict_use(long_las, leader, champion)
    lasgun = create_weapon("Lasgun", profiles=[("", 0)], price=15, category=lasguns)
    restrict_use(lasgun, leader)
    armour = create_wargear(
        "Carapace armour (light)",
        price=80,
        category=create_category("Wargear", "Armour"),
    )
    restrict_use(armour, create_subtype("Champion"))
    van_saar = create_collection("Van Saar Equipment List", entries=[long_las])
    trading_post = create_collection("Trading Post", entries=[long_las, armour])
    narrowed = add_entry(van_saar, armour)
    restrict_use(narrowed, champion)
    return {
        "long_las": long_las,
        "lasgun": lasgun,
        "armour": armour,
        "van_saar": van_saar,
        "trading_post": trading_post,
        "narrowed": narrowed,
        "leader": leader,
        "champion": champion,
    }


class TestTheItemRestrictionClearing:
    """The repair: the "<Fighter> only" brackets the upload
    wrote onto items every list shares come off, item by item, and
    nothing written by hand or on an entry moves."""

    def test_its_lock_is_unique_and_its_slug_is_permanent(self):
        keys = list(LOCK_KEYS.values())
        assert len(keys) == len(set(keys))
        assert LOCK_KEYS[Operation.CLEAR_ITEM_RESTRICTIONS] == 826_020_623
        assert Operation.CLEAR_ITEM_RESTRICTIONS.value == "n26_clear_item_restrictions"

    def test_the_operation_is_registered_and_named(self):
        registered = {op.operation for op in operations()}

        assert Operation.CLEAR_ITEM_RESTRICTIONS.value in registered
        found = resolve_operation(Operation.CLEAR_ITEM_RESTRICTIONS.value)
        assert found.name == Operation.CLEAR_ITEM_RESTRICTIONS.label
        assert found.view is clear_item_restrictions_view
        assert found.detail_template

    def test_it_is_not_retired(self):
        assert (
            Operation.CLEAR_ITEM_RESTRICTIONS not in TestARepairThatHasBeenRun.RETIRED
        )

    def test_it_runs_through_the_one_transaction_runner(self):
        """Library-only work, in one transaction: the guard reads the
        module as one that never commits inside a loop."""
        assert "clear_item_restrictions" in one_transaction_route_names()
        assert not commits_row_by_row("n26.library.item_restrictions")

    def test_only_a_superuser_may_reach_it(self, client, staffer):
        client.force_login(staffer)

        response = client.get(reverse("admin:maintenance_n26_clear_item_restrictions"))

        assert response.status_code in (302, 403)

    def test_its_page_shows_nothing_to_clear_when_no_listed_item_is_restricted(
        self, client, superuser, default_pack
    ):
        client.force_login(superuser)

        response = client.get(reverse("admin:maintenance_n26_clear_item_restrictions"))

        page = response.content.decode()
        assert response.status_code == 200
        assert "Nothing to clear" in page
        assert "No listed item carries a restriction to fighter entries" in page
        assert not Backfill.objects.exists()

    def test_it_reads_every_listed_item_that_names_a_fighter_entry(
        self, restricted_world
    ):
        from n26.library.item_restrictions import find, listable_kinds

        found = find()

        assert not found.nothing_here
        (item,) = found.items
        assert item.label == "Long las (weapon)"
        assert item.profiles == ("Van Saar Champion", "Van Saar Leader")
        assert item.lists == ("Trading Post", "Van Saar Equipment List")
        assert item.pack == ""
        assert {column for column, _ in listable_kinds()} == {
            "weapon",
            "weapon_profile",
            "wargear",
            "weapon_accessory",
            "skill",
            "power",
        }

    def test_its_page_lists_each_item_and_writes_nothing(
        self, client, superuser, restricted_world
    ):
        client.force_login(superuser)

        response = client.get(reverse("admin:maintenance_n26_clear_item_restrictions"))

        page = response.content.decode()
        assert response.status_code == 200
        assert (
            "clear Long las (weapon): usable by Van Saar Champion, Van Saar Leader only"
            in page
        )
        assert "listed in Trading Post, Van Saar Equipment List" in page
        assert "Lasgun" not in page
        assert "Carapace armour" not in page
        assert not Backfill.objects.exists()
        assert restricted_world["long_las"].usable_by_words() != ""

    def test_two_lists_printing_one_name_are_told_apart(
        self, restricted_world, other_pack
    ):
        """A collection is unique by pack, name and qualifier together,
        so the plan names each list the way an author would tell them
        apart — the name alone would fold three lists into one."""
        from n26.library.authoring import create_collection
        from n26.library.item_restrictions import find

        long_las = restricted_world["long_las"]
        create_collection(
            "Van Saar Equipment List", qualifier="Outcasts", entries=[long_las]
        )
        create_collection(
            "Van Saar Equipment List", entries=[long_las], pack=other_pack
        )

        (item,) = find().items

        assert item.lists == (
            "Trading Post",
            "Van Saar Equipment List",
            "Van Saar Equipment List [Other]",
            "Van Saar Equipment List — Outcasts",
        )

    def test_reading_the_plan_takes_no_more_queries_as_the_items_grow(
        self, restricted_world, make_profile
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.authoring import create_collection, create_weapon, restrict_use
        from n26.library.item_restrictions import find

        def queries():
            with CaptureQueriesContext(connection) as captured:
                found = find()
            return len(captured), found

        small, _ = queries()
        listing = create_collection("Another list")
        for index in range(9):
            weapon = create_weapon(f"Las {index}", profiles=[("", 0)], price=10)
            restrict_use(weapon, restricted_world["leader"])
            listing.entries.create(weapon=weapon, position=index)

        large, found = queries()

        assert len(found.items) == 10
        assert large == small

    def test_applying_records_the_plan_and_what_it_cleared_and_leaves_the_rest(
        self, client, superuser, restricted_world
    ):
        client.force_login(superuser)

        response = client.post(reverse("admin:maintenance_n26_clear_item_restrictions"))

        assert response.status_code == 302
        run = Backfill.objects.get(operation=Operation.CLEAR_ITEM_RESTRICTIONS)
        assert run.status == Backfill.Status.DONE
        (planned,) = run.summary["plan"]
        assert planned["model"] == "library.weapon"
        assert planned["pk"] == str(restricted_world["long_las"].pk)
        assert set(planned["profile_ids"]) == {
            str(restricted_world["leader"].pk),
            str(restricted_world["champion"].pk),
        }
        assert run.summary["report"][0] == (
            "Cleared the restriction to fighter entries from 1 listed item."
        )
        assert any("Long las" in line for line in run.summary["report"])
        world = restricted_world
        assert world["long_las"].usable_by_words() == ""
        # Written by hand: no list carries the lasgun's bracket on its
        # way past, so it stays.
        assert world["lasgun"].usable_by_words() == "Van Saar Leader"
        # A subtype, which the upload never wrote.
        assert world["armour"].usable_by_words() == "Champion"
        # The entry's own narrowing is the right place, and stays.
        assert world["narrowed"].usable_by_words() == "Van Saar Champion"

    def test_the_record_page_says_what_it_did(
        self, client, superuser, restricted_world
    ):
        client.force_login(superuser)
        client.post(reverse("admin:maintenance_n26_clear_item_restrictions"))
        run = Backfill.objects.get(operation=Operation.CLEAR_ITEM_RESTRICTIONS)

        page = client.get(
            reverse("admin:maintenance_backfill_detail", args=[run.id])
        ).content.decode()

        assert "What it did" in page
        assert "cleared Long las (weapon): was usable by" in page
        assert f"Took {run.summary['seconds']} second" in page

    def test_the_record_page_shows_the_deadline_warning(
        self, client, superuser, restricted_world
    ):
        """A run that used more than half of one delivery is written up
        on its record, and the page has to show it, or nobody moves
        the work before running it again."""
        client.force_login(superuser)
        client.post(reverse("admin:maintenance_n26_clear_item_restrictions"))
        run = Backfill.objects.get(operation=Operation.CLEAR_ITEM_RESTRICTIONS)
        warning = "This run took 400 of the 600 seconds one delivery may take"
        Backfill.objects.filter(pk=run.pk).update(
            summary={**run.summary, "seconds": 400, "warning": warning}
        )

        page = client.get(
            reverse("admin:maintenance_backfill_detail", args=[run.id])
        ).content.decode()

        assert "Took 400 seconds." in page
        assert warning in page

    def test_the_record_page_of_a_refused_run_says_what_it_planned(
        self, client, superuser, restricted_world
    ):
        """A refusal ends the record failed with its preview still on it
        and no report. The page must not call that a run in progress."""
        from n26.library.authoring import restrict_use
        from n26.library.item_restrictions import find

        found = find()
        record = Backfill.objects.create(
            operation=Operation.CLEAR_ITEM_RESTRICTIONS,
            triggered_by=superuser,
            status=Backfill.Status.RUNNING,
            summary={"preview": list(found.preview()), **found.recorded()},
        )
        restrict_use(restricted_world["armour"], restricted_world["leader"])
        maintenance.clear_item_restrictions.call(backfill_id=str(record.id))
        record.refresh_from_db()
        assert record.status == Backfill.Status.FAILED
        assert "report" not in record.summary
        client.force_login(superuser)

        page = client.get(
            reverse("admin:maintenance_backfill_detail", args=[record.id])
        ).content.decode()

        assert "What it planned to do" in page
        assert "ended without clearing" in page
        assert "What it is doing" not in page
        assert "What it did" not in page
        assert "clear Long las (weapon): usable by" in page

    def test_the_record_page_of_a_running_run_says_what_it_is_doing(
        self, client, superuser, restricted_world
    ):
        from n26.library.item_restrictions import find

        found = find()
        record = Backfill.objects.create(
            operation=Operation.CLEAR_ITEM_RESTRICTIONS,
            triggered_by=superuser,
            status=Backfill.Status.RUNNING,
            summary={"preview": list(found.preview()), **found.recorded()},
        )
        client.force_login(superuser)

        page = client.get(
            reverse("admin:maintenance_backfill_detail", args=[record.id])
        ).content.decode()

        assert "What it is doing" in page
        assert "What it planned to do" not in page

    def test_the_run_holds_the_listings_that_make_an_item_eligible(
        self, restricted_world
    ):
        """The items are locked, and so are the entries that list them:
        a listing taken off while the run is reading would leave it
        stripping an item no list carries. The proof is the lock on the
        entry table itself, not a race — one query per kind."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.item_restrictions import apply, find
        from n26.library.models import CollectionEntry

        approved = find().recorded()["plan"]

        with CaptureQueriesContext(connection) as captured:
            apply(approved)

        table = CollectionEntry._meta.db_table
        held = [
            q["sql"] for q in captured if table in q["sql"] and "FOR UPDATE" in q["sql"]
        ]
        assert len(held) == 1
        assert restricted_world["long_las"].usable_by_words() == ""

    def test_applying_a_second_time_records_no_run(
        self, client, superuser, restricted_world
    ):
        client.force_login(superuser)
        client.post(reverse("admin:maintenance_n26_clear_item_restrictions"))

        client.post(reverse("admin:maintenance_n26_clear_item_restrictions"))

        assert Backfill.objects.count() == 1

    def test_it_refuses_when_an_item_was_restricted_after_the_preview(
        self, restricted_world
    ):
        """The plan somebody approved is the plan that runs. An item
        restricted after the preview was read is not swept up by it."""
        from n26.library.authoring import restrict_use
        from n26.library.item_restrictions import Refused, apply, find

        approved = find().recorded()["plan"]
        restrict_use(restricted_world["armour"], restricted_world["leader"])

        with pytest.raises(Refused, match="changed since the preview was read"):
            apply(approved)

        assert restricted_world["long_las"].usable_by_words() != ""
        assert restricted_world["armour"].usable_by_words() != "Champion"

    def test_it_refuses_when_a_previewed_items_restriction_moved(
        self, restricted_world
    ):
        from n26.library.authoring import restrict_use
        from n26.library.item_restrictions import Refused, apply, find

        approved = find().recorded()["plan"]
        restricted_world["long_las"].usable_by_profiles.remove(
            restricted_world["champion"]
        )
        restrict_use(restricted_world["long_las"], restricted_world["leader"])

        with pytest.raises(Refused, match="changed since the preview was read"):
            apply(approved)

        assert restricted_world["long_las"].usable_by_words() == "Van Saar Leader"

    def test_a_redelivery_after_the_clearing_committed_ends_done_not_failed(
        self, restricted_world, superuser
    ):
        """The clearing commits, then the record is written. A worker
        cut off between the two leaves the record running, and the
        queue delivers the task again to a world where the approved
        items already carry nothing: that is the plan carried out, and
        the record ends done rather than failed."""
        from n26.library.item_restrictions import apply, find

        found = find()
        record = Backfill.objects.create(
            operation=Operation.CLEAR_ITEM_RESTRICTIONS,
            triggered_by=superuser,
            status=Backfill.Status.RUNNING,
            summary={
                "preview": list(found.preview()),
                "attempts": 1,
                **found.recorded(),
            },
        )
        apply(found.recorded()["plan"])

        maintenance.clear_item_restrictions.call(backfill_id=str(record.id))

        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE
        assert record.summary["report"][0].startswith(
            "Nothing left to clear: none of the 1 listed item the preview named"
        )
        assert restricted_world["long_las"].usable_by_words() == ""
        assert restricted_world["lasgun"].usable_by_words() == "Van Saar Leader"

    def test_a_plan_only_partly_carried_out_is_still_a_changed_plan(
        self, restricted_world
    ):
        """Already cleared means every approved item carries nothing.
        One of two cleared by hand is a plan that changed, and the run
        refuses rather than clearing the other on a preview nobody saw
        in this state."""
        from n26.library.authoring import restrict_use
        from n26.library.item_restrictions import Refused, apply, find

        restrict_use(restricted_world["armour"], restricted_world["leader"])
        approved = find().recorded()["plan"]
        assert len(approved) == 2
        restricted_world["long_las"].usable_by_profiles.clear()

        with pytest.raises(Refused, match="changed since the preview was read"):
            apply(approved)

        assert restricted_world["armour"].usable_by_words() != "Champion"

    def test_a_record_without_a_plan_is_refused(self, restricted_world):
        from n26.library.item_restrictions import Refused, apply

        with pytest.raises(Refused, match="holds no plan"):
            apply(None)

        assert restricted_world["long_las"].usable_by_words() != ""

    def test_the_task_reads_the_plan_off_its_own_record(
        self, restricted_world, superuser
    ):
        """What the task clears is what its record says was approved,
        not whatever a fresh scan finds when it starts."""
        from n26.library.authoring import restrict_use
        from n26.library.item_restrictions import find

        found = find()
        record = Backfill.objects.create(
            operation=Operation.CLEAR_ITEM_RESTRICTIONS,
            triggered_by=superuser,
            status=Backfill.Status.RUNNING,
            summary={
                "preview": list(found.preview()),
                "attempts": 0,
                **found.recorded(),
            },
        )
        restrict_use(restricted_world["armour"], restricted_world["leader"])

        maintenance.clear_item_restrictions.call(backfill_id=str(record.id))

        record.refresh_from_db()
        assert record.status == Backfill.Status.FAILED
        assert "changed since the preview was read" in record.error
        assert restricted_world["long_las"].usable_by_words() != ""
        assert restricted_world["armour"].usable_by_words() != "Champion"

    def test_a_refusal_ends_the_record_in_its_own_words(
        self, restricted_world, superuser
    ):
        from n26.library.authoring import restrict_use
        from n26.library.item_restrictions import Refused, apply, find

        found = find()
        restrict_use(restricted_world["armour"], restricted_world["leader"])
        record = Backfill.objects.create(
            operation=Operation.CLEAR_ITEM_RESTRICTIONS,
            triggered_by=superuser,
            status=Backfill.Status.RUNNING,
            summary={"preview": list(found.preview()), "attempts": 0},
        )

        maintenance._run_recorded(
            record.id,
            Operation.CLEAR_ITEM_RESTRICTIONS,
            "Item restriction clearing",
            lambda: apply(found.recorded()["plan"]),
            Refused,
        )

        record.refresh_from_db()
        assert record.status == Backfill.Status.FAILED
        assert "changed since the preview was read" in record.error
        assert restricted_world["long_las"].usable_by_words() != ""

    def test_an_item_in_another_pack_says_which(
        self, restricted_world, other_pack, make_profile
    ):
        from n26.library.authoring import create_collection, create_weapon, restrict_use
        from n26.library.item_restrictions import find

        homebrew = create_weapon(
            "Homebrew las", profiles=[("", 0)], price=10, pack=other_pack
        )
        restrict_use(homebrew, restricted_world["leader"])
        create_collection("Homebrew list", entries=[homebrew], pack=other_pack)

        found = find()

        lines = found.preview()
        assert any("Homebrew las (weapon) [Other]" in line for line in lines)
