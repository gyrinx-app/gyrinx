"""A territory's answer is an ordinary assignment for one ownership period.

The holding, its ownership revision and the authored Slot identify the
question. Its answer and everything that answer brings leave together when
the territory changes hands, while their ledger history stays readable.
"""

from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.http import Http404
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.campaigns import campaign_operation
from n26.core.card import build_gang_card, build_modifier_index, carriers
from n26.core.effects import compute, compute_gang
from n26.core.history import build
from n26.core.models import (
    Assignment,
    CampaignAsset,
    DismissedOffer,
    LedgerEvent,
    Miniature,
)
from n26.core.operations import Refusal, clone_gang, operation
from n26.core.reconcile import assert_reconciled
from n26.core.render import GANG_SLOT_HOST, choice_lines, render_gang, slot_key
from n26.core.views.choose import find_slot, settle_dismissed
from n26.library.authoring import (
    add_asset_type,
    add_built_in,
    add_picklist_member,
    create_asset,
    create_campaign_type,
    create_counter,
    create_hidden,
    create_pickable,
    create_picklist,
    create_profile,
    create_slot,
    create_slot_type,
    create_wargear,
    ef_adds,
    ef_contributes_to_counter,
    modifier,
    op_adds_model,
    op_changes_counter,
    targets_every_model,
    targets_gang,
    targets_gang_alone,
)
from n26.library.journal_content import seed_journal_content
from n26.library.models import Asset, CampaignType
from n26.tests.fixtures import admit_to_founding, library_setup
from n26.tests.sandbox.actions import (
    add_asset,
    archive_campaign,
    assign,
    assign_asset,
    found_campaign,
    found_gang,
    hire,
    join_campaign,
    remove,
    remove_asset,
    remove_from_campaign,
    transfer_asset,
    unassign_asset,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
@library_setup
def content(default_pack, gang_type, person_type):
    income = create_counter("Income")
    reputation = create_counter("Reputation")
    campaign_type = create_campaign_type("Territory choices")
    add_built_in(campaign_type, income)
    add_built_in(campaign_type, reputation)
    territory = add_asset_type(campaign_type, "Territory", "pooled")
    asset = create_asset("Workshop", territory, income=15)
    kind = create_slot_type("Territory benefit")
    income_pick = create_pickable(
        "Extra income",
        kind,
        effects=[(targets_gang_alone(), ef_contributes_to_counter(income, 5))],
    )
    reputation_pick = create_pickable(
        "Local reputation",
        kind,
        effects=[(targets_gang_alone(), ef_contributes_to_counter(reputation, 2))],
    )
    table = create_picklist(
        "Workshop benefits", kind, members=[income_pick, reputation_pick]
    )
    slot = create_slot("Workshop benefit", kind, table, assigned_to="gang")
    modifier(
        "Workshop offers a benefit",
        targets_gang_alone(),
        ef_adds(slot),
        attach_to=asset,
    )
    profile = create_profile("Guard", person_type, gang_type)
    return {
        "campaign_type": campaign_type,
        "asset": asset,
        "kind": kind,
        "slot": slot,
        "income": income,
        "reputation": reputation,
        "income_pick": income_pick,
        "reputation_pick": reputation_pick,
        "profile": profile,
    }


@pytest.fixture
def campaign(content):
    return found_campaign(
        "Dust Falls",
        content["campaign_type"],
        owner=User.objects.create_user("arbitrator"),
        budget=1000,
    )


@pytest.fixture
def gang(gang_type, owner, campaign):
    gang = found_gang("Workshop keepers", gang_type, owner=owner)
    join_campaign(gang, campaign)
    return gang


@pytest.fixture
def rival(gang_type, campaign):
    gang = found_gang(
        "Other keepers", gang_type, owner=User.objects.create_user("rival")
    )
    join_campaign(gang, campaign)
    return gang


@pytest.fixture
def holding(campaign, gang, content):
    return assign_asset(add_asset(campaign, content["asset"]), gang)


def computed(gang):
    card = build_gang_card(gang)
    return compute_gang(card, build_modifier_index(carriers(card)))


def question(gang, holding, slot):
    return next(
        choice
        for choice in computed(gang).choices
        if choice.holding is not None
        and choice.holding.pk == holding.pk
        and choice.slot.pk == slot.pk
    )


def key_for(gang, holding, slot):
    return slot_key(question(gang, holding, slot), GANG_SLOT_HOST)


def choose_for(holding, pick, slot, *, gang=None, previous=None, roll=None):
    gang = gang or holding.holder.gang
    with campaign_operation(holding.campaign, actor=gang.owner):
        with operation(gang, actor=gang.owner) as op:
            if previous is not None:
                op.remove(previous)
            return op.choose(holding, pick, slot=slot, roll=roll)


def values(gang):
    return {reading.name: reading.value for reading in computed(gang).counters}


def counts():
    return (
        Assignment.objects.count(),
        LedgerEvent.objects.count(),
        DismissedOffer.objects.count(),
    )


def sentences(gang):
    return ["".join(span.text for span in act.spans) for act in build(gang)]


class TestStandingHoldingChoices:
    """Two copies of one territory ask separate questions and apply each answer once."""

    def test_the_pick_is_a_free_gang_assignment_with_an_explicit_holding_origin(
        self, holding, gang, content
    ):
        assert values(gang) == {"Income": 15, "Reputation": 0}
        pick = choose_for(holding, content["income_pick"], content["slot"])
        assert pick.gang_id == gang.pk
        assert pick.chosen_for_holding_id == holding.pk
        assert pick.chosen_for_holding_revision == holding.ownership_revision
        assert pick.chosen_for_slot_id == content["slot"].pk
        assert pick.chosen_for_id is None and pick.caused_by_id is None
        assert pick.parent_id is None and pick.miniature_root_id is None
        assert (pick.ledger_entry.paid, pick.ledger_entry.rating_contribution) == (0, 0)
        assert not gang.assignments.filter(asset=content["asset"]).exists()
        assert values(gang) == {"Income": 20, "Reputation": 0}
        assert len(question(gang, holding, content["slot"]).picks) == 1
        assert LedgerEvent.objects.filter(
            assignment=pick, kind=LedgerEvent.Kind.GRANTED
        ).exists()
        assert_reconciled(gang)

    def test_two_holdings_of_the_same_asset_keep_independent_answers(
        self, holding, gang, campaign, content
    ):
        second = assign_asset(
            add_asset(campaign, content["asset"], name="East Workshop"), gang
        )
        first_key = key_for(gang, holding, content["slot"])
        second_key = key_for(gang, second, content["slot"])
        assert first_key != second_key
        assert (
            first_key
            == f"holding:{holding.pk}@{holding.ownership_revision}:{content['slot'].pk}"
        )
        first_pick = choose_for(holding, content["income_pick"], content["slot"])
        assert not question(gang, second, content["slot"]).picks
        second_pick = choose_for(second, content["reputation_pick"], content["slot"])
        assert [
            pick.assignment.pk
            for pick in question(gang, holding, content["slot"]).picks
        ] == [first_pick.pk]
        assert [
            pick.assignment.pk for pick in question(gang, second, content["slot"]).picks
        ] == [second_pick.pk]
        assert values(gang) == {"Income": 35, "Reputation": 2}
        sheet = render_gang(gang)
        assert [line.name for line in sheet.campaign.holdings] == [
            "Workshop",
            "East Workshop",
        ]
        assert {line.key for line in sheet.campaign.choices} == {first_key, second_key}

    def test_two_holdings_keep_separate_choices_through_the_same_hidden_carrier(
        self, gang, campaign, content
    ):
        favour = create_counter("Favour")
        add_built_in(content["profile"], favour)
        hidden = create_hidden(
            "Workshop benefits carrier",
            effects=[
                (targets_gang_alone(), ef_adds(content["slot"])),
                (targets_every_model(), ef_contributes_to_counter(favour, 3)),
            ],
        )
        asset = create_asset("Shared office", content["asset"].asset_type, income=7)
        modifier(
            "An office gives workshop benefits",
            targets_gang(),
            ef_adds(hidden),
            attach_to=asset,
        )
        holdings = [assign_asset(add_asset(campaign, asset), gang) for _ in range(2)]
        fighter = hire(gang, content["profile"], "Office keeper")
        choices = computed(gang).choices
        assert {choice.holding.pk for choice in choices} == {
            holding.pk for holding in holdings
        }
        assert all(
            choice.anchor is None and choice.slot.pk == content["slot"].pk
            for choice in choices
        )
        choose_for(holdings[0], content["income_pick"], content["slot"])
        choose_for(holdings[1], content["reputation_pick"], content["slot"])
        assert values(gang) == {"Income": 19, "Reputation": 2}
        card = build_gang_card(gang)
        index = build_modifier_index(carriers(card, *card.members.values()))
        with CaptureQueriesContext(connection) as queries:
            compute_gang(card, index)
            member = compute(card.members[fighter.pk], index)
            member_lines = choice_lines(member, str(fighter.pk))
        assert len(queries) == 0
        assert not [choice for choice in member.choices if choice.holding is not None]
        assert not [line for line in member_lines if line.key.startswith("holding:")]
        assert (
            sum(
                contribution.amount
                for contribution in member.counter_contributions
                if contribution.counter.pk == favour.pk
            )
            == 6
        )

    def test_replacement_and_removal_use_the_normal_assignment_lifecycle(
        self, holding, gang, content
    ):
        first = choose_for(holding, content["income_pick"], content["slot"])
        second = choose_for(
            holding, content["reputation_pick"], content["slot"], previous=first
        )
        first.refresh_from_db()
        assert first.archived and not second.archived
        assert values(gang) == {"Income": 15, "Reputation": 2}
        remove(second)
        assert not question(gang, holding, content["slot"]).picks
        assert values(gang) == {"Income": 15, "Reputation": 0}
        assert first.ledger_entry.pk is not None
        assert LedgerEvent.objects.filter(
            assignment=first, kind=LedgerEvent.Kind.REMOVED
        ).exists()

    def test_nested_choices_and_both_hosted_and_caused_children_leave_with_the_answer(
        self, holding, gang, content
    ):
        kind = create_slot_type("Workshop follow-up")
        nested_pick = create_pickable(
            "Well-known workshop",
            kind,
            effects=[
                (
                    targets_gang_alone(),
                    ef_contributes_to_counter(content["reputation"], 3),
                )
            ],
        )
        table = create_picklist("Workshop follow-ups", kind, members=[nested_pick])
        slot = create_slot("Follow-up", kind, table, assigned_to="gang")
        modifier(
            "Extra income asks a follow-up",
            targets_gang_alone(),
            ef_adds(slot),
            attach_to=content["income_pick"],
        )
        root = choose_for(holding, content["income_pick"], content["slot"])
        with operation(gang, actor=gang.owner) as op:
            nested = op.choose(root, nested_pick, slot=slot)
            hosted = op.assign(create_wargear("Workshop token"), parent=nested)
            caused = op.assign(
                create_wargear("Workshop grant"), gang=gang, caused_by=nested
            )
        assert values(gang) == {"Income": 20, "Reputation": 3}
        unassign_asset(holding)
        for assignment in (root, nested, hosted, caused):
            assignment.refresh_from_db()
            assert assignment.archived
            assert assignment.ledger_entry.pk is not None
        assert not computed(gang).choices
        assert values(gang) == {"Income": 0, "Reputation": 0}
        assert "Extra income" in " ".join(sentences(gang))
        assert_reconciled(gang)

    def test_a_selected_pick_runs_stored_effects_once_through_ordinary_assignment(
        self, holding, gang, content
    ):
        modifier(
            "Local reputation records goodwill",
            targets_gang_alone(),
            op_changes_counter(content["reputation"], "add", 3),
            attach_to=content["reputation_pick"],
        )
        pick = choose_for(holding, content["reputation_pick"], content["slot"])
        assert values(gang)["Reputation"] == 5
        counter = Assignment.objects.get(
            gang=gang, counter=content["reputation"], archived=False
        )
        assert counter.counter_value.value == 3
        before = counts()
        render_gang(gang)
        render_gang(gang)
        assert counts() == before
        counter.refresh_from_db()
        assert counter.counter_value.value == 3
        remove(pick)
        assert values(gang)["Reputation"] == 3
        assert_reconciled(gang)


class TestOwnershipLifetime:
    """A new ownership period never inherits an earlier answer or address."""

    def test_transfer_archives_the_old_answer_and_gives_the_recipient_an_open_question(
        self, holding, gang, rival, content
    ):
        pick = choose_for(holding, content["income_pick"], content["slot"])
        old_key = key_for(gang, holding, content["slot"])
        old_revision = holding.ownership_revision
        current = transfer_asset(holding, rival)
        assert current.ownership_revision == old_revision + 1
        pick.refresh_from_db()
        assert pick.archived
        assert values(gang)["Income"] == 0
        assert values(rival)["Income"] == 15
        assert not question(rival, current, content["slot"]).picks
        assert key_for(rival, current, content["slot"]) != old_key
        with pytest.raises(Http404):
            find_slot(gang, old_key)
        with pytest.raises(Http404):
            find_slot(rival, old_key)
        assert pick.chosen_for_holding_revision == old_revision
        assert_reconciled(gang)
        assert_reconciled(rival)

    def test_loss_and_reacquisition_create_a_new_question_for_the_same_gang(
        self, holding, gang, content
    ):
        pick = choose_for(holding, content["reputation_pick"], content["slot"])
        old_key = key_for(gang, holding, content["slot"])
        revision = holding.ownership_revision
        unassign_asset(holding)
        current = assign_asset(holding, gang)
        assert current.ownership_revision == revision + 2
        assert not question(gang, current, content["slot"]).picks
        assert values(gang) == {"Income": 15, "Reputation": 0}
        pick.refresh_from_db()
        assert pick.archived
        before = counts()
        with pytest.raises(Refusal, match="ownership"):
            choose_for(holding, content["income_pick"], content["slot"], gang=gang)
        assert counts() == before
        with pytest.raises(Http404):
            find_slot(gang, old_key)

    def test_repeated_assignment_keeps_the_ownership_revision_and_answer(
        self, holding, gang, content
    ):
        pick = choose_for(holding, content["income_pick"], content["slot"])
        before = counts()
        current = assign_asset(holding, gang)
        assert current.ownership_revision == holding.ownership_revision
        assert counts() == before
        assert (
            question(gang, current, content["slot"]).picks[0].assignment.pk == pick.pk
        )

    @pytest.mark.parametrize(
        "exit_campaign",
        [remove_from_campaign, archive_campaign],
        ids=["leave", "archive"],
    )
    def test_leaving_or_archiving_ends_the_answer_in_the_ownership_transaction(
        self, holding, gang, campaign, content, exit_campaign
    ):
        pick = choose_for(holding, content["income_pick"], content["slot"])
        revision = holding.ownership_revision
        if exit_campaign is remove_from_campaign:
            exit_campaign(gang, campaign)
        else:
            exit_campaign(campaign)
        holding.refresh_from_db()
        pick.refresh_from_db()
        assert holding.holder_id is None
        assert holding.ownership_revision == revision + 1
        assert pick.archived
        assert render_gang(gang).campaign is None
        assert LedgerEvent.objects.filter(assignment=pick).exists()
        assert_reconciled(gang)

    def test_removing_an_unheld_asset_preserves_the_answer_and_its_history(
        self, holding, gang, content
    ):
        pick = choose_for(holding, content["income_pick"], content["slot"])
        revision = holding.ownership_revision
        unassign_asset(holding)
        remove_asset(holding)
        assert not CampaignAsset.objects.filter(pk=holding.pk).exists()
        pick.refresh_from_db()
        assert pick.archived and pick.chosen_for_holding_id is None
        assert pick.chosen_for_holding_revision == revision
        assert pick.chosen_for_slot_id == content["slot"].pk
        assert LedgerEvent.objects.filter(assignment=pick).exists()
        history = " ".join(sentences(gang))
        assert "Extra income" in history and "Workshop" in history
        assert_reconciled(gang)

    def test_ownership_change_and_answer_removal_roll_back_together(
        self, holding, gang, content
    ):
        pick = choose_for(holding, content["income_pick"], content["slot"])
        before = counts()
        with pytest.raises(RuntimeError, match="cancel the act"):
            with campaign_operation(
                holding.campaign, actor=holding.campaign.owner
            ) as act:
                act.unassign(holding)
                raise RuntimeError("cancel the act")
        holding.refresh_from_db()
        pick.refresh_from_db()
        assert holding.held and not pick.archived
        assert holding.ownership_revision == pick.chosen_for_holding_revision
        assert counts() == before
        assert values(gang)["Income"] == 20


class TestTheSharedPicker:
    """The existing picker and dismissal flow resolve the holding's current address."""

    def test_the_owner_can_choose_and_replace_at_the_normal_picker(
        self, client, owner, holding, gang, content
    ):
        admit_to_founding(owner)
        client.force_login(owner)
        url = reverse(
            "n26-choose", args=[gang.pk, key_for(gang, holding, content["slot"])]
        )
        before = counts()
        response = client.get(url)
        assert response.status_code == 200
        assert "Extra income" in response.content.decode()
        assert counts() == before
        assert (
            client.post(
                url, {"thing": f"library.pickable:{content['income_pick'].pk}"}
            ).status_code
            == 302
        )
        first = Assignment.objects.get(chosen_for_holding=holding, archived=False)
        assert (
            client.post(
                url, {"thing": f"library.pickable:{content['reputation_pick'].pk}"}
            ).status_code
            == 302
        )
        first.refresh_from_db()
        assert first.archived
        assert (
            Assignment.objects.get(
                chosen_for_holding=holding, archived=False
            ).pickable_id
            == content["reputation_pick"].pk
        )
        assert values(gang) == {"Income": 15, "Reputation": 2}

    def test_old_gets_posts_and_dismissals_cannot_follow_a_reacquired_holding(
        self, client, owner, holding, gang, content
    ):
        admit_to_founding(owner)
        client.force_login(owner)
        old_key = key_for(gang, holding, content["slot"])
        unassign_asset(holding)
        current = assign_asset(holding, gang)
        assert key_for(gang, current, content["slot"]) != old_key
        before = counts()
        url = reverse("n26-choose", args=[gang.pk, old_key])
        assert client.get(url).status_code == 404
        assert (
            client.post(
                url, {"thing": f"library.pickable:{content['income_pick'].pk}"}
            ).status_code
            == 404
        )
        assert (
            client.post(
                reverse("n26-dismiss-offer", args=[gang.pk, old_key])
            ).status_code
            == 404
        )
        assert counts() == before
        assert not question(gang, current, content["slot"]).picks

    def test_a_dismissal_hides_only_one_holding_and_one_ownership_period(
        self, client, owner, holding, gang, campaign, content
    ):
        admit_to_founding(owner)
        client.force_login(owner)
        second = assign_asset(add_asset(campaign, content["asset"]), gang)
        old_key = key_for(gang, holding, content["slot"])

        def dismiss(key):
            return client.post(reverse("n26-dismiss-offer", args=[gang.pk, key]))

        assert dismiss(old_key).status_code == 302
        assert dismiss(old_key).status_code == 302
        assert DismissedOffer.objects.filter(gang=gang).count() == 1
        sheet = render_gang(gang)
        settle_dismissed(gang, hide_only=(sheet,))
        assert [line.key for line in sheet.campaign.choices] == [
            key_for(gang, second, content["slot"])
        ]
        unassign_asset(holding)
        current = assign_asset(holding, gang)
        fresh_key = key_for(gang, current, content["slot"])
        sheet = render_gang(gang)
        settle_dismissed(gang, hide_only=(sheet,))
        assert fresh_key in {line.key for line in sheet.campaign.choices}
        assert dismiss(fresh_key).status_code == 302
        assert (
            client.post(
                reverse("n26-restore-offer", args=[gang.pk, old_key])
            ).status_code
            == 302
        )
        assert DismissedOffer.objects.filter(gang=gang, slot_key=fresh_key).exists()

    @pytest.mark.parametrize("change", ["transfer", "loss", "reacquire"])
    def test_a_nested_choice_form_cannot_write_after_its_holding_answer_ends(
        self, client, owner, holding, gang, rival, content, change
    ):
        modifier(
            "Extra income asks another benefit",
            targets_gang_alone(),
            ef_adds(content["slot"]),
            attach_to=content["income_pick"],
        )
        root = choose_for(holding, content["income_pick"], content["slot"])
        nested = next(
            choice
            for choice in computed(gang).choices
            if choice.holding is None and choice.anchor.assignment.pk == root.pk
        )
        url = reverse("n26-choose", args=[gang.pk, slot_key(nested, GANG_SLOT_HOST)])
        admit_to_founding(owner)
        client.force_login(owner)
        assert client.get(url).status_code == 200
        if change == "transfer":
            transfer_asset(holding, rival)
        else:
            unassign_asset(holding)
            if change == "reacquire":
                assign_asset(holding, gang)
        before = counts()
        assert client.get(url).status_code == 404
        assert (
            client.post(
                url, {"thing": f"library.pickable:{content['reputation_pick'].pk}"}
            ).status_code
            == 404
        )
        with pytest.raises(Refusal):
            with operation(gang, actor=owner) as op:
                op.choose(root, content["reputation_pick"], slot=content["slot"])
        assert counts() == before
        assert not Assignment.objects.filter(chosen_for=root).exists()

    def test_another_player_and_the_arbitrator_cannot_answer_for_the_owner(
        self, client, holding, gang, rival, campaign, content
    ):
        key = key_for(gang, holding, content["slot"])
        url = reverse("n26-choose", args=[gang.pk, key])
        before = counts()
        for user in (rival.owner, campaign.owner):
            admit_to_founding(user)
            client.force_login(user)
            assert client.get(url).status_code == 404
            assert (
                client.post(
                    url, {"thing": f"library.pickable:{content['income_pick'].pk}"}
                ).status_code
                == 404
            )
            assert (
                client.post(
                    reverse("n26-dismiss-offer", args=[gang.pk, key])
                ).status_code
                == 404
            )
        with pytest.raises(Refusal, match="ownership"):
            choose_for(holding, content["income_pick"], content["slot"], gang=rival)
        assert counts() == before

    def test_a_slot_not_offered_by_the_holding_cannot_be_answered(
        self, holding, gang, content
    ):
        slot = create_slot(
            "Unavailable", content["kind"], content["slot"].picklist, assigned_to="gang"
        )
        before = counts()
        with pytest.raises(Refusal, match="no longer available"):
            choose_for(holding, content["income_pick"], slot)
        assert counts() == before


class TestHoldingRolls:
    """A roll belongs to the exact holding and its ownership period."""

    def test_other_holdings_ordinary_rolls_and_old_ownership_rolls_cannot_settle_a_question(
        self, client, owner, holding, gang, campaign, content
    ):
        table = create_picklist(
            "Rolled benefits", content["kind"], dice="d6", roll_selects="band"
        )
        add_picklist_member(table, content["income_pick"], roll_low=1, roll_high=3)
        add_picklist_member(table, content["reputation_pick"], roll_low=4, roll_high=6)
        slot = create_slot("Rolled benefit", content["kind"], table, assigned_to="gang")
        modifier(
            "Workshop offers a rolled benefit",
            targets_gang_alone(),
            ef_adds(slot),
            attach_to=content["asset"],
        )
        second = assign_asset(add_asset(campaign, content["asset"]), gang)
        with campaign_operation(campaign, actor=owner):
            with operation(gang, actor=owner) as op:
                first_roll = op.roll(slot, campaign_asset=holding, rolled=2)
                ordinary_roll = op.roll(slot, rolled=2)
        assert first_roll.campaign_asset_id == holding.pk
        assert first_roll.holding_revision == holding.ownership_revision
        for roll in (first_roll, ordinary_roll):
            before = counts()
            with pytest.raises(Refusal, match="different holding"):
                choose_for(second, content["income_pick"], slot, roll=roll)
            assert counts() == before
        unassign_asset(holding)
        current = assign_asset(holding, gang)
        admit_to_founding(owner)
        client.force_login(owner)
        url = reverse("n26-choose", args=[gang.pk, key_for(gang, current, slot)])
        before = counts()
        assert client.get(f"{url}?roll={first_roll.pk}").status_code == 404
        assert (
            client.post(
                url,
                {
                    "thing": f"library.pickable:{content['income_pick'].pk}",
                    "roll": str(first_roll.pk),
                },
            ).status_code
            == 404
        )
        with pytest.raises(Refusal, match="different holding"):
            choose_for(current, content["income_pick"], slot, roll=first_roll)
        assert counts() == before
        assert LedgerEvent.objects.filter(pk=first_roll.pk).exists()


class TestReadingHoldingChoices:
    """Computation and choice rendering use loaded data, and reads stay flat as holdings grow."""

    def test_computing_and_rendering_holding_questions_issue_no_queries(
        self, holding, gang, content
    ):
        choose_for(holding, content["income_pick"], content["slot"])
        card = build_gang_card(gang)
        index = build_modifier_index(carriers(card))
        with CaptureQueriesContext(connection) as queries:
            done = compute_gang(card, index)
            lines = choice_lines(done, GANG_SLOT_HOST)
        assert len(queries) == 0
        assert (
            lines[0].key
            == f"holding:{holding.pk}@{holding.ownership_revision}:{content['slot'].pk}"
        )
        assert lines[0].chosen == "Extra income"
        assert {reading.name: reading.value for reading in done.counters} == {
            "Income": 20,
            "Reputation": 0,
        }

    def test_the_sheet_and_picker_have_the_same_query_count_with_more_holdings_and_fighters(
        self, client, owner, holding, gang, campaign, content
    ):
        admit_to_founding(owner)
        client.force_login(owner)
        choose_for(holding, content["income_pick"], content["slot"])
        hire(gang, content["profile"], "First guard")
        key = key_for(gang, holding, content["slot"])
        url = reverse("n26-choose", args=[gang.pk, key])
        client.get(url)
        with CaptureQueriesContext(connection) as small_sheet:
            render_gang(gang)
        with CaptureQueriesContext(connection) as small_picker:
            assert client.get(url).status_code == 200
        for n in range(4):
            extra = assign_asset(
                add_asset(campaign, content["asset"], name=f"Workshop {n}"), gang
            )
            choose_for(extra, content["reputation_pick"], content["slot"])
            hire(gang, content["profile"], f"Guard {n}")
        with CaptureQueriesContext(connection) as large_sheet:
            sheet = render_gang(gang)
        with CaptureQueriesContext(connection) as large_picker:
            assert client.get(url).status_code == 200
        assert len(sheet.campaign.holdings) == 5
        assert len(large_sheet) == len(small_sheet)
        assert len(large_picker) == len(small_picker)

    def test_the_catalogues_baseline_income_and_per_holding_override_still_apply(
        self, default_pack, gang_type, owner
    ):
        seed_journal_content()
        kind = CampaignType.objects.get(name="Territory campaign")
        asset = Asset.objects.get(name="Slug House", asset_type__campaign_type=kind)
        campaign = found_campaign("Catalogue campaign", kind, owner=owner)
        gang = found_gang("Catalogue keepers", gang_type, owner=owner)
        join_campaign(gang, campaign)
        plain = assign_asset(add_asset(campaign, asset), gang)
        with campaign_operation(campaign, actor=owner) as act:
            act.add_assets([asset], income=42, request_key=uuid4())
        override = CampaignAsset.objects.exclude(pk=plain.pk).get(campaign=campaign)
        assign_asset(override, gang)
        done = computed(gang)
        assert not [choice for choice in done.choices if choice.holding is not None]
        assert {reading.name: reading.value for reading in done.counters}[
            "Income"
        ] == 62
        assert not gang.assignments.filter(chosen_for_holding__isnull=False).exists()
        assert_reconciled(gang)


class TestCloningDoesNotKeepHoldingBenefits:
    """An independent snapshot cannot turn temporary campaign benefits into permanent assignments."""

    def test_gang_and_fighter_clones_exclude_holding_answers_and_their_descendants(
        self, holding, gang, content, owner
    ):
        fighter = hire(gang, content["profile"], "Keeper")
        ordinary_gear = create_wargear("Personal kit")
        assign(ordinary_gear, miniature=fighter)
        root = choose_for(holding, content["income_pick"], content["slot"])
        temporary_gear = create_wargear("Workshop kit")
        hosted_gear = create_wargear("Workshop attachment")
        with operation(gang, actor=owner) as op:
            child = op.assign(temporary_gear, miniature=fighter, caused_by=root)
            op.assign(hosted_gear, parent=child)
            ordinary_question = op.assign(content["slot"], miniature=fighter)
            ordinary_pick = op.choose(
                ordinary_question, content["reputation_pick"], slot=content["slot"]
            )
            fighter_clone = op.clone_miniature(fighter, name="Independent keeper")
        clone = clone_gang(gang, name="Independent gang", owner=owner, actor=owner)
        assert Assignment.objects.filter(
            miniature_root=fighter_clone, wargear=ordinary_gear, archived=False
        ).exists()
        assert not Assignment.objects.filter(
            miniature_root=fighter_clone, wargear__in=[temporary_gear, hosted_gear]
        ).exists()
        assert clone.assignments.filter(wargear=ordinary_gear, archived=False).exists()
        assert not clone.assignments.filter(pickable=content["income_pick"]).exists()
        assert not clone.assignments.filter(
            wargear__in=[temporary_gear, hosted_gear]
        ).exists()
        assert not CampaignAsset.objects.filter(holder__gang=clone).exists()
        assert not clone.assignments.filter(
            chosen_for_holding_revision__isnull=False
        ).exists()
        assert Assignment.objects.filter(
            gang_root=gang,
            pickable=ordinary_pick.pickable,
            caused_by__miniature_root=fighter_clone,
            archived=False,
        ).exists()
        assert clone.assignments.filter(
            pickable=ordinary_pick.pickable,
            chosen_for_holding_revision__isnull=True,
            archived=False,
        ).exists()
        assert Assignment.objects.filter(pk=child.pk, archived=False).exists()
        assert_reconciled(gang)
        assert_reconciled(clone)

    def test_a_model_brought_by_a_holding_is_neither_copied_with_the_gang_nor_cloned_on_its_own(
        self, holding, gang, content, owner
    ):
        modifier(
            "Workshop brings a guard",
            targets_gang_alone(),
            op_adds_model(content["profile"]),
            attach_to=content["income_pick"],
        )
        root = choose_for(holding, content["income_pick"], content["slot"])
        guard = Miniature.objects.get(membership__caused_by=root)
        independent_gear = create_wargear("Guard's personal kit")
        kit = assign(independent_gear, miniature=guard)
        before = counts()
        with pytest.raises(Refusal, match="holding"):
            with operation(gang, actor=owner) as op:
                op.clone_miniature(guard)
        assert counts() == before
        clone = clone_gang(gang, name="Independent gang", owner=owner, actor=owner)
        assert not Miniature.objects.filter(membership__gang=clone).exists()
        assert not clone.assignments.filter(profile=content["profile"]).exists()
        assert not clone.assignments.filter(wargear=independent_gear).exists()
        kit.refresh_from_db()
        assert not kit.archived
        unassign_asset(holding)
        guard.membership.refresh_from_db()
        assert guard.membership.archived
        assert_reconciled(gang)
        assert_reconciled(clone)
