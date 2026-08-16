"""Counters, with XP as the first one — and effects hanging off values.

XP is a Counter so that the machinery gets
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
    counter_at_least,
    create_counter,
    create_default_set,
    create_rule,
    found_gang,
    hire_with_option,
    modifier,
    offers_choice,
    tally,
    targets_every_model,
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
        targets_every_model(counter_at_least(xp, 75)),
        offers_choice(Skill),
        carried_by=gang_type,
    )
    modifier(
        "Veteran title at 100 XP",
        targets_every_model(counter_at_least(xp, 100)),
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


class TestWhatTheCardShows:
    """The XP cell on a card is the counter's value — one number, not two.

    A fighter hired with "Starting XP 61" printed on their entry read
    0 XP on their card while the counter beside it said 61.
    """

    def test_a_hired_fighters_card_opens_at_their_starting_xp(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        card, _ = drawn(yolanda)

        assert card.xp == 61
        assert card.xp_display == "61/–"

    def test_the_card_follows_the_tally(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), +5)

        assert drawn(yolanda)[0].xp == 66

    def test_a_counter_is_not_drawn_as_a_piece_of_equipment(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")

        assert [line.name for line in drawn(yolanda)[0].equipment] == []


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


class TestARuleThatMovesACounter:
    """The stored effect: assigning its carrier tallies the bearer's
    counter, through the ledger. "If selected as the Outcast Leader …
    starts with 61 XP" — the selection arrives after the hire, so no
    built-in member can carry the value; the carrier moves it instead.
    Taking the carrier back never moves it back: a tally is history.
    """

    @pytest.fixture
    def leader_mark(self, xp):
        from n26.tests.sandbox.actions import create_subtype, op_changes_counter

        subtype = create_subtype("Chosen Leader")
        modifier(
            "The chosen Leader starts with 61 XP",
            targets_model(),
            op_changes_counter(xp, "set", 61),
            carried_by=subtype,
        )
        return subtype

    def test_assigning_the_carrier_sets_the_counter(self, gang, queen, leader_mark):
        from n26.core.reconcile import assert_reconciled
        from n26.tests.sandbox.actions import assign

        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), -51)  # spent down to 10 before the selection
        assign(leader_mark, miniature=yolanda)

        assert xp_row(yolanda).counter_value.value == 61
        assert_reconciled(gang)

    def test_the_move_is_a_ledger_event_naming_its_source(
        self, gang, queen, leader_mark
    ):
        from n26.tests.sandbox.actions import assign

        yolanda = hire_with_option(gang, queen, "Yolanda")
        assign(leader_mark, miniature=yolanda)

        event = xp_row(yolanda).ledger_events.filter(kind="tallied").latest("created")
        assert event.note == "Chosen Leader"

    def test_add_and_subtract_move_it_relative(self, gang, xp, make_profile):
        from n26.tests.sandbox.actions import (
            assign,
            create_default_set,
            create_subtype,
            op_changes_counter,
        )

        profile = make_profile("Plain Ganger", price=10)
        profile.built_ins = create_default_set("Kit", members=[(xp, {"amount": 10})])
        profile.save()
        fighter = hire_with_option(gang, profile, "Vex")

        bloodied = create_subtype("Bloodied")
        modifier(
            "Bloodied grants 3 XP",
            targets_model(),
            op_changes_counter(xp, "add", 3),
            carried_by=bloodied,
        )
        humbled = create_subtype("Humbled")
        modifier(
            "Humbled takes 100 XP",
            targets_model(),
            op_changes_counter(xp, "subtract", 100),
            carried_by=humbled,
        )

        assign(bloodied, miniature=fighter)
        assert xp_row(fighter).counter_value.value == 13
        assign(humbled, miniature=fighter)
        # The floor is tally's own: a counter never goes below zero.
        assert xp_row(fighter).counter_value.value == 0

    def test_a_bearer_without_the_counter_gains_it(self, gang, xp, make_profile):
        """A model whose entry never carried the counter still ends up
        keeping one — created by the rule, caused by its carrier, so it
        leaves if the carrier does."""
        from n26.tests.sandbox.actions import (
            assign,
            create_subtype,
            op_changes_counter,
        )

        profile = make_profile("Counterless", price=10)
        fighter = hire_with_option(gang, profile, "Nix")

        marked = create_subtype("Marked")
        modifier(
            "Marked starts the count at 5",
            targets_model(),
            op_changes_counter(xp, "set", 5),
            carried_by=marked,
        )
        carrier = assign(marked, miniature=fighter)

        row = xp_row(fighter)
        assert row.counter_value.value == 5
        assert row.caused_by == carrier

    def test_taking_the_carrier_back_does_not_move_it_back(
        self, gang, queen, leader_mark
    ):
        from n26.tests.sandbox.actions import assign, remove

        yolanda = hire_with_option(gang, queen, "Yolanda")
        carrier = assign(leader_mark, miniature=yolanda)
        remove(carrier)

        # The counter row predates the rule, so it stays — and so does
        # the value the rule set: a tally is history, not state the
        # carrier holds open.
        assert xp_row(yolanda).counter_value.value == 61
