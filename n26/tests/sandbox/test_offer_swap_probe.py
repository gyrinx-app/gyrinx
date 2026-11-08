"""A Specialist subtype grants a general affiliation offer. The Subjugator profile replaces
it with a narrower offer while the plain profile keeps the general menu. Hidden-offer
and slots-and-picks versions must both expose answerable questions anchored on stored
assignments.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.render import build_choice_offer
from n26.library.models import Affiliation
from n26.tests.sandbox.actions import (
    create_affiliation,
    create_collection,
    create_default_set,
    create_hidden,
    create_profile,
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


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def affiliations(default_pack):
    return {
        name: create_affiliation(name)
        for name in ("Sniper", "Gunner", "Medic", "Armourer")
    }


@pytest.fixture
def general_menu(affiliations):
    """All four affiliations in one default section."""
    collection = create_collection(
        "Affiliation Offer", entries=list(affiliations.values())
    )
    return section_of(collection, "Affiliations", 0, is_default=True)


@pytest.fixture
def general_offer(general_menu):
    """The hidden carrier granted by the Specialist subtype."""
    hidden = create_hidden("Affiliation Offer (general)")
    modifier(
        "General offer: a affiliation from the whole menu",
        targets_model(),
        offers_choice(Affiliation, from_section=general_menu, label="affiliation"),
        carried_by=hidden,
    )
    return hidden


@pytest.fixture
def specialist(general_offer):
    """The subtype grants the hidden carrier rather than carrying the offer directly."""
    subtype = create_subtype("Specialist")
    modifier(
        "Specialist: the general offer arrives",
        targets_model(),
        ef_adds(general_offer),
        carried_by=subtype,
    )
    return subtype


@pytest.fixture
def narrow_menu(affiliations):
    collection = create_collection(
        "Affiliation Offer (Subjugator)", entries=[affiliations["Gunner"]]
    )
    return section_of(collection, "Affiliations", 0, is_default=True)


@pytest.fixture
def narrow_offer(narrow_menu):
    hidden = create_hidden("Affiliation offer (Subjugator)")
    modifier(
        "Subjugator offer: a affiliation from the short menu",
        targets_model(),
        offers_choice(Affiliation, from_section=narrow_menu, label="affiliation"),
        carried_by=hidden,
    )
    return hidden


@pytest.fixture
def profiles(person_type, gang_type, specialist, general_offer, narrow_offer):
    """Both profiles are Specialists; only the Subjugator replaces the offer."""
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


def computed_for(miniature):
    card = build_card(miniature)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


def names_on(offer):
    return {option.name for group in offer.groups for option in group.options}


def questions_on(miniature):
    """Read each card choice and the names available in its picker."""
    computed = computed_for(miniature)
    return [
        (slot, names_on(build_choice_offer(slot, computed)))
        for slot in computed.choices
    ]


class TestThePlainPatrolOfficer:
    """The Specialist grant supplies the complete menu."""

    def test_the_card_asks_one_question_over_the_whole_menu(self, officers):
        ((slot, names),) = questions_on(officers["plain"])
        assert slot.kind_label == "Affiliation"
        assert not slot.is_resolved
        assert names == {"Sniper", "Gunner", "Medic", "Armourer"}


class TestTheSubjugatorPatrolOfficer:
    """Removing the general carrier leaves only the narrow question."""

    def test_the_card_asks_one_question_over_the_short_menu(self, officers):
        ((slot, names),) = questions_on(officers["subjugator"])
        assert slot.kind_label == "Affiliation"
        assert names == {"Gunner"}

    def test_the_plan_shows_the_general_offer_ran_and_was_then_retracted(
        self, officers
    ):
        plan = computed_for(officers["subjugator"]).plan
        removal = next(
            step
            for step in plan
            if str(step.source) == "Subjugator Patrol Officer"
            and "Affiliation Offer (general)" in step.effect
        )
        assert removal.outcome == "reached"
        assert removal.took_away == ("Affiliation Offer (general)",)
        general = next(
            step for step in plan if str(step.source) == "Affiliation Offer (general)"
        )
        assert general.outcome == "retracted"

        narrow = next(
            step
            for step in plan
            if str(step.source) == "Affiliation offer (Subjugator)"
        )
        assert narrow.outcome == "reached"


class TestTheSwapWithTheHiddenBuiltIn:
    """A stored built-in general carrier can also be replaced by the narrow carrier granted
    by the profile.
    """

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
            ({"Gunner"}, True)
        ]


class TestWhetherTheQuestionCanBeSettled:
    """Granted hidden carriers have no stored assignment. Their questions use the stored
    subtype or profile anchoring the grant chain.
    """

    def test_each_ranks_question_is_anchored_on_what_its_chain_stands_on(
        self, officers, specialist
    ):
        ((plain, _),) = questions_on(officers["plain"])
        ((subjugator, _),) = questions_on(officers["subjugator"])

        # The stored subtype anchors the general offer; the stored profile anchors the
        # narrow offer.
        assert plain.anchor.assignment.assignable == specialist
        assert subjugator.anchor.assignment.assignable == (
            officers["subjugator"].membership.profile
        )

    def test_the_drawn_line_carries_an_address(self, officers):
        from n26.core.render import choice_lines

        for miniature in officers.values():
            (line,) = choice_lines(computed_for(miniature), host=str(miniature.pk))
            assert line.key != ""

    def test_the_narrow_question_settles_from_the_screen(
        self, gang, officers, owner, client, affiliations
    ):
        """The picker submits the narrow choice against its stored anchor."""
        from n26.core.models import Assignment
        from n26.core.reconcile import assert_reconciled
        from n26.core.render import render_gang
        from n26.core.views.choose import link_slots

        subjugator = officers["subjugator"]
        client.force_login(owner)
        sheet = render_gang(gang)
        link_slots(gang, sheet, *sheet.models)
        card = next(drawn for drawn in sheet.models if drawn.name == "Kade")
        (line,) = card.questions

        body = client.get(line.href).content.decode()
        assert "Gunner" in body and "Sniper" not in body
        response = client.post(
            line.href,
            {"thing": f"library.affiliation:{affiliations['Gunner'].pk}"},
        )

        assert response.status_code == 302
        (settled,) = computed_for(subjugator).choices
        assert settled.chosen_name == "Gunner"
        assert (
            Assignment.objects.get(affiliation=affiliations["Gunner"]).miniature
            == subjugator
        )
        assert_reconciled(gang)


class TestTheSameSwapBuiltAsSlotsAndPicks:
    """The slot version also replaces the general question with a narrow, answerable
    question anchored on its stored grant source.
    """

    @pytest.fixture
    def slotted(self, person_type, gang_type, default_pack):
        from n26.library.authoring import (
            create_pickable,
            create_picklist,
            create_slot,
            create_slot_type,
        )

        slot_type = create_slot_type("Affiliation")
        picks = {
            name: create_pickable(name, slot_type)
            for name in ("Sniper", "Gunner", "Medic", "Armourer")
        }
        general = create_slot(
            "Affiliation",
            slot_type,
            create_picklist("Affiliations", slot_type, members=list(picks.values())),
        )
        narrow = create_slot(
            "Affiliation (Subjugator)",
            slot_type,
            create_picklist("Subjugator options", slot_type, members=[picks["Gunner"]]),
            label="Affiliation",
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
