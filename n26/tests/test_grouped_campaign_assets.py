"""The same named campaign asset groups on screen, paper, text and captures."""

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.capture import gang_state
from n26.core.render import render_gang
from n26.core.render_text import gang_to_text
from n26.flags import CAMPAIGNS
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
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
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
    assert groups["Territories"].names == "Old Ruins, Shop (x2), Sump shop"
    assert groups["Territories"].held
    assert groups["Settlements"].names == "Settlement"
    assert not groups["Settlements"].held
    assert (
        next(counter.value for counter in block.counters if counter.name == "Income")
        == 60
    )
    assert len(block.holdings) == 4


def test_screen_uses_one_row_and_links_the_named_list(client, grouped):
    from bs4 import BeautifulSoup

    gang, campaign, _, _ = grouped
    html = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    soup = BeautifulSoup(html, "html.parser")
    label = soup.find("dt", string="Territories")
    assert label is not None
    names = label.find_next_sibling("dd")
    assert "Old Ruins, Shop (x2), Sump shop" in names.get_text(" ", strip=True)
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
    assert "Old Ruins, Shop (x2), Sump shop" in html
    text = gang_to_text(gang)
    assert "Campaign: Dust Falls" in text
    assert "Territories: Old Ruins, Shop (x2), Sump shop" in text
    assert "Settlements: Settlement" in text
    assert "Income: 60" in text


def test_capture_keeps_the_group_and_detects_a_lost_copy(grouped):
    gang, _, _, tokens = grouped
    before = gang_state(gang)
    assert ("Territories", "Old Ruins, Shop (x2), Sump shop") in before["campaign"][
        "assets"
    ]
    unassign_asset(tokens[0])
    after = gang_state(gang)
    assert before != after
    assert ("Territories", "Old Ruins, Shop, Sump shop") in after["campaign"]["assets"]
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
        if group.label == "Settlements"
    )
    assert group.names == "Settlement (x2)"
