"""This edition's repairs, as the maintenance console offers them.

A seam test: the console is the platform's, the conversion is ours, and
what is proven here is that the two meet — the operation is registered and
gated, the page shows the plan without writing, applying records what
happened, and every way a run can end leaves an honest record behind.

The conversion's own discipline is proven in
``n26/tests/sandbox/test_conversion_specialisation.py``; this file cares
only about the door it is triggered through.
"""

from contextlib import contextmanager

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.maintenance.models import Backfill
from gyrinx.maintenance.registry import operations, resolve_operation
from n26.core.models import Assignment
from n26.maintenance import (
    MAX_ATTEMPTS,
    Operation,
    convert_gang_legacy_view,
    convert_skill_tree_view,
    convert_specialisation,
    convert_specialisation_view,
    retire_gang_legacy_pilot_view,
)
from n26.tests.sandbox.test_conversion_gang_legacy import (
    build_prod_shape as build_gang_legacy_shape,
)
from n26.tests.sandbox.test_conversion_gang_legacy import (
    build_world as build_gang_legacy_world,
)
from n26.tests.sandbox.test_conversion_skill_tree import (
    build_prod_shape as build_skill_tree_shape,
)
from n26.tests.sandbox.test_conversion_skill_tree import (
    build_world as build_skill_tree_world,
)
from n26.tests.sandbox.test_conversion_specialisation import (
    build_prod_shape,
    build_world,
)

pytestmark = pytest.mark.django_db

URL_NAME = "admin:maintenance_n26_convert_specialisation"


@contextmanager
def _lock_held_elsewhere(operation=None):
    """Hold one run's lock on another connection, as a run in flight does."""
    from django.db import connections

    from n26.maintenance import LOCK_KEYS

    key = LOCK_KEYS[operation or Operation.CONVERT_SPECIALISATION]
    other = connections.create_connection("default")
    try:
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [key])
        yield
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [key])
    finally:
        other.close()


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def prod_shape(default_pack):
    return build_prod_shape()


@pytest.fixture
def world(prod_shape, person_type, owner, default_pack):
    return build_world(prod_shape, person_type, owner)


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser("boss", "boss@example.com", "password")


@pytest.fixture
def staffer(db):
    return User.objects.create_user(
        "clerk", "clerk@example.com", "password", is_staff=True
    )


class TestTheConsoleOffersIt:
    def test_the_operation_is_registered_and_named(self):
        registered = {op.operation for op in operations()}

        assert Operation.CONVERT_SPECIALISATION.value in registered
        found = resolve_operation(Operation.CONVERT_SPECIALISATION.value)
        assert found.name == Operation.CONVERT_SPECIALISATION.label
        assert found.view is convert_specialisation_view

    def test_only_a_superuser_may_reach_it(self, client, staffer):
        client.force_login(staffer)

        assert client.get(reverse(URL_NAME)).status_code == 403

    def test_a_stranger_is_sent_to_the_login(self, client):
        response = client.get(reverse(URL_NAME))

        assert response.status_code in (302, 403)


class TestThePage:
    def test_it_shows_the_plan_and_writes_nothing(self, client, superuser, world):
        client.force_login(superuser)

        response = client.get(reverse(URL_NAME))

        page = response.content.decode()
        assert response.status_code == 200
        assert "create slot type “Specialisation”" in page
        assert "prove 2 of 2 reached gangs read the same" in page
        assert not Backfill.objects.exists()
        assert Assignment.objects.filter(specialisation__isnull=False).exists()


class TestTheSkillTreeConversion:
    """The second conversion the console offers, riding the same runner,
    lock, and record discipline as the first."""

    @pytest.fixture
    def tree_world(self, person_type, owner, default_pack):
        shape = build_skill_tree_shape()
        return build_skill_tree_world(shape, person_type, owner)

    def test_the_operation_is_registered_and_named(self):
        registered = {op.operation for op in operations()}

        assert Operation.CONVERT_SKILL_TREE.value in registered
        found = resolve_operation(Operation.CONVERT_SKILL_TREE.value)
        assert found.name == Operation.CONVERT_SKILL_TREE.label
        assert found.view is convert_skill_tree_view

    def test_its_page_shows_the_plan_and_writes_nothing(
        self, client, superuser, tree_world
    ):
        client.force_login(superuser)

        response = client.get(reverse("admin:maintenance_n26_convert_skill_tree"))

        page = response.content.decode()
        assert response.status_code == 200
        assert "create slot type “Skill Tree”, refusing repeats" in page
        assert "prove 4 of 4 reached gangs read the same" in page
        assert not Backfill.objects.exists()
        assert Assignment.objects.filter(skill_tree__isnull=False).exists()

    def test_one_conversion_running_does_not_strand_the_other(
        self, client, superuser, tree_world
    ):
        """The locks are per operation. Were they shared, this run would
        stand down at the other conversion's lock without writing, its
        message would be acknowledged, and its record would say RUNNING
        for ever — with the running-guard then refusing every retry."""
        client.force_login(superuser)

        with _lock_held_elsewhere(Operation.CONVERT_SPECIALISATION):
            client.post(reverse("admin:maintenance_n26_convert_skill_tree"))

        run = Backfill.objects.get(operation=Operation.CONVERT_SKILL_TREE)
        assert run.status == Backfill.Status.DONE

    def test_applying_records_what_it_did(self, client, superuser, tree_world):
        client.force_login(superuser)

        response = client.post(reverse("admin:maintenance_n26_convert_skill_tree"))

        assert response.status_code == 302
        run = Backfill.objects.get(operation=Operation.CONVERT_SKILL_TREE)
        assert run.status == Backfill.Status.DONE
        assert any("applied" in line for line in run.summary["report"])
        # Every answer moved; the doubled click's spare is all that
        # still says skill_tree, exactly as the plan promised.
        left = Assignment.objects.filter(
            skill_tree__isnull=False, archived=False
        ).exclude(removes=True)
        assert left.count() == 1


class TestTheGangLegacyPair:
    """The pilot retirement and the Gang Legacy conversion, in the
    order the console must run them: the conversion refuses while the
    pilot stands, and converts once it is retired."""

    @pytest.fixture
    def legacy_world(self, person_type, owner, default_pack):
        shape = build_gang_legacy_shape(person_type)
        return build_gang_legacy_world(shape, owner)

    def test_both_operations_are_registered_and_named(self):
        registered = {op.operation for op in operations()}

        assert Operation.CONVERT_GANG_LEGACY.value in registered
        assert Operation.RETIRE_GANG_LEGACY_PILOT.value in registered
        assert (
            resolve_operation(Operation.CONVERT_GANG_LEGACY.value).view
            is convert_gang_legacy_view
        )
        assert (
            resolve_operation(Operation.RETIRE_GANG_LEGACY_PILOT.value).view
            is retire_gang_legacy_pilot_view
        )

    def test_the_retirement_page_shows_the_plan_and_writes_nothing(
        self, client, superuser, legacy_world
    ):
        from n26.tests.sandbox.actions import create_slot_type

        create_slot_type("Gang Legacy")
        client.force_login(superuser)

        response = client.get(reverse("admin:maintenance_n26_retire_gang_legacy_pilot"))

        page = response.content.decode()
        assert response.status_code == 200
        assert "hollow pickables" in page
        assert not Backfill.objects.exists()

    def test_the_conversion_refuses_while_the_pilot_stands(
        self, client, superuser, legacy_world
    ):
        from n26.tests.sandbox.actions import create_slot_type

        create_slot_type("Gang Legacy")
        client.force_login(superuser)

        response = client.get(reverse("admin:maintenance_n26_convert_gang_legacy"))

        assert "retire the pilot first" in response.content.decode()

    def test_retire_then_convert_in_the_console_order(
        self, client, superuser, legacy_world
    ):
        from n26.tests.sandbox.actions import create_slot_type

        create_slot_type("Gang Legacy")
        client.force_login(superuser)

        client.post(reverse("admin:maintenance_n26_retire_gang_legacy_pilot"))
        retired = Backfill.objects.get(operation=Operation.RETIRE_GANG_LEGACY_PILOT)
        assert retired.status == Backfill.Status.DONE

        client.post(reverse("admin:maintenance_n26_convert_gang_legacy"))
        converted = Backfill.objects.get(operation=Operation.CONVERT_GANG_LEGACY)
        assert converted.status == Backfill.Status.DONE
        assert any("applied" in line for line in converted.summary["report"])
        left = Assignment.objects.filter(
            archetype__isnull=False, archived=False
        ).exclude(removes=True)
        # The doubled click's spare and the other system's pick remain.
        assert left.count() == 2


class TestApplying:
    def test_it_records_what_it_did(self, client, superuser, world):
        client.force_login(superuser)

        response = client.post(reverse(URL_NAME), follow=True)

        backfill = Backfill.objects.get()
        assert backfill.operation == Operation.CONVERT_SPECIALISATION.value
        assert backfill.triggered_by == superuser
        assert backfill.status == Backfill.Status.DONE
        assert "applied; every page reads the same" in backfill.summary["report"][-1]
        assert backfill.summary["attempts"] == 1
        # The run really converted: every answer this world holds now
        # names a pickable. Said of the answers rather than of the column,
        # because a spare left by a doubled click keeps the old one and is
        # meant to.
        answers = Assignment.objects.filter(
            chosen_for_slot__isnull=False, archived=False
        )
        assert answers.count() == 3
        assert all(row.pickable_id is not None for row in answers)
        assert str(backfill.id) in response.redirect_chain[-1][0]

    def test_the_detail_page_says_what_happened(self, client, superuser, world):
        client.force_login(superuser)
        client.post(reverse(URL_NAME))
        backfill = Backfill.objects.get()

        response = client.get(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )

        assert "What it did" in response.content.decode()

    def test_a_second_run_finds_nothing_to_convert(self, client, superuser, world):
        client.force_login(superuser)
        client.post(reverse(URL_NAME))

        response = client.get(reverse(URL_NAME))

        assert "Nothing to convert" in response.content.decode()

    def test_applying_twice_records_only_the_run_that_did_something(
        self, client, superuser, world
    ):
        """A page left open across someone else's run: submitting it
        again must not file a record for work there is none of."""
        client.force_login(superuser)
        client.post(reverse(URL_NAME))

        client.post(reverse(URL_NAME), follow=True)

        assert Backfill.objects.count() == 1

    def test_a_run_already_going_is_not_started_again(self, client, superuser, world):
        Backfill.objects.create(
            operation=Operation.CONVERT_SPECIALISATION,
            status=Backfill.Status.RUNNING,
        )
        client.force_login(superuser)

        client.post(reverse(URL_NAME), follow=True)

        assert Backfill.objects.count() == 1
        assert Assignment.objects.filter(specialisation__isnull=False).exists()


class TestTheRunsOwnGuards:
    def test_a_refusal_is_written_down_never_raised(self, world, prod_shape):
        """A raised error would be redelivered for ever, so every ending
        lands on the record instead."""
        from n26.library.authoring import attach_modifiers_to
        from n26.tests.sandbox.actions import create_subtype

        specialist, _, _, _ = prod_shape
        offer = next(
            m
            for m in specialist.modifiers.all()
            if getattr(m, "offers_choice", None) is not None
        )
        attach_modifiers_to(create_subtype("Understudy"), [offer])
        backfill = Backfill.objects.create(
            operation=Operation.CONVERT_SPECIALISATION,
            status=Backfill.Status.RUNNING,
        )

        convert_specialisation.enqueue(backfill_id=str(backfill.id))

        backfill.refresh_from_db()
        assert backfill.status == Backfill.Status.FAILED
        assert "shared" in backfill.error
        assert Assignment.objects.filter(specialisation__isnull=False).exists()

    def test_a_run_that_keeps_being_restarted_gives_up(self, world):
        backfill = Backfill.objects.create(
            operation=Operation.CONVERT_SPECIALISATION,
            status=Backfill.Status.RUNNING,
            summary={"attempts": MAX_ATTEMPTS},
        )

        convert_specialisation.enqueue(backfill_id=str(backfill.id))

        backfill.refresh_from_db()
        assert backfill.status == Backfill.Status.FAILED
        assert "without finishing" in backfill.error
        assert Assignment.objects.filter(specialisation__isnull=False).exists()

    def test_a_second_copy_arriving_mid_run_leaves_no_trace(self, world):
        """Delivery is at-least-once, so a copy can arrive while the first
        is still working. It must not touch the record at all — counting
        its arrival would let a long run be failed out from under itself.

        The run in flight is held on its own connection, as a second
        delivery really is: Postgres hands the same session a lock it
        already holds, so a same-connection stand-in would prove nothing.
        """
        backfill = Backfill.objects.create(
            operation=Operation.CONVERT_SPECIALISATION,
            status=Backfill.Status.RUNNING,
            summary={"attempts": MAX_ATTEMPTS},
        )

        with _lock_held_elsewhere():
            convert_specialisation.enqueue(backfill_id=str(backfill.id))

        backfill.refresh_from_db()
        assert backfill.status == Backfill.Status.RUNNING
        assert backfill.summary["attempts"] == MAX_ATTEMPTS
        assert backfill.error == ""

    def test_a_delivery_arriving_after_success_cannot_unsay_it(
        self, client, superuser, world
    ):
        """A run finishes close to the moment its delivery is retried, so
        the copy that arrives to find the work already done is the likely
        one. It must not file a successful conversion as a failure."""
        client.force_login(superuser)
        client.post(reverse(URL_NAME))
        backfill = Backfill.objects.get()
        assert backfill.status == Backfill.Status.DONE
        report = backfill.summary["report"]

        convert_specialisation.enqueue(backfill_id=str(backfill.id))

        backfill.refresh_from_db()
        assert backfill.status == Backfill.Status.DONE
        assert backfill.error == ""
        assert backfill.summary["report"] == report

    def test_it_survives_a_message_from_another_version(self, world):
        """Delivery outlives a deploy: a message can name arguments this
        version no longer has, and a task that refuses its own message is
        retried for ever."""
        backfill = Backfill.objects.create(
            operation=Operation.CONVERT_SPECIALISATION,
            status=Backfill.Status.RUNNING,
        )

        convert_specialisation.enqueue(backfill_id=str(backfill.id), unheard_of=1)

        backfill.refresh_from_db()
        assert backfill.status == Backfill.Status.DONE

    def test_a_message_asking_not_to_keep_its_work_does_not_keep_it(self, world):
        """A version ago this could be told to do the whole thing and
        throw it away. Ignoring that instruction would commit what
        somebody asked to be careful about."""
        backfill = Backfill.objects.create(
            operation=Operation.CONVERT_SPECIALISATION,
            status=Backfill.Status.RUNNING,
        )

        convert_specialisation.enqueue(backfill_id=str(backfill.id), keep=False)

        backfill.refresh_from_db()
        assert backfill.status == Backfill.Status.FAILED
        assert "cannot do" in backfill.error
        assert Assignment.objects.filter(specialisation__isnull=False).exists()

    def test_the_gentler_button_of_an_old_page_converts_nothing(
        self, client, superuser, world
    ):
        client.force_login(superuser)

        client.post(reverse(URL_NAME), {"keep": "no"}, follow=True)

        assert not Backfill.objects.exists()
        assert Assignment.objects.filter(specialisation__isnull=False).exists()

    def test_a_cancelled_run_stays_cancelled(self, world):
        backfill = Backfill.objects.create(
            operation=Operation.CONVERT_SPECIALISATION,
            status=Backfill.Status.CANCELLED,
        )

        convert_specialisation.enqueue(backfill_id=str(backfill.id))

        backfill.refresh_from_db()
        assert backfill.status == Backfill.Status.CANCELLED
