"""Cycle controls share the campaign's permissions and record a real application."""

import json

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.cycles import start_cycle
from n26.core.models import CycleResolution
from n26.flags import CAMPAIGNS
from n26.library.authoring import add_asset_type, create_asset, create_campaign_type
from n26.library.models import AssetType
from n26.tests.sandbox.actions import (
    add_asset,
    assign_asset,
    found_campaign,
    found_gang,
    join_campaign,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def game(default_pack, gang_type, client):
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
    owner = User.objects.create_user("cycle-arbitrator")
    client.force_login(owner)
    campaign = found_campaign(
        "Cinderhaven", create_campaign_type("Cycles"), owner=owner
    )
    gang = found_gang("Iron keepers", gang_type, owner=owner, budget=100)
    join_campaign(gang, campaign)
    kind = add_asset_type(
        campaign.campaign_type, "Territory", AssetType.Ownership.HOLDING
    )
    holding = add_asset(campaign, create_asset("Workshop", kind, income=15))
    assign_asset(holding, gang)
    return campaign, gang


def props(response):
    soup = BeautifulSoup(response.content, "html.parser")
    host = soup.select_one('[data-react-name="cycle-rewards"]')
    return json.loads(soup.find(id=host["data-react-props"]).string)


def test_start_review_apply_receipt_and_compact_metadata(client, game):
    campaign, gang = game
    edit = reverse("n26-edit-cycle", args=[campaign.pk])
    assert client.get(edit).status_code == 200
    assert (
        client.post(edit, {"name": "Opening games", "previous": ""}).status_code == 302
    )
    cycle = campaign.cycles.get()
    url = reverse("n26-cycle-rewards", args=[campaign.pk, cycle.pk])
    response = client.get(url)
    data = props(response)
    assert data["gangs"][0]["lines"][0]["amount"] == 15
    selection = {
        str(gang.pk): {
            "comment": "After the games",
            "lines": {
                line["key"]: {"skip": False} for line in data["gangs"][0]["lines"]
            },
        }
    }
    response = client.post(
        url, {"token": data["token"], "selections": json.dumps(selection)}
    )
    assert response.status_code == 302
    receipt = CycleResolution.objects.get()
    gang.refresh_from_db()
    assert gang.credits == 115
    read = client.get(reverse("n26-cycle-receipt", args=[campaign.pk, receipt.pk]))
    assert read.status_code == 200
    assert "After the games" in read.content.decode()
    assert "Income 15¢" in BeautifulSoup(read.content, "html.parser").get_text(
        " ", strip=True
    )
    campaign_page = client.get(reverse("n26-campaign", args=[campaign.pk]))
    assert campaign_page.status_code == 200
    assert "Cycle 1 · Opening games" in campaign_page.content.decode()
    gang_page = client.get(reverse("n26-gang", args=[gang.pk]))
    assert gang_page.status_code == 200
    body = gang_page.content.decode()
    assert "Boons applied" in body
    assert "View receipt" in body
    assert (
        client.get(reverse("n26-cycle-history", args=[campaign.pk])).status_code == 200
    )


def test_player_cannot_manage_or_apply_cycles(client, game):
    campaign, _gang = game
    cycle = start_cycle(campaign, actor=campaign.owner)
    client.force_login(User.objects.create_user("reader"))
    assert client.get(reverse("n26-edit-cycle", args=[campaign.pk])).status_code == 404
    url = reverse("n26-cycle-rewards", args=[campaign.pk, cycle.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert props(response)["readOnly"] is True
    assert (
        BeautifulSoup(response.content, "html.parser").h1.get_text(strip=True)
        == "Cycle boons"
    )
    assert "Only the campaign arbitrator can apply" in response.content.decode()
    assert client.post(url, {"selections": "{}"}).status_code == 404
    assert (
        client.get(reverse("n26-cycle-history", args=[campaign.pk])).status_code == 200
    )


def test_malformed_submission_and_stale_preview_move_nothing(client, game):
    campaign, gang = game
    cycle = start_cycle(campaign, actor=campaign.owner)
    url = reverse("n26-cycle-rewards", args=[campaign.pk, cycle.pk])
    for submission in ("not json", "[]", '{"bad": null}'):
        response = client.post(url, {"token": "stale", "selections": submission})
        assert response.status_code == 200
        assert props(response)["problem"]
    gang.refresh_from_db()
    assert gang.credits == 100
    assert not cycle.resolutions.exists()


def test_next_cycle_requires_explicit_pending_acknowledgement(client, game):
    campaign, _gang = game
    cycle = start_cycle(campaign, actor=campaign.owner)
    url = reverse("n26-edit-cycle", args=[campaign.pk])
    response = client.post(url, {"previous": str(cycle.pk), "name": "Next"})
    assert response.status_code == 200
    assert campaign.cycles.count() == 1
    soup = BeautifulSoup(response.content, "html.parser")
    checkbox = soup.select_one('input[name="leave_pending"]')
    assert checkbox["value"] == "on"
    assert "checked" not in checkbox.attrs
    assert not checkbox.find_parent(attrs={"role": "checkbox"})
    response = client.post(
        url, {"previous": str(cycle.pk), "name": "Next", "leave_pending": "on"}
    )
    assert response.status_code == 302
    assert campaign.cycles.count() == 2


def test_more_territories_do_not_add_queries_to_the_campaign_page(client, game):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    campaign, gang = game
    start_cycle(campaign, actor=campaign.owner)
    url = reverse("n26-campaign", args=[campaign.pk])
    client.get(url)
    with CaptureQueriesContext(connection) as queries:
        assert client.get(url).status_code == 200
    small = len(queries)
    asset = campaign.campaign_assets.get().asset
    for _ in range(6):
        assign_asset(add_asset(campaign, asset), gang)
    client.get(url)
    with CaptureQueriesContext(connection) as queries:
        assert client.get(url).status_code == 200
    assert len(queries) <= small


def test_refused_preview_preserves_only_known_gangs_and_controls(client, game):
    campaign, gang = game
    cycle = start_cycle(campaign, actor=campaign.owner)
    url = reverse("n26-cycle-rewards", args=[campaign.pk, cycle.pk])
    data = props(client.get(url))
    line = data["gangs"][0]["lines"][0]["key"]
    selection = {
        str(gang.pk): {
            "comment": "Already paid",
            "lines": {line: {"skip": True}, "unknown": {"skip": False}},
        },
        "not-a-member": {"comment": "Ignore", "lines": {}},
    }
    response = client.post(url, {"token": "stale", "selections": json.dumps(selection)})
    refreshed = props(response)
    assert refreshed["problem"]
    assert refreshed["submitted"] == {
        str(gang.pk): {"comment": "Already paid", "lines": {line: {"skip": True}}}
    }
    assert not cycle.resolutions.exists()
    gang.refresh_from_db()
    assert gang.credits == 100


def test_campaign_and_history_show_each_gangs_pending_or_recorded_boons(
    client, game, gang_type
):
    from n26.core.cycle_rewards import apply_cycle, preview_cycle

    campaign, iron = game
    rust = found_gang("Rust keepers", gang_type, owner=campaign.owner, budget=100)
    join_campaign(rust, campaign)
    cycle = start_cycle(campaign, actor=campaign.owner, name="Opening games")
    plan = preview_cycle(cycle)
    iron_plan = next(gang for gang in plan.gangs if gang.gang_id == str(iron.pk))
    receipt = apply_cycle(
        cycle,
        actor=campaign.owner,
        token=plan.token,
        selections={
            str(iron.pk): {
                "comment": "Paid",
                "lines": {line.key: {"skip": False} for line in iron_plan.lines},
            }
        },
    )[0]
    history_url = reverse("n26-cycle-history", args=[campaign.pk])
    response = client.get(history_url)
    drawn = BeautifulSoup(response.content, "html.parser")
    body = drawn.get_text(" ", strip=True)
    assert "Iron keepers Applied View receipt" in body
    assert "Rust keepers Pending Review boons" in body
    assert drawn.find(
        "a", href=reverse("n26-cycle-receipt", args=[campaign.pk, receipt.pk])
    )
    table = BeautifulSoup(
        client.get(reverse("n26-campaign", args=[campaign.pk])).content, "html.parser"
    ).find(id="n26-campaign-gangs")
    assert "Cycle boons Applied View receipt" in table.get_text(" ", strip=True)
    assert "Cycle boons Pending Review boons" in table.get_text(" ", strip=True)
    start_cycle(
        campaign,
        actor=campaign.owner,
        previous=str(cycle.pk),
        leave_pending=True,
        name="Mid-campaign",
    )
    late = found_gang("Late arrivals", gang_type, owner=campaign.owner)
    join_campaign(late, campaign)
    response = client.get(history_url)
    entries = response.context["page"].object_list
    old = next(entry for entry in entries if entry.label == "Cycle 1 · Opening games")
    assert [gang.name for gang in old.gangs] == ["Iron keepers", "Rust keepers"]
    assert old.gangs[1].state == "Not applied before the cycle ended"
    assert not old.gangs[1].review_href
    client.force_login(User.objects.create_user("cycle-history-reader"))
    assert "Review boons" not in client.get(history_url).content.decode()


def test_more_cycles_and_pending_gangs_do_not_add_history_queries(
    client, game, gang_type
):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    campaign, _gang = game
    cycle = start_cycle(campaign, actor=campaign.owner)
    url = reverse("n26-cycle-history", args=[campaign.pk])
    client.get(url)
    with CaptureQueriesContext(connection) as queries:
        assert client.get(url).status_code == 200
    baseline = len(queries)
    for index in range(6):
        gang = found_gang(f"Pending gang {index}", gang_type, owner=campaign.owner)
        join_campaign(gang, campaign)
        cycle = start_cycle(
            campaign, actor=campaign.owner, previous=str(cycle.pk), leave_pending=True
        )
    with CaptureQueriesContext(connection) as queries:
        assert client.get(url).status_code == 200
    assert len(queries) == baseline


def test_reward_preview_queries_stay_flat_with_more_pending_gangs_and_fighters(
    client, game, gang_type, make_profile
):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from n26.library.authoring import (
        create_wargear,
        ef_offers_cycle_equipment,
        ef_offers_cycle_recruitment,
        modifier,
        targets_gang_alone,
    )
    from n26.tests.sandbox.actions import hire

    campaign, first = game
    asset = campaign.campaign_assets.get().asset
    profile = make_profile("Cycle recruit", price=50)
    modifier(
        "Cycle recruitment",
        targets_gang_alone(),
        ef_offers_cycle_recruitment(profiles=[profile], discount=25),
        attach_to=asset,
    )
    equipment = create_wargear("Cycle respirator", price=15)
    modifier(
        "Cycle equipment",
        targets_gang_alone(),
        ef_offers_cycle_equipment(equipment, quantity=2),
        attach_to=asset,
    )
    hire(first, profile, "Existing fighter", paid=0)
    cycle = start_cycle(campaign, actor=campaign.owner)
    url = reverse("n26-cycle-rewards", args=[campaign.pk, cycle.pk])
    client.get(url)
    with CaptureQueriesContext(connection) as queries:
        response = client.get(url)
    baseline = len(queries)
    assert {line["kind"] for line in props(response)["gangs"][0]["lines"]} == {
        "income",
        "recruitment",
        "equipment",
    }
    for index in range(4):
        gang = found_gang(
            f"Pending {index}", gang_type, owner=campaign.owner, budget=100
        )
        join_campaign(gang, campaign)
        holding = add_asset(campaign, asset)
        assign_asset(holding, gang)
        hire(gang, profile, f"Existing {index}", paid=0)
    with CaptureQueriesContext(connection) as queries:
        response = client.get(url)
    assert len(props(response)["gangs"]) == 5
    assert len(queries) == baseline
