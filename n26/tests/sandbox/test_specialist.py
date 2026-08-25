"""Specialist: a subtype that grants the slot asking which field it took.

The slot is computed; only what was picked is stored. "Active but empty"
is never a written state — it is the absence of a pick beside a computed
slot, so deferring costs nothing and nothing pending can go stale.

Three layers compose: the subtype (stored) grants the slot (computed);
the pick (stored, caused by the subtype's assignment) answers it; the
pickable's own modifier grants the skill (computed). Remove the subtype
and the whole chain unwinds through machinery that already existed.
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
from n26.library.models import OffersChoice, Trait
from n26.tests.sandbox.actions import (
    assign,
    choose,
    create_pickable,
    create_picklist,
    create_skill,
    create_slot,
    create_slot_type,
    create_subtype,
    ef_adds,
    found_gang,
    hire,
    modifier,
    remove,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def specialisation(db):
    return create_slot_type("Specialisation")


@pytest.fixture
def fields(specialisation):
    """The two a Specialist may take, each granting its own skill."""
    made = {}
    for key, name, skill in (
        ("sharpshooter", "Sharpshooter", "Fast Shot"),
        ("medic", "Medicae", "Field Surgery"),
    ):
        pickable = create_pickable(name, specialisation)
        modifier(
            f"{name}: its skill",
            targets_model(),
            ef_adds(create_skill(skill)),
            carried_by=pickable,
        )
        made[key] = pickable
    return made


@pytest.fixture
def specialisation_slot(specialisation, fields):
    return create_slot(
        "Specialisation",
        specialisation,
        create_picklist(
            "Specialisations", specialisation, members=list(fields.values())
        ),
    )


@pytest.fixture
def specialist(specialisation_slot):
    subtype = create_subtype("Specialist")
    modifier(
        "Specialist is asked its specialisation",
        targets_model(),
        ef_adds(specialisation_slot),
        carried_by=subtype,
    )
    return subtype


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


def slots_of(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([n.assignable for n in card.all_nodes()])
    return compute(card, index).choices


def anchor_of(miniature):
    (slot,) = slots_of(miniature)
    return slot.anchor.assignment


def pick(miniature, pickable, source="Specialist"):
    """Answer the slot the named carrier granted.

    A granted slot has no assignment of its own, so the anchor is the
    line the grant stands on — which may carry several — and the one
    being answered is named.
    """
    slot = next(row for row in slots_of(miniature) if row.source == source)
    return choose(slot.anchor.assignment, pickable, slot=slot.slot)


class TestTheUnresolvedSlot:
    def test_the_grant_is_a_slot_on_the_card(self, yolanda):
        card = card_for(yolanda)
        (choice,) = card.choices
        assert choice.kind_label == "Specialisation"
        assert choice.chosen is None
        assert choice.is_resolved is False

    def test_nothing_pending_is_stored(self, yolanda):
        """Deferral is free because unresolved is absence, not state."""
        assert Assignment.objects.filter(pickable__isnull=False).count() == 0

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
    def test_the_pick_resolves_the_slot(self, yolanda, fields):
        pick(yolanda, fields["sharpshooter"])
        card = card_for(yolanda)
        (choice,) = card.choices
        assert choice.chosen == "Sharpshooter"
        assert choice.is_resolved is True

    def test_the_pick_is_the_choice_row_not_loose_equipment(self, yolanda, fields):
        """What was picked draws as the slot's own row, and nowhere else."""
        pick(yolanda, fields["sharpshooter"])
        card = card_for(yolanda)
        assert card.equipment == []

        text = "\n".join(render_model_card(card))
        print("\n" + text)
        assert "Specialisation: Sharpshooter" in text
        # It grants a skill computedly, but is itself nobody's equipment.
        assert "Equipment:" not in text

    def test_the_skill_arrives_computed(self, yolanda, fields):
        """Stored subtype -> stored pick -> computed skill: three layers."""
        pick(yolanda, fields["sharpshooter"])
        card = card_for(yolanda)
        (skill,) = card.skills
        assert skill.name == "Fast Shot"
        assert skill.provenance.source == "Sharpshooter"
        # No sort-of-thing word: "pickable" is plumbing, and a player is
        # never shown it — the source names the field they took instead.
        assert skill.provenance.source_kind == ""
        assert skill.provenance.computed is True

    def test_the_pick_is_free_and_caused_by_the_subtype(self, yolanda, fields):
        anchor = anchor_of(yolanda)
        picked = pick(yolanda, fields["sharpshooter"])
        assert picked.ledger_entry.paid == 0
        assert picked.caused_by == anchor

    def test_only_what_the_slot_lists_may_be_picked(self, yolanda):
        """A refusal rather than an error: the sentence is one a player
        could be shown, because a screen that drew the click has to say
        something."""
        with pytest.raises(Refusal):
            choose(anchor_of(yolanda), Trait.objects.create(name="Melee"))

    def test_an_anchor_granting_no_slot_refuses(self, yolanda, fields):
        ganger_assignment = assign(create_subtype("Ganger"), miniature=yolanda)
        with pytest.raises(Refusal):
            choose(ganger_assignment, fields["sharpshooter"])


class TestChangingYourMind:
    def test_unchoosing_reopens_the_slot(self, yolanda, fields):
        picked = pick(yolanda, fields["sharpshooter"])
        remove(picked)

        card = card_for(yolanda)
        (choice,) = card.choices
        assert choice.chosen is None
        assert card.skills == []

    def test_rechoosing_works_and_the_ledger_remembers(self, yolanda, fields):
        first = pick(yolanda, fields["sharpshooter"])
        remove(first)
        pick(yolanda, fields["medic"])

        card = card_for(yolanda)
        (choice,) = card.choices
        assert choice.chosen == "Medicae"
        assert [s.name for s in card.skills] == ["Field Surgery"]
        # The abandoned pick survives, archived, in the ledger.
        assert (
            Assignment.objects.filter(pickable__isnull=False, archived=True).count()
            == 1
        )


class TestRemovingTheSubtype:
    def test_the_whole_chain_unwinds(self, yolanda, fields):
        anchor = anchor_of(yolanda)
        pick(yolanda, fields["sharpshooter"])
        remove(anchor)

        card = card_for(yolanda)
        assert card.choices == []
        assert card.skills == []
        assert Assignment.objects.filter(archived=True).count() == 2


class TestTwoSlots:
    def test_two_granting_subtypes_are_two_independent_slots(
        self, yolanda, specialisation, fields
    ):
        second_slot = create_slot(
            "Second Specialisation",
            specialisation,
            create_picklist(
                "Second Specialisations", specialisation, members=list(fields.values())
            ),
        )
        second = create_subtype("Twice-Specialised")
        modifier(
            "Twice-Specialised is asked as well",
            targets_model(),
            ef_adds(second_slot),
            carried_by=second,
        )
        assign(second, miniature=yolanda)
        pick(yolanda, fields["sharpshooter"])

        card = card_for(yolanda)
        # Two slots of the same kind — the provenance, though never
        # displayed, is what keeps them apart.
        by_source = {c.provenance.source: c.chosen for c in card.choices}
        assert by_source == {
            "Specialist": "Sharpshooter",
            "Twice-Specialised": None,
        }


class TestTheOfferAllowList:
    """Offering a choice of a kind outright is the older mechanism, still
    used where the answer is any row of a kind rather than a listed one.
    Its allow-list governs which kinds that may be."""

    def test_unofferable_kinds_are_refused_at_authoring_time(self, db):
        from n26.library.models import Weapon

        with pytest.raises(ValidationError, match="cannot be offered"):
            OffersChoice.of(Weapon).clean()

    def test_the_granting_modifier_validates_whole(self, db, specialist):
        grant = specialist.modifiers.get()
        grant.full_clean()  # scope + effect + compatibility all pass


class TestThePicker:
    def test_the_slot_says_what_may_be_picked(self, yolanda, fields):
        """The first real database consumer: a choice UI's queryset."""
        (slot,) = slots_of(yolanda)

        listed = [member.pickable for member in slot.slot.picklist.members.all()]
        assert sorted(pickable.name for pickable in listed) == [
            "Medicae",
            "Sharpshooter",
        ]
