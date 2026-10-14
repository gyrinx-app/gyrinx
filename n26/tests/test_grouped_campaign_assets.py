"""The same named campaign asset groups on screen, paper, text and captures."""

import pytest
from bs4 import BeautifulSoup
from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.capture import gang_state
from n26.core.render import render_gang
from n26.core.render_text import gang_to_text
from n26.library.authoring import create_asset
from n26.library.core_campaign import CAMPAIGN_TYPE, seed_core_campaign
from n26.library.models import CampaignType
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
def grouped(client, default_pack, gang_type):
    seed_core_campaign(apps)
    owner = User.objects.create_user("asset-groups-arbitrator")
    kind = CampaignType.objects.get(name=CAMPAIGN_TYPE)
    campaign = found_campaign("Dust Falls", kind, owner=owner)
    gang = found_gang("Rust Kings", gang_type, owner=owner)
    join_campaign(gang, campaign)
    territory = kind.asset_types.get(label_singular="Territory")
    shop = create_asset("Shop", territory, income=10)
    ruins = create_asset("Old Ruins", territory, income=30)
    tokens = []
    for asset, name in [(shop, ""), (shop, ""), (shop, "Sump shop"), (ruins, "")]:
        token = add_asset(campaign, asset, name=name)
        assign_asset(token, gang)
        tokens.append(token)
    client.force_login(owner)
    return gang, campaign, shop, tokens


def test_named_groups_keep_multiples_and_renamed_copies(grouped):
    gang, _, _, _ = grouped
    block = render_gang(gang).campaign
    groups = {group.label: group for group in block.asset_groups}
    assert groups["Territories"].names == "Settlement, Old Ruins, Shop (x2), Sump shop"
    assert groups["Territories"].held
    assert "Settlements" not in groups
    assert (
        next(counter.value for counter in block.counters if counter.name == "Income")
        == 60
    )
    assert len(block.holdings) == 4


def test_asset_dialog_links_receive_live_view_navigation_props(client, grouped):
    import json

    _, campaign, _, tokens = grouped
    unassign_asset(tokens[0])
    response = client.get(reverse("n26-campaign", args=[campaign.pk]))
    soup = BeautifulSoup(response.content, "html.parser")
    dialogs = []
    for host in soup.select('[data-react-name="campaign-view-link"]'):
        props = json.loads(soup.find(id=host["data-react-props"]).string)
        if props["dialog"]:
            dialogs.append(props)
            assert host.find("a").get("hx-swap") == "none"
    assert {props["label"] for props in dialogs} >= {"Assign", "Unassign", "Transfer"}
    for props in dialogs:
        assert str(campaign.pk) in props["href"]


def test_screen_uses_one_row_and_links_the_named_list(client, grouped):
    from bs4 import BeautifulSoup

    gang, campaign, _, _ = grouped
    html = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    soup = BeautifulSoup(html, "html.parser")
    label = soup.find("dt", string="Territories")
    assert label is not None
    names = label.find_next_sibling("dd")
    assert "Settlement, Old Ruins, Shop (x2), Sump shop" in names.get_text(
        " ", strip=True
    )
    assert (
        names.find("a")["href"]
        == reverse("n26-campaign", args=[campaign.pk]) + "#assets"
    )
    assert "income" not in names.get_text().lower()
    assert len(soup.find_all("dt", string="Territories")) == 1


def test_print_and_text_follow_the_same_groups(client, grouped):
    gang, _, _, _ = grouped
    html = client.get(reverse("n26-print", args=[gang.pk])).content.decode()
    assert "Territories" in html
    assert "Settlement, Old Ruins, Shop (x2), Sump shop" in html
    text = gang_to_text(gang)
    assert "Campaign: Dust Falls" in text
    assert "Territories: Settlement, Old Ruins, Shop (x2), Sump shop" in text
    assert "Settlements:" not in text
    assert "Income: 60" in text


def test_capture_keeps_the_group_and_detects_a_lost_copy(grouped, monkeypatch):
    from n26.core import capture

    gang, _, _, tokens = grouped
    before = gang_state(gang)
    assert ("Territories", "Settlement, Old Ruins, Shop (x2), Sump shop") in before[
        "campaign"
    ]["assets"]
    reordered = render_gang(gang)
    reordered.campaign.lines.reverse()
    reordered.campaign.holdings.reverse()
    reordered.campaign.asset_types.reverse()
    with monkeypatch.context() as patch:
        patch.setattr(capture, "render_gang", lambda _: reordered)
        assert gang_state(gang) == before
    unassign_asset(tokens[0])
    after = gang_state(gang)
    assert before != after
    assert ("Territories", "Settlement, Old Ruins, Shop, Sump shop") in after[
        "campaign"
    ]["assets"]
    assert ("Income", "50") in after["campaign"]["counters"]


def test_print_header_toggle_keeps_campaign_facts_off_the_cards_only_run(
    client, grouped
):
    gang, _, _, _ = grouped
    response = client.get(reverse("n26-print", args=[gang.pk]), {"pick": "1"})
    assert "Shop (x2)" not in response.content.decode()


def test_more_holdings_do_not_add_queries_to_the_sheet_or_print(client, grouped):
    gang, campaign, shop, _ = grouped
    pages = [reverse("n26-gang", args=[gang.pk]), reverse("n26-print", args=[gang.pk])]

    def counts():
        sizes = []
        for page in pages:
            client.get(page)
            with CaptureQueriesContext(connection) as queries:
                assert client.get(page).status_code == 200
            sizes.append(len(queries))
        return sizes

    small = counts()
    for _ in range(8):
        assign_asset(add_asset(campaign, shop), gang)
    assert counts() == small


def test_asset_dialogs_use_the_current_table_view_instead_of_the_original_link(
    client, grouped
):
    _, campaign, _, tokens = grouped
    page = reverse("n26-campaign", args=[campaign.pk])
    target = reverse("n26-campaign-asset-unassign", args=[campaign.pk, tokens[0].pk])
    response = client.get(
        target,
        {"sort": "name", "group": "old"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_CURRENT_URL="http://testserver" + page + "?sort=-wealth&group=",
    )
    assert response.status_code == 200
    assert response.context["back"] == page + "?sort=-wealth&group=#assets"
    assert response.context["action"] == target + "?sort=-wealth&group="
    assert response["HX-Replace-Url"] == response.context["action"]


def test_asset_creation_keeps_the_view_when_switching_sources_and_saving(
    client, grouped
):
    _, campaign, shop, _ = grouped
    target = reverse("n26-campaign-add-asset", args=[campaign.pk])
    query = {"type": str(shop.asset_type_id), "sort": "-wealth", "group": ""}
    page = client.get(target, query)
    assert "sort=-wealth&group=" in page.context["custom_href"]
    custom = client.get(page.context["custom_href"])
    assert "sort=-wealth&group=" in custom.context["catalogue_href"]
    back = reverse("n26-campaign", args=[campaign.pk]) + "?sort=-wealth&group=#assets"
    assert custom.context["back"] == back
    invalid = client.post(page.context["custom_href"], {})
    assert invalid.status_code == 200 and invalid.context["back"] == back
    saved = client.post(
        page.context["custom_href"],
        {
            "asset_type": str(shop.asset_type_id),
            "name": "Custom shop",
            "annotation": "",
            "income": "0",
        },
    )
    assert saved.status_code == 302 and saved.url == back


def test_repeated_campaign_possessions_are_grouped_too(grouped):
    from n26.core.operations import operation
    from n26.library.models import Asset

    gang, campaign, _, _ = grouped
    membership = campaign.memberships.get(gang=gang, left__isnull=True)
    settlement = Asset.objects.get(
        name="Settlement", asset_type__campaign_type=campaign.campaign_type
    )
    with operation(gang, actor=gang.owner) as op:
        op.assign(settlement, gang=gang, caused_by=membership.type_carrier, paid=0)
    group = next(
        group
        for group in render_gang(gang).campaign.asset_groups
        if group.label == "Territories"
    )
    assert group.names == "Settlement (x2), Old Ruins, Shop (x2), Sump shop"


def test_table_tokens_keep_the_selected_columns_when_earlier_additions_are_archived(
    client, grouped
):
    from n26.core.campaigns import campaign_operation
    from n26.tests.fixtures import island_props

    _, campaign, _, _ = grouped
    with campaign_operation(campaign, actor=campaign.owner) as op:
        first_counter = op.add_counter("First")
        selected_counter = op.add_counter("Selected")
        first_label = op.add_label("First label", ["A"])
        selected_label = op.add_label("Selected label", ["B"])
    query = {
        "sort": f"-counter:{selected_counter.pk}",
        "group": f"label:{selected_label.pk}",
    }
    page = reverse("n26-campaign", args=[campaign.pk])
    before = island_props(client.get(page, query).content, "campaign-gangs")
    assert (before["sort"], before["group"]) == (query["sort"], query["group"])
    members = campaign.additions.built_ins.members
    with campaign_operation(campaign, actor=campaign.owner) as op:
        op.archive_counter(members.get(counter=first_counter, archived=False))
        op.archive_label(members.get(slot=first_label, archived=False))
    after = island_props(client.get(page, query).content, "campaign-gangs")
    assert (after["sort"], after["group"]) == (query["sort"], query["group"])
    assert before["labels"][1]["token"] == after["labels"][0]["token"]
    with campaign_operation(campaign, actor=campaign.owner) as op:
        op.archive_counter(members.get(counter=selected_counter, archived=False))
        op.archive_label(members.get(slot=selected_label, archived=False))
    missing = island_props(client.get(page, query).content, "campaign-gangs")
    assert (missing["sort"], missing["group"]) == ("name", "")


def test_campaign_choices_appear_once_in_text_and_stay_dismissed_on_print(
    client, grouped
):
    from n26.core.campaigns import campaign_operation
    from n26.core.views.choose import link_slots

    gang, campaign, _, _ = grouped
    with campaign_operation(campaign, actor=campaign.owner) as op:
        label = op.add_label("League division", ["Upper", "Lower"])
    from n26.core.operations import operation

    membership = campaign.memberships.get(gang=gang, left__isnull=True)
    with operation(gang, actor=gang.owner) as op:
        op.assign(label, gang=gang, caused_by=membership.additions_carrier, paid=0)
    sheet = render_gang(gang)
    assert gang_to_text(gang).count("League division:") == 1
    link_slots(gang, sheet)
    choice = next(
        choice
        for choice in sheet.campaign.choices
        if choice.kind_label == "League division"
    )
    assert client.post(choice.dismiss_href).status_code == 302
    assert (
        "League division"
        not in client.get(reverse("n26-print", args=[gang.pk])).content.decode()
    )


def test_a_campaign_print_with_only_one_side_uses_one_column():
    from django.template import Context, Template

    from n26.core.render import CampaignAssetLine, CampaignBlock

    campaign = CampaignBlock(
        name="Dust Falls",
        campaign_id="campaign",
        holdings=[CampaignAssetLine("Territory", "Shop", type_plural="Territories")],
    )
    rendered = Template('{% include "n26/print_gang.html" %}').render(
        Context({"campaign": campaign})
    )
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(rendered, "html.parser")
    card = soup.find(string="Dust Falls").find_parent(class_="n26-print-card")
    assert len(card.select(".n26-print-column")) == 1


def test_authored_display_groups_combine_arbitrary_types_on_both_sheets(grouped):
    from n26.core.render import render_campaign
    from n26.library.authoring import add_asset_type
    from n26.library.models import AssetType

    gang, campaign, _, _ = grouped
    for singular in ["Workshop", "Depot"]:
        kind = add_asset_type(
            campaign.campaign_type,
            singular,
            AssetType.Ownership.HOLDING,
            display_group="Supply sites",
        )
        asset = create_asset(singular + " East", kind)
        assign_asset(add_asset(campaign, asset), gang)
    block = render_gang(gang).campaign
    group = next(group for group in block.asset_groups if group.label == "Supply sites")
    assert group.names == "Workshop East, Depot East"
    line = render_campaign(campaign).gangs[0]
    group = next(detail for detail in line.details if detail.label == "Supply sites")
    assert group.text == "Workshop East, Depot East"
    assert campaign.campaign_type.asset_types.get(label_singular="Workshop").is_holding


def test_arbitrator_sets_shared_grouping_and_colours_with_viewer_override(
    client, grouped
):
    from n26.core.campaigns import campaign_operation
    from n26.core.models import CampaignEvent
    from n26.core.operations import operation
    from n26.library.models import Pickable
    from n26.tests.sandbox.actions import choose

    gang, campaign, _, _ = grouped
    with campaign_operation(campaign, actor=campaign.owner) as op:
        slot = op.add_label("Division", ["Upper", "Lower"])
    with operation(gang, actor=gang.owner) as op:
        anchor = op.assign(slot, gang=gang, paid=0)
    upper = Pickable.objects.get(pack=campaign.pack, name="Upper")
    choose(anchor, upper)
    url = reverse("n26-campaign-grouping", args=[campaign.pk])
    response = client.get(url)
    assert response.status_code == 200
    payload = {"grouping": str(slot.pk), f"colour_{slot.pk}_{upper.pk}": "red"}
    assert client.post(url, payload).status_code == 302
    campaign.refresh_from_db()
    assert campaign.gang_grouping_id == slot.pk
    assert campaign.group_colours == {str(slot.pk): {str(upper.pk): "red"}}
    events = campaign.events.filter(kind=CampaignEvent.Kind.GROUPING_CHANGED).count()
    assert client.post(url, payload).status_code == 302
    assert (
        campaign.events.filter(kind=CampaignEvent.Kind.GROUPING_CHANGED).count()
        == events
    )
    response = client.get(reverse("n26-campaign", args=[campaign.pk]))
    assert response.context["sheet"].table_group == f"label:{slot.pk}"
    group = response.context["sheet"].table_groups[0]
    assert (group["label"], group["colour"]) == ("Upper", "red")
    from n26.tests.fixtures import island_props

    props = island_props(response.content, "campaign-gangs")
    assert props["group"] == f"label:{slot.pk}"
    assert props["labels"][0]["colours"]["Upper"] == "var(--color-red-500)"
    assert props["gangs"][0]["labels"] == ["Upper"]
    response = client.get(reverse("n26-campaign", args=[campaign.pk]), {"group": ""})
    assert response.context["sheet"].table_group == ""
    campaign.refresh_from_db()
    assert campaign.gang_grouping_id == slot.pk
    assert (
        "changed the gang grouping and colours"
        in client.get(reverse("n26-campaign-log", args=[campaign.pk])).content.decode()
    )


def test_group_settings_reject_foreign_labels_invalid_colours_and_other_players(
    client, grouped
):
    from n26.core.campaigns import campaign_operation
    from n26.library.models import Pickable

    _, campaign, _, _ = grouped
    with campaign_operation(campaign, actor=campaign.owner) as op:
        slot = op.add_label("Division", ["Upper"])
    upper = Pickable.objects.get(pack=campaign.pack, name="Upper")
    url = reverse("n26-campaign-grouping", args=[campaign.pk])
    response = client.post(url, {"grouping": "not-a-label"})
    assert response.status_code == 200
    assert response.context["form"].errors["grouping"]
    text = BeautifulSoup(response.content, "html.parser").get_text(" ", strip=True)
    assert all(error in text for error in response.context["form"].errors["grouping"])
    response = client.post(
        url, {"grouping": str(slot.pk), f"colour_{slot.pk}_{upper.pk}": "invalid"}
    )
    assert response.status_code == 200
    assert response.context["form"].errors[f"colour_{slot.pk}_{upper.pk}"]
    text = BeautifulSoup(response.content, "html.parser").get_text(" ", strip=True)
    assert all(
        error in text
        for error in response.context["form"].errors[f"colour_{slot.pk}_{upper.pk}"]
    )
    other = User.objects.create_user("group-settings-player")
    client.force_login(other)
    assert client.get(url).status_code == 404
    assert client.post(url, {"grouping": str(slot.pk)}).status_code == 404
    response = client.get(reverse("n26-campaign", args=[campaign.pk]))
    assert all(action.target != url for action in response.context["more_actions"])
    campaign.refresh_from_db()
    assert campaign.gang_grouping is None and campaign.group_colours == {}


def test_coloured_grouping_adds_no_queries_as_campaign_gangs_grow(client, grouped):
    from n26.core.campaigns import campaign_operation
    from n26.core.operations import operation
    from n26.library.models import Pickable
    from n26.tests.sandbox.actions import choose

    gang, campaign, _, _ = grouped
    with campaign_operation(campaign, actor=campaign.owner) as op:
        slot = op.add_label("Division", ["Upper"])
    upper = Pickable.objects.get(pack=campaign.pack, name="Upper")
    with operation(gang, actor=gang.owner) as op:
        anchor = op.assign(slot, gang=gang, paid=0)
    choose(anchor, upper)
    with campaign_operation(campaign, actor=campaign.owner) as op:
        op.set_gang_grouping(str(slot.pk), {str(slot.pk): {str(upper.pk): "green"}})
    url = reverse("n26-campaign", args=[campaign.pk])

    def queries():
        client.get(url)
        with CaptureQueriesContext(connection) as captured:
            assert client.get(url).status_code == 200
        return len(captured)

    before = queries()
    for index in range(4):
        extra = found_gang(f"Extra {index}", gang.gang_type, owner=campaign.owner)
        join_campaign(extra, campaign)
        choose(extra.assignments.get(slot=slot, archived=False), upper)
    assert queries() == before
