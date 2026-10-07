"""The stash lines' menus and the campaign gangs' menus, drawn by React.

Each menu is an action-menu host whose props carry the links. The view sets
the order and the separators; n26/core/test_stash_menu.py pins that rule. A
campaign gang offers Remove from campaign alone, and only where the reader may
take that gang out. Both menus sit in regions that htmx redraws, and a redrawn
region carries its hosts again.
"""

import json

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import campaign_operation
from n26.core.models import CampaignParticipant
from n26.flags import CAMPAIGNS
from n26.tests.sandbox.actions import (
    assign,
    create_wargear,
    found_campaign,
    found_gang,
)

pytestmark = pytest.mark.django_db


def menus(html, within=None):
    """Each action-menu host's props, by its label."""
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find(id=within) if within else soup
    found = {}
    for host in root.select('[data-react-name="action-menu"]'):
        props = json.loads(soup.find(id=host["data-react-props"]).string)
        found[props["label"]] = props
    return found


def drawn(props):
    """Each item as its label, with a rule written where a separator falls."""
    rows = []
    for item in props["items"]:
        if item["separatorBefore"]:
            rows.append("—")
        rows.append(item["label"])
    return rows


@pytest.fixture
def player():
    return User.objects.create_user("player")


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Ashen Choir", gang_type, owner=player, budget=1000)


@pytest.fixture
def stashed(gang, default_pack):
    return assign(create_wargear("Respirator", price=15), stash=gang.stash, paid=15)


class TestTheGangSheetStash:
    """The owner gets one menu per stash line; nobody else gets one."""

    def test_the_owner_gets_one_host_per_line_with_the_menu_in_order(
        self, client, gang, stashed
    ):
        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        props = menus(body)["Actions for Respirator"]
        assert drawn(props) == ["Reassign", "Refund", "—", "Sell", "—", "Delete"]
        assert (props["trigger"], props["variant"], props["align"]) == (
            "chevron",
            "default",
            "end",
        )
        assert props["minWidth"] == "10rem"
        at = reverse("n26-gang", args=[gang.pk])
        assert [item["href"] for item in props["items"]] == [
            f"{at}?reassign={stashed.pk}",
            f"{at}?refund={stashed.pk}",
            f"{at}?sell={stashed.pk}",
            f"{at}?remove={stashed.pk}",
        ]
        assert [item["tone"] for item in props["items"]] == [
            "default",
            "default",
            "danger",
            "danger",
        ]
        # The fallback button names the line once; the props never carry
        # the attribute.
        assert body.count('aria-label="Actions for Respirator"') == 1

    def test_a_reader_who_does_not_own_the_gang_gets_no_host(
        self, client, gang, stashed
    ):
        client.force_login(User.objects.create_user("reader"))
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert "Actions for Respirator" not in body
        assert not menus(body)

    def test_more_lines_cost_no_more_queries(self, client, gang, stashed):
        client.force_login(gang.owner)
        address = reverse("n26-gang", args=[gang.pk])
        client.get(address)
        with CaptureQueriesContext(connection) as one:
            client.get(address)
        for name in ("Filter plugs", "Photo-goggles", "Grapnel"):
            assign(create_wargear(name, price=10), stash=gang.stash, paid=10)
        client.get(address)
        with CaptureQueriesContext(connection) as four:
            body = client.get(address).content.decode()

        assert len(menus(body)) == 4
        assert len(four) <= len(one)


@pytest.fixture
def campaigns_open(db):
    return FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )


@pytest.fixture
def arbitrator():
    return User.objects.create_user("arbitrator")


@pytest.fixture
def campaign(campaigns_open, campaign_type, arbitrator, gang, player):
    campaign = found_campaign("Dust Falls", campaign_type, owner=arbitrator)
    CampaignParticipant.objects.create(
        campaign=campaign, user=player, state=CampaignParticipant.State.ACCEPTED
    )
    with campaign_operation(campaign, actor=arbitrator) as op:
        op.add_label("Allegiance", ["Loyal", "Rebel"])
        op.add_gang(gang)
    return campaign


@pytest.fixture
def rivals(campaign, gang_type, arbitrator):
    rivals = found_gang(
        "Rust Kings", gang_type, owner=User.objects.create_user("rust"), budget=1000
    )
    with campaign_operation(campaign, actor=arbitrator) as op:
        op.add_gang(rivals)
    return rivals


class TestTheGangSheetRedraw:
    """A sheet redrawn over htmx carries its stash menus again."""

    def test_saving_a_campaign_label_redraws_the_sheet_with_its_stash_hosts(
        self, client, campaign, gang, stashed
    ):
        client.force_login(gang.owner)
        page = BeautifulSoup(
            client.get(reverse("n26-gang", args=[gang.pk])).content, "html.parser"
        )
        url = page.find("a", {"aria-label": "Edit Allegiance"})["href"]
        dialog = BeautifulSoup(
            client.get(url, HTTP_HX_REQUEST="true").content, "html.parser"
        )
        choice = dialog.find("input", {"type": "radio"})["value"]

        response = client.post(
            url,
            {"thing": choice, "return": reverse("n26-gang", args=[gang.pk])},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        body = response.content.decode()
        soup = BeautifulSoup(body, "html.parser")
        assert soup.find(id="n26-gang-sheet")["hx-swap-oob"] == "true"
        props = menus(body, within="n26-gang-sheet")["Actions for Respirator"]
        assert drawn(props) == ["Reassign", "Refund", "—", "Sell", "—", "Delete"]


class TestTheCampaignGangs:
    """Each gang the reader may take out gets a Remove from campaign menu."""

    def test_the_arbitrator_gets_a_remove_menu_on_every_gang(
        self, client, campaign, gang, rivals, arbitrator
    ):
        client.force_login(arbitrator)
        body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()

        found = menus(body, within="n26-campaign-gangs")
        assert set(found) == {"Actions for The Ashen Choir", "Actions for Rust Kings"}
        props = found["Actions for Rust Kings"]
        assert props["items"] == [
            {
                "label": "Remove from campaign",
                "href": reverse(
                    "n26-campaign-remove-gang", args=[campaign.pk, rivals.pk]
                ),
                "tone": "danger",
                "separatorBefore": False,
            }
        ]
        assert (props["trigger"], props["variant"], props["align"]) == (
            "ellipsis",
            "ghost",
            "end",
        )
        assert props["minWidth"] == "12rem"
        assert body.count('aria-label="Actions for Rust Kings"') == 1

    def test_an_owner_gets_the_menu_on_their_own_gang_alone(
        self, client, campaign, gang, rivals, player
    ):
        client.force_login(player)
        body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()

        assert set(menus(body, within="n26-campaign-gangs")) == {
            "Actions for The Ashen Choir"
        }
        assert "Actions for Rust Kings" not in body
