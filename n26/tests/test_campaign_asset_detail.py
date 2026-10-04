"""Clickable holding details retain the campaign gate and action permissions."""

from datetime import date

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import campaign_operation
from n26.core.models import Battle, CampaignParticipant, LedgerEvent
from n26.flags import CAMPAIGNS
from n26.library.authoring import (
    add_asset_type,
    create_asset,
    create_rule,
    ef_adds,
    modifier,
    targets_gang,
)
from n26.library.models import AssetType
from n26.tests.sandbox.actions import found_campaign, found_gang

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(client, campaign_type, gang_type):
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
    arbitrator = User.objects.create_user("arbitrator")
    player = User.objects.create_user("player")
    kind = add_asset_type(
        campaign_type,
        "Territory",
        AssetType.Ownership.HOLDING,
        label_plural="Territories",
    )
    asset = create_asset("Old Ruins", kind, income=30)
    modifier(
        "Ruins Salvage",
        targets_gang(),
        ef_adds(create_rule("Salvage")),
        attach_to=asset,
    )
    campaign = found_campaign("Dust Falls", campaign_type, owner=arbitrator)
    CampaignParticipant.objects.create(
        campaign=campaign, user=player, state=CampaignParticipant.State.ACCEPTED
    )
    one = found_gang("Rust Kings", gang_type, owner=player)
    two = found_gang("Ash Vipers", gang_type, owner=arbitrator)
    with campaign_operation(campaign, actor=arbitrator) as op:
        first = op.add_gang(one)
        second = op.add_gang(two)
        holding = op.add_asset(asset, name="Ruins by the sump")
        op.assign(holding, first)
    client.force_login(arbitrator)
    return arbitrator, player, campaign, holding, first, second


def address(campaign, holding):
    return reverse("n26-campaign-asset", args=[campaign.pk, holding.pk])


def test_details_show_the_holding_name_income_boons_holder_and_creation_time_without_writes(
    client, setup
):
    _, _, campaign, holding, first, _ = setup
    before = LedgerEvent.objects.count()
    response = client.get(address(campaign, holding))
    assert response.status_code == 200
    assert response.context["details"].income == 30
    assert response.context["details"].boons == ["Salvage."]
    assert response.context["details"].holder == first.gang.name
    html = response.content.decode()
    assert "Ruins by the sump" in html and "Old Ruins" in html
    assert "Added to the campaign" in html
    assert "went to Rust Kings" in html
    assert LedgerEvent.objects.count() == before
    assert client.post(address(campaign, holding)).status_code == 405


def test_asset_row_and_holding_log_link_to_the_exact_holding(client, setup):
    _, _, campaign, holding, _, _ = setup
    soup = BeautifulSoup(
        client.get(reverse("n26-campaign", args=[campaign.pk])).content, "html.parser"
    )
    links = soup.find_all("a", href=address(campaign, holding))
    assert len(links) >= 2
    assert all("Ruins by the sump" in link.get_text() for link in links)


@pytest.mark.parametrize(
    "person,labels",
    [
        ("arbitrator", {"Transfer", "Unassign"}),
        ("player", {"Hand over", "Unassign"}),
        ("reader", set()),
    ],
)
def test_held_actions_follow_existing_owner_and_arbitrator_permissions(
    client, setup, person, labels
):
    arbitrator, player, campaign, holding, _, _ = setup
    viewer = (
        arbitrator
        if person == "arbitrator"
        else player
        if person == "player"
        else User.objects.create_user("reader")
    )
    client.force_login(viewer)
    response = client.get(address(campaign, holding))
    assert {action.label for action in response.context["actions"]} == labels


@pytest.mark.parametrize("person", ["arbitrator", "player", "reader"])
@pytest.mark.parametrize("held", [True, False])
def test_asset_dropdown_keeps_permission_gated_links_and_dialog_fetches(
    client, setup, person, held
):
    arbitrator, player, campaign, holding, _, _ = setup
    if not held:
        with campaign_operation(campaign, actor=arbitrator) as op:
            op.unassign(holding)
    viewer = {"arbitrator": arbitrator, "player": player}.get(person)
    client.force_login(viewer or User.objects.create_user("reader"))
    soup = BeautifulSoup(
        client.get(reverse("n26-campaign", args=[campaign.pk])).content,
        "html.parser",
    )
    panel_id = f"asset-actions-{holding.pk}"
    panel = soup.find(id=panel_id)
    labels = (
        {"Transfer", "Unassign"}
        if held and person == "arbitrator"
        else {"Hand over", "Unassign"}
        if held and person == "player"
        else {"Assign", "Remove"}
        if not held and person == "arbitrator"
        else set()
    )
    if not labels:
        assert panel is None
        assert soup.find("button", popovertarget=panel_id) is None
        return
    assert panel["popover"] == "auto"
    trigger = soup.find("button", popovertarget=panel_id)
    assert trigger["aria-label"] == f"Actions for {holding.name}"
    links = panel.find_all("a")
    assert {link.get_text(strip=True) for link in links} == labels
    for link in links:
        if link.get_text(strip=True) != "Remove":
            assert link["hx-get"] == link["href"]
            assert link["hx-swap"] == "none"


def test_unclaimed_asset_offers_assign_remove_only_to_arbitrator(client, setup):
    arbitrator, player, campaign, holding, _, _ = setup
    with campaign_operation(campaign, actor=arbitrator) as op:
        op.unassign(holding)
    response = client.get(address(campaign, holding))
    assert response.context["details"].holder == ""
    assert {action.label for action in response.context["actions"]} == {
        "Assign",
        "Remove",
    }
    client.force_login(player)
    assert client.get(address(campaign, holding)).context["actions"] == []


def test_ownership_history_folds_a_transfer_once_and_keeps_same_named_holdings_separate(
    client, setup
):
    arbitrator, _, campaign, holding, first, second = setup
    with campaign_operation(campaign, actor=arbitrator) as op:
        op.transfer(holding, second)
        other = op.add_asset(holding.asset, name=holding.name)
        op.assign(other, first)
        op.unassign(holding)
    response = client.get(address(campaign, holding))
    history = [
        "".join(span.text for span in act.spans) for act in response.context["history"]
    ]
    assert history == [
        "Ash Vipers lost Ruins by the sump",
        "Ruins by the sump went from Rust Kings to Ash Vipers",
        "Ruins by the sump went to Rust Kings",
    ]


def stake_battle(campaign, holding, first, second, number, *, transfer=False):
    with campaign_operation(campaign, actor=campaign.owner) as op:
        battle = op.record_battle(
            date.today(),
            gangs=[first.gang, second.gang],
            scenario=f"Sump duel {number}",
        )
        return op.edit_battle(
            battle,
            date=battle.date,
            scenario=battle.scenario,
            gangs=[first.gang, second.gang],
            result=Battle.Result.WINNERS if transfer else Battle.Result.DRAW,
            winners=[second.gang] if transfer else [],
            revision=battle.revision,
            stake=holding,
            stake_awarded_to=second.gang if transfer else None,
        )


def test_staked_battles_show_results_and_recorded_transfer_without_moving_again(
    client, setup
):
    _, _, campaign, holding, first, second = setup
    battle = stake_battle(campaign, holding, first, second, 1, transfer=True)
    before = LedgerEvent.objects.count()
    response = client.get(address(campaign, holding))
    row = response.context["battles"][0]
    assert row.href == reverse("n26-battle", args=[campaign.pk, battle.pk])
    assert row.outcome == "Winners: Ash Vipers"
    assert row.transferred_to == "Ash Vipers"
    assert response.context["details"].holder == "Ash Vipers"
    assert LedgerEvent.objects.count() == before


def test_bad_keys_other_campaigns_and_closed_feature_do_not_expose_details(
    client, setup, campaign_type
):
    arbitrator, _, campaign, holding, _, _ = setup
    other = found_campaign("Other campaign", campaign_type, owner=arbitrator)
    assert client.get(address(other, holding)).status_code == 404
    assert (
        client.get(
            reverse("n26-campaign-asset", args=[campaign.pk, "bad-key"])
        ).status_code
        == 404
    )
    FeatureFlag.objects.filter(slug=CAMPAIGNS).update(availability=Availability.OFF)
    assert client.get(address(campaign, holding)).status_code == 404
    FeatureFlag.objects.filter(slug=CAMPAIGNS).update(
        availability=Availability.EVERYONE
    )
    client.logout()
    assert client.get(address(campaign, holding)).status_code == 404


def test_more_battles_boons_and_ownership_changes_do_not_add_queries(client, setup):
    arbitrator, _, campaign, holding, first, second = setup
    path = address(campaign, holding)
    stake_battle(campaign, holding, first, second, 0)
    client.get(path)
    with CaptureQueriesContext(connection) as few:
        assert client.get(path).status_code == 200
    for number in range(1, 9):
        modifier(
            f"Boon {number}",
            targets_gang(),
            ef_adds(create_rule(f"Rule {number}")),
            attach_to=holding.asset,
        )
        with campaign_operation(campaign, actor=arbitrator) as op:
            holding.refresh_from_db()
            op.transfer(holding, second if holding.holder_id == first.pk else first)
        stake_battle(campaign, holding, first, second, number)
    with CaptureQueriesContext(connection) as many:
        response = client.get(path)
    assert len(response.context["battles"]) == 9
    assert len(response.context["details"].boons) == 9
    assert len(many) <= len(few)


def test_ownership_history_pages_complete_transfers_instead_of_individual_ledger_records(
    client, setup
):
    arbitrator, _, campaign, holding, first, second = setup
    for _number in range(50):
        with campaign_operation(campaign, actor=arbitrator) as op:
            holding.refresh_from_db()
            op.transfer(holding, second if holding.holder_id == first.pk else first)
    page_one = client.get(address(campaign, holding))
    assert page_one.context["total"] == 51
    assert len(page_one.context["history"]) == 50
    page_two = client.get(address(campaign, holding), {"page": 2})
    assert len(page_two.context["history"]) == 1
    assert "went to Rust Kings" in page_two.content.decode()


def test_static_asset_creation_and_roll_routes_remain_reachable():
    from django.urls import resolve

    assert (
        resolve("/n26/campaigns/example/assets/new/").url_name
        == "n26-campaign-new-asset"
    )
    assert (
        resolve("/n26/campaigns/example/assets/roll/").url_name
        == "n26-campaign-roll-asset"
    )


@pytest.mark.parametrize("actor", ["arbitrator", "player"])
def test_transferring_from_a_holding_detail_keeps_the_page_and_updates_its_actions(
    client, setup, actor
):
    arbitrator, player, campaign, holding, first, second = setup
    client.force_login(arbitrator if actor == "arbitrator" else player)
    url = (
        reverse("n26-campaign-asset-transfer", args=[campaign.pk, holding.pk])
        + "?from=detail"
    )
    response = client.get(url, HTTP_HX_REQUEST="true")
    soup = BeautifulSoup(response.content, "html.parser")
    dialog = soup.find(id="n26-asset-dialog")
    assert dialog.find("form")["hx-post"] == url
    assert first.gang.name in dialog.get_text()
    assert dialog.find("input", {"value": str(second.pk)})
    assert not dialog.find("input", {"value": str(first.pk)})
    assert second.gang.owner.username in dialog.get_text()
    response = client.post(url, {}, HTTP_HX_REQUEST="true")
    assert response.context["form"].errors["membership"]
    holding.refresh_from_db()
    assert holding.holder_id == first.pk
    response = client.post(url, {"membership": second.pk}, HTTP_HX_REQUEST="true")
    soup = BeautifulSoup(response.content, "html.parser")
    assert not soup.find("html")
    assert soup.find(id="n26-campaign-asset-detail")["hx-swap-oob"] == "true"
    assert response["HX-Replace-Url"] == address(campaign, holding)
    assert not soup.find(id="n26-asset-dialog-host").get_text(strip=True)
    holding.refresh_from_db()
    assert holding.holder_id == second.pk
    assert response.context["details"].holder == second.gang.name
    assert bool(response.context["actions"]) == (actor == "arbitrator")


def test_the_holding_detail_opens_assignment_and_unassignment_dialogs(client, setup):
    _, _, campaign, holding, _, second = setup
    soup = BeautifulSoup(client.get(address(campaign, holding)).content, "html.parser")
    assert soup.find(id="n26-asset-dialog-host")
    for action in soup.select("a[hx-get]"):
        assert "from=detail" in action["href"]
    url = (
        reverse("n26-campaign-asset-unassign", args=[campaign.pk, holding.pk])
        + "?from=detail"
    )
    response = client.post(url, HTTP_HX_REQUEST="true")
    assert response.context["details"].holder == ""
    url = (
        reverse("n26-campaign-asset-assign", args=[campaign.pk, holding.pk])
        + "?from=detail"
    )
    response = client.get(url, HTTP_HX_REQUEST="true")
    assert response.context["back"] == address(campaign, holding)
    response = client.post(url, {"membership": second.pk}, HTTP_HX_REQUEST="true")
    assert response.context["details"].holder == second.gang.name
    assert response["HX-Replace-Url"] == address(campaign, holding)
