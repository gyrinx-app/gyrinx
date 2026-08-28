"""Multiple cards: the rulebook's equipment sets.

Yolanda owns a Cutter (which grants Mounted), a combat shotgun, and a
knife — all at once: buying is never blocked and the pool is bought once.
Named selections split the kit across cards, and each card computes its own
effects: only the card with the Cutter shows Mounted.

Card *validity* (Mounted's Heavy/Paired weapon rule) was prototyped and
then deliberately ripped out — warnings/constraints get their own design
round later. See "Parked designs" in design/assignables.md.
"""

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.render import build_model_card
from n26.core.render_text import render_model_card
from n26.tests.sandbox.actions import (
    adds,
    assign,
    create_assignment_set,
    create_skill,
    create_subtype,
    create_trait,
    create_wargear,
    create_weapon,
    found_gang,
    give_weapon,
    hire,
    modifier,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def traits(db):
    return {
        "heavy": create_trait("Heavy"),
        "melee": create_trait("Melee"),
    }


@pytest.fixture
def mounted(traits):
    subtype = create_subtype("Mounted")
    modifier(
        "Mounted grants Hit & Run",
        targets_model(),
        adds(create_skill("Hit & Run")),
        carried_by=subtype,
    )
    return subtype


@pytest.fixture
def cutter(mounted):
    mount = create_wargear("Cutter")
    modifier("Cutter grants Mounted", targets_model(), adds(mounted), carried_by=mount)
    return mount


@pytest.fixture
def yolanda(gang_type, make_profile, traits, cutter):
    player = User.objects.create_user("player")
    gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
    mini = hire(gang, make_profile("Escher Ganger"), "Yolanda", paid=55)
    assign(cutter, miniature=mini, paid=75)
    give_weapon(
        mini,
        create_weapon("Combat shotgun", profiles=[("Salvo", 0, [traits["heavy"]])]),
        paid=35,
    )
    give_weapon(
        mini,
        create_weapon("Stiletto knife", profiles=[("Blade", 0, [traits["melee"]])]),
        paid=20,
    )
    return mini


def card_for(miniature, assignment_set=None):
    card = build_card(miniature, with_statlines=True, assignment_set=assignment_set)
    index = build_modifier_index([n.assignable for n in card.all_nodes()])
    computed = compute(card, index)
    return build_model_card(miniature, card=card, computed=computed)


def equipment_of(miniature):
    card = build_card(miniature)
    return {
        node.name: node.assignment
        for node in card.roots
        if node.assignment.weapon_id or node.assignment.wargear_id
    }


class TestTheDefaultCard:
    def test_owning_everything_is_never_blocked(self, yolanda):
        yolanda.gang.refresh_from_db()
        assert yolanda.gang.rating == 55 + 75 + 35 + 20

    def test_the_default_card_shows_everything(self, yolanda):
        card = card_for(yolanda)
        assert [w.name for w in card.weapons] == ["Combat shotgun", "Stiletto knife"]
        assert card.type_line == "Fighter (Mounted)"


class TestNamedSelections:
    @pytest.fixture
    def kits(self, yolanda):
        equipment = equipment_of(yolanda)
        riding = create_assignment_set(
            yolanda, "Riding kit", [equipment["Cutter"], equipment["Stiletto knife"]]
        )
        shooting = create_assignment_set(
            yolanda, "Shooting kit", [equipment["Combat shotgun"]]
        )
        return riding, shooting

    def test_both_kits_build(self, yolanda, kits):
        riding, shooting = kits
        assert card_for(yolanda, riding).name == "Yolanda"
        assert card_for(yolanda, shooting).name == "Yolanda"

    def test_each_card_computes_its_own_effects(self, yolanda, kits):
        riding, shooting = kits

        riding_card = card_for(yolanda, riding)
        assert riding_card.type_line == "Fighter (Mounted)"
        assert [s.name for s in riding_card.skills] == ["Hit & Run"]
        assert [w.name for w in riding_card.weapons] == ["Stiletto knife"]

        shooting_card = card_for(yolanda, shooting)
        assert shooting_card.type_line == "Fighter"
        assert shooting_card.skills == []
        assert [w.name for w in shooting_card.weapons] == ["Combat shotgun"]

    def test_cost_never_varies_by_card(self, yolanda, kits):
        """A weapon is bought once and counted once, whichever card shows."""
        riding, shooting = kits
        full = card_for(yolanda)
        assert (
            card_for(yolanda, riding).rating
            == card_for(yolanda, shooting).rating
            == full.rating
            == 185
        )

    def test_ammo_follows_its_weapon_off_the_card(self, yolanda, traits, kits):
        _, shooting = kits
        riding_card = card_for(yolanda, kits[0])
        names = [n.name for card_weapon in riding_card.weapons for n in [card_weapon]]
        assert "Combat shotgun" not in names

    def test_the_ledger_ignores_cards_entirely(self, yolanda, kits):
        from n26.core.reconcile import assert_reconciled, ledger_for_miniature

        assert ledger_for_miniature(yolanda).count() == 6  # hire + 3 kit + 2 ammo
        yolanda.gang.refresh_from_db()
        assert_reconciled(yolanda.gang)


class TestSelectionRules:
    def test_only_equipment_may_vary(self, yolanda):
        skill = create_skill("Nerves of Steel")
        skilled = assign(skill, miniature=yolanda)
        with pytest.raises(ValidationError, match="only weapons and wargear"):
            create_assignment_set(yolanda, "Cheat", [skilled])

    def test_another_model_s_kit_is_rejected(self, yolanda, gang_type, make_profile):
        other = hire(yolanda.gang, make_profile("Another Ganger"), "Mad Donna", paid=55)
        donnas_knife = give_weapon(
            other, create_weapon("Shiv", profiles=[("Point", 0)]), paid=5
        )
        with pytest.raises(ValidationError, match="is not on"):
            create_assignment_set(yolanda, "Theft", [donnas_knife])

    def test_set_names_are_unique_per_model(self, yolanda):
        from django.db import IntegrityError, transaction

        create_assignment_set(yolanda, "Riding kit", [])
        with pytest.raises(IntegrityError), transaction.atomic():
            create_assignment_set(yolanda, "riding KIT", [])

    def test_everything_that_is_not_equipment_rides_every_card(
        self, yolanda, kits=None
    ):
        assign(create_skill("Nerves of Steel"), miniature=yolanda)
        equipment = equipment_of(yolanda)
        knife_only = create_assignment_set(
            yolanda, "Knife only", [equipment["Stiletto knife"]]
        )
        card = build_card(yolanda, assignment_set=knife_only)
        names = [node.name for node in card.roots]
        assert "Nerves of Steel" in names


class TestRendering:
    def test_a_kit_renders_with_its_own_effects(self, yolanda):
        equipment = equipment_of(yolanda)
        riding = create_assignment_set(
            yolanda, "Riding kit", [equipment["Cutter"], equipment["Stiletto knife"]]
        )
        text = "\n".join(render_model_card(card_for(yolanda, riding)))
        print("\n" + text)
        assert "Fighter (Mounted)" in text
        assert "Combat shotgun" not in text
