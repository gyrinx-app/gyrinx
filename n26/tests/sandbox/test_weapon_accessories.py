"""Weapon accessories: wargear that changes the gun it hangs off.

The book's seven accessories (topic 19) attach one-per-weapon and modify
that weapon — a telescopic sight improves its short range, suspensors
change its handling. Structurally an accessory was always expressible
(a wargear assigned with the weapon's assignment as parent); what was
missing was a scope meaning "the weapon I am attached to" —
``TargetsAttachedWeapon``, positional rather than factual, anchored on
the carrier node so two identical sights each reach their own gun.

Deferred with the weapon-slots feature: suspensors' slot-cost change.
One-per-weapon is informational, later.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card
from n26.tests.sandbox.actions import (
    attach,
    changes_stat,
    create_stat,
    create_trait,
    create_weapon,
    create_weapon_accessory,
    found_gang,
    give_weapon,
    hire_with_option,
    modifier,
    move,
    remove,
    sell,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def short_range(db):
    return create_stat("SR", "Short Range", is_inches=True)


@pytest.fixture
def weapon_stats(short_range, default_pack):
    from n26.tests.sandbox.actions import create_statline_type

    return create_statline_type("Weapon statline", [short_range])


@pytest.fixture
def sight(short_range):
    """A telescopic sight: +6 short range on the weapon it is fitted to."""
    from n26.library.models import TargetsAttachedWeapon

    accessory = create_weapon_accessory("Telescopic sight", price=25)
    modifier(
        "Telescopic sight lengthens short range",
        TargetsAttachedWeapon.objects.create(),
        changes_stat(short_range, mode="improve", amount=6),
        carried_by=accessory,
    )
    return accessory


@pytest.fixture
def gang(gang_type):
    return found_gang(
        "The Bad Girls", gang_type, owner=User.objects.create_user("t"), budget=1000
    )


@pytest.fixture
def ganger(make_profile):
    """One profile, hired more than once — two of the same entry would
    trip the library's unique name."""
    return make_profile("Ganger", price=50)


@pytest.fixture
def fighter(gang, ganger):
    return hire_with_option(gang, ganger, "Yolanda")


@pytest.fixture
def second_fighter(gang, ganger):
    return hire_with_option(gang, ganger, "Nell")


def make_gun(name, weapon_stats):
    from n26.tests.sandbox.actions import set_statline

    gun = create_weapon(name, profiles=[("Standard", 0)], statline_type=weapon_stats)
    set_statline(gun.profiles.get(), short_range=8)
    return gun


def reconciled(gang):
    """Check the books against the database rather than the caller's copy.

    An operation repins the gang it looked up, which is never the object
    a fixture is holding — so a test that handed its own copy over would
    be comparing a stale cache with a fresh sum and failing for that.
    """
    from n26.core.models import Gang

    assert_reconciled(Gang.objects.get(pk=gang.pk))


def books(gang):
    """The gang, its stash and its credits as they now stand."""
    from n26.core.models import Gang

    return Gang.objects.select_related("stash").get(pk=gang.pk)


def drawn(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([n.assignable for n in card.all_nodes()])
    return build_model_card(miniature, card=card, computed=compute(card, index))


class TestAnAccessory:
    def test_it_reaches_only_its_own_weapon(self, fighter, sight, weapon_stats):
        """The point of the scope: two guns, one sight — one changed."""
        scoped = give_weapon(fighter, make_gun("Lasgun", weapon_stats), paid=15)
        give_weapon(fighter, make_gun("Autogun", weapon_stats), paid=20)
        attach(scoped, sight, paid=25)

        card = drawn(fighter)
        by_name = {w.name: w for w in card.weapons}
        assert by_name["Lasgun"].profiles[0].statline.get("SR").value == '14"'
        assert by_name["Autogun"].profiles[0].statline.get("SR").value == '8"'

    def test_the_change_names_its_source(self, fighter, sight, weapon_stats):
        gun = give_weapon(fighter, make_gun("Lasgun", weapon_stats), paid=15)
        attach(gun, sight, paid=25)

        cell = drawn(fighter).weapons[0].profiles[0].statline.get("SR")
        assert [p.source for p in cell.modified_by] == ["Telescopic sight"]

    def test_it_draws_under_its_weapon_and_counts_its_price(
        self, fighter, sight, weapon_stats
    ):
        gun = give_weapon(fighter, make_gun("Lasgun", weapon_stats), paid=15)
        attach(gun, sight, paid=25)

        card = drawn(fighter)
        (line,) = card.weapons[0].accessories
        assert line.name == "Telescopic sight"
        assert line.rating == 25
        # It goes where the gun goes, so it counts in what the gun is
        # worth — a screen totalling weapons must not leave it unaccounted
        # for on the fighter.
        assert card.weapons[0].extras_rating == 25
        assert card.weapons[0].total_rating == 40
        fighter.refresh_from_db()
        assert fighter.rating == 50 + 15 + 25

    def test_two_sights_on_two_guns_stay_apart(self, fighter, sight, weapon_stats):
        """One content row, two attachments — each anchored to its node."""
        first = give_weapon(fighter, make_gun("Lasgun", weapon_stats), paid=15)
        second = give_weapon(fighter, make_gun("Autogun", weapon_stats), paid=20)
        attach(first, sight, paid=25)
        attach(second, sight, paid=25)

        card = drawn(fighter)
        values = {w.name: w.profiles[0].statline.get("SR").value for w in card.weapons}
        assert values == {"Lasgun": '14"', "Autogun": '14"'}

    def test_removing_the_weapon_takes_the_accessory(
        self, fighter, sight, weapon_stats
    ):
        gun = give_weapon(fighter, make_gun("Lasgun", weapon_stats), paid=15)
        attach(gun, sight, paid=25)
        remove(gun)

        assert drawn(fighter).weapons == []
        fighter.refresh_from_db()
        assert fighter.rating == 50

    def test_it_renders(self, fighter, sight, weapon_stats):
        from n26.core.render_text import render_model_card

        gun = give_weapon(fighter, make_gun("Lasgun", weapon_stats), paid=15)
        attach(gun, sight, paid=25)

        text = "\n".join(render_model_card(drawn(fighter)))
        print("\n" + text)
        assert "+ Telescopic sight" in text
        assert 'SR 14"' in text

    def test_an_accessory_can_also_add_a_trait(self, fighter, weapon_stats):
        from n26.library.models import TargetsAttachedWeapon
        from n26.tests.sandbox.actions import adds

        stabiliser = create_weapon_accessory("Gun stabiliser", price=30)
        modifier(
            "Stabiliser steadies the weapon",
            TargetsAttachedWeapon.objects.create(),
            adds(create_trait("Steady")),
            carried_by=stabiliser,
        )
        gun = give_weapon(fighter, make_gun("Lasgun", weapon_stats), paid=15)
        attach(gun, stabiliser)

        profile_line = drawn(fighter).weapons[0].profiles[0]
        assert "Steady" in [t.name for t in profile_line.traits]


class TestWhatFitsWhere:
    """The bracket in the accessory's name, as data — informing, never
    policing. "Focusing Crystal (Las Weapons Only)" is a home-category
    restriction; "Suspensors (Weapons Marked With * Only)" is the
    two-slot asterisk."""

    @pytest.fixture
    def las_weapons(self, db):
        from n26.tests.sandbox.actions import create_category

        return create_category("Ranged Weapons", "Las Weapons", 0)

    def test_the_bracket_compiles(self, las_weapons):
        crystal = create_weapon_accessory("Focusing Crystal", fits_category=las_weapons)
        suspensors = create_weapon_accessory("Suspensors", fits_asterisked=True)
        sight = create_weapon_accessory("Mono-Sight")

        assert str(crystal.fits_selector()) == "homed in Las Weapons"
        assert str(suspensors.fits_selector()) == "takes 2 slots"
        assert str(sight.fits_selector()) == "anything"

    def test_fits_answers_per_weapon(self, las_weapons, weapon_stats):
        crystal = create_weapon_accessory("Focusing Crystal", fits_category=las_weapons)
        suspensors = create_weapon_accessory("Suspensors", fits_asterisked=True)

        lasgun = create_weapon(
            "Lasgun", profiles=[("Standard", 0)], category=las_weapons
        )
        heavy = create_weapon("Heavy stubber", profiles=[("Standard", 0)], slots=2)

        assert crystal.fits(lasgun) is True
        assert crystal.fits(heavy) is False
        assert suspensors.fits(heavy) is True
        assert suspensors.fits(lasgun) is False

    def test_browsing_for_a_weapon_notes_what_will_not_fit(
        self, las_weapons, weapon_stats
    ):
        from n26.core.browse import browse, with_fit_notes
        from n26.tests.sandbox.actions import create_collection

        crystal = create_weapon_accessory(
            "Focusing Crystal",
            annotation="Las Weapons Only",
            fits_category=las_weapons,
            price=25,
        )
        sight = create_weapon_accessory("Telescopic sight", price=25)
        post = create_collection("Trading Post", entries=[crystal, sight])
        heavy = create_weapon("Heavy stubber", profiles=[("Standard", 0)], slots=2)

        view = with_fit_notes(browse(post), heavy)
        by_name = {line.thing.name: line.notes for line in view.all_lines()}

        assert by_name["Telescopic sight"] == ()
        (note,) = by_name["Focusing Crystal"]
        assert note.about == crystal
        assert "homed in Las Weapons only" in note.text

    def test_attaching_anyway_is_still_allowed(
        self, las_weapons, fighter, weapon_stats
    ):
        """Inform, never police: the note is for the shop; the owner
        may bolt anything to anything."""
        crystal = create_weapon_accessory("Focusing Crystal", fits_category=las_weapons)
        heavy = give_weapon(fighter, make_gun("Heavy stubber", weapon_stats), paid=70)

        attached = attach(heavy, crystal, paid=25)
        assert attached.parent == heavy


class TestBuyingOneOntoAGunAlreadyOwned:
    """An accessory is bought onto the weapon's own row rather than onto
    the fighter, which is what makes selling the gun reach it and its
    effects land on that gun alone."""

    def test_it_hangs_off_the_weapon_and_counts_towards_the_fighter(
        self, gang, fighter, sight, weapon_stats
    ):
        gun = give_weapon(fighter, make_gun("Lasgun", weapon_stats), paid=15)

        bolted = attach(gun, sight)

        assert bolted.parent == gun
        assert bolted.miniature_root == fighter
        fighter.refresh_from_db()
        assert fighter.rating == 50 + 15 + 25
        reconciled(gang)

    def test_nobody_naming_a_price_pays_the_librarys(
        self, gang, fighter, sight, weapon_stats
    ):
        """The dialog submits which accessory and never its price, so the
        figure has to come from the library."""
        gun = give_weapon(fighter, make_gun("Lasgun", weapon_stats), paid=15)
        before = books(gang).credits

        bolted = attach(gun, sight)

        assert bolted.ledger_entry.paid == 25
        assert bolted.ledger_entry.rating_contribution == 25
        assert books(gang).credits == before - 25
        reconciled(gang)

    def test_an_owner_may_pay_their_own_price(self, gang, fighter, sight, weapon_stats):
        """Haggling moves the credits and never the rating: a sight bought
        cheap is still twenty-five credits of sight."""
        gun = give_weapon(fighter, make_gun("Lasgun", weapon_stats), paid=15)

        bolted = attach(gun, sight, paid=10, list_price=25, discount=15)

        assert bolted.ledger_entry.paid == 10
        assert bolted.ledger_entry.rating_contribution == 25
        reconciled(gang)


class TestSellingTheGunUnderIt:
    """A sale takes the whole subtree, so an accessory the gang means to
    keep has to leave the gun first. Both answers are real ones; which a
    click meant is the seller's to say."""

    @pytest.fixture
    def kitted(self, fighter, sight, weapon_stats):
        """A lasgun with a telescopic sight on it: 15¢ of gun, 25¢ of sight."""
        gun = give_weapon(fighter, make_gun("Lasgun", weapon_stats), paid=15)
        return gun, attach(gun, sight)

    def test_stashing_it_first_leaves_it_owned_after_the_sale(
        self, gang, fighter, kitted
    ):
        gun, bolted = kitted

        move(bolted, gang.stash)
        sell(gun)

        bolted.refresh_from_db()
        assert bolted.archived is False
        assert bolted.stash_root == gang.stash
        assert bolted.parent is None
        reconciled(gang)

    def test_a_stashed_accessory_is_worth_what_it_always_was(
        self, gang, fighter, kitted
    ):
        """A move never re-prices. The rating leaves the fighter and
        arrives in the stash unchanged, because the stash counts towards
        the gang's wealth where the roster counts towards its rating."""
        gun, bolted = kitted

        move(bolted, gang.stash)
        sell(gun)

        fighter.refresh_from_db()
        now = books(gang)
        assert fighter.rating == 50
        assert now.rating == 50
        assert now.stash.rating == 25
        assert bolted.ledger_entry.rating_contribution == 25

    def test_the_gun_alone_pays_for_the_gun_alone(self, gang, kitted):
        """Fifteen credits of gun halves to eight, and nothing is paid for
        what the gang kept."""
        gun, bolted = kitted
        before = books(gang).credits

        move(bolted, gang.stash)
        proceeds = sell(gun)

        assert proceeds == 8
        assert books(gang).credits == before + 8
        reconciled(gang)

    def test_selling_it_all_together_takes_the_accessory_too(
        self, gang, fighter, kitted
    ):
        gun, bolted = kitted
        before = books(gang).credits

        # Forty credits of gun and sight, halved.
        proceeds = sell(gun)

        assert proceeds == 20
        bolted.refresh_from_db()
        assert bolted.archived is True
        fighter.refresh_from_db()
        now = books(gang)
        assert fighter.rating == 50
        assert now.rating == 50
        assert now.stash.rating == 0
        assert now.credits == before + 20
        reconciled(gang)

    def test_what_each_answer_pays_can_be_asked_before_either_happens(self, kitted):
        """The confirmation quotes a figure against each answer, so both
        have to be priceable without anything being written."""
        from n26.core.operations import detachable_children, sale_of

        gun, bolted = kitted
        keepable = detachable_children(gun)

        assert [child.pk for child in keepable] == [bolted.pk]
        assert sale_of(gun, keeping=keepable)[2] == 8
        assert sale_of(gun)[2] == 20

    def test_a_sight_the_gun_came_with_is_not_the_gangs_to_keep(
        self, gang, fighter, sight, weapon_stats
    ):
        """What a purchase brought belongs to the package. Removing what
        caused a row removes it, so offering to stash one would be
        offering something the sale takes straight back."""
        from n26.core.models import Reason
        from n26.core.operations import detachable_children, operation

        gun = give_weapon(fighter, make_gun("Lasgun", weapon_stats), paid=15)
        with operation(gang, actor=gang.owner) as op:
            op.assign(sight, parent=gun, caused_by=gun, paid=0, reason=Reason.DEFAULT)

        assert detachable_children(gun) == []


class TestFittingItToAnotherGun:
    """The other half of surviving a sale: a stashed accessory is gear
    waiting for a gun, and it goes back onto one."""

    @pytest.fixture
    def stashed(self, gang, fighter, sight, weapon_stats):
        """A sight that has been through a sale and sits in the stash."""
        gun = give_weapon(fighter, make_gun("Lasgun", weapon_stats), paid=15)
        bolted = attach(gun, sight)
        move(bolted, gang.stash)
        sell(gun)
        return bolted

    def test_it_goes_back_onto_a_weapon(
        self, gang, second_fighter, stashed, weapon_stats
    ):
        autogun = give_weapon(
            second_fighter, make_gun("Autogun", weapon_stats), paid=20
        )

        move(stashed, autogun)

        stashed.refresh_from_db()
        assert stashed.parent == autogun
        assert stashed.miniature_root == second_fighter
        assert stashed.stash_root is None
        reconciled(gang)

    def test_its_effects_now_reach_the_new_gun(
        self, gang, second_fighter, stashed, weapon_stats
    ):
        """The scope is positional — the weapon it is attached to — so
        re-fitting it re-aims it with nothing else edited."""
        autogun = give_weapon(
            second_fighter, make_gun("Autogun", weapon_stats), paid=20
        )
        give_weapon(second_fighter, make_gun("Stub gun", weapon_stats), paid=10)

        move(stashed, autogun)

        card = drawn(second_fighter)
        values = {w.name: w.profiles[0].statline.get("SR").value for w in card.weapons}
        assert values == {"Autogun": '14"', "Stub gun": '8"'}

    def test_the_move_charges_nothing_and_re_prices_nothing(
        self, gang, second_fighter, stashed, weapon_stats
    ):
        autogun = give_weapon(
            second_fighter, make_gun("Autogun", weapon_stats), paid=20
        )
        before = books(gang).credits

        move(stashed, autogun)

        stashed.refresh_from_db()
        second_fighter.refresh_from_db()
        now = books(gang)
        assert now.credits == before
        assert stashed.ledger_entry.rating_contribution == 25
        # Out of the gang's wealth and into what the roster is worth.
        assert now.stash.rating == 0
        assert second_fighter.rating == 50 + 20 + 25
        reconciled(gang)

    def test_a_gun_may_be_handed_a_sight_it_does_not_suit(
        self, gang, second_fighter, stashed, weapon_stats
    ):
        """Inform, never police. Fitting shortens a list of accessories;
        it is not a rule, and a move is not where one would be kept."""
        heavy = give_weapon(
            second_fighter, make_gun("Heavy stubber", weapon_stats), paid=70
        )

        move(stashed, heavy)

        stashed.refresh_from_db()
        assert stashed.parent == heavy

    def test_a_weapons_own_firing_line_cannot_be_unbolted(
        self, gang, fighter, weapon_stats
    ):
        """A firing line names one gun and is nothing away from it, so the
        move is refused in a sentence rather than leaving a line
        somewhere nothing can read it."""
        from n26.core.operations import Refusal

        gun = give_weapon(fighter, make_gun("Lasgun", weapon_stats), paid=15)
        firing_line = gun.children.get()

        with pytest.raises(Refusal) as refused:
            move(firing_line, gang.stash)

        assert "is part of" in str(refused.value)
        firing_line.refresh_from_db()
        assert firing_line.parent == gun
