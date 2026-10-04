"""Owner budget guidance and privacy-preserving campaign links on gang lists."""

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
from n26.tests.sandbox.actions import found_campaign, found_gang

pytestmark = pytest.mark.django_db


@pytest.fixture
def table(client, campaign_type):
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
    owner = User.objects.create_user("arbitrator")
    campaign = found_campaign("Dust Falls", campaign_type, owner=owner, budget=1000)
    client.force_login(owner)
    return owner, campaign


def join(campaign, gang):
    with campaign_operation(campaign, actor=campaign.owner) as op:
        op.add_gang(gang)


def test_add_gang_explains_unlimited_credits_and_links_to_inspect_and_edit(
    client, table, gang_type
):
    owner, campaign = table
    gang = found_gang("Unlimited gang", gang_type, owner=owner)
    response = client.get(reverse("n26-campaign-add-gang", args=[campaign.pk]))
    soup = BeautifulSoup(response.content, "html.parser")
    assert any(
        link.get_text(strip=True) == gang.name
        for link in soup.find_all("a", href=reverse("n26-gang", args=[gang.pk]))
    )
    assert soup.find(
        "a", href=reverse("n26-edit-gang", args=[gang.pk]) + "#starting-credits"
    )
    assert "credit balances are not tracked" in soup.get_text()
    assert "joining budget is 1000¢" in soup.get_text()
    assert "does not change its credits budget" in soup.get_text()
    gang.refresh_from_db()
    assert gang.starting_credits is None


def test_arbitrator_can_inspect_a_players_gang_but_cannot_change_its_budget(
    client, table, gang_type
):
    _, campaign = table
    player = User.objects.create_user("player")
    CampaignParticipant.objects.create(
        campaign=campaign, user=player, state=CampaignParticipant.State.ACCEPTED
    )
    gang = found_gang("Player gang", gang_type, owner=player)
    soup = BeautifulSoup(
        client.get(reverse("n26-campaign-add-gang", args=[campaign.pk])).content,
        "html.parser",
    )
    assert soup.find("a", href=reverse("n26-gang", args=[gang.pk]))
    assert not soup.find(
        "a", href=reverse("n26-edit-gang", args=[gang.pk]) + "#starting-credits"
    )


def test_joining_leaves_the_budget_unchanged_and_owner_can_explicitly_set_it(
    client, table, gang_type
):
    owner, campaign = table
    gang = found_gang("Unlimited gang", gang_type, owner=owner)
    response = client.post(
        reverse("n26-campaign-add-gang", args=[campaign.pk]),
        {"gang": gang.pk},
        follow=True,
    )
    assert "uses unlimited credits" in response.content.decode()
    gang.refresh_from_db()
    assert gang.starting_credits is None
    sheet_url = reverse("n26-gang", args=[gang.pk])
    assert "Use a custom budget" in client.get(sheet_url).content.decode()
    response = client.post(
        reverse("n26-edit-gang", args=[gang.pk]),
        {"name": gang.name, "starting_credits": 1000, "colour": ""},
    )
    assert response.status_code == 302
    gang.refresh_from_db()
    assert gang.starting_credits == 1000
    assert gang.credits == 1000
    assert "Use a custom budget" not in client.get(sheet_url).content.decode()


def test_unlimited_guidance_is_only_for_owner_of_a_participating_gang(
    client, table, gang_type
):
    owner, campaign = table
    gang = found_gang("Unlimited gang", gang_type, owner=owner)
    path = reverse("n26-gang", args=[gang.pk])
    assert "Use a custom budget" not in client.get(path).content.decode()
    join(campaign, gang)
    client.logout()
    assert "Use a custom budget" not in client.get(path).content.decode()
    stranger = User.objects.create_user("stranger")
    client.force_login(stranger)
    assert "Use a custom budget" not in client.get(path).content.decode()
    assert (
        client.post(
            reverse("n26-edit-gang", args=[gang.pk]),
            {"name": gang.name, "starting_credits": 1000},
        ).status_code
        == 404
    )


@pytest.mark.parametrize("page", ["n26-gangs", "n26-dashboard"])
def test_indexes_link_to_active_campaigns_the_reader_is_in(
    client, table, gang_type, page
):
    owner, campaign = table
    gang = found_gang("Playing gang", gang_type, owner=owner)
    join(campaign, gang)
    soup = BeautifulSoup(client.get(reverse(page)).content, "html.parser")
    row = soup.select_one("[data-record-row]")
    assert (
        row.find("a", href=reverse("n26-campaign", args=[campaign.pk])).get_text(
            strip=True
        )
        == campaign.name
    )


def test_public_gang_index_does_not_disclose_other_peoples_campaigns(
    client, table, gang_type
):
    owner, campaign = table
    gang = found_gang("Public gang", gang_type, owner=owner)
    join(campaign, gang)
    viewer = User.objects.create_user("viewer")
    client.force_login(viewer)
    path = reverse("n26-gangs") + "?everyone=1"
    html = client.get(path).content.decode()
    assert gang.name in html
    assert campaign.name not in html
    assert reverse("n26-campaign", args=[campaign.pk]) not in html
    CampaignParticipant.objects.create(
        campaign=campaign, user=viewer, state=CampaignParticipant.State.INVITED
    )
    assert campaign.name not in client.get(path).content.decode()
    CampaignParticipant.objects.filter(campaign=campaign, user=viewer).update(
        state=CampaignParticipant.State.ACCEPTED
    )
    assert campaign.name in client.get(path).content.decode()
    FeatureFlag.objects.filter(slug=CAMPAIGNS).update(availability=Availability.OFF)
    assert campaign.name not in client.get(path).content.decode()


def test_more_participating_gangs_do_not_add_index_queries(client, table, gang_type):
    owner, campaign = table

    def add(number):
        gang = found_gang(f"Gang {number}", gang_type, owner=owner)
        join(campaign, gang)

    path = reverse("n26-gangs")
    add(0)
    client.get(path)
    with CaptureQueriesContext(connection) as few:
        assert client.get(path).status_code == 200
    for number in range(1, 9):
        add(number)
    with CaptureQueriesContext(connection) as many:
        assert client.get(path).status_code == 200
    assert len(many) <= len(few)


def test_the_owner_can_use_the_current_campaign_budget_in_one_submission(
    client, table, gang_type
):
    owner, campaign = table
    gang = found_gang("Unlimited gang", gang_type, owner=owner)
    join(campaign, gang)
    path = reverse("n26-use-campaign-budget", args=[gang.pk])
    assert client.get(path).status_code == 405
    assert (
        "Use campaign budget"
        in client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    )
    response = client.post(path, {"starting_credits": 1})
    assert response.url == reverse("n26-gang", args=[gang.pk])
    gang.refresh_from_db()
    assert gang.starting_credits == 1000
    assert gang.credits == 1000
    assert "Use campaign budget" not in client.get(response.url).content.decode()


def test_the_campaign_arbitrator_cannot_set_a_players_budget(client, table, gang_type):
    _, campaign = table
    player = User.objects.create_user("player")
    CampaignParticipant.objects.create(
        campaign=campaign, user=player, state=CampaignParticipant.State.ACCEPTED
    )
    gang = found_gang("Player gang", gang_type, owner=player)
    join(campaign, gang)
    assert (
        client.post(reverse("n26-use-campaign-budget", args=[gang.pk])).status_code
        == 404
    )
    gang.refresh_from_db()
    assert gang.starting_credits is None
