"""Cycle previews, deliberately skipped rewards and durable ledger receipts."""

import pytest
from django.contrib.auth.models import User

from n26.core.cycle_rewards import apply_cycle, pending_gangs, preview_cycle
from n26.core.cycles import start_cycle
from n26.core.models import CycleResolution
from n26.core.operations import Refusal
from n26.core.reconcile import assert_reconciled
from n26.library.authoring import add_asset_type, create_asset, create_campaign_type
from n26.library.models import AssetType
from n26.tests.sandbox.actions import (
    add_asset,
    assign_asset,
    found_campaign,
    found_gang,
    join_campaign,
    transfer_asset,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def scenario(default_pack, gang_type):
    actor = User.objects.create_user("rewards-arbitrator")
    campaign = found_campaign(
        "Cinderhaven", create_campaign_type("Rewards campaign"), owner=actor
    )
    kind = add_asset_type(
        campaign.campaign_type, "Territory", AssetType.Ownership.HOLDING
    )
    asset = create_asset("Workshop", kind, income=15)
    gangs = [
        found_gang(name, gang_type, owner=User.objects.create_user(name), budget=100)
        for name in ("Iron", "Rust")
    ]
    for gang in gangs:
        join_campaign(gang, campaign)
    holding = add_asset(campaign, asset)
    assign_asset(holding, gangs[0])
    cycle = start_cycle(campaign, actor=actor)
    return campaign, cycle, gangs, holding


def selected(plan, gang, *, skip=False, comment=""):
    rewards = next(rewards for rewards in plan.gangs if rewards.gang_id == str(gang.pk))
    return {
        str(gang.pk): {
            "comment": comment,
            "lines": {line.key: {"skip": skip} for line in rewards.lines},
        }
    }


def test_income_is_recorded_once_and_unselected_gangs_stay_pending(scenario):
    campaign, cycle, (iron, rust), holding = scenario
    plan = preview_cycle(cycle)
    receipts = apply_cycle(
        cycle,
        actor=campaign.owner,
        token=plan.token,
        selections=selected(plan, iron, comment="Collected after the games."),
    )
    iron.refresh_from_db()
    rust.refresh_from_db()
    assert (iron.credits, rust.credits) == (115, 100)
    assert receipts[0].comment == "Collected after the games."
    assert receipts[0].snapshot["lines"][0]["amount"] == 15
    assert [membership.gang_id for membership in pending_gangs(cycle)] == [rust.pk]
    with pytest.raises(Refusal, match="changed"):
        apply_cycle(
            cycle,
            actor=campaign.owner,
            token=plan.token,
            selections=selected(plan, iron),
        )
    assert CycleResolution.objects.count() == 1
    assert_reconciled(iron)


def test_skipping_finalises_without_moving_credits(scenario):
    campaign, cycle, (iron, _rust), _holding = scenario
    plan = preview_cycle(cycle)
    receipt = apply_cycle(
        cycle,
        actor=campaign.owner,
        token=plan.token,
        selections=selected(
            plan, iron, skip=True, comment="Already collected manually."
        ),
    )[0]
    iron.refresh_from_db()
    assert iron.credits == 100
    assert receipt.snapshot["lines"][0]["status"] == "skipped"
    assert receipt.claims.count() == 1
    assert_reconciled(iron)


def test_transfer_cannot_award_the_same_territory_again(scenario):
    campaign, cycle, (iron, rust), holding = scenario
    plan = preview_cycle(cycle)
    apply_cycle(
        cycle, actor=campaign.owner, token=plan.token, selections=selected(plan, iron)
    )
    transfer_asset(holding, rust)
    plan = preview_cycle(cycle)
    rewards = next(item for item in plan.gangs if item.gang_id == str(rust.pk))
    assert rewards.lines[0].claimed == iron.name
    apply_cycle(
        cycle, actor=campaign.owner, token=plan.token, selections=selected(plan, rust)
    )
    rust.refresh_from_db()
    assert rust.credits == 100
    assert_reconciled(rust)


def test_changed_ownership_invalidates_an_open_preview(scenario):
    campaign, cycle, (iron, rust), holding = scenario
    plan = preview_cycle(cycle)
    transfer_asset(holding, rust)
    with pytest.raises(Refusal, match="changed"):
        apply_cycle(
            cycle,
            actor=campaign.owner,
            token=plan.token,
            selections=selected(plan, iron),
        )
    assert not cycle.resolutions.exists()


def test_progression_names_and_requires_acknowledgement_of_pending_gangs(scenario):
    campaign, cycle, _gangs, _holding = scenario
    with pytest.raises(Refusal, match="unapplied"):
        start_cycle(campaign, actor=campaign.owner, previous=str(cycle.pk))
    next_cycle = start_cycle(
        campaign, actor=campaign.owner, previous=str(cycle.pk), leave_pending=True
    )
    assert next_cycle.number == 2
    assert len(pending_gangs(next_cycle)) == 2


def test_player_cannot_collect_on_behalf_of_the_campaign(scenario):
    _campaign, cycle, (iron, _rust), _holding = scenario
    plan = preview_cycle(cycle)
    with pytest.raises(Refusal, match="arbitrator"):
        apply_cycle(
            cycle, actor=iron.owner, token=plan.token, selections=selected(plan, iron)
        )
    assert not cycle.resolutions.exists()
