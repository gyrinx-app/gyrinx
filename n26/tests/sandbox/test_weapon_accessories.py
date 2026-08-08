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
    remove,
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
def fighter(gang_type, make_profile):
    gang = found_gang("The Bad Girls", gang_type, owner=User.objects.create_user("t"))
    return hire_with_option(gang, make_profile("Ganger", price=50), "Yolanda")


def make_gun(name, weapon_stats):
    from n26.tests.sandbox.actions import set_statline

    gun = create_weapon(name, profiles=[("Standard", 0)], statline_type=weapon_stats)
    set_statline(gun.profiles.get(), short_range=8)
    return gun


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
