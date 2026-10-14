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
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.campaigns import campaign_operation
from n26.core.card import build_gang_card, build_modifier_index, carriers
from n26.core.effects import compute, compute_gang, counter_contributions_by_holding
from n26.core.history import build
from n26.core.models import (
    Assignment,
    CampaignAsset,
    CampaignMembership,
    DismissedOffer,
    LedgerEvent,
    Miniature,
)
from n26.core.operations import Refusal, clone_gang, operation
from n26.core.reconcile import assert_reconciled
from n26.core.render import (
    GANG_SLOT_HOST,
    choice_lines,
    holding_income,
    render_campaign,
    render_gang,
    slot_key,
)
from n26.core.views.campaign_assets import _asset_context
from n26.core.views.choose import find_slot, settle_dismissed
from n26.library.authoring import (
    add_asset_type,
    add_built_in,
    add_picklist_member,
    create_asset,
    create_campaign_type,
    create_counter,
    create_hidden,
    create_pack,
    create_pickable,
    create_picklist,
    create_profile,
    create_rule,
    create_slot,
    create_slot_type,
    create_wargear,
    ef_adds,
    ef_contributes_to_counter,
    ef_removes,
    has_gang_pickable,
    modifier,
    op_adds_model,
    op_changes_counter,
    revise,
    targets_every_model,
    targets_gang,
    targets_gang_alone,
)
from n26.library.income import income_of
from n26.library.journal_content import seed_journal_content
from n26.library.models import Asset, CampaignType
from n26.tests.fixtures import library_setup
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
    """Replace a single pick within this holding's current ownership period."""
    gang = gang or holding.holder.gang
    with campaign_operation(holding.campaign, actor=gang.owner):
        with operation(gang, actor=gang.owner) as op:
            if previous is None and slot.max_picks == 1:
                previous = Assignment.objects.filter(
                    gang_root=gang,
                    chosen_for_holding=holding,
                    chosen_for_holding_revision=holding.ownership_revision,
                    chosen_for_slot=slot,
                    archived=False,
                ).first()
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


class TestAcquisitionDefaults:
    """A new holding starts with the first available standing boon."""

    def test_authored_order_determines_the_default_instead_of_option_names(
        self, gang, campaign, content
    ):
        revise(
            content["slot"].picklist.members.get(pickable=content["reputation_pick"]),
            position=0,
        )
        revise(
            content["slot"].picklist.members.get(pickable=content["income_pick"]),
            position=1,
        )
        holding = assign_asset(add_asset(campaign, content["asset"]), gang)
        assert (
            question(gang, holding, content["slot"]).chosen_name == "Local reputation"
        )
        assert values(gang) == {"Income": 15, "Reputation": 2}
        assert_reconciled(gang)

    @pytest.mark.parametrize(
        "unavailable",
        [
            "archived_member",
            "archived_pick",
            "archived_pack",
            "staged_member",
            "staged_pick",
            "record_only",
        ],
    )
    def test_unavailable_options_are_skipped_before_the_default_is_written(
        self, gang, campaign, content, unavailable
    ):
        member = content["slot"].picklist.members.get(pickable=content["income_pick"])
        if unavailable == "archived_member":
            revise(member, archived=True)
        elif unavailable == "archived_pick":
            revise(content["income_pick"], archived=True)
        elif unavailable == "archived_pack":
            pack = create_pack("Withdrawn boons")
            revise(content["income_pick"], pack=pack)
            revise(pack, archived=True)
        elif unavailable == "staged_member":
            revise(member, staged=True)
        elif unavailable == "staged_pick":
            revise(content["income_pick"], staged=True)
        else:
            revise(content["income_pick"], record_only=True)
        holding = assign_asset(add_asset(campaign, content["asset"]), gang)
        assert (
            question(gang, holding, content["slot"]).chosen_name == "Local reputation"
        )
        assert not Assignment.objects.filter(
            chosen_for_holding=holding, pickable=content["income_pick"]
        ).exists()

    def test_an_empty_available_list_stays_unselected_and_reads_never_fill_it(
        self, gang, campaign, content
    ):
        revise(content["income_pick"], archived=True)
        revise(content["reputation_pick"], staged=True)
        holding = assign_asset(add_asset(campaign, content["asset"]), gang)
        assert not question(gang, holding, content["slot"]).picks
        revise(content["income_pick"], archived=False)
        before = counts()
        render_gang(gang)
        render_gang(gang)
        assign_asset(holding, gang)
        assert counts() == before
        assert not question(gang, holding, content["slot"]).picks

    @pytest.mark.parametrize("recipient_is_staff", [False, True])
    def test_staged_options_follow_the_recipient_visibility_rather_than_the_arbitrator(
        self, gang, campaign, content, recipient_is_staff
    ):
        campaign.owner.is_staff = True
        campaign.owner.save(update_fields=["is_staff"])
        gang.owner.is_staff = recipient_is_staff
        gang.owner.save(update_fields=["is_staff"])
        revise(content["income_pick"], staged=True)
        asset = add_asset(campaign, content["asset"])
        with campaign_operation(campaign, actor=campaign.owner) as act:
            holding = act.assign(
                asset,
                CampaignMembership.objects.get(
                    campaign=campaign, gang=gang, left__isnull=True
                ),
            )
        expected = "Extra income" if recipient_is_staff else "Local reputation"
        assert question(gang, holding, content["slot"]).chosen_name == expected

    @pytest.mark.parametrize("staged", ["slot", "picklist"])
    def test_a_staged_choice_or_list_is_not_automatically_selected_for_a_player(
        self, gang, campaign, content, staged
    ):
        target = content["slot"] if staged == "slot" else content["slot"].picklist
        revise(target, staged=True)
        holding = assign_asset(add_asset(campaign, content["asset"]), gang)
        assert not question(gang, holding, content["slot"]).picks
        assert values(gang) == {"Income": 15, "Reputation": 0}

    @pytest.mark.parametrize(
        "special", ["optional", "multiple", "none", "hidden", "status", "tier", "roll"]
    )
    def test_choices_with_other_selection_rules_stay_unselected(
        self, gang, campaign, content, special
    ):
        slot = content["slot"]
        if special == "optional":
            revise(slot, min_picks=0)
        elif special == "multiple":
            revise(slot, min_picks=2, max_picks=2)
        elif special == "none":
            revise(slot, min_picks=0, max_picks=0)
        elif special == "hidden":
            revise(slot, hidden=True)
        elif special == "status":
            revise(slot, follows_status=True, assigned_to="bearer")
        elif special == "tier":
            for level, member in enumerate(slot.picklist.members.all(), start=1):
                revise(member, level=level)
            revise(slot, mode="tier_ladder")
        else:
            revise(slot.picklist, dice="d6", roll_selects="band")
        holding = assign_asset(add_asset(campaign, content["asset"]), gang)
        assert not Assignment.objects.filter(chosen_for_holding=holding).exists()
        assert values(gang) == {"Income": 15, "Reputation": 0}

    def test_a_removed_default_is_not_reapplied_by_reads_or_repeated_assignment(
        self, holding, gang, content
    ):
        pick = question(gang, holding, content["slot"]).picks[0].assignment
        remove(pick)
        before = counts()
        render_gang(gang)
        render_gang(gang)
        assign_asset(holding, gang)
        assert counts() == before
        assert not question(gang, holding, content["slot"]).picks
        assert values(gang) == {"Income": 15, "Reputation": 0}

    def test_a_default_runs_stored_effects_once_and_leaves_nested_choices_open(
        self, gang, campaign, content
    ):
        modifier(
            "Workshop records goodwill on acquisition",
            targets_gang_alone(),
            op_changes_counter(content["reputation"], "add", 3),
            attach_to=content["income_pick"],
        )
        follow_up = create_slot(
            "Workshop follow-up",
            content["kind"],
            content["slot"].picklist,
            assigned_to="gang",
        )
        modifier(
            "Extra income offers a follow-up",
            targets_gang_alone(),
            ef_adds(follow_up),
            attach_to=content["income_pick"],
        )
        holding = assign_asset(add_asset(campaign, content["asset"]), gang)
        assert values(gang) == {"Income": 20, "Reputation": 3}
        follow_up_choice = next(
            choice
            for choice in computed(gang).choices
            if choice.slot.pk == follow_up.pk
        )
        assert follow_up_choice.holding is None and not follow_up_choice.picks
        before = counts()
        assign_asset(holding, gang)
        render_gang(gang)
        render_gang(gang)
        assert counts() == before
        assert values(gang) == {"Income": 20, "Reputation": 3}
        unassign_asset(holding)
        assert values(gang) == {"Income": 0, "Reputation": 3}
        assert_reconciled(gang)

    def test_a_default_that_retracts_a_later_choice_does_not_fill_the_retracted_choice(
        self, gang, campaign, content
    ):
        later = create_slot(
            "Workshop alternative",
            content["kind"],
            content["slot"].picklist,
            assigned_to="gang",
            position=1,
        )
        modifier(
            "Workshop offers another choice",
            targets_gang_alone(),
            ef_adds(later),
            attach_to=content["asset"],
        )
        modifier(
            "Extra income removes the alternative",
            targets_gang_alone(),
            ef_removes(later),
            attach_to=content["income_pick"],
        )
        holding = assign_asset(add_asset(campaign, content["asset"]), gang)
        assert Assignment.objects.filter(chosen_for_holding=holding).count() == 1
        assert [choice.slot.pk for choice in computed(gang).choices] == [
            content["slot"].pk
        ]
        assert values(gang) == {"Income": 20, "Reputation": 0}

    def test_ownership_and_automatic_selection_roll_back_together(
        self, gang, campaign, content
    ):
        asset = add_asset(campaign, content["asset"])
        before = counts()

        def abort_acquisition():
            with campaign_operation(campaign, actor=campaign.owner) as act:
                act.assign(
                    asset,
                    CampaignMembership.objects.get(
                        campaign=campaign, gang=gang, left__isnull=True
                    ),
                )
                raise RuntimeError("cancel acquisition")

        caught = pytest.raises(RuntimeError, abort_acquisition)
        assert str(caught.value) == "cancel acquisition"
        asset.refresh_from_db()
        assert asset.holder_id is None and asset.ownership_revision == 0
        assert counts() == before
        assert values(gang) == {"Income": 0, "Reputation": 0}


class TestStandingHoldingChoices:
    """Two copies of one territory ask separate questions and apply each answer once."""

    def test_the_pick_is_a_free_gang_assignment_with_an_explicit_holding_origin(
        self, holding, gang, content
    ):
        assert values(gang) == {"Income": 20, "Reputation": 0}
        pick = question(gang, holding, content["slot"]).picks[0].assignment
        assert pick.pickable_id == content["income_pick"].pk
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
        assert question(gang, second, content["slot"]).chosen_name == "Extra income"
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

    def test_transfer_archives_the_old_pick_and_gives_the_recipient_a_fresh_default(
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
        assert values(rival)["Income"] == 20
        received = question(rival, current, content["slot"]).picks[0].assignment
        assert received.pickable_id == content["income_pick"].pk
        assert received.pk != pick.pk
        assert received.chosen_for_holding_revision == current.ownership_revision
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
        assert question(gang, current, content["slot"]).chosen_name == "Extra income"
        assert values(gang) == {"Income": 20, "Reputation": 0}
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

        def abort_ownership_change():
            with campaign_operation(
                holding.campaign, actor=holding.campaign.owner
            ) as act:
                act.unassign(holding)
                raise RuntimeError("cancel the act")

        caught = pytest.raises(RuntimeError, abort_ownership_change)
        assert str(caught.value) == "cancel the act"
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
        assert question(gang, current, content["slot"]).chosen_name == "Extra income"

    def test_a_dismissal_hides_only_one_holding_and_one_ownership_period(
        self, client, owner, holding, gang, campaign, content
    ):
        client.force_login(owner)
        second = assign_asset(add_asset(campaign, content["asset"]), gang)
        remove(question(gang, holding, content["slot"]).picks[0].assignment)
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
        remove(question(gang, current, content["slot"]).picks[0].assignment)
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


class TestHoldingIncome:
    """Each territory shows the Income it currently gives, including its boons."""

    def test_same_and_different_territories_keep_their_own_income_without_gang_income(
        self, holding, gang, campaign, content
    ):
        second = assign_asset(
            add_asset(campaign, content["asset"], name="East Workshop"), gang
        )
        other_asset = create_asset(
            "Trading post", content["asset"].asset_type, income=9
        )
        modifier(
            "Trading post offers workshop boons",
            targets_gang_alone(),
            ef_adds(content["slot"]),
            attach_to=other_asset,
        )
        third = assign_asset(add_asset(campaign, other_asset), gang)
        unrelated = create_hidden(
            "Independent gang income",
            effects=[
                (targets_gang_alone(), ef_contributes_to_counter(content["income"], 11))
            ],
        )
        assign(unrelated, gang=gang)
        first_address = (holding.pk, holding.ownership_revision)
        second_address = (second.pk, second.ownership_revision)
        third_address = (third.pk, third.ownership_revision)
        assert holding_income(computed(gang)) == {
            first_address: 20,
            second_address: 20,
            third_address: 14,
        }
        assert values(gang)["Income"] == 65

        choose_for(second, content["reputation_pick"], content["slot"])
        done = computed(gang)
        assert holding_income(done) == {
            first_address: 20,
            second_address: 15,
            third_address: 14,
        }
        assert values(gang) == {"Income": 60, "Reputation": 2}
        assert (
            sum(
                contribution.amount
                for contribution in counter_contributions_by_holding(done)[
                    second_address
                ]
                if contribution.counter.pk == content["reputation"].pk
            )
            == 2
        )
        assert income_of(content["asset"]) == 15
        assert income_of(other_asset) == 9
        assert_reconciled(gang)

    def test_choice_replacement_updates_territory_campaign_and_gang_displays_together(
        self, holding, gang, campaign, content, owner
    ):
        second = assign_asset(
            add_asset(campaign, content["asset"], name="East Workshop"), gang
        )
        request = RequestFactory().get(
            reverse("n26-campaign-asset", args=[campaign.pk, holding.pk])
        )
        request.user = owner

        def displayed_income():
            gang_sheet = render_gang(gang)
            campaign_sheet = render_campaign(campaign, viewer=owner)
            return (
                {
                    line.campaign_asset_id: line.income
                    for line in gang_sheet.campaign.holdings
                },
                {
                    entry.campaign_asset_id: entry.income
                    for table in campaign_sheet.assets
                    for entry in table.entries
                },
                _asset_context(request, campaign.pk, holding.pk)["details"].income,
            )

        for pick, income in (
            (None, 20),
            (content["reputation_pick"], 15),
            (content["income_pick"], 20),
        ):
            if pick is not None:
                choose_for(holding, pick, content["slot"])
            before = counts()
            expected = {str(holding.pk): income, str(second.pk): 20}
            assert displayed_income() == (expected, expected, income)
            assert counts() == before
        assert income_of(content["asset"]) == 15
        assert_reconciled(gang)

    def test_nested_picks_granted_rules_and_stored_children_belong_to_the_originating_territory(
        self, holding, gang, campaign, content
    ):
        kind = create_slot_type("Workshop income follow-up")
        rule = create_rule("Workshop trade agreement")
        modifier(
            "Trade agreement brings income",
            targets_gang_alone(),
            ef_contributes_to_counter(content["income"], 4),
            attach_to=rule,
        )
        nested_pick = create_pickable(
            "Workshop trade",
            kind,
            effects=[
                (targets_gang_alone(), ef_contributes_to_counter(content["income"], 3)),
                (targets_gang_alone(), ef_adds(rule)),
            ],
        )
        table = create_picklist("Workshop trades", kind, members=[nested_pick])
        slot = create_slot("Workshop trade", kind, table, assigned_to="gang")
        modifier(
            "Extra income offers a trade",
            targets_gang_alone(),
            ef_adds(slot),
            attach_to=content["income_pick"],
        )
        hosted_item = create_wargear("Workshop trade token")
        modifier(
            "Trade token brings income",
            targets_gang_alone(),
            ef_contributes_to_counter(content["income"], 2),
            attach_to=hosted_item,
        )
        caused_item = create_hidden(
            "Workshop trade delivery",
            effects=[
                (targets_gang_alone(), ef_contributes_to_counter(content["income"], 6))
            ],
        )
        unrelated = create_hidden(
            "Independent income",
            effects=[
                (targets_gang_alone(), ef_contributes_to_counter(content["income"], 11))
            ],
        )
        root = question(gang, holding, content["slot"]).picks[0].assignment
        with operation(gang, actor=gang.owner) as op:
            nested = op.choose(root, nested_pick, slot=slot)
            hosted = op.assign(hosted_item, parent=nested)
            caused = op.assign(caused_item, gang=gang, caused_by=nested)
            op.assign(unrelated, gang=gang)
        second = assign_asset(add_asset(campaign, content["asset"]), gang)
        assert holding_income(computed(gang)) == {
            (holding.pk, holding.ownership_revision): 35,
            (second.pk, second.ownership_revision): 20,
        }
        assert values(gang)["Income"] == 66

        choose_for(holding, content["reputation_pick"], content["slot"])
        assert holding_income(computed(gang)) == {
            (holding.pk, holding.ownership_revision): 15,
            (second.pk, second.ownership_revision): 20,
        }
        assert values(gang)["Income"] == 46
        for assignment in (nested, hosted, caused):
            assignment.refresh_from_db()
            assert assignment.archived
        assert_reconciled(gang)

    def test_retracted_granted_income_is_absent_until_its_blocker_leaves(
        self, holding, gang, content
    ):
        rule = create_rule("Workshop trade income")
        modifier(
            "Workshop trade brings income",
            targets_gang_alone(),
            ef_contributes_to_counter(content["income"], 7),
            attach_to=rule,
        )
        modifier(
            "Extra income grants workshop trade",
            targets_gang_alone(),
            ef_adds(rule),
            attach_to=content["income_pick"],
        )
        blocker = assign(
            create_hidden(
                "Trade is closed",
                effects=[(targets_gang_alone(), ef_removes(rule))],
            ),
            gang=gang,
        )
        address = (holding.pk, holding.ownership_revision)
        assert holding_income(computed(gang)) == {address: 20}
        assert values(gang)["Income"] == 20
        remove(blocker)
        assert holding_income(computed(gang)) == {address: 27}
        assert values(gang)["Income"] == 27
        assert_reconciled(gang)

    @pytest.mark.parametrize("carrier_mode", ["stored", "computed_chain"])
    def test_a_shared_income_grant_belongs_to_the_pick_that_survives_suppression(
        self, gang, campaign, content, carrier_mode
    ):
        shared = create_hidden(
            "Shared trade income",
            effects=[
                (targets_gang_alone(), ef_contributes_to_counter(content["income"], 5))
            ],
        )
        holdings = []
        carriers = []
        roots = []
        for name, income in (("First depot", 10), ("Second depot", 20)):
            carrier = create_hidden(
                f"{name} trade carrier",
                effects=[(targets_gang_alone(), ef_adds(shared))],
            )
            effects = []
            if carrier_mode == "computed_chain":
                effects = [(targets_gang_alone(), ef_adds(carrier))]
            pick = create_pickable(
                f"{name} trade",
                content["kind"],
                effects=effects,
            )
            table = create_picklist(f"{name} boons", content["kind"], members=[pick])
            slot = create_slot(
                f"{name} boon", content["kind"], table, assigned_to="gang"
            )
            asset = create_asset(name, content["asset"].asset_type, income=income)
            modifier(
                f"{name} offers a boon",
                targets_gang_alone(),
                ef_adds(slot),
                attach_to=asset,
            )
            holding = assign_asset(add_asset(campaign, asset), gang)
            holdings.append(holding)
            root = question(gang, holding, slot).picks[0].assignment
            roots.append(root)
            if carrier_mode == "stored":
                assign(carrier, gang=gang, caused_by=root)
            carriers.append(carrier)
        assert values(gang)["Income"] == 35
        assert holding_income(computed(gang)) == {
            (holdings[0].pk, holdings[0].ownership_revision): 15,
            (holdings[1].pk, holdings[1].ownership_revision): 20,
        }
        assign(
            create_hidden(
                "First depot trade is closed",
                effects=[(targets_gang_alone(), ef_removes(carriers[0]))],
            ),
            gang=gang,
        )
        before = counts()
        done = computed(gang)
        assert holding_income(done) == {
            (holdings[0].pk, holdings[0].ownership_revision): 10,
            (holdings[1].pk, holdings[1].ownership_revision): 25,
        }
        assert {reading.name: reading.value for reading in done.counters}[
            "Income"
        ] == 35
        assert {node.key for node in done.card.all_nodes()} >= {
            root.pk for root in roots
        }
        assert not any(
            node.suppressed for node in done.card.all_nodes() if node.key == roots[0].pk
        )
        assert counts() == before
        assert_reconciled(gang)

    def test_conditional_income_is_read_from_the_effects_of_the_current_choice(
        self, holding, gang, content
    ):
        modifier(
            "A locally known workshop brings income",
            targets_gang_alone(has_gang_pickable(content["reputation_pick"])),
            ef_contributes_to_counter(content["income"], 7),
            attach_to=content["asset"],
        )
        address = (holding.pk, holding.ownership_revision)
        assert holding_income(computed(gang)) == {address: 20}
        choose_for(holding, content["reputation_pick"], content["slot"])
        assert holding_income(computed(gang)) == {address: 22}
        assert values(gang)["Income"] == 22
        choose_for(holding, content["income_pick"], content["slot"])
        assert holding_income(computed(gang)) == {address: 20}
        assert income_of(content["asset"]) == 15

    def test_an_income_override_replaces_only_the_baseline_and_keeps_the_selected_boon(
        self, holding, gang, campaign, content
    ):
        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.add_assets([content["asset"]], income=42, request_key=uuid4())
        override = CampaignAsset.objects.exclude(pk=holding.pk).get(campaign=campaign)
        override = assign_asset(override, gang)
        address = (override.pk, override.ownership_revision)
        assert holding_income(computed(gang)) == {
            (holding.pk, holding.ownership_revision): 20,
            address: 47,
        }
        assert values(gang)["Income"] == 67
        choose_for(override, content["reputation_pick"], content["slot"])
        assert holding_income(computed(gang)) == {
            (holding.pk, holding.ownership_revision): 20,
            address: 42,
        }
        assert values(gang)["Income"] == 62
        assert income_of(content["asset"]) == 15
        assert_reconciled(gang)

    def test_income_follows_the_current_owner_and_reacquisition_has_a_fresh_origin(
        self, holding, gang, rival, campaign, content
    ):
        old_address = (holding.pk, holding.ownership_revision)
        choose_for(holding, content["reputation_pick"], content["slot"])
        assert holding_income(computed(gang)) == {old_address: 15}
        transferred = transfer_asset(holding, rival)
        transferred_address = (transferred.pk, transferred.ownership_revision)
        assert holding_income(computed(gang)) == {}
        assert holding_income(computed(rival)) == {transferred_address: 20}
        unassign_asset(transferred)
        assert holding_income(computed(rival)) == {}
        unclaimed = next(
            entry
            for table in render_campaign(campaign).assets
            for entry in table.entries
            if entry.campaign_asset_id == str(holding.pk)
        )
        assert not unclaimed.held and unclaimed.income == 15

        current = assign_asset(transferred, gang)
        current_address = (current.pk, current.ownership_revision)
        assert current_address not in (old_address, transferred_address)
        assert holding_income(computed(gang)) == {current_address: 20}
        assert holding_income(computed(rival)) == {}
        assert_reconciled(gang)
        assert_reconciled(rival)

    def test_both_computed_shapes_resolve_holding_income_without_queries_or_writes(
        self, holding, gang, campaign, content
    ):
        second = assign_asset(add_asset(campaign, content["asset"]), gang)
        choose_for(second, content["reputation_pick"], content["slot"])
        card = build_gang_card(gang)
        index = build_modifier_index(carriers(card))
        before = counts()
        with CaptureQueriesContext(connection) as queries:
            card_done = compute(card, index)
            card_income = holding_income(card_done)
            card_contributions = counter_contributions_by_holding(card_done)
            gang_done = compute_gang(card, index)
            gang_income = holding_income(gang_done)
            gang_contributions = counter_contributions_by_holding(gang_done)
        assert len(queries) == 0
        assert counts() == before
        assert (
            card_income
            == gang_income
            == {
                (holding.pk, holding.ownership_revision): 20,
                (second.pk, second.ownership_revision): 15,
            }
        )
        assert card_contributions == gang_contributions


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
