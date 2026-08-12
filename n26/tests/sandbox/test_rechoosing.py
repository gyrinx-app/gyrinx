"""Changing an option after the hire — the later edit ChosenProfileOption
was stored for.

``op.rechoose`` swaps which of its sets a carrier is taken with: the
departing set's rows leave the way a refund leaves, the arriving set
materialises exactly as at hire, and the price difference lands on the
carrier's own entry as one amendment — on paid and list and rating
alike, in either direction. Everything here reconciles after every act,
because the books are the point of doing this as an operation.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.models import Assignment, LedgerEvent
from n26.core.operations import NotEnoughCredits, operation
from n26.core.reconcile import assert_reconciled
from n26.library.models import Profile
from n26.tests.sandbox.actions import (
    create_default_set,
    create_option_group,
    create_wargear,
    create_weapon,
    found_gang,
    hire_with_option,
    offer_option,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def player():
    return User.objects.create_user("tom")


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Bad Girls", gang_type, owner=player, budget=1000)


@pytest.fixture
def weapons(default_pack):
    return {
        name: create_weapon(name, profiles=[("Attack", 0)])
        for name in (
            "Chemical cloud breath",
            "Gaseous eruption breath",
            "Talons",
            "Razor-sharp talons",
        )
    }


@pytest.fixture
def khimerix(person_type, gang_type, weapons, default_pack):
    """A profile with one choose-one group of three priced sets."""
    profile = Profile.objects.create(
        name="Khimerix", profile_type=person_type, gang_type=gang_type, price=210
    )
    for position, (name, members, price) in enumerate(
        [
            ("Standard Khimerix", ["Chemical cloud breath", "Talons"], 0),
            ("Eruption breath", ["Gaseous eruption breath", "Talons"], 25),
            (
                "Eruption and razors",
                ["Gaseous eruption breath", "Razor-sharp talons"],
                50,
            ),
        ]
    ):
        offer_option(
            profile,
            name,
            default_set=create_default_set(
                name, members=[weapons[n] for n in members], price=price
            ),
            position=position,
        )
    return profile


def sets_of(profile):
    """The profile's sets by name, for naming a selection in a test."""
    return {
        option.default_set.name: option.default_set for option in profile.options.all()
    }


def weapon_names(miniature):
    return sorted(
        assignment.assignable.name
        for assignment in Assignment.objects.filter(
            miniature_root=miniature, archived=False, weapon__isnull=False
        )
    )


def rechoose(gang, miniature, option):
    with operation(gang, actor=gang.owner) as op:
        op.rechoose(miniature.membership, option=option)


class TestSwappingAChoice:
    def test_the_new_sets_rows_arrive_and_the_old_ones_leave(self, gang, khimerix):
        beast = hire_with_option(gang, khimerix, "Vhast")
        assert weapon_names(beast) == ["Chemical cloud breath", "Talons"]

        rechoose(gang, beast, sets_of(khimerix)["Eruption and razors"])

        assert weapon_names(beast) == [
            "Gaseous eruption breath",
            "Razor-sharp talons",
        ]
        assert_reconciled(gang)

    def test_the_difference_is_charged_on_the_carriers_own_line(self, gang, khimerix):
        beast = hire_with_option(gang, khimerix, "Vhast")
        gang.refresh_from_db()
        cash = gang.credits
        entry = beast.membership.ledger_entry

        rechoose(gang, beast, sets_of(khimerix)["Eruption and razors"])

        gang.refresh_from_db()
        entry.refresh_from_db()
        beast.refresh_from_db()
        assert gang.credits == cash - 50
        assert entry.paid == 210 + 50
        assert entry.list_price == 210 + 50
        assert entry.rating_contribution == 210 + 50
        assert beast.rating == 260
        assert_reconciled(gang)

    def test_changing_back_returns_the_difference(self, gang, khimerix):
        beast = hire_with_option(
            gang, khimerix, "Vhast", option=sets_of(khimerix)["Eruption breath"]
        )
        gang.refresh_from_db()
        cash = gang.credits

        rechoose(gang, beast, sets_of(khimerix)["Standard Khimerix"])

        gang.refresh_from_db()
        assert gang.credits == cash + 25
        assert weapon_names(beast) == ["Chemical cloud breath", "Talons"]
        assert_reconciled(gang)

    def test_the_record_of_what_is_taken_follows(self, gang, khimerix):
        beast = hire_with_option(gang, khimerix, "Vhast")
        eruption = sets_of(khimerix)["Eruption breath"]

        rechoose(gang, beast, eruption)

        taken = [row.default_set for row in beast.membership.chosen_options.all()]
        assert taken == [eruption]

    def test_naming_what_is_already_taken_changes_nothing(self, gang, khimerix):
        eruption = sets_of(khimerix)["Eruption breath"]
        beast = hire_with_option(gang, khimerix, "Vhast", option=eruption)
        events = LedgerEvent.objects.count()
        rows = Assignment.objects.count()

        rechoose(gang, beast, eruption)

        assert LedgerEvent.objects.count() == events
        assert Assignment.objects.count() == rows
        assert_reconciled(gang)

    def test_a_set_the_profile_does_not_offer_is_refused(self, gang, khimerix):
        beast = hire_with_option(gang, khimerix, "Vhast")
        stray = create_default_set("Someone else's kit", price=5)

        with pytest.raises(ValueError):
            rechoose(gang, beast, stray)
        assert_reconciled(gang)

    def test_an_upgrade_the_gang_cannot_afford_unwinds_whole(self, gang, khimerix):
        beast = hire_with_option(gang, khimerix, "Vhast")
        gang.starting_credits = 210
        gang.save(update_fields=["starting_credits"])
        with operation(gang, actor=gang.owner) as op:
            op.settle()
        gang.refresh_from_db()
        assert gang.credits == 0

        with pytest.raises(NotEnoughCredits):
            rechoose(gang, beast, sets_of(khimerix)["Eruption and razors"])

        # The instances carry the unwound operation's in-memory repins;
        # what the books say is what the database kept.
        gang.refresh_from_db()
        beast.refresh_from_db()
        assert weapon_names(beast) == ["Chemical cloud breath", "Talons"]
        taken = [row.default_set.name for row in beast.membership.chosen_options.all()]
        assert taken == ["Standard Khimerix"]
        assert_reconciled(gang)

    def test_a_rechosen_fighter_matches_a_fresh_hire(self, gang, khimerix):
        """The equivalence that makes this safe to offer: changing your
        mind lands exactly where deciding right the first time did."""
        eruption = sets_of(khimerix)["Eruption and razors"]
        changed = hire_with_option(gang, khimerix, "Changed")
        rechoose(gang, changed, eruption)
        decided = hire_with_option(gang, khimerix, "Decided", option=eruption)

        assert weapon_names(changed) == weapon_names(decided)
        changed.refresh_from_db()
        decided.refresh_from_db()
        assert changed.rating == decided.rating
        assert (
            changed.membership.ledger_entry.paid == decided.membership.ledger_entry.paid
        )
        assert_reconciled(gang)


class TestWhatTheDepartingSetTookAlong:
    def test_paid_kit_inside_a_departing_row_is_refunded(self, gang, khimerix):
        """A sight bought onto an option's weapon comes back when the
        option goes: the money was the player's, and the row it rode
        leaves the roster."""
        beast = hire_with_option(gang, khimerix, "Vhast")
        talons = Assignment.objects.get(
            miniature_root=beast, weapon__name="Talons", archived=False
        )
        sight = create_wargear("Targeting charm", price=15)
        with operation(gang, actor=gang.owner) as op:
            op.assign(sight, parent=talons, paid=15)
        gang.refresh_from_db()
        cash = gang.credits

        rechoose(gang, beast, sets_of(khimerix)["Eruption and razors"])

        gang.refresh_from_db()
        # 15 back for the charm, 50 out for the dearer option.
        assert gang.credits == cash + 15 - 50
        charm = Assignment.objects.get(wargear=sight)
        assert charm.archived is True
        assert_reconciled(gang)


class TestAmmoRidesTheRightGun:
    @pytest.fixture
    def gunner(self, person_type, gang_type, default_pack):
        """Built-ins bring the launcher; an any-of option adds paid ammo
        for it — the set grants a profile of a gun it does not bring."""
        from n26.library.models import WeaponProfile

        launcher = create_weapon("Grenade launcher", profiles=[("Frag", 0)])
        # Priced, so it is not a free profile the gun auto-grants: the
        # option set is the only way this round arrives.
        smoke = WeaponProfile.objects.create(
            name="Smoke", weapon=launcher, price=10, position=1
        )
        profile = Profile.objects.create(
            name="Gunner", profile_type=person_type, gang_type=gang_type, price=100
        )
        profile.built_ins = create_default_set("Gunner kit", members=[launcher])
        profile.save()
        extras = create_option_group(profile, "Extras", choose="any")
        offer_option(
            profile,
            "Smoke rounds",
            default_set=create_default_set("Smoke rounds", members=[smoke], price=10),
            group=extras,
        )
        return profile, smoke

    def test_an_arriving_sets_ammo_lands_under_the_standing_gun(self, gang, gunner):
        profile, smoke = gunner
        fighter = hire_with_option(gang, profile, "Boom")
        gun = Assignment.objects.get(
            miniature_root=fighter, weapon__isnull=False, archived=False
        )

        rechoose(gang, fighter, sets_of(profile)["Smoke rounds"])

        round_ = Assignment.objects.get(
            weapon_profile=smoke, miniature_root=fighter, archived=False
        )
        assert round_.caused_by_id == gun.pk
        assert round_.parent_id == gun.pk
        assert_reconciled(gang)

    def test_and_leaves_it_when_the_set_goes(self, gang, gunner):
        profile, smoke = gunner
        fighter = hire_with_option(
            gang, profile, "Boom", option=sets_of(profile)["Smoke rounds"]
        )
        gang.refresh_from_db()
        cash = gang.credits

        rechoose(gang, fighter, [])

        assert not Assignment.objects.filter(
            weapon_profile=smoke, miniature_root=fighter, archived=False
        ).exists()
        # The gun the built-ins brought stays.
        assert Assignment.objects.filter(
            miniature_root=fighter, weapon__isnull=False, archived=False
        ).exists()
        gang.refresh_from_db()
        assert gang.credits == cash + 10
        assert_reconciled(gang)
