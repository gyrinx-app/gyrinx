"""The More actions menus in the gang sheet and campaign headers.

React draws both menus. The server picks the links, so these tests read the
island's props and, on the gang sheet, the list drawn for a reader without
JavaScript.
"""

import json

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import campaign_operation
from n26.core.models import CampaignParticipant, Gang
from n26.flags import CAMPAIGNS
from n26.tests.sandbox.actions import found_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def gang(owner, gang_type):
    return Gang.objects.create(
        name="The Ashen Choir",
        owner=owner,
        gang_type=gang_type,
        starting_credits=1000,
        credits=1000,
    )


@pytest.fixture
def campaigns_open(db):
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )


@pytest.fixture
def campaign(campaigns_open, campaign_type):
    arbitrator = User.objects.create_user("arbitrator")
    return found_campaign("Dust Falls", campaign_type, owner=arbitrator)


def menus(html):
    """Each More actions menu on the page: its host's props, and the links
    in its no-JavaScript list (None when it has none)."""
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for host in soup.select('[data-react-name="action-menu"]'):
        props = json.loads(soup.find(id=host["data-react-props"]).string)
        if props["label"] != "More actions":
            continue
        noscript = host.find("noscript")
        listed = None
        if noscript is not None:
            inner = BeautifulSoup(noscript.decode_contents(), "html.parser")
            listed = [
                (a.get_text(strip=True), a["href"])
                for a in inner.select("[data-action-menu-list] a")
            ]
        found.append((host, props, listed))
    return found


def the_menu(html):
    (menu,) = menus(html)
    return menu


def entries(props):
    return [
        (item["label"], item["href"], item["tone"], item["separatorBefore"])
        for item in props["items"]
    ]


def gang_url(route, gang):
    return reverse(route, args=[gang.pk])


class TestTheGangSheetHeader:
    def test_the_owner_gets_every_whole_gang_link_with_delete_last(
        self, client, owner, gang
    ):
        client.force_login(owner)
        html = client.get(gang_url("n26-gang", gang)).content.decode()

        host, props, listed = the_menu(html)

        assert entries(props) == [
            ("History", gang_url("n26-gang-history", gang), "default", False),
            ("Notes", gang_url("n26-gang-notes", gang), "default", False),
            ("Lore", gang_url("n26-gang-lore", gang), "default", False),
            ("Clone gang", gang_url("n26-clone-gang", gang), "default", False),
            ("Delete gang", gang_url("n26-delete-gang", gang), "danger", False),
        ]
        assert (props["trigger"], props["variant"], props["align"]) == (
            "ellipsis",
            "default",
            "end",
        )
        assert listed == [(item["label"], item["href"]) for item in props["items"]]
        # The wrapper, not the host, is the group's child: the group's
        # corner and height rules must not see the props script.
        wrapper = host.parent
        assert wrapper.has_attr("data-action-menu-scriptless")
        assert "n26-button-group" in wrapper.parent["class"]
        assert wrapper.parent.find("a", string=lambda s: s and "Print" in s)

    def test_a_signed_in_reader_gets_notes_lore_and_clone(self, client, gang):
        client.force_login(User.objects.create_user("someone-else"))
        html = client.get(gang_url("n26-gang", gang)).content.decode()

        _, props, listed = the_menu(html)

        assert entries(props) == [
            ("Notes", gang_url("n26-gang-notes", gang), "default", False),
            ("Lore", gang_url("n26-gang-lore", gang), "default", False),
            ("Clone gang", gang_url("n26-clone-gang", gang), "default", False),
        ]
        assert listed == [(item["label"], item["href"]) for item in props["items"]]
        assert gang_url("n26-gang-history", gang) not in html
        assert gang_url("n26-delete-gang", gang) not in html

    def test_a_visitor_gets_notes_and_lore_as_buttons_and_no_menu(self, client, gang):
        html = client.get(gang_url("n26-gang", gang)).content.decode()

        assert menus(html) == []
        assert 'aria-label="More actions"' not in html
        soup = BeautifulSoup(html, "html.parser")
        assert soup.find("a", href=gang_url("n26-gang-notes", gang))
        assert soup.find("a", href=gang_url("n26-gang-lore", gang))
        assert gang_url("n26-clone-gang", gang) not in html

    def test_the_trigger_draws_before_the_island_mounts(self, client, owner, gang):
        client.force_login(owner)
        html = client.get(gang_url("n26-gang", gang)).content.decode()

        host, _, _ = the_menu(html)
        (button,) = host.find_all("button", recursive=False)
        assert button["aria-label"] == "More actions"
        assert button["aria-haspopup"] == "menu"
        assert html.count('aria-label="More actions"') == 1


@pytest.fixture
def labelled(campaign, gang):
    """The gang in a campaign that keeps a label, so its owner can redraw
    the sheet by choosing one."""
    with campaign_operation(campaign, actor=campaign.owner) as op:
        op.add_label("Allegiance", ["Loyal", "Rebel"])
    CampaignParticipant.objects.create(
        campaign=campaign,
        user=gang.owner,
        state=CampaignParticipant.State.ACCEPTED,
    )
    with campaign_operation(campaign, actor=campaign.owner) as op:
        op.add_gang(gang)
    return gang


def test_the_menu_comes_back_when_a_label_choice_redraws_the_sheet(
    client, owner, labelled
):
    gang = labelled
    client.force_login(owner)
    sheet = BeautifulSoup(client.get(gang_url("n26-gang", gang)).content, "html.parser")
    pencil = sheet.find(id="n26-campaign-state").find(
        "a", {"aria-label": "Edit Allegiance"}
    )
    dialog = BeautifulSoup(
        client.get(pencil["href"], HTTP_HX_REQUEST="true").content, "html.parser"
    )
    choice = dialog.find("input", {"type": "radio"})["value"]

    response = client.post(
        pencil["href"],
        {"thing": choice, "return": gang_url("n26-gang", gang)},
        HTTP_HX_REQUEST="true",
    )

    html = response.content.decode()
    soup = BeautifulSoup(html, "html.parser")
    assert soup.find(id="n26-gang-sheet")["hx-swap-oob"] == "true"
    _, props, listed = the_menu(html)
    assert [item["label"] for item in props["items"]] == [
        "History",
        "Notes",
        "Lore",
        "Clone gang",
        "Delete gang",
    ]
    assert len(listed) == 5


class TestTheCampaignHeader:
    def test_the_arbitrator_gets_the_log_counters_asset_types_and_archive(
        self, client, campaign
    ):
        client.force_login(campaign.owner)
        html = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()

        host, props, listed = the_menu(html)

        assert entries(props) == [
            (
                "View log",
                reverse("n26-campaign-log", args=[campaign.pk]),
                "default",
                False,
            ),
            (
                "Counters and labels",
                reverse("n26-edit-campaign", args=[campaign.pk])
                + "?tab=counters-and-labels",
                "default",
                False,
            ),
            (
                "Asset types",
                reverse("n26-edit-campaign", args=[campaign.pk]) + "?tab=asset-types",
                "default",
                False,
            ),
            (
                "Archive campaign",
                reverse("n26-archive-campaign", args=[campaign.pk]),
                "default",
                False,
            ),
        ]
        assert (props["trigger"], props["variant"], props["align"]) == (
            "ellipsis",
            "default",
            "end",
        )
        assert listed is None
        assert "n26-button-group" in host.parent.parent["class"]

    def test_a_player_gets_only_the_log(self, client, campaign):
        player = User.objects.create_user("seated")
        CampaignParticipant.objects.create(
            campaign=campaign,
            user=player,
            state=CampaignParticipant.State.ACCEPTED,
        )
        client.force_login(player)
        html = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()

        _, props, _ = the_menu(html)

        assert [item["label"] for item in props["items"]] == ["View log"]
        assert reverse("n26-archive-campaign", args=[campaign.pk]) not in html
