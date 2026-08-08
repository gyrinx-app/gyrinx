"""Counters, with XP as the first one — and effects hanging off values.

Tom's design (2026-08-05): XP is a Counter so that the machinery gets
proven on day one — a threshold-conditioned scope reveals a promotion
offer at 5 XP and confers a title at 10, computed, withdrawn if the
value drops. The definition is content; who has one is assignment (XP
rides the fighter entry's built-ins, opening at the printed Starting
XP); the running value is player-side state written only by ``tally``,
one ledger event per change.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import Assignment
from n26.core.render import build_model_card
from n26.library.models import Skill
from n26.tests.sandbox.actions import (
    adds,
    create_counter,
    create_default_set,
    create_rule,
    found_gang,
    hire_with_option,
    modifier,
    offers_choice,
    tally,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def xp(db):
    return create_counter("XP")


@pytest.fixture
def gang(gang_type):
    return found_gang("The Bad Girls", gang_type, owner=User.objects.create_user("t"))


@pytest.fixture
def queen(make_profile, xp, gang_type):
    """A fighter entry printing Starting XP 61 — the set member's amount."""
    profile = make_profile("Gang Queen", price=135)
    profile.built_ins = create_default_set(
        "Queen built-ins", members=[(xp, {"amount": 61})]
    )
    profile.save()
    # The gang-wide rules that hang off the value:
    modifier(
        "Promotion offer at 75 XP",
        targets_model(when_counter=xp, at_least=75),
        offers_choice(Skill),
        carried_by=gang_type,
    )
    modifier(
        "Veteran title at 100 XP",
        targets_model(when_counter=xp, at_least=100),
        adds(create_rule("Veteran")),
        carried_by=gang_type,
    )
    return profile


def xp_row(miniature):
    return Assignment.objects.get(miniature=miniature, counter__isnull=False)


def drawn(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([n.assignable for n in card.all_nodes()])
    return build_model_card(miniature, card=card, computed=compute(card, index)), (
        compute(card, index)
    )


class TestTheTally:
    def test_a_fighter_arrives_at_their_starting_xp(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        assert xp_row(yolanda).counter_value.value == 61

    def test_tally_moves_it_and_floors_at_zero(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        row = xp_row(yolanda)

        assert tally(row, +5, note="won a battle") == 66
        assert tally(row, -100) == 0

    def test_every_change_is_a_ledger_event(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        row = xp_row(yolanda)
        tally(row, +5, note="won a battle")

        kinds = [event.kind for event in row.ledger_events.all()]
        assert kinds.count("tallied") == 1


class TestEffectsHangOffValues:
    def test_below_the_threshold_nothing_shows(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        card, computed = drawn(yolanda)

        assert computed.choices == []
        assert card.rules == []

    def test_the_offer_appears_when_xp_crosses_75(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), +14)  # 75

        card, computed = drawn(yolanda)
        (slot,) = computed.choices
        assert slot.is_resolved is False
        assert card.rules == []  # the title needs 100

    def test_the_title_appears_at_100_and_names_its_source(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), +39)  # 100

        card, _ = drawn(yolanda)
        (title,) = card.rules
        assert title.name == "Veteran"
        assert title.provenance.computed is True

    def test_it_withdraws_if_the_value_drops(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        row = xp_row(yolanda)
        tally(row, +39)
        tally(row, -50)

        card, computed = drawn(yolanda)
        assert computed.choices == []
        assert card.rules == []

    def test_the_plan_shows_the_threshold_round(self, gang, queen):
        """The debugging surface: why is my promotion not showing?"""
        yolanda = hire_with_option(gang, queen, "Yolanda")
        _, computed = drawn(yolanda)

        step = next(s for s in computed.plan if "offers a choice" in s.effect)
        assert step.ran_in == 1  # conditioned scopes wait for settled facts
        assert step.outcome == "skipped"
        assert "at XP 75+" in step.scope
