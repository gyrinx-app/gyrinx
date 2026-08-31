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
from django.urls import reverse

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
def kills(db):
    """A second counter, so a card has to keep more than one."""
    return create_counter("Kill Count")


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
    return Assignment.objects.get(miniature=miniature, counter__name="XP")


def kill_row(miniature):
    return Assignment.objects.get(miniature=miniature, counter__name="Kill Count")


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

    def test_a_counter_draws_a_line_of_its_own(self, gang, queen, kills):
        """Every counter a model keeps is a line on their card. A
        Spyrer's Kill Count is granted, stored and tallied like any
        other, and reads on the card like any other."""
        from n26.tests.sandbox.actions import assign

        yolanda = hire_with_option(gang, queen, "Yolanda")
        assign(kills, miniature=yolanda)

        assert [(line.name, line.value) for line in drawn(yolanda)[0].counters] == [
            ("XP", 61),
            ("Kill Count", 0),
        ]

    def test_the_line_follows_the_tally(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), +5)

        assert drawn(yolanda)[0].counters[0].value == 66

    def test_xp_leads_however_the_card_holds_them(self, gang, queen, kills):
        """XP first: it is the one every model keeps and the one a
        reader looks for."""
        from n26.tests.sandbox.actions import assign

        yolanda = hire_with_option(gang, queen, "Yolanda")
        assign(kills, miniature=yolanda)

        assert [line.name for line in drawn(yolanda)[0].counters] == [
            "XP",
            "Kill Count",
        ]

    def test_a_line_carries_the_assignment_behind_it(self, gang, queen):
        """What a control posts to. A card built from library alone has
        none, which is how it says there is nothing here to change."""
        yolanda = hire_with_option(gang, queen, "Yolanda")

        assert drawn(yolanda)[0].counters[0].assignment_id == str(xp_row(yolanda).pk)

    def test_a_line_has_no_address_until_somebody_gives_it_one(self, gang, queen):
        """Every control is drawn from an href, and nothing here fills
        one: a gang sheet and a print sheet draw settled numbers."""
        yolanda = hire_with_option(gang, queen, "Yolanda")

        assert drawn(yolanda)[0].counters[0].href == ""

    def test_an_xp_nobody_can_move_is_the_cell_and_not_a_line(self, gang, queen, kills):
        """XP has a cell with its target in it. The line earns its place
        by being where the number is changed, so where nothing can be
        changed it would only say 61 twice."""
        yolanda = hire_with_option(gang, queen, "Yolanda")
        from n26.tests.sandbox.actions import assign

        assign(kills, miniature=yolanda)
        card = drawn(yolanda)[0]

        assert [line.name for line in card.counter_lines] == ["Kill Count"]

    def test_it_is_a_line_again_once_it_can_be_moved(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        card = drawn(yolanda)[0]
        card.counters[0].href = "/somewhere/"

        assert [line.name for line in card.counter_lines] == ["XP"]


class TestMovingACounterByHand:
    """The control on the model's own page, and the address behind it.

    A counter is drawn wherever a card is and moved in one place. The
    same address serves XP, a Spyrer's Kill Count and the gang's own
    tallies, because what it names is the assignment.
    """

    def address(self, miniature):
        """Where this model's XP is moved from."""
        row = Assignment.objects.get(miniature=miniature, counter__name="XP")
        return reverse("n26-tally", args=[row.pk])

    def test_the_models_own_page_offers_the_control(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        page = client.get(reverse("n26-edit-fighter", args=[yolanda.pk]))

        assert self.address(yolanda) in page.content.decode()

    def test_the_gang_sheet_does_not(self, client, gang, queen, kills):
        """Changing these quickly, for a roster at a time after a battle,
        is a screen built for it — not a control the sheet grows."""
        from n26.tests.sandbox.actions import assign

        yolanda = hire_with_option(gang, queen, "Yolanda")
        counted = assign(kills, miniature=yolanda)
        client.force_login(gang.owner)

        page = client.get(reverse("n26-gang", args=[gang.pk]))

        drawn_there = page.content.decode()
        # The number is on the sheet; the way to change it is not.
        assert "Kill Count" in drawn_there
        assert reverse("n26-tally", args=[counted.pk]) not in drawn_there

    def test_a_step_up_moves_it(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        client.post(self.address(yolanda), {"change": "1"})

        assert xp_row(yolanda).counter_value.value == 62

    def test_a_step_down_moves_it_back(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        client.post(self.address(yolanda), {"change": "-1"})

        assert xp_row(yolanda).counter_value.value == 60

    def test_it_floors_at_zero(self, client, gang, queen):
        """The floor is ``tally``'s own, so a control that has gone
        stale takes the value to zero rather than below it."""
        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), -61)
        client.force_login(gang.owner)

        client.post(self.address(yolanda), {"change": "-1"})

        assert xp_row(yolanda).counter_value.value == 0

    def test_the_change_is_a_ledger_event(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        client.post(self.address(yolanda), {"change": "1"})

        event = xp_row(yolanda).ledger_events.filter(kind="tallied").latest("created")
        assert event.note == "+1 → 62"

    def test_it_returns_to_the_page_the_click_came_from(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        back = reverse("n26-edit-fighter", args=[yolanda.pk])
        client.force_login(gang.owner)

        response = client.post(self.address(yolanda), {"change": "1", "back": back})

        assert response.status_code == 302
        assert response["Location"] == back

    def test_it_will_not_be_sent_somewhere_else(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        response = client.post(
            self.address(yolanda), {"change": "1", "back": "https://elsewhere.test/"}
        )

        assert response["Location"] == reverse("n26-gang", args=[gang.pk])

    def test_somebody_elses_counter_is_not_theirs_to_move(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(User.objects.create_user("interloper"))

        response = client.post(self.address(yolanda), {"change": "1"})

        assert response.status_code == 404
        assert xp_row(yolanda).counter_value.value == 61

    def test_only_counters_are_tallied(self, client, gang, queen):
        """Every other assignment has verbs of its own, and none of them
        is a running number."""
        from n26.tests.sandbox.actions import assign

        yolanda = hire_with_option(gang, queen, "Yolanda")
        not_a_counter = assign(create_rule("Bonded to the Rig"), miniature=yolanda)
        client.force_login(gang.owner)

        response = client.post(
            reverse("n26-tally", args=[not_a_counter.pk]), {"change": "1"}
        )

        assert response.status_code == 404

    def test_a_step_of_nothing_is_not_an_act(self, client, gang, queen):
        """It would write a ledger event recording that nothing
        happened. No control offers it; a crafted post is refused."""
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        response = client.post(self.address(yolanda), {"change": "0"})

        assert response.status_code == 404
        assert not xp_row(yolanda).ledger_events.filter(kind="tallied").exists()

    def test_a_step_past_what_the_column_holds_is_refused(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        response = client.post(self.address(yolanda), {"change": "99999999999"})

        assert response.status_code == 404
        assert xp_row(yolanda).counter_value.value == 61

    def test_a_change_that_is_not_a_number_is_no_address_at_all(
        self, client, gang, queen
    ):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        response = client.post(self.address(yolanda), {"change": "lots"})

        assert response.status_code == 404
        assert xp_row(yolanda).counter_value.value == 61


class TestTheOtherSurfaces:
    """Print and text draw the same counters the screen card draws.

    Both read ``counter_lines``, so neither can disagree with the card
    about which counters a model keeps — nor about XP, which has a cell
    in the statline on all three and draws a line on none of them.
    """

    def test_the_text_card_lists_them(self, gang, queen, kills):
        from n26.core.render_text import render_model_card
        from n26.tests.sandbox.actions import assign

        yolanda = hire_with_option(gang, queen, "Yolanda")
        assign(kills, miniature=yolanda)
        tally(kill_row(yolanda), +3)

        assert "Kill Count: 3" in "\n".join(render_model_card(drawn(yolanda)[0]))

    def test_the_text_card_keeps_xp_to_its_own_line(self, gang, queen):
        from n26.core.render_text import render_model_card

        yolanda = hire_with_option(gang, queen, "Yolanda")

        told = render_model_card(drawn(yolanda)[0])
        assert len([line for line in told if "XP" in line]) == 1

    def test_the_print_sheet_leads_with_them(self, gang, queen, kills):
        from n26.core.printing import detail_groups
        from n26.tests.sandbox.actions import assign

        yolanda = hire_with_option(gang, queen, "Yolanda")
        assign(kills, miniature=yolanda)

        groups = detail_groups(drawn(yolanda)[0])
        assert (groups[0].label, groups[0].text) == ("Kill Count", "0")

    def test_the_print_sheet_says_xp_once(self, gang, queen):
        """It has a cell in the statline above, and a card somebody cuts
        out has no room to say a number twice."""
        from n26.core.printing import detail_groups

        yolanda = hire_with_option(gang, queen, "Yolanda")

        assert not [
            group for group in detail_groups(drawn(yolanda)[0]) if group.label == "XP"
        ]


class TestWhatTheHistorySays:
    """A tally drawn as a sentence: what moved, and where it landed.

    The number on the card is the only thing a reader can check the log
    against, so the log has to state it.
    """

    def told(self, gang):
        from n26.core import history

        return [
            "".join(span.text for span in act.spans)
            for act in history.build(gang, viewer=gang.owner)
        ]

    def test_it_says_what_moved_and_where_it_landed(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), +5)

        assert any(
            "changed XP" in told and "+5, now 66" in told for told in self.told(gang)
        )

    def test_a_step_that_hit_the_floor_says_where_it_stopped(self, gang, queen):
        """The movement stated is the one that happened, not the one
        asked for."""
        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), -100)

        assert any("-61, now 0" in told for told in self.told(gang))

    def test_what_caused_it_rides_along(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), +5, note="won a battle")

        assert any("(won a battle)" in told for told in self.told(gang))

    def test_the_note_is_not_printed_under_the_sentence_as_well(self, gang, queen):
        """The sentence already holds both halves of it."""
        from n26.core import history

        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), +5, note="won a battle")

        # Spans carry their own spacing, so the phrase only reads whole
        # once they are joined.
        tallied = [
            act
            for act in history.build(gang, viewer=gang.owner)
            if "changed XP" in "".join(span.text for span in act.spans)
        ]
        assert tallied and all(not act.note for act in tallied)


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
        # What moved and where it landed, then what caused it. A reader
        # auditing the number needs both halves.
        assert event.note == "+0 → 61: Chosen Leader"

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
