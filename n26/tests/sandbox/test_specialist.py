"""Specialist: a subtype that offers a choice of specialisation.

The slot is computed; only what was chosen is stored. "Active but empty" is
never a written state — it is the absence of a resolution next to a
computed offer, so deferring the pick costs nothing and nothing pending
can go stale.

Three layers compose: the subtype (stored) offers the choice (computed
slot); the pick (stored, caused by the subtype's assignment) resolves it;
the specialisation's own modifier grants the skill (computed). Remove the
subtype and the whole chain unwinds through machinery that already existed.
"""

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import Assignment
from n26.core.operations import Refusal
from n26.core.render import build_model_card
from n26.core.render_text import render_model_card
from n26.library.models import (
    OffersChoice,
    Specialisation,
    TargetsMiniature,
    Trait,
)
from n26.tests.sandbox.actions import (
    assign,
    choose,
    create_skill,
    create_specialisation,
    create_subtype,
    found_gang,
    hire,
    modifier,
    offers_choice,
    remove,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def specialist(db):
    subtype = create_subtype("Specialist")
    modifier(
        "Specialist chooses a specialisation",
        TargetsMiniature.objects.create(),
        offers_choice(Specialisation),
        carried_by=subtype,
    )
    return subtype


@pytest.fixture
def specialisations(db):
    return {
        "sharpshooter": create_specialisation(
            "Sharpshooter", grants_skill=create_skill("Fast Shot")
        ),
        "medic": create_specialisation(
            "Medicae", grants_skill=create_skill("Field Surgery")
        ),
    }


@pytest.fixture
def yolanda(gang_type, make_profile, specialist):
    player = User.objects.create_user("player")
    gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
    mini = hire(gang, make_profile("Escher Ganger"), "Yolanda", paid=55)
    assign(specialist, miniature=mini)
    return mini


def card_for(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([n.assignable for n in card.all_nodes()])
    return build_model_card(miniature, card=card, computed=compute(card, index))


def anchor_of(miniature):
    return Assignment.objects.get(subtype__name="Specialist", miniature=miniature)


class TestTheUnresolvedSlot:
    def test_the_offer_is_a_slot_on_the_card(self, yolanda):
        card = card_for(yolanda)
        (choice,) = card.choices
        assert choice.kind_label == "Specialisation"
        assert choice.chosen is None
        assert choice.is_resolved is False

    def test_nothing_pending_is_stored(self, yolanda):
        """Deferral is free because unresolved is absence, not state."""
        assert Assignment.objects.filter(specialisation__isnull=False).count() == 0

    def test_it_renders_as_a_row_like_any_other_assignable(self, yolanda):
        text = "\n".join(render_model_card(card_for(yolanda)))
        print("\n" + text)
        assert "Specialisation: — (not chosen)" in text
        # The source is data (it tells two slots apart) but is not shown.
        assert "Specialist]" not in text

    def test_a_model_without_the_subtype_has_no_slot(
        self, gang_type, make_profile, specialist
    ):
        player = User.objects.create_user("someone")
        gang = found_gang("Plain gang", gang_type, owner=player, budget=500)
        plain = hire(gang, make_profile("Plain Ganger"), "Nobody", paid=55)
        assert card_for(plain).choices == []


class TestChoosing:
    def test_the_pick_resolves_the_slot(self, yolanda, specialisations):
        choose(anchor_of(yolanda), specialisations["sharpshooter"])
        card = card_for(yolanda)
        (choice,) = card.choices
        assert choice.chosen == "Sharpshooter"
        assert choice.is_resolved is True

    def test_the_pick_is_the_choice_row_not_loose_equipment(
        self, yolanda, specialisations
    ):
        """What was chosen draws as the choice's own row, and nowhere else."""
        choose(anchor_of(yolanda), specialisations["sharpshooter"])
        card = card_for(yolanda)
        assert card.equipment == []

        text = "\n".join(render_model_card(card))
        print("\n" + text)
        assert "Specialisation: Sharpshooter" in text
        # It grants a skill computedly, but is itself nobody's equipment.
        assert "Equipment:" not in text

    def test_the_skill_arrives_computed(self, yolanda, specialisations):
        """Stored subtype -> stored pick -> computed skill: three layers."""
        choose(anchor_of(yolanda), specialisations["sharpshooter"])
        card = card_for(yolanda)
        (skill,) = card.skills
        assert skill.name == "Fast Shot"
        assert skill.provenance.source == "Sharpshooter"
        assert skill.provenance.source_kind == "specialisation"
        assert skill.provenance.computed is True

    def test_the_pick_is_free_and_caused_by_the_subtype(self, yolanda, specialisations):
        picked = choose(anchor_of(yolanda), specialisations["sharpshooter"])
        assert picked.ledger_entry.paid == 0
        assert picked.caused_by == anchor_of(yolanda)

    def test_only_offered_kinds_may_be_chosen(self, yolanda):
        """A refusal rather than an error: the sentence is one a player
        could be shown, because a screen that drew the click has to say
        something."""
        with pytest.raises(Refusal, match="does not offer a choice of trait"):
            choose(anchor_of(yolanda), Trait.objects.create(name="Melee"))

    def test_an_unoffering_anchor_refuses(self, yolanda, specialisations):
        ganger_assignment = assign(create_subtype("Ganger"), miniature=yolanda)
        with pytest.raises(Refusal, match="does not offer"):
            choose(ganger_assignment, specialisations["sharpshooter"])


class TestChangingYourMind:
    def test_unchoosing_reopens_the_slot(self, yolanda, specialisations):
        picked = choose(anchor_of(yolanda), specialisations["sharpshooter"])
        remove(picked)

        card = card_for(yolanda)
        (choice,) = card.choices
        assert choice.chosen is None
        assert card.skills == []

    def test_rechoosing_works_and_the_ledger_remembers(self, yolanda, specialisations):
        first = choose(anchor_of(yolanda), specialisations["sharpshooter"])
        remove(first)
        choose(anchor_of(yolanda), specialisations["medic"])

        card = card_for(yolanda)
        (choice,) = card.choices
        assert choice.chosen == "Medicae"
        assert [s.name for s in card.skills] == ["Field Surgery"]
        # The abandoned pick survives, archived, in the ledger.
        assert (
            Assignment.objects.filter(
                specialisation__isnull=False, archived=True
            ).count()
            == 1
        )


class TestRemovingTheSubtype:
    def test_the_whole_chain_unwinds(self, yolanda, specialisations):
        choose(anchor_of(yolanda), specialisations["sharpshooter"])
        remove(anchor_of(yolanda))

        card = card_for(yolanda)
        assert card.choices == []
        assert card.skills == []
        assert Assignment.objects.filter(archived=True).count() == 2


class TestTwoSlots:
    def test_two_offering_subtypes_are_two_independent_slots(
        self, yolanda, specialisations
    ):
        second = create_subtype("Twice-Specialised")
        modifier(
            "Twice-Specialised also chooses",
            TargetsMiniature.objects.create(),
            offers_choice(Specialisation),
            carried_by=second,
        )
        assign(second, miniature=yolanda)
        choose(anchor_of(yolanda), specialisations["sharpshooter"])

        card = card_for(yolanda)
        # Two slots of the same kind — the provenance, though never
        # displayed, is what keeps them apart.
        by_source = {c.provenance.source: c.chosen for c in card.choices}
        assert by_source == {
            "Specialist": "Sharpshooter",
            "Twice-Specialised": None,
        }


class TestTheAllowList:
    def test_unofferable_kinds_are_refused_at_authoring_time(self, db):
        from n26.library.models import Weapon

        with pytest.raises(ValidationError, match="cannot be offered"):
            OffersChoice.of(Weapon).clean()

    def test_the_modifier_validates_whole(self, db, specialist):
        offer = specialist.modifiers.get()
        offer.full_clean()  # scope + effect + compatibility all pass


class TestThePicker:
    def test_the_offer_says_what_may_be_picked(self, yolanda, specialisations):
        """The first real database consumer: a choice UI's queryset."""
        from n26.library.models.modifier import OffersChoice

        offer = next(
            modifier.effect
            for modifier in anchor_of(yolanda).assignable.modifiers.all()
            if isinstance(modifier.effect, OffersChoice)
        )
        assert sorted(s.name for s in offer.choosables()) == [
            "Medicae",
            "Sharpshooter",
        ]
        assert str(offer.selector()) == "any specialisation"
