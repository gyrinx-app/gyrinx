"""Public account links and the seam into campaign invitations."""

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import campaign_operation
from n26.core.models import CampaignParticipant
from n26.core.operations import operation
from n26.flags import CAMPAIGNS
from n26.tests.sandbox.actions import found_campaign, found_gang

pytestmark = pytest.mark.django_db


@pytest.fixture
def people(client):
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
    arbitrator = User.objects.create_user("arbitrator")
    player = User.objects.create_user(
        "public-player",
        email="private@example.com",
        first_name="Private",
        last_name="Name",
    )
    stranger = User.objects.create_user("other-arbitrator")
    client.force_login(arbitrator)
    return arbitrator, player, stranger


def test_public_profile_shows_gang_links_without_account_or_campaign_details(
    client, people, gang_type, campaign_type
):
    _, player, _ = people
    gang = found_gang("Rust Kings", gang_type, owner=player)
    archived = found_gang("Hidden archive", gang_type, owner=player)
    with operation(archived, actor=player) as op:
        op.archive_gang()
    found_campaign("Private campaign name", campaign_type, owner=player)
    client.logout()
    response = client.get(reverse("n26-user-profile", args=[player.pk]))
    assert response.status_code == 200
    html = response.content.decode()
    soup = BeautifulSoup(html, "html.parser")
    assert soup.find("a", href=reverse("n26-gang", args=[gang.pk]))
    for hidden in [
        player.email,
        "Private Name",
        "Hidden archive",
        "Private campaign name",
        "Invite to campaign",
    ]:
        assert hidden not in html


def test_campaign_username_opens_the_named_public_profile(
    client, people, campaign_type, gang_type
):
    arbitrator, _, _ = people
    gang = found_gang("Profile gang", gang_type, owner=arbitrator)
    drawn = BeautifulSoup(
        client.get(reverse("n26-gang", args=[gang.pk])).content, "html.parser"
    )
    assert drawn.find("a", href=reverse("n26-user-profile", args=[arbitrator.pk]))
    campaign = found_campaign("Dust Falls", campaign_type, owner=arbitrator)
    soup = BeautifulSoup(
        client.get(reverse("n26-campaign", args=[campaign.pk])).content, "html.parser"
    )
    profile_links = soup.find_all(
        "a", href=reverse("n26-user-profile", args=[arbitrator.pk])
    )
    assert profile_links
    assert all(
        link.get_text(" ", strip=True).startswith("arbitrator")
        for link in profile_links
    )
    assert not soup.select("button a")


def test_campaign_choice_continues_into_the_existing_invitation_screen(
    client, people, campaign_type
):
    arbitrator, player, stranger = people
    first = found_campaign("Dust Falls", campaign_type, owner=arbitrator)
    second = found_campaign("Sump league", campaign_type, owner=arbitrator)
    other = found_campaign("Other campaign", campaign_type, owner=stranger)
    response = client.get(reverse("n26-invite-user", args=[player.pk]))
    values = {option["value"] for option in response.context["options"]}
    assert values == {str(first.pk), str(second.pk)}
    assert other.name not in response.content.decode()
    assert not CampaignParticipant.objects.filter(user=player).exists()
    response = client.post(
        reverse("n26-invite-user", args=[player.pk]), {"campaign": str(second.pk)}
    )
    assert (
        response.url
        == reverse("n26-campaign-add-player", args=[second.pk]) + f"?invite={player.pk}"
    )
    assert not CampaignParticipant.objects.filter(user=player).exists()
    message_page = client.get(response.url)
    assert message_page.context["asking"] == player
    client.post(
        reverse("n26-campaign-add-player", args=[second.pk]),
        {"user": str(player.pk), "message": "Join the league."},
    )
    invitation = CampaignParticipant.objects.get(campaign=second, user=player)
    assert invitation.state == CampaignParticipant.State.INVITED
    assert invitation.message == "Join the league."


def test_pending_and_accepted_memberships_explain_why_they_are_not_offered(
    client, people, campaign_type
):
    arbitrator, player, _ = people
    pending = found_campaign("Pending league", campaign_type, owner=arbitrator)
    joined = found_campaign("Joined league", campaign_type, owner=arbitrator)
    declined = found_campaign("Declined league", campaign_type, owner=arbitrator)
    for campaign in [pending, joined, declined]:
        with campaign_operation(campaign, actor=arbitrator) as op:
            op.invite(player)
    with campaign_operation(joined, actor=player) as op:
        op.answer_invitation(player, accepted=True)
    with campaign_operation(declined, actor=player) as op:
        op.answer_invitation(player, accepted=False)
    response = client.get(reverse("n26-invite-user", args=[player.pk]))
    assert {item["value"] for item in response.context["options"]} == {str(declined.pk)}
    assert {item["status"] for item in response.context["existing"]} == {
        "Invitation pending",
        "Already playing",
    }
    response = client.post(
        reverse("n26-invite-user", args=[player.pk]), {"campaign": str(pending.pk)}
    )
    assert response.status_code == 200
    assert (
        pending.participants.get(user=player).state == CampaignParticipant.State.INVITED
    )


def test_a_forged_campaign_choice_cannot_open_somebody_elses_invitation(
    client, people, campaign_type
):
    arbitrator, player, stranger = people
    found_campaign("Own league", campaign_type, owner=arbitrator)
    other = found_campaign("Other league", campaign_type, owner=stranger)
    response = client.post(
        reverse("n26-invite-user", args=[player.pk]), {"campaign": str(other.pk)}
    )
    assert response.status_code == 200
    assert "Select one of your available campaigns." in response.content.decode()
    assert other.name not in response.content.decode()
    assert not other.participants.exists()


def test_invitation_entry_respects_authentication_and_the_campaign_flag(client, people):
    _, player, _ = people
    client.logout()
    assert client.get(reverse("n26-invite-user", args=[player.pk])).status_code == 404
    flag = FeatureFlag.objects.get(slug=CAMPAIGNS)
    flag.availability = Availability.OFF
    flag.save()
    assert client.get(reverse("n26-invite-user", args=[player.pk])).status_code == 404
    assert client.get(reverse("n26-user-profile", args=[player.pk])).status_code == 200


def test_profiles_do_not_show_inactive_accounts(client, people):
    _, player, _ = people
    player.is_active = False
    player.save()
    assert client.get(reverse("n26-user-profile", args=[player.pk])).status_code == 404


def test_more_gangs_and_campaigns_do_not_add_queries(
    client, people, gang_type, campaign_type
):
    arbitrator, player, _ = people
    found_gang("Rust Kings", gang_type, owner=player)
    found_campaign("First league", campaign_type, owner=arbitrator)
    paths = [
        reverse("n26-user-profile", args=[player.pk]),
        reverse("n26-invite-user", args=[player.pk]),
    ]

    def counts():
        sizes = []
        for path in paths:
            client.get(path)
            with CaptureQueriesContext(connection) as queries:
                assert client.get(path).status_code == 200
            sizes.append(len(queries))
        return sizes

    small = counts()
    for number in range(8):
        found_gang(f"Gang {number}", gang_type, owner=player)
        found_campaign(f"League {number}", campaign_type, owner=arbitrator)
    assert counts() == small
