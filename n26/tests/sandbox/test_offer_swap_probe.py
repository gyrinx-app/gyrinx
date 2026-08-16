"""Swapping one hidden offer for a narrower one, profile by profile.

The Subjugator Patrol Officer pattern: a Specialist subtype grants a
hidden carrier whose modifier offers the general choice of
specialisation; one profile with that subtype built in takes the
general carrier away again and grants a narrower one of its own, so
its card should ask the same question over a shorter list. The plain
profile keeps the general offer untouched.

This file is a probe, not a contract: it pins what the engine does with
the pattern today, plan evidence and all.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.render import build_choice_offer
from n26.library.models import Specialisation
from n26.tests.sandbox.actions import (
    create_collection,
    create_default_set,
    create_hidden,
    create_profile,
    create_specialisation,
    create_subtype,
    ef_adds,
    ef_removes,
    found_gang,
    hire,
    modifier,
    offers_choice,
    section_of,
    targets_model,
)

pytestmark = pytest.mark.django_db


# --- The content: one subtype, two hiddens, two profiles -------------------


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def specialisations(default_pack):
    return {
        name: create_specialisation(name)
        for name in ("Sniper", "Gunner", "Medic", "Armourer")
    }


@pytest.fixture
def general_menu(specialisations):
    """The whole menu: all four, in one default section."""
    collection = create_collection(
        "Specialisation Offer", entries=list(specialisations.values())
    )
    return section_of(collection, "Specialisations", 0, is_default=True)


@pytest.fixture
def general_offer(general_menu):
    """The hidden carrier every Specialist is granted."""
    hidden = create_hidden("Specialisation Offer (general)")
    modifier(
        "General offer: a specialisation from the whole menu",
        targets_model(),
        offers_choice(
            Specialisation, from_section=general_menu, label="specialisation"
        ),
        carried_by=hidden,
    )
    return hidden


@pytest.fixture
def specialist(general_offer):
    """The subtype does not carry the offer itself — it grants the
    hidden that does, which is the shape under probe."""
    subtype = create_subtype("Specialist")
    modifier(
        "Specialist: the general offer arrives",
        targets_model(),
        ef_adds(general_offer),
        carried_by=subtype,
    )
    return subtype


@pytest.fixture
def narrow_menu(specialisations):
    collection = create_collection(
        "Specialisation Offer (Subjugator)", entries=[specialisations["Gunner"]]
    )
    return section_of(collection, "Specialisations", 0, is_default=True)


@pytest.fixture
def narrow_offer(narrow_menu):
    hidden = create_hidden("Specialisation offer (Subjugator)")
    modifier(
        "Subjugator offer: a specialisation from the short menu",
        targets_model(),
        offers_choice(Specialisation, from_section=narrow_menu, label="specialisation"),
        carried_by=hidden,
    )
    return hidden


@pytest.fixture
def profiles(person_type, gang_type, specialist, general_offer, narrow_offer):
    """Both ranks are Specialists; only the Subjugator swaps the offer."""
    made = {}
    for key, name in [
        ("plain", "Patrol Officer"),
        ("subjugator", "Subjugator Patrol Officer"),
    ]:
        profile = create_profile(name, person_type, gang_type, price=0)
        profile.built_ins = create_default_set(
            f"{name} built-ins", members=[specialist]
        )
        profile.save()
        made[key] = profile
    modifier(
        "Subjugator: the general offer goes",
        targets_model(),
        ef_removes(general_offer),
        carried_by=made["subjugator"],
    )
    modifier(
        "Subjugator: the narrow offer arrives",
        targets_model(),
        ef_adds(narrow_offer),
        carried_by=made["subjugator"],
    )
    return made


@pytest.fixture
def gang(gang_type, owner):
    return found_gang("The Watch", gang_type, owner=owner)


@pytest.fixture
def officers(gang, profiles):
    return {
        "plain": hire(gang, profiles["plain"], "Vex"),
        "subjugator": hire(gang, profiles["subjugator"], "Kade"),
    }


# --- Reading the card the way the pages do ---------------------------------


def computed_for(miniature):
    card = build_card(miniature)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


def names_on(offer):
    return {option.name for group in offer.groups for option in group.options}


def questions_on(miniature):
    """Each choice on the card, with the names its picker would list."""
    computed = computed_for(miniature)
    return [
        (slot, names_on(build_choice_offer(slot, computed)))
        for slot in computed.choices
    ]


class TestThePlainPatrolOfficer:
    """The general offer arrives through the Specialist grant and lists
    the whole menu."""

    def test_the_card_asks_one_question_over_the_whole_menu(self, officers):
        ((slot, names),) = questions_on(officers["plain"])
        assert slot.kind_label == "Specialisation"
        assert not slot.is_resolved
        assert names == {"Sniper", "Gunner", "Medic", "Armourer"}


class TestTheSubjugatorPatrolOfficer:
    """Taking the granted carrier away cancels the question it put up,
    and the narrow carrier's question stands alone."""

    def test_the_card_asks_one_question_over_the_short_menu(self, officers):
        ((slot, names),) = questions_on(officers["subjugator"])
        assert slot.kind_label == "Specialisation"
        assert names == {"Gunner"}

    def test_the_plan_shows_the_general_offer_ran_and_was_then_retracted(
        self, officers
    ):
        plan = computed_for(officers["subjugator"]).plan
        removal = next(
            step
            for step in plan
            if str(step.source) == "Subjugator Patrol Officer"
            and "Specialisation Offer (general)" in step.effect
        )
        assert removal.outcome == "reached"
        assert removal.took_away == ("Specialisation Offer (general)",)
        general = next(
            step
            for step in plan
            if str(step.source) == "Specialisation Offer (general)"
        )
        assert general.outcome == "retracted"
        # The narrow carrier's own offer stands.
        narrow = next(
            step
            for step in plan
            if str(step.source) == "Specialisation offer (Subjugator)"
        )
        assert narrow.outcome == "reached"


class TestTheSwapWithTheHiddenBuiltIn:
    """The other possible wiring of the original experiment: the general
    hidden arrives as a *built-in* of each profile — a stored assignment.
    Half of it works: the plain officer's question is anchored and
    settleable, and the removal silences the stored hidden's question on
    the Subjugator. The narrow half still cannot work, because the
    narrow hidden has to arrive by the profile's own modifier — that is
    the whole trick — and a granted hidden's question is anchorless.
    Both wirings of the experiment fail at the same spot."""

    @pytest.fixture
    def built_in_profiles(self, person_type, gang_type, general_offer, narrow_offer):
        made = {}
        for key, name in [
            ("plain", "Stored Patrol Officer"),
            ("subjugator", "Stored Subjugator"),
        ]:
            profile = create_profile(name, person_type, gang_type, price=0)
            profile.built_ins = create_default_set(
                f"{name} built-ins", members=[general_offer]
            )
            profile.save()
            made[key] = profile
        modifier(
            "Stored Subjugator: the general offer goes",
            targets_model(),
            ef_removes(general_offer),
            carried_by=made["subjugator"],
        )
        modifier(
            "Stored Subjugator: the narrow offer arrives",
            targets_model(),
            ef_adds(narrow_offer),
            carried_by=made["subjugator"],
        )
        return made

    def test_the_plain_officers_question_is_anchored_and_whole(
        self, gang, built_in_profiles
    ):
        officer = hire(gang, built_in_profiles["plain"], "Vex")

        ((slot, names),) = questions_on(officer)

        assert names == {"Sniper", "Gunner", "Medic", "Armourer"}
        assert slot.anchor is not None and slot.anchor.assignment is not None

    def test_the_subjugator_sees_only_the_short_menu(self, gang, built_in_profiles):
        subjugator = hire(gang, built_in_profiles["subjugator"], "Kade")

        questions = questions_on(subjugator)

        assert [(names, slot.anchor is not None) for slot, names in questions] == [
            ({"Gunner"}, False)
        ]


class TestWhetherTheQuestionCanBeSettled:
    """Where the pattern comes apart today. A choice is settled against
    the stored assignment that carries the offer — but a hidden that
    arrives by grant is computed, so nothing on the card anchors its
    question. The list is right on both ranks; neither slot has an
    address, so no picker can be reached and no pick can ever resolve
    it. The working shapes store the carrier instead: the offer sits on
    the subtype itself (a built-in assignment), or the hidden is a
    member of the profile's default set."""

    def test_neither_ranks_question_is_anchored_to_any_stored_row(self, officers):
        for miniature in officers.values():
            ((slot, _),) = questions_on(miniature)
            assert slot.anchor is None

    def test_the_drawn_line_carries_no_address(self, officers):
        from n26.core.render import choice_lines

        for miniature in officers.values():
            (line,) = choice_lines(computed_for(miniature), host=str(miniature.pk))
            assert line.key == ""


class TestTheSameSwapBuiltAsSlotsAndPicks:
    """The migration's answer to the pattern: the general slot arrives
    from the subtype, the Subjugator takes it away and grants its own
    narrow slot. Every question is anchored on the stored assignment
    that granted it, so — unlike the hidden-offer build above — the
    picker has an address and the choice can actually be settled."""

    @pytest.fixture
    def slotted(self, person_type, gang_type, default_pack):
        from n26.library.authoring import (
            create_pickable,
            create_picklist,
            create_slot,
            create_slot_type,
        )

        slot_type = create_slot_type("Specialisation")
        picks = {
            name: create_pickable(name, slot_type)
            for name in ("Sniper", "Gunner", "Medic", "Armourer")
        }
        general = create_slot(
            "Specialisation",
            slot_type,
            create_picklist("Specialisations", slot_type, members=list(picks.values())),
        )
        narrow = create_slot(
            "Specialisation (Subjugator)",
            slot_type,
            create_picklist("Subjugator options", slot_type, members=[picks["Gunner"]]),
            label="Specialisation",
        )
        subtype = create_subtype("Slotted Specialist")
        modifier(
            "Slotted Specialist: the general question arrives",
            targets_model(),
            ef_adds(general),
            carried_by=subtype,
        )
        made = {}
        for key, name in [("plain", "Officer"), ("subjugator", "Subjugator")]:
            profile = create_profile(name, person_type, gang_type, price=0)
            profile.built_ins = create_default_set(
                f"{name} slotted built-ins", members=[subtype]
            )
            profile.save()
            made[key] = profile
        modifier(
            "Subjugator: the general question goes",
            targets_model(),
            ef_removes(general),
            carried_by=made["subjugator"],
        )
        modifier(
            "Subjugator: the narrow question arrives",
            targets_model(),
            ef_adds(narrow),
            carried_by=made["subjugator"],
        )
        return made, picks, narrow, subtype

    def test_both_cards_ask_an_anchored_question(self, gang, slotted):
        made, picks, narrow, subtype = slotted
        plain = hire(gang, made["plain"], "Vosk")
        subjugator = hire(gang, made["subjugator"], "Krell")

        (plain_q,) = questions_on(plain)
        (subjugator_q,) = questions_on(subjugator)
        assert plain_q[1] == {"Sniper", "Gunner", "Medic", "Armourer"}
        assert subjugator_q[1] == {"Gunner"}
        for slot, _ in (plain_q, subjugator_q):
            assert slot.anchor is not None
            assert slot.anchor.assignment is not None

    def test_the_narrow_question_settles_on_its_bearer(self, gang, slotted):
        from n26.core.models import Assignment
        from n26.core.reconcile import assert_reconciled
        from n26.tests.sandbox.actions import choose

        made, picks, narrow, subtype = slotted
        subjugator = hire(gang, made["subjugator"], "Krell")
        (slot_row,) = computed_for(subjugator).choices

        choose(
            slot_row.anchor.assignment,
            picks["Gunner"],
            slot=narrow,
            miniature=subjugator,
        )

        (settled,) = computed_for(subjugator).choices
        assert settled.chosen_name == "Gunner"
        assert Assignment.objects.get(pickable=picks["Gunner"]).miniature == (
            subjugator
        )
        assert_reconciled(gang)
