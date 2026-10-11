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
    iron.refresh_from_db()
    iron.stash.refresh_from_db()
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
    iron.refresh_from_db()
    iron.stash.refresh_from_db()
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


def add_reward(holding, effect):
    from n26.library.authoring import modifier, targets_gang_alone

    return modifier(
        f"Cycle reward {effect.pk}",
        targets_gang_alone(),
        effect,
        attach_to=holding.asset,
    )


def test_recruitment_discount_creates_an_independent_fighter(scenario, make_profile):
    from n26.core.models import Miniature
    from n26.library.authoring import ef_offers_cycle_recruitment

    campaign, cycle, (iron, rust), holding = scenario
    profile = make_profile("Ganger", price=20)
    profile.price = 20
    profile.save()
    add_reward(holding, ef_offers_cycle_recruitment(profiles=[profile], discount=25))
    plan = preview_cycle(cycle)
    line = next(line for line in plan.gangs[0].lines if line.kind == "recruitment")
    assert line.options[0]["payment"] == 0
    selections = selected(plan, iron)
    selections[str(iron.pk)]["lines"][line.key].update(
        option=line.options[0]["key"], name="New ganger"
    )
    receipt = apply_cycle(
        cycle, actor=campaign.owner, token=plan.token, selections=selections
    )[0]
    created = next(
        line for line in receipt.snapshot["lines"] if line["kind"] == "recruitment"
    )["created"][0]
    fighter = Miniature.objects.get(pk=created)
    assert fighter.membership.caused_by_id is None
    assert fighter.membership.ledger_entry.paid == 0
    assert fighter.membership.rating == 20
    transfer_asset(holding, rust)
    assert Miniature.objects.filter(pk=created, membership__archived=False).exists()
    iron.refresh_from_db()
    iron.stash.refresh_from_db()
    assert_reconciled(iron)


def test_equipment_arrives_in_stash_and_remains_after_transfer(scenario):
    from n26.core.models import Assignment
    from n26.library.authoring import create_wargear, ef_offers_cycle_equipment

    campaign, cycle, (iron, rust), holding = scenario
    equipment = create_wargear("Hazard suit", price=15)
    add_reward(holding, ef_offers_cycle_equipment(equipment, quantity=3))
    plan = preview_cycle(cycle)
    receipt = apply_cycle(
        cycle, actor=campaign.owner, token=plan.token, selections=selected(plan, iron)
    )[0]
    created = next(
        line for line in receipt.snapshot["lines"] if line["kind"] == "equipment"
    )["created"]
    assert len(created) == 3
    assert (
        Assignment.objects.filter(
            pk__in=created,
            stash=iron.stash,
            ledger_entry__paid=0,
            ledger_entry__rating_contribution=15,
            caused_by__isnull=True,
        ).count()
        == 3
    )
    transfer_asset(holding, rust)
    assert Assignment.objects.filter(pk__in=created, archived=False).count() == 3
    iron.refresh_from_db()
    iron.stash.refresh_from_db()
    assert_reconciled(iron)


def test_invalid_recruitment_rolls_back_income_and_receipt(scenario, make_profile):
    from n26.library.authoring import ef_offers_cycle_recruitment

    campaign, cycle, (iron, _rust), holding = scenario
    profile = make_profile("Ganger", price=20)
    add_reward(holding, ef_offers_cycle_recruitment(profiles=[profile], discount=25))
    plan = preview_cycle(cycle)
    with pytest.raises(Refusal, match="Choose an eligible"):
        apply_cycle(
            cycle,
            actor=campaign.owner,
            token=plan.token,
            selections=selected(plan, iron),
        )
    iron.refresh_from_db()
    assert iron.credits == 100
    assert not cycle.resolutions.exists()
    assert not cycle.claims.exists()
    iron.refresh_from_db()
    iron.stash.refresh_from_db()
    assert_reconciled(iron)


def test_two_recruitment_rewards_cannot_exceed_the_same_limit(scenario, make_profile):
    from n26.library.authoring import ef_offers_cycle_recruitment

    campaign, cycle, (iron, _rust), holding = scenario
    profile = make_profile("Ammo-jack", price=30)
    for _ in range(2):
        add_reward(
            holding,
            ef_offers_cycle_recruitment(profiles=[profile], discount=30, maximum=1),
        )
    plan = preview_cycle(cycle)
    selections = selected(plan, iron)
    for line in plan.gangs[0].lines:
        if line.kind == "recruitment":
            selections[str(iron.pk)]["lines"][line.key].update(
                option=line.options[0]["key"], name="Helper"
            )
    with pytest.raises(Refusal, match="maximum"):
        apply_cycle(
            cycle, actor=campaign.owner, token=plan.token, selections=selections
        )
    assert not cycle.resolutions.exists()
    from n26.core.models import Miniature

    assert not Miniature.objects.filter(
        membership__gang=iron, membership__profile=profile
    ).exists()


def test_recruitment_charges_the_discounted_price(scenario, make_profile):
    from n26.library.authoring import ef_offers_cycle_recruitment

    campaign, cycle, (iron, _rust), holding = scenario
    profile = make_profile("Ganger", price=50)
    add_reward(holding, ef_offers_cycle_recruitment(profiles=[profile], discount=25))
    plan = preview_cycle(cycle)
    line = next(line for line in plan.gangs[0].lines if line.kind == "recruitment")
    selections = selected(plan, iron)
    selections[str(iron.pk)]["lines"][line.key].update(
        option=line.options[0]["key"], name="New ganger"
    )
    apply_cycle(cycle, actor=campaign.owner, token=plan.token, selections=selections)
    iron.refresh_from_db()
    assert iron.credits == 90
    assert_reconciled(iron)


def test_recruitment_uses_the_carried_collection_price(scenario, make_profile):
    from n26.library.authoring import create_collection, ef_offers_cycle_recruitment
    from n26.tests.sandbox.actions import assign

    campaign, cycle, (iron, _rust), holding = scenario
    profile = make_profile("Discounted ganger", price=80)
    collection = create_collection(
        "Allied roster", entries=[(profile, {"price_override": 45})]
    )
    assign(collection, gang=iron)
    add_reward(holding, ef_offers_cycle_recruitment(profiles=[profile], discount=25))
    plan = preview_cycle(cycle)
    line = next(line for line in plan.gangs[0].lines if line.kind == "recruitment")
    offered = next(option for option in line.options if option["list_price"] == 45)
    assert offered["payment"] == 20
    selections = selected(plan, iron)
    selections[str(iron.pk)]["lines"][line.key].update(
        option=offered["key"], name="Ally"
    )
    receipt = apply_cycle(
        cycle, actor=campaign.owner, token=plan.token, selections=selections
    )[0]
    iron.refresh_from_db()
    assert iron.credits == 95
    recruitment = next(
        row for row in receipt.snapshot["lines"] if row["kind"] == "recruitment"
    )
    assert recruitment["selected_option"]["payment"] == 20
    assert_reconciled(iron)


@pytest.mark.django_db(transaction=True)
def test_concurrent_applications_move_credits_only_once(scenario):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import connections

    from n26.core.models import CampaignCycle

    campaign, cycle, (iron, _rust), _holding = scenario
    plan = preview_cycle(cycle)
    selections = selected(plan, iron)
    ready = Barrier(2)

    def apply():
        try:
            own_cycle = CampaignCycle.objects.select_related("campaign").get(
                pk=cycle.pk
            )
            actor = User.objects.get(pk=campaign.owner_id)
            ready.wait(timeout=10)
            try:
                return apply_cycle(
                    own_cycle, actor=actor, token=plan.token, selections=selections
                )
            except Refusal:
                return None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: apply(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert CycleResolution.objects.filter(cycle=cycle).count() == 1
    iron.refresh_from_db()
    assert iron.credits == 115
    assert_reconciled(iron)
