"""Approved dashboard behaviour over campaign, holding and counter operations."""

import json
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import campaign_operation
from n26.core.models import CounterValue, LedgerEvent
from n26.core.operations import operation
from n26.core.render import render_campaign, render_gang
from n26.flags import CAMPAIGNS
from n26.library.authoring import (
    create_asset,
    ef_contributes_to_counter,
    modifier,
    targets_gang,
)
from n26.library.core_campaign import seed_core_campaign
from n26.library.models import CampaignType, Counter, Modifier
from n26.tests.sandbox.actions import (
    add_asset,
    assign_asset,
    found_campaign,
    found_gang,
    join_campaign,
    unassign_asset,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def dashboard(client, gang_type, default_pack):
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
    seed_core_campaign(apps)
    kind = CampaignType.objects.get(name="Territory campaign")
    arb = User.objects.create_user("dashboard-arbitrator")
    player = User.objects.create_user("dashboard-player")
    campaign = found_campaign("Dashboard acceptance", kind, owner=arb)
    with campaign_operation(campaign, actor=arb) as act:
        act.invite(player)
    with campaign_operation(campaign, actor=player) as act:
        act.answer_invitation(player, accepted=True)
    gang = found_gang("The Rust Kings", gang_type, owner=player)
    join_campaign(gang, campaign)
    territory = kind.asset_types.get(label_singular="Territory")
    asset = create_asset("Old Ruins", territory, income=20)
    holding = add_asset(campaign, asset)
    assign_asset(holding, gang)
    client.force_login(arb)
    return campaign, gang, holding, arb, player


def income(gang):
    return next(line for line in render_gang(gang).campaign.counters if line.is_income)


@pytest.mark.parametrize("actor", ["arbitrator", "owner"])
def test_income_adjustment_survives_loss_and_gain_and_reset_records_one_change(
    client, dashboard, actor
):
    campaign, gang, holding, arb, player = dashboard
    client.force_login(arb if actor == "arbitrator" else player)
    assignment = gang.assignments.get(counter__name="Income")
    credits = gang.credits
    href = reverse("n26-tally", args=[assignment.pk])
    assert client.post(href, {"adjust": 1, "value": 25}).status_code == 302
    assert (income(gang).value, income(gang).tallied) == (25, 5)
    unassign_asset(holding)
    assert (income(gang).value, income(gang).tallied) == (5, 5)
    assign_asset(holding, gang)
    assert (income(gang).value, income(gang).tallied) == (25, 5)
    with operation(gang, actor=gang.owner) as op:
        op.tally(assignment, 2000)
    before = LedgerEvent.objects.filter(
        assignment=assignment, kind=LedgerEvent.Kind.TALLIED
    ).count()
    assert client.post(href, {"adjust": 1, "reset": 1}).status_code == 302
    assert (income(gang).value, income(gang).tallied) == (20, 0)
    tallies = LedgerEvent.objects.filter(
        assignment=assignment, kind=LedgerEvent.Kind.TALLIED
    )
    assert tallies.count() == before + 1
    assert tallies.latest("created").note == "-2005 → 0"
    assert tallies.latest("created").actor == (arb if actor == "arbitrator" else player)
    assert CounterValue.objects.get(assignment=assignment).value == 0
    gang.refresh_from_db()
    assert gang.credits == credits


def test_reader_sees_income_breakdown_but_cannot_adjust_or_add(client, dashboard):
    campaign, gang, _, _, _ = dashboard
    client.force_login(User.objects.create_user("dashboard-reader"))
    page = client.get(reverse("n26-campaign", args=[campaign.pk]))
    assert page.status_code == 200
    soup = BeautifulSoup(page.content, "html.parser")
    help_host = soup.select_one('[data-react-name="income-tooltip"]')
    explanation = json.loads(soup.find(id=help_host["data-react-props"]).string)
    assert explanation == {"value": 20, "contributed": 20, "adjustment": 0}
    assert "Adjustment 0¢" not in page.content.decode()
    assignment = gang.assignments.get(counter__name="Income")
    assert (
        client.post(
            reverse("n26-tally", args=[assignment.pk]), {"adjust": 1, "value": 25}
        ).status_code
        == 404
    )
    assert (
        client.get(reverse("n26-campaign-add-asset", args=[campaign.pk])).status_code
        == 404
    )
    assert income(gang).value == 20


def test_income_total_uses_current_assets_and_repeated_saves_add_no_history(
    client, dashboard
):
    _, gang, holding, _, _ = dashboard
    assignment = gang.assignments.get(counter__name="Income")
    href = reverse("n26-tally", args=[assignment.pk])
    response = client.get(href)
    assert response.context["counter_preview"]["inputValue"] == "20"
    unassign_asset(holding)
    assert client.post(href, {"adjust": 1, "value": 25}).status_code == 302
    assert (income(gang).value, income(gang).tallied) == (25, 25)
    tallies = LedgerEvent.objects.filter(
        assignment=assignment, kind=LedgerEvent.Kind.TALLIED
    )
    assert tallies.latest("created").note == "+25 → 25"
    before = tallies.count()
    assert client.post(href, {"adjust": 1, "value": 25}).status_code == 302
    assert tallies.count() == before
    assign_asset(holding, gang)
    assert client.post(href, {"adjust": 1, "value": 20}).status_code == 302
    assert (income(gang).value, income(gang).tallied) == (20, 0)


@pytest.mark.parametrize("total", ["", "1.5", "19", "2147483668"])
def test_income_total_errors_keep_the_input_and_do_not_write(client, dashboard, total):
    _, gang, _, _, _ = dashboard
    assignment = gang.assignments.get(counter__name="Income")
    response = client.post(
        reverse("n26-tally", args=[assignment.pk]), {"adjust": 1, "value": total}
    )
    assert response.status_code == 200
    assert response.context["counter_preview"]["inputValue"] == total
    assert response.context["form"].errors["value"]
    assert (income(gang).value, income(gang).tallied) == (20, 0)
    assert not LedgerEvent.objects.filter(
        assignment=assignment, kind=LedgerEvent.Kind.TALLIED
    ).exists()


def test_settlement_is_first_in_one_territories_detail_without_changing_types(
    dashboard,
):
    campaign, gang, _, _, _ = dashboard
    line = render_campaign(campaign).gangs[0]
    assets = [
        detail
        for detail in line.details
        if detail.label in {"Settlements", "Territories"}
    ]
    assert [(detail.label, detail.text) for detail in assets] == [
        ("Territories", "Settlement, Old Ruins")
    ]
    settlement = gang.assignments.get(asset__name="Settlement")
    assert not settlement.asset.asset_type.is_holding
    assert not campaign.campaign_assets.filter(asset=settlement.asset).exists()


@pytest.mark.parametrize("override", [0, 7])
def test_catalogue_batch_override_preserves_catalogue_and_applies_to_each_holding(
    client, dashboard, override
):
    campaign, gang, holding, _, _ = dashboard
    asset = holding.asset
    second = create_asset("Toll Crossing", asset.asset_type, income=30)
    modifier(
        "Toll Crossing: reputation",
        targets_gang(),
        ef_contributes_to_counter(Counter.objects.get(name="Reputation"), 2),
        attach_to=second,
    )
    href = (
        reverse("n26-campaign-add-asset", args=[campaign.pk])
        + f"?type={asset.asset_type_id}"
    )
    key = str(uuid4())
    data = {
        "asset": [str(asset.pk), str(second.pk)],
        "income": override,
        "request_key": key,
    }
    assert client.post(href, data).status_code == 302
    added = list(campaign.campaign_assets.exclude(pk=holding.pk))
    assert len(added) == 2
    assert all(item.holder_id is None for item in added)
    assert {item.income_override.contributes_to_counter.amount for item in added} == {
        override
    }
    shared = added[0].income_override
    assert shared.scope.echoes is False
    for item in added:
        assign_asset(item, gang)
    assert income(gang).value == 20 + 2 * override
    assert (
        next(
            line.value
            for line in render_gang(gang).campaign.counters
            if line.name == "Reputation"
        )
        == 2
    )
    assert holding.asset.income == 20 and second.income == 30
    assert client.post(href, data).status_code == 302
    assert campaign.campaign_assets.count() == 3
    sheet = render_campaign(campaign)
    assert [
        item.income
        for item in sheet.assets[0].entries
        if item.campaign_asset_id != str(holding.pk)
    ] == [override, override]
    for item in added:
        detail = client.get(reverse("n26-campaign-asset", args=[campaign.pk, item.pk]))
        assert detail.context["details"].income == override
        unassign_asset(item)
    assert income(gang).value == 20
    scope, effect = shared.scope, shared.effect
    scope_pk, effect_pk = scope.pk, effect.pk
    with campaign_operation(campaign, actor=campaign.owner) as act:
        act.remove_asset(added[0])
    assert Modifier.objects.filter(pk=shared.pk).exists()
    with campaign_operation(campaign, actor=campaign.owner) as act:
        act.remove_asset(added[1])
    assert not Modifier.objects.filter(pk=shared.pk).exists()
    assert not type(scope).objects.filter(pk=scope_pk).exists()
    assert not type(effect).objects.filter(pk=effect_pk).exists()


def test_income_override_refuses_out_of_range_before_writing(client, dashboard):
    campaign, _, holding, _, _ = dashboard
    href = reverse("n26-campaign-add-asset", args=[campaign.pk])
    response = client.post(
        href,
        {
            "asset": str(holding.asset_id),
            "income": 2147483648,
            "request_key": str(uuid4()),
        },
    )
    assert response.status_code == 200
    assert response.context["form"].errors["income"]
    assert campaign.campaign_assets.count() == 1


def test_custom_entry_adds_an_unclaimed_territory_and_both_sources_share_add(
    client, dashboard
):
    campaign, _, holding, _, _ = dashboard
    href = (
        reverse("n26-campaign-add-asset", args=[campaign.pk])
        + f"?type={holding.asset.asset_type_id}"
    )
    custom = href + "&source=custom"
    page = client.get(href)
    assert "Create custom territory" in page.content.decode()
    assert client.get(custom).status_code == 200
    assert (
        client.post(
            custom,
            {
                "asset_type": str(holding.asset.asset_type_id),
                "name": "Sump Bridge",
                "income": 12,
            },
        ).status_code
        == 302
    )
    made = campaign.campaign_assets.get(asset__name="Sump Bridge")
    assert made.holder_id is None
    assert made.asset.income == 12
    assert made.asset.pack_id == campaign.pack_id
    html = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
    assert 'title="Assets"' not in html
    assert "Create territory" not in html
    assert "Add territories" in html


def test_player_counts_status_and_gangs_are_accurate_and_query_growth_is_flat(
    client, dashboard, gang_type
):
    campaign, gang, _, arb, player = dashboard
    pending = User.objects.create_user("pending-player")
    declined = User.objects.create_user("declined-player")
    accepted = User.objects.create_user("accepted-without-gang")
    with campaign_operation(campaign, actor=arb) as act:
        act.invite(pending)
        act.invite(declined)
        act.invite(accepted)
    with campaign_operation(campaign, actor=declined) as act:
        act.answer_invitation(declined, accepted=False)
    with campaign_operation(campaign, actor=accepted) as act:
        act.answer_invitation(accepted, accepted=True)
    second_gang = found_gang("Pit of Teeth", gang_type, owner=player)
    join_campaign(second_gang, campaign)
    href = reverse("n26-campaign", args=[campaign.pk])
    client.get(href)
    with CaptureQueriesContext(connection) as before:
        page = client.get(href)
    soup = BeautifulSoup(page.content, "html.parser")
    section = soup.select_one("#players")
    assert "2 accepted players · 1 pending invitation" in section.get_text(
        " ", strip=True
    )
    assert "Accepted" in section.get_text() and "No gang yet" in section.get_text()
    assert (
        section.find("a", href=reverse("n26-gang", args=[second_gang.pk])).text
        == second_gang.name
    )
    assert (
        "Playing" in section.get_text()
        and "Invited" in section.get_text()
        and "Declined" in section.get_text()
    )
    assert section.find("a", href=reverse("n26-gang", args=[gang.pk])).text == gang.name
    for number in range(8):
        with campaign_operation(campaign, actor=arb) as act:
            act.invite(User.objects.create_user(f"extra-player-{number}"))
    client.get(href)
    with CaptureQueriesContext(connection) as after:
        page = client.get(href)
    assert len(after) <= len(before)
    assert "2 accepted players · 9 pending invitations" in page.content.decode()
    assert "n26/arbitrator.svg" in page.content.decode()
