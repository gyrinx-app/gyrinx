"""This edition's repairs, as the maintenance console offers them.

A seam test: the console is the platform's, the repair is ours, and what
is proven here is that the two meet — the operation is registered and
gated, the page shows the plan without writing, applying records what
happened, and a repair that has been run keeps its name without keeping
its page.

Each repair's own discipline is proven beside it; this file cares only
about the door it is triggered through.
"""

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
from n26.core.reconcile import assert_reconciled
from n26.maintenance import (
    Operation,
    convert_outcast_affiliation_view,
    delete_nameless_gang_type_view,
)

pytestmark = pytest.mark.django_db


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
        assert Pickable.objects.filter(name="Clanless Outcast").exists()
