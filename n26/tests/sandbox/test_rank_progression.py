"""Earned rank actions keep their original table as effective access changes."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db import connection
from django.template.loader import render_to_string
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.card import build_card, build_modifier_index, carriers
from n26.core.effects import compute
from n26.core.models import ActionAllowance
from n26.core.operations import operation
from n26.core.progression import progression_for
from n26.core.render import build_model_card, render_gang
from n26.library import authoring as a
from n26.tests.sandbox.actions import found_gang, hire

pytestmark = pytest.mark.django_db


@pytest.fixture
def fighter_with_ranks(
    default_pack, gang_type, make_profile, make_statline, counter_tracking
):
    owner = User.objects.create_user("rank-history-player")
    gang = found_gang("The Climbers", gang_type, owner=owner, budget=1000)
    profile = make_profile("Prospect", price=100)
    make_statline(profile)
    fighter = hire(gang, profile, "Kara", paid=100)
    xp = a.create_counter("XP")
    table = a.create_rank_table("Prospect ranks", xp, initial_title="Rookie")
    for threshold, title in (
        (4, "Rookie"),
        (7, "Rookie"),
        (10, "Gang Member"),
    ):
        a.add_rank_threshold(table, threshold, title=title)
    outcome = a.create_outcome(
        "Training complete", a.apply_changes(a.counter_change(xp, "add", 1))
    )
    action = a.create_action(
        "Training",
        "post_cycle",
        outcomes=[outcome],
        allowance_rule=a.rank_allowance_rule(xp),
    )
    with operation(gang, actor=owner) as op:
        op.assign(action, miniature=fighter)
        table_assignment = op.assign(table, miniature=fighter)
        counter_assignment = op.assign(xp, miniature=fighter)
        op.open_counter(counter_assignment, 0)
    return SimpleNamespace(
        owner=owner,
        gang=gang,
        fighter=fighter,
        profile=profile,
        table=table,
        table_assignment=table_assignment,
        counter=counter_assignment,
        action=action,
        outcome=outcome,
    )


def _read(fighter):
    card = build_card(fighter)
    computed = compute(card, build_modifier_index(carriers(card)))
    with CaptureQueriesContext(connection) as queries:
        display = progression_for(fighter, card=card, computed=computed)
    return display, len(queries)


class TestRankActionHistory:
    """A title is current standing; earned allowances and results are history."""

    def test_zero_value_has_an_initial_title_but_no_earned_history(
        self, fighter_with_ranks
    ):
        display, _ = _read(fighter_with_ranks.fighter)

        assert display.history == ()
        assert (
            display.summaries[0].value,
            display.summaries[0].current_title,
            display.summaries[0].next_threshold,
        ) == (0, "Rookie", 4)

    def test_history_survives_access_loss_and_does_not_query_per_rank(
        self, fighter_with_ranks
    ):
        setup = fighter_with_ranks
        with operation(setup.gang, actor=setup.owner) as op:
            op.tally(setup.counter, 4)
        allowance = ActionAllowance.objects.get(fighter=setup.fighter, threshold=4)
        with operation(setup.gang, actor=setup.owner) as op:
            record = op.start_action(
                setup.fighter, setup.action, uuid4(), allowance=allowance
            )
        with operation(setup.gang, actor=setup.owner) as op:
            record = op.review_action(record, outcome=setup.outcome)
        with operation(setup.gang, actor=setup.owner) as op:
            op.complete_action(
                record,
                revision=record.revision,
                review=record.review,
                outcome=setup.outcome,
            )
        first, one_query_count = _read(setup.fighter)
        assert (
            first.summaries[0].value,
            first.summaries[0].next_threshold,
            first.history[0].threshold,
            first.history[0].title,
            first.history[0].state,
            first.history[0].result,
        ) == (5, 7, 4, "Rookie", "completed", "Training complete")
        status = render_to_string(
            "n26/includes/progression_status.html", {"progression": first}
        )
        history = render_to_string(
            "n26/includes/progression_history.html",
            {"progression": first, "miniature": setup.fighter},
        )
        assert "Next rank at 7 XP" in status
        assert "4 XP" in history
        assert "Training · Training complete" in history
        assert "View receipt" in history

        with operation(setup.gang, actor=setup.owner) as op:
            op.tally(setup.counter, 5)
        more, many_query_count = _read(setup.fighter)
        assert one_query_count == many_query_count
        assert [(row.threshold, row.state) for row in more.history] == [
            (4, "completed"),
            (7, "available"),
            (10, "available"),
        ]
        assert more.summaries[0].current_title == "Gang Member"

        with operation(setup.gang, actor=setup.owner) as op:
            op.remove(setup.table_assignment)
        former, _ = _read(setup.fighter)
        assert former.summaries == ()
        assert [row.table_name for row in former.history] == [
            "Prospect ranks",
            "Prospect ranks",
            "Prospect ranks",
        ]


class TestRankedCardSurfaces:
    """The card and live updates agree with the effective rank table."""

    def test_competing_xp_tables_do_not_choose_a_rank_target(self, fighter_with_ranks):
        setup = fighter_with_ranks
        other = a.create_rank_table("Other prospect ranks", setup.counter.counter)
        a.add_rank_threshold(other, 5, title="Other rank")
        with operation(setup.gang, actor=setup.owner) as op:
            op.assign(other, miniature=setup.fighter)

        rendered = build_model_card(setup.fighter)

        assert rendered.rank_summaries == ()
        assert rendered.xp_target == setup.fighter.xp_target
        assert rendered.xp_display == "0/–"

    def test_rank_target_keeps_effective_xp_from_a_modifier(self, fighter_with_ranks):
        setup = fighter_with_ranks
        a.add_rank_threshold(setup.table, 73, title="Gang Exemplar")
        carrier = a.create_subtype("Seasoned")
        a.modifier(
            "Seasoned adds 5 XP",
            a.targets_model(),
            a.ef_contributes_to_counter(setup.counter.counter, 5),
            attach_to=carrier,
        )
        with operation(setup.gang, actor=setup.owner) as op:
            op.tally(setup.counter, 61)
            op.assign(carrier, miniature=setup.fighter)

        card = build_card(setup.fighter)
        computed = compute(card, build_modifier_index(carriers(card)))
        rendered = build_model_card(setup.fighter, card=card, computed=computed)

        assert rendered.xp == 66
        assert rendered.xp_target == 73
        assert rendered.xp_display == "66/73"
        assert rendered.rank_summaries[0].value == 61

    def test_annotated_xp_still_sets_the_rank_target(self, fighter_with_ranks):
        setup = fighter_with_ranks
        xp = setup.counter.counter
        xp.annotation = "Campaign"
        xp.save(update_fields=["annotation"])

        rendered = build_model_card(setup.fighter)

        assert rendered.rank_summaries[0].counter_name == "XP (Campaign)"
        assert rendered.rank_summaries[0].is_xp
        assert rendered.xp_target == 4
        assert rendered.xp_display == "0/4"

    def test_the_card_and_both_model_screens_show_the_next_authored_xp_target(
        self, client, fighter_with_ranks
    ):
        setup = fighter_with_ranks
        card = build_model_card(setup.fighter)
        assert card.rank_summaries[0].current_title == "Rookie"
        assert card.xp_display == "0/4"
        client.force_login(setup.owner)

        edit = client.get(reverse("n26-edit-fighter", args=[setup.fighter.pk]))
        equip = client.get(reverse("n26-equip", args=[setup.fighter.pk]))

        assert edit.status_code == equip.status_code == 200
        for response in (edit, equip):
            assert "Rookie" in response.content.decode()
            assert "Next rank at 4 XP" in response.content.decode()
        assert 'id="n26-progression-status"' in edit.content.decode()
        assert 'id="n26-progression-status"' not in equip.content.decode()

    def test_a_live_counter_change_replaces_edit_status_history_and_equip_card(
        self, client, fighter_with_ranks
    ):
        setup = fighter_with_ranks
        with operation(setup.gang, actor=setup.owner) as op:
            op.tally(setup.counter, 3)
        client.force_login(setup.owner)
        tally_url = reverse("n26-tally", args=[setup.counter.pk])
        edit_url = reverse("n26-edit-fighter", args=[setup.fighter.pk])
        equip_url = reverse("n26-equip", args=[setup.fighter.pk])

        edit_update = client.post(
            tally_url,
            {"change": "1", "back": edit_url},
            HTTP_HX_REQUEST="true",
        )
        edit_html = edit_update.content.decode()
        assert edit_update.status_code == 200
        edit_page = BeautifulSoup(edit_html, "html.parser")
        assert edit_page.find(id="n26-progression-status").get("hx-swap-oob") == (
            "outerHTML"
        )
        assert edit_page.find(id="n26-progression-history").get("hx-swap-oob") == (
            "outerHTML"
        )
        assert "Next rank at 7 XP" in edit_html
        assert "4 XP" in edit_html

        equip_update = client.post(
            tally_url,
            {"change": "1", "back": equip_url},
            HTTP_HX_REQUEST="true",
        )
        equip_html = equip_update.content.decode()
        assert equip_update.status_code == 200
        assert 'id="n26-model-card-host"' in equip_html
        assert "Next rank at 7 XP" in equip_html
        assert 'id="n26-progression-status"' not in equip_html

    def test_more_ranked_fighters_do_not_add_roster_queries(self, fighter_with_ranks):
        setup = fighter_with_ranks

        def measure():
            with CaptureQueriesContext(connection) as queries:
                sheet = render_gang(setup.gang)
            assert all(card.rank_summaries for card in sheet.models)
            return len(queries)

        one = measure()
        for number in range(3):
            fighter = hire(setup.gang, setup.profile, f"Prospect {number}", paid=100)
            with operation(setup.gang, actor=setup.owner) as op:
                op.assign(setup.action, miniature=fighter)
                op.assign(setup.table, miniature=fighter)
                counter = op.assign(setup.counter.counter, miniature=fighter)
                op.open_counter(counter, 0)
        assert measure() == one
