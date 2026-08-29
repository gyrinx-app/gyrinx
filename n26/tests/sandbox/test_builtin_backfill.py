"""The built-ins backfill: fighters catch up with what they were hired without.

Grants written before provenance existed carry only their shape — reason
``DEFAULT``, caused by the carrier — and a member added to a set after a
hire never reached the models already hired from it. The backfill walks
every unarchived gang on the batched runner and, per gang, tags each
legacy grant with the member and carrier it came from, then reconciles
every live carrier so a later member arrives as caught up. Proven here:
tagging alone moves no money; a gained member is granted with a
catch-up event, free as every built-in is; twin guns pair one copy per
member; a grant whose member is gone is left untagged and counted; the
gang's founding and an option set tag like any carrier; a sold grant is
tagged so it is never handed back; a model already holding a member's
thing another way is skipped and named rather than given a second; a
second run does nothing; and the console offers the operation without
writing on GET.

The legacy shape is planted the way it really arose: hire normally, then
strip the provenance the hire recorded.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.maintenance.models import Backfill
from gyrinx.maintenance.registry import operations, resolve_operation
from n26.core.models import Assignment, LedgerEvent, Reason
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.library.models import DefaultAssignment
from n26.maintenance import Operation, backfill_built_ins, backfill_built_ins_view
from n26.tests.sandbox.actions import (
    add_built_in,
    create_option_group,
    create_profile,
    create_rule,
    create_skill,
    create_weapon,
    found_gang,
    hire,
    hire_with_option,
    learn,
    offer_option,
    sell,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def player():
    return User.objects.create_user("veteran")


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Old Guard", gang_type, owner=player, budget=1000)


@pytest.fixture
def launcher(default_pack):
    return create_weapon("Launcher", profiles=[("Frag", 0)], price=30)


@pytest.fixture
def ganger(person_type, gang_type, default_pack, launcher):
    """A profile that comes with a rule and a gun."""
    profile = create_profile("Ganger", person_type, gang_type, price=50)
    add_built_in(profile, create_rule("Gang Fighter"))
    add_built_in(profile, launcher)
    return profile


def strip_provenance(gang):
    """What every grant looked like before provenance was recorded."""
    return Assignment.objects.filter(
        gang_root=gang, materialised_from__isnull=False
    ).update(materialised_from=None, materialised_for=None)


def legacy_grants(gang):
    return Assignment.objects.filter(
        gang_root=gang,
        materialised_from__isnull=True,
        ledger_entry__reason=Reason.DEFAULT,
        weapon_profile__isnull=True,
    )


def run_backfill():
    record = Backfill.objects.create(
        operation=Operation.BACKFILL_BUILT_INS,
        status=Backfill.Status.RUNNING,
        summary={"attempts": 0},
    )
    backfill_built_ins.func(backfill_id=str(record.pk))
    record.refresh_from_db()
    return record


def settled(gang):
    gang.refresh_from_db()
    assert_reconciled(gang)
    return gang


class TestTaggingLegacyGrants:
    """A grant written without provenance is matched to the member it
    came from, and the tag is all that is written."""

    def test_a_legacy_fighter_whose_set_is_unchanged_is_tagged_and_gains_nothing(
        self, gang, ganger
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        stripped = strip_provenance(gang)
        assert stripped == 2
        rating = settled(gang).rating
        events = LedgerEvent.objects.filter(gang=gang).count()

        record = run_backfill()

        assert record.status == Backfill.Status.DONE
        assert record.summary["totals"]["tagged"] == 2
        assert record.summary["totals"]["granted"] == 0
        assert record.summary["totals"]["unmatched"] == 0
        assert not legacy_grants(gang).exists()
        for member in ganger.built_ins.members.all():
            assert Assignment.objects.filter(
                materialised_from=member,
                materialised_for=fighter.membership,
                archived=False,
            ).exists()
        assert LedgerEvent.objects.filter(gang=gang).count() == events
        assert settled(gang).rating == rating

    def test_a_member_gained_after_the_hire_arrives_as_caught_up(
        self, gang, ganger, default_pack
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        strip_provenance(gang)
        rating = settled(gang).rating
        knife = create_weapon("Knife", profiles=[("Stab", 0)], price=15)
        # Propagation is shut, so the member waits for the backfill.
        member = add_built_in(ganger, knife)
        assert not Assignment.objects.filter(materialised_from=member).exists()

        record = run_backfill()

        assert record.summary["totals"]["tagged"] == 2
        assert record.summary["totals"]["granted"] == 1
        copy = Assignment.objects.get(
            materialised_from=member, materialised_for=fighter.membership
        )
        assert copy.archived is False
        assert copy.miniature_root_id == fighter.pk
        assert LedgerEvent.objects.filter(
            gang=gang, assignment=copy, kind=LedgerEvent.Kind.CAUGHT_UP
        ).exists()
        # A built-in is free: the hire's package carries the money, so
        # what arrives late is worth nothing on its own.
        assert copy.ledger_entry.rating_contribution == 0
        assert settled(gang).rating == rating

    def test_twin_guns_pair_one_copy_to_each_member(
        self, gang, person_type, gang_type, default_pack, launcher
    ):
        profile = create_profile("Twin gunner", person_type, gang_type, price=50)
        first = add_built_in(profile, launcher)
        second = add_built_in(profile, launcher)
        fighter = hire(gang, profile, "Ana", paid=50)
        strip_provenance(gang)

        record = run_backfill()

        assert record.summary["totals"]["tagged"] == 2
        assert record.summary["totals"]["ambiguous"] == 0
        assert record.summary["totals"]["granted"] == 0
        tagged = Assignment.objects.filter(
            materialised_for=fighter.membership, weapon=launcher
        )
        assert sorted(tagged.values_list("materialised_from_id", flat=True)) == sorted(
            [first.pk, second.pk]
        )
        assert (
            Assignment.objects.filter(
                miniature_root=fighter, weapon=launcher, archived=False
            ).count()
            == 2
        )
        settled(gang)

    def test_a_grant_whose_member_is_gone_is_left_untagged_and_counted(
        self, gang, ganger
    ):
        hire(gang, ganger, "Ana", paid=50)
        strip_provenance(gang)
        gone = ganger.built_ins.members.get(rule__isnull=False)
        DefaultAssignment.objects.filter(pk=gone.pk).delete()
        events = LedgerEvent.objects.filter(gang=gang).count()

        record = run_backfill()

        assert record.status == Backfill.Status.DONE
        assert record.summary["totals"]["tagged"] == 1
        assert record.summary["totals"]["unmatched"] == 1
        assert record.summary["totals"]["granted"] == 0
        orphan = legacy_grants(gang).get()
        assert orphan.rule is not None
        assert orphan.archived is False
        assert LedgerEvent.objects.filter(gang=gang).count() == events
        settled(gang)


class TestEveryKindOfCarrier:
    """The gang's founding and an option set materialise the same way a
    hire does, and are tagged and caught up the same way."""

    def test_the_gang_type_set_tags_and_catches_up_on_the_gang(
        self, gang_type, player, default_pack
    ):
        creed = add_built_in(gang_type, create_rule("House Creed"))
        gang = found_gang("The Old Guard", gang_type, owner=player, budget=1000)
        strip_provenance(gang)
        later = add_built_in(gang_type, create_rule("New Law"))

        record = run_backfill()

        assert record.summary["totals"]["tagged"] == 1
        assert record.summary["totals"]["granted"] == 1
        for member in (creed, later):
            copy = Assignment.objects.get(
                materialised_from=member, materialised_for=gang.founding
            )
            assert copy.gang_id == gang.pk
            assert copy.miniature_root_id is None
        settled(gang)

    def test_an_option_sets_members_are_tagged_for_the_carrier_that_took_it(
        self, gang, person_type, gang_type, default_pack
    ):
        profile = create_profile("Chooser", person_type, gang_type, price=100)
        offer_option(profile, "Plain", thing=create_rule("Plain Style"))
        fancy = offer_option(profile, "Fancy", thing=create_rule("Fancy Style"))
        fancy_style = fancy.default_set.members.get()
        took_it = hire_with_option(gang, profile, "Ana", option=fancy.default_set)
        went_plain = hire_with_option(gang, profile, "Bea")
        strip_provenance(gang)

        record = run_backfill()

        assert record.summary["totals"]["granted"] == 0
        assert record.summary["totals"]["unmatched"] == 0
        assert Assignment.objects.filter(
            materialised_from=fancy_style, materialised_for=took_it.membership
        ).exists()
        assert not Assignment.objects.filter(
            materialised_from=fancy_style, materialised_for=went_plain.membership
        ).exists()
        assert not legacy_grants(gang).exists()
        settled(gang)

    def test_a_built_in_and_an_option_naming_the_same_gun_each_keep_their_own_copy(
        self, gang, person_type, gang_type, default_pack
    ):
        """The built-ins materialise first, so the older copy is the
        built-in's and the newer the option's — and dropping the option
        later must take only its own copy."""
        autopistol = create_weapon("Autopistol", profiles=[("Standard", 0)], price=10)
        profile = create_profile("Pistolier", person_type, gang_type, price=50)
        built_in = add_built_in(profile, autopistol)
        plain = offer_option(profile, "Plain", thing=create_rule("Plain Style"))
        twin = offer_option(profile, "Second pistol", thing=autopistol)
        twin_member = twin.default_set.members.get()
        fighter = hire_with_option(gang, profile, "Ana", option=twin.default_set)
        strip_provenance(gang)

        run_backfill()

        older, newer = Assignment.objects.filter(
            miniature_root=fighter, weapon=autopistol
        ).order_by("pk")
        assert older.materialised_from_id == built_in.pk
        assert newer.materialised_from_id == twin_member.pk

        with operation(gang, actor=gang.owner) as op:
            op.rechoose(fighter.membership, option=plain.default_set)

        older.refresh_from_db()
        newer.refresh_from_db()
        assert older.archived is False
        assert newer.archived is True
        settled(gang)

    def test_two_options_naming_the_same_thing_each_unwind_their_own_copy(
        self, gang, person_type, gang_type, default_pack
    ):
        """Two chosen sets naming one thing pair deterministically: the
        set recorded last claims the newest copy, so each copy leaves
        with the set that brought it."""
        grit = create_rule("Grit")
        profile = create_profile("Stubborn", person_type, gang_type, price=50)
        first = offer_option(profile, "First grit", thing=grit)
        extra = create_option_group(profile, "Extra", choose="any")
        second = offer_option(profile, "Second grit", thing=grit, group=extra)
        first_member = first.default_set.members.get()
        second_member = second.default_set.members.get()
        fighter = hire_with_option(
            gang, profile, "Ana", option=[first.default_set, second.default_set]
        )
        strip_provenance(gang)

        record = run_backfill()

        assert record.summary["totals"]["ambiguous"] == 0
        older, newer = Assignment.objects.filter(
            miniature_root=fighter, rule=grit
        ).order_by("pk")
        recorded_last = fighter.membership.chosen_options.order_by("-pk").first()
        assert recorded_last.default_set_id == second.default_set.pk
        assert older.materialised_from_id == first_member.pk
        assert newer.materialised_from_id == second_member.pk

        with operation(gang, actor=gang.owner) as op:
            op.rechoose(fighter.membership, option=[first.default_set])

        older.refresh_from_db()
        newer.refresh_from_db()
        assert older.archived is False
        assert newer.archived is True
        settled(gang)


class TestWhatTheOwnerAlreadySettled:
    """A grant the owner sold is tagged where it lies, so it is never
    handed back; a thing the model already holds another way is not
    duplicated, and the carrier is named."""

    def test_a_sold_built_in_is_tagged_and_not_granted_again(
        self, gang, ganger, launcher
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        gun = Assignment.objects.get(miniature_root=fighter, weapon=launcher)
        sell(gun)
        strip_provenance(gang)
        credits = settled(gang).credits

        record = run_backfill()

        assert record.summary["totals"]["tagged"] == 2
        assert record.summary["totals"]["granted"] == 0
        gun.refresh_from_db()
        assert gun.archived is True
        assert gun.materialised_for_id == fighter.membership.pk
        assert not Assignment.objects.filter(
            miniature_root=fighter, weapon=launcher, archived=False
        ).exists()
        assert settled(gang).credits == credits

    def test_a_member_the_model_holds_as_a_reward_is_skipped_and_named(
        self, gang, ganger, default_pack
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        strip_provenance(gang)
        nerves = create_skill("Nerves of Steel")
        learn(fighter, nerves)
        member = add_built_in(ganger, nerves)
        rating = settled(gang).rating

        record = run_backfill()

        assert record.status == Backfill.Status.DONE
        assert record.summary["totals"]["granted"] == 0
        assert record.summary["totals"]["held_another_way"] == 1
        assert record.summary["held_another_way"] == [
            "Ana (Ganger) already holds Nerves of Steel another way"
        ]
        assert not Assignment.objects.filter(materialised_from=member).exists()
        held = Assignment.objects.filter(
            miniature_root=fighter, skill=nerves, archived=False
        )
        assert held.count() == 1
        assert held.get().ledger_entry.reason == Reason.REWARD
        assert settled(gang).rating == rating

    def test_a_legacy_ammo_line_under_the_gun_is_not_granted_twice(
        self, gang, person_type, gang_type, default_pack, launcher
    ):
        """A set's ammo member materialised before provenance existed
        looks exactly like the gun's own free line — caused by the gun,
        reason DEFAULT — so tagging leaves it alone; catch-up must still
        see it under the gun rather than stack a second."""
        from n26.library.models import WeaponProfile

        smoke = WeaponProfile.objects.create(
            name="Smoke", weapon=launcher, price=10, position=1
        )
        profile = create_profile("Gunner", person_type, gang_type, price=50)
        gun_member = add_built_in(profile, launcher)
        ammo_member = add_built_in(profile, smoke, gun_member=gun_member)
        fighter = hire(gang, profile, "Ana", paid=50)
        strip_provenance(gang)
        rating = settled(gang).rating

        record = run_backfill()

        assert record.status == Backfill.Status.DONE
        assert record.summary["totals"]["granted"] == 0
        assert record.summary["held_another_way"] == [
            "Ana (Gunner) already carries Smoke under its Launcher"
        ]
        gun = Assignment.objects.get(
            materialised_from=gun_member, materialised_for=fighter.membership
        )
        lines = Assignment.objects.filter(
            parent=gun, weapon_profile=smoke, archived=False
        )
        assert lines.count() == 1
        assert lines.get().materialised_from_id is None
        assert not Assignment.objects.filter(materialised_from=ammo_member).exists()
        assert settled(gang).rating == rating


class TestRunningTwice:
    """The walk is idempotent: a second run tags nothing and grants
    nothing."""

    def test_a_second_run_finds_nothing_to_do(self, gang, ganger, default_pack):
        hire(gang, ganger, "Ana", paid=50)
        strip_provenance(gang)
        add_built_in(ganger, create_rule("Late Addition"))
        first = run_backfill()
        assert first.summary["totals"]["tagged"] == 2
        assert first.summary["totals"]["granted"] == 1
        assignments = Assignment.objects.filter(gang_root=gang).count()
        events = LedgerEvent.objects.filter(gang=gang).count()

        second = run_backfill()

        assert second.status == Backfill.Status.DONE
        assert second.summary["totals"]["tagged"] == 0
        assert second.summary["totals"]["granted"] == 0
        assert Assignment.objects.filter(gang_root=gang).count() == assignments
        assert LedgerEvent.objects.filter(gang=gang).count() == events
        settled(gang)


class TestTheConsoleDoor:
    """The operation is registered under its label, and its page says
    what a run would walk without writing anything."""

    @pytest.fixture
    def superuser(self, db):
        return User.objects.create_superuser("boss", "boss@example.com", "password")

    def test_the_operation_is_registered_and_named(self):
        registered = {op.operation for op in operations()}

        assert Operation.BACKFILL_BUILT_INS.value in registered
        found = resolve_operation(Operation.BACKFILL_BUILT_INS.value)
        assert found.name == Operation.BACKFILL_BUILT_INS.label
        assert found.view is backfill_built_ins_view

    def test_its_page_counts_the_legacy_grants_and_writes_nothing(
        self, client, superuser, gang, ganger
    ):
        hire(gang, ganger, "Ana", paid=50)
        strip_provenance(gang)
        client.force_login(superuser)

        response = client.get(reverse("admin:maintenance_n26_backfill_built_ins"))

        page = response.content.decode()
        assert response.status_code == 200
        assert "1 gang would be walked" in page
        assert "2 grants still without provenance" in page
        assert "a weapon's own firing lines — left alone" in page
        assert not Backfill.objects.exists()
        assert legacy_grants(gang).count() == 2
