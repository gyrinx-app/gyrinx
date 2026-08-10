"""What a profile comes with, and what may be chosen instead.

The Khimerix is the shape this proves. It carries chemical cloud breath
and talons as built-ins, and offers two swaps when it joins a roster:
gaseous eruption breath for the breath, razor-sharp talons for the
talons, each at +25.

Nothing is ever *replaced*. A choice decides which set materialises at
hire, and the option not taken simply never comes into being — which is
what keeps this clear of v1's inherited-then-overridden mess.

Two independent picks are modelled as the combinations, because the choice
is one-of. A profile is ``(built_ins, [options])``: the built-ins always
come, and the head of the options list is what a hire takes unasked.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.models import Assignment, ChosenProfileOption, Reason
from n26.core.reconcile import assert_reconciled, ledger_for_gang
from n26.core.render import build_model_card
from n26.core.render_text import render_model_card
from n26.library.models import Profile
from n26.tests.sandbox.actions import (
    create_default_set,
    create_subtype,
    create_weapon,
    found_gang,
    hire_with_option,
    offer_option,
    remove,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def player():
    return User.objects.create_user("tom")


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Bad Girls", gang_type, owner=player, budget=1000)


@pytest.fixture
def weapons(db):
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
    """Cost lives on the profile; the option sets price the alternatives."""
    profile = Profile.objects.create(
        name="Khimerix", profile_type=person_type, gang_type=gang_type, price=210
    )
    profile.built_ins = create_default_set(
        "Khimerix built-ins", members=[create_subtype("Exotic Beast")]
    )
    profile.save()

    # The head of the list is the default — a profile is (built_ins, [options]).
    for position, (name, members, price) in enumerate(
        [
            ("Standard Khimerix", ["Chemical cloud breath", "Talons"], 0),
            ("Eruption breath", ["Gaseous eruption breath", "Talons"], 25),
            ("Razor talons", ["Chemical cloud breath", "Razor-sharp talons"], 25),
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


def weapon_names(miniature):
    return sorted(w.name for w in build_model_card(miniature).weapons)


class TestTheDefaultHire:
    def test_it_comes_with_its_built_ins_and_default_option(self, gang, khimerix):
        beast = hire_with_option(gang, khimerix, "Growler")
        card = build_model_card(beast)

        assert card.type_line == "Fighter (Exotic Beast)"
        assert weapon_names(beast) == ["Chemical cloud breath", "Talons"]

    def test_the_advertised_price_is_charged(self, gang, khimerix):
        beast = hire_with_option(gang, khimerix, "Growler")
        assert khimerix.price_with() == 210
        assert beast.membership.ledger_entry.paid == 210

    def test_the_items_themselves_are_free(self, gang, khimerix):
        hire_with_option(gang, khimerix, "Growler")
        entries = {str(e.assignable): e for e in ledger_for_gang(gang) if e.paid == 0}
        assert entries["Talons"].reason == Reason.DEFAULT
        assert entries["Talons"].rating_contribution == 0

    def test_default_weapons_carry_their_profiles(self, gang, khimerix):
        """However a weapon arrives, it is the same weapon.

        Granted kit used to land without its free profiles, so a Khimerix's
        talons drew as a bare nameplate with no statline and no traits while
        an identical bought weapon drew in full.
        """
        beast = hire_with_option(gang, khimerix, "Growler")
        card = build_model_card(beast)
        for weapon in card.weapons:
            assert weapon.profiles, f"{weapon.name} has no profile lines"

    def test_they_are_caused_by_the_hire(self, gang, khimerix):
        beast = hire_with_option(gang, khimerix, "Growler")
        for assignment in Assignment.objects.filter(miniature=beast):
            assert assignment.caused_by == beast.membership


class TestChoosingAnOption:
    def test_picking_one_swaps_what_materialises(self, gang, khimerix):
        razors = khimerix.options.get(default_set__name="Razor talons").default_set
        beast = hire_with_option(gang, khimerix, "Growler", option=razors)

        assert weapon_names(beast) == [
            "Chemical cloud breath",
            "Razor-sharp talons",
        ]

    def test_the_option_not_taken_never_existed(self, gang, khimerix):
        """Not removed, not archived — simply never created."""
        razors = khimerix.options.get(default_set__name="Razor talons").default_set
        hire_with_option(gang, khimerix, "Growler", option=razors)

        assert not Assignment.objects.filter(weapon__name="Talons").exists()
        assert Assignment.objects.filter(archived=True).count() == 0

    def test_the_surcharge_lands_on_the_hire_line(self, gang, khimerix):
        razors = khimerix.options.get(default_set__name="Razor talons").default_set
        beast = hire_with_option(gang, khimerix, "Growler", option=razors)

        entry = beast.membership.ledger_entry
        assert entry.paid == 235  # 210 + 25
        assert entry.rating_contribution == 235
        # And the swapped-in weapon is still free.
        razor_entry = next(
            e
            for e in ledger_for_gang(gang)
            if str(e.assignable) == "Razor-sharp talons"
        )
        assert razor_entry.paid == 0

    def test_both_picks_at_once(self, gang, khimerix):
        both = khimerix.options.get(default_set__name="Eruption and razors").default_set
        beast = hire_with_option(gang, khimerix, "Growler", option=both)

        assert weapon_names(beast) == [
            "Gaseous eruption breath",
            "Razor-sharp talons",
        ]
        assert beast.membership.ledger_entry.paid == 260

    def test_the_pick_is_recorded(self, gang, khimerix):
        razors = khimerix.options.get(default_set__name="Razor talons").default_set
        beast = hire_with_option(gang, khimerix, "Growler", option=razors)

        assert [c.default_set for c in beast.membership.chosen_options.all()] == [
            razors
        ]
        assert ChosenProfileOption.objects.count() == 1

    def test_built_ins_come_regardless(self, gang, khimerix):
        both = khimerix.options.get(default_set__name="Eruption and razors").default_set
        beast = hire_with_option(gang, khimerix, "Growler", option=both)
        assert build_model_card(beast).type_line == "Fighter (Exotic Beast)"

    def test_the_gang_adds_up(self, gang, khimerix):
        razors = khimerix.options.get(default_set__name="Razor talons").default_set
        hire_with_option(gang, khimerix, "Growler", option=razors)
        gang.refresh_from_db()

        assert gang.rating == 235
        assert gang.credits == 1000 - 235
        assert_reconciled(gang)


class TestPricingIsAdditive:
    def test_the_cost_may_live_on_the_built_ins_instead(
        self, gang, person_type, gang_type, weapons
    ):
        """Every profile has built-ins, so they can carry the price."""
        profile = Profile.objects.create(
            name="Cheap beast",
            profile_type=person_type,
            gang_type=gang_type,
            price=0,
        )
        profile.built_ins = create_default_set(
            "Cheap beast built-ins", members=[weapons["Talons"]], price=90
        )
        profile.save()

        beast = hire_with_option(gang, profile, "Snapper")
        assert profile.price_with() == 90
        assert beast.membership.ledger_entry.paid == 90

    def test_a_profile_with_no_sets_still_works(self, gang, make_profile):
        """Everything before this round had neither slot filled."""
        plain = make_profile("Escher Ganger", price=55)
        fighter = hire_with_option(gang, plain, "Yolanda")
        assert fighter.membership.ledger_entry.paid == 55
        assert build_model_card(fighter).weapons == []


class TestChoicesAreNotForced:
    def test_a_profile_may_offer_nothing(self, gang, make_profile):
        assert make_profile("Plain").offers_a_choice is False

    def test_a_profile_with_no_options_has_no_default(self, gang, make_profile):
        """Derived from the list, so an empty list means no default."""
        plain = make_profile("Plain", price=40)
        assert plain.default_option is None
        assert plain.option_sets() == []

        fighter = hire_with_option(gang, plain, "Nobody")
        assert build_model_card(fighter).weapons == []
        assert fighter.membership.ledger_entry.paid == 40

    def test_options_are_listed_default_first(self, gang, khimerix):
        names = [s.name for s in khimerix.option_sets()]
        assert names[0] == "Standard Khimerix"
        assert khimerix.offers_a_choice is True


class TestAnOptionalPick:
    """A one-or-none set — the book's "may take one of the following".

    The alternatives exclude each other, and taking neither is fine:
    nothing is taken unless the player picks it, so the advertised
    price never includes it.
    """

    @pytest.fixture
    def grenadier(self, person_type, gang_type, default_pack):
        from n26.library.authoring import create_option_group

        profile = Profile.objects.create(
            name="Grenadier",
            profile_type=person_type,
            gang_type=gang_type,
            price=100,
        )
        maybe = create_option_group(profile, "A grenade", choose="one-or-none")
        for position, (name, price) in enumerate([("Choke gas", 15), ("Stun", 10)]):
            offer_option(
                profile,
                name,
                default_set=create_default_set(
                    name, members=[create_weapon(name + " grenades")], price=price
                ),
                group=maybe,
                position=position,
            )
        return profile

    def test_nothing_is_taken_unasked(self, gang, grenadier):
        assert grenadier.resolve_selection() == []
        assert grenadier.price_with() == 100

        fighter = hire_with_option(gang, grenadier, "Vex")
        assert weapon_names(fighter) == []
        assert fighter.membership.ledger_entry.paid == 100
        assert_reconciled(gang)

    def test_picking_one_takes_it_and_charges_it(self, gang, grenadier):
        choke = next(
            s
            for s in (o.default_set for o in grenadier.options.all())
            if s.name == "Choke gas"
        )
        assert grenadier.resolve_selection(choke) == [choke]
        assert grenadier.price_with(choke) == 115

        fighter = hire_with_option(gang, grenadier, "Vex", option=choke)
        assert weapon_names(fighter) == ["Choke gas grenades"]
        assert fighter.membership.ledger_entry.paid == 115
        assert_reconciled(gang)

    def test_two_from_the_set_are_refused(self, gang, grenadier):
        both = [o.default_set for o in grenadier.options.all()]
        with pytest.raises(ValueError, match="at most one"):
            grenadier.resolve_selection(both)


class TestRemoval:
    def test_removing_the_hire_takes_its_kit(self, gang, khimerix):
        beast = hire_with_option(gang, khimerix, "Growler")
        remove(beast.membership)

        assert (
            Assignment.objects.filter(archived=False, gang_type__isnull=True).count()
            == 0
        )
        gang.refresh_from_db()
        assert gang.rating == 0
        assert_reconciled(gang)


class TestRendering:
    def test_the_card_shows_what_materialised(self, gang, khimerix):
        razors = khimerix.options.get(default_set__name="Razor talons").default_set
        beast = hire_with_option(gang, khimerix, "Growler", option=razors)
        text = "\n".join(render_model_card(build_model_card(beast)))
        print("\n" + text)

        assert "Growler — 235cr" in text
        assert "Fighter (Exotic Beast)" in text
        # Kit that came with the hire carries no number: its value is
        # inside the fighter's own line, and a zero would read as "free".
        assert "Razor-sharp talons" in text
        assert "— 0cr" not in text
        assert "Talons — " not in text.replace("Razor-sharp talons", "")
