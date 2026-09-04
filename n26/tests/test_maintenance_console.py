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
    LOCK_KEYS,
    Operation,
    convert_chaos_god_view,
    convert_outcast_affiliation_view,
    convert_variant_view,
    delete_empty_affiliations_view,
    delete_nameless_gang_type_view,
    open_founding_actions_view,
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
