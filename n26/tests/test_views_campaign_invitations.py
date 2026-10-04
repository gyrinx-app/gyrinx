"""Invitation links and answers across the dashboard and platform inbox."""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag, Notification
from n26.core.campaigns import campaign_operation
from n26.core.models import CampaignEvent, CampaignParticipant
from n26.flags import CAMPAIGNS
from n26.tests.sandbox.actions import found_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def invitation(client, campaign_type):
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
    owner = User.objects.create_user("inviting-arbitrator")
    user = User.objects.create_user("invited-player")
    campaign = found_campaign("Invitation review", campaign_type, owner=owner)
    with campaign_operation(campaign, actor=owner) as act:
        player = act.invite(user, message="Bring your gang on Sunday.")
    client.force_login(user)
    return player


def page(player):
    return reverse("n26-campaign", args=[player.campaign_id])


def answer(client, player, value, **extra):
    return client.post(
        reverse("n26-campaign-answer-invitation", args=[player.campaign_id]),
        {"answer": value, **extra},
    )


class TestOpeningAnInvitation:
    def test_the_campaign_offers_its_invitee_both_answers(self, client, invitation):
        response = client.get(page(invitation))
        assert response.context["invitations"] == [invitation]
        assert not response.context["may_add_gang"]
        assert not response.context["may_record"]
        html = response.content.decode()
        assert "Bring your gang on Sunday." in html
        assert 'value="accept"' in html
        assert 'value="decline"' in html

    def test_an_unrelated_reader_is_not_offered_an_answer(self, client, invitation):
        client.force_login(User.objects.create_user("other-reader"))
        response = client.get(page(invitation))
        assert response.context["invitations"] == []
        assert answer(client, invitation, "accept").status_code == 404

    def test_the_notification_destination_offers_the_answer(
        self, client, invitation, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            with campaign_operation(
                invitation.campaign, actor=invitation.campaign.owner
            ) as act:
                act.remove_player(invitation)
                player = act.invite(invitation.user, message="Try this link.")
        sent = Notification.objects.get(owner=invitation.user)
        assert sent.target == player
        assert sent.target.get_absolute_url() == page(player)
        assert client.get(sent.target.get_absolute_url()).context["invitations"] == [
            player
        ]

    def test_the_home_page_links_to_the_campaign_before_answering(
        self, client, invitation
    ):
        html = client.get("/n26/").content.decode()
        assert f'href="{page(invitation)}"' in html
        assert "Bring your gang on Sunday." in html


class TestAnsweringAnInvitation:
    @pytest.mark.parametrize("next_url", ["/n26/", "https://example.test/", ""])
    def test_accepting_opens_the_campaign_and_removes_the_question(
        self, client, invitation, next_url
    ):
        response = answer(client, invitation, "accept", next=next_url)
        assert response["Location"] == page(invitation)
        invitation.refresh_from_db()
        assert invitation.state == CampaignParticipant.State.ACCEPTED
        response = client.get(page(invitation))
        assert response.context["invitations"] == []
        assert response.context["may_add_gang"]
        assert response.context["may_record"]
        assert not response.context["yours"]

    @pytest.mark.parametrize(
        "first,second",
        [
            ("accept", "accept"),
            ("decline", "decline"),
            ("accept", "decline"),
            ("decline", "accept"),
        ],
    )
    def test_stale_answers_do_not_change_the_record_or_repeat_history(
        self, client, invitation, first, second
    ):
        answer(client, invitation, first)
        invitation.refresh_from_db()
        state, answered = invitation.state, invitation.answered
        events = CampaignEvent.objects.filter(campaign=invitation.campaign).count()
        response = answer(client, invitation, second, next="/n26/")
        invitation.refresh_from_db()
        assert response.status_code == 302
        assert (invitation.state, invitation.answered) == (state, answered)
        assert (
            CampaignEvent.objects.filter(campaign=invitation.campaign).count() == events
        )
        assert response["Location"] == (
            page(invitation) if first == "accept" else "/n26/"
        )

    def test_declining_keeps_the_safe_return_address(self, client, invitation):
        assert (
            answer(client, invitation, "decline", next="/n26/")["Location"] == "/n26/"
        )

    def test_declining_cannot_redirect_to_another_site(self, client, invitation):
        assert (
            answer(client, invitation, "decline", next="//example.test/")["Location"]
            == "/n26/campaigns/"
        )

    def test_an_invitation_withdrawn_since_the_form_opened_has_a_clear_result(
        self, client, invitation, monkeypatch
    ):
        from n26.core.campaigns import CampaignOperation

        original = CampaignOperation.answer_invitation

        def withdraw_then_answer(op, user, accepted):
            op.remove_player(
                CampaignParticipant.objects.get(campaign=op.campaign, user=user)
            )
            return original(op, user, accepted)

        monkeypatch.setattr(
            CampaignOperation, "answer_invitation", withdraw_then_answer
        )
        response = answer(client, invitation, "accept")
        assert response.status_code == 302
        assert response["Location"] == "/n26/campaigns/"
        assert (
            "This invitation is no longer available."
            in client.get(response["Location"]).content.decode()
        )
        assert not CampaignParticipant.objects.filter(pk=invitation.pk).exists()
        assert not invitation.campaign.events.filter(
            kind=CampaignEvent.Kind.INVITE_ACCEPTED
        ).exists()

    def test_an_archived_campaign_cannot_be_joined(self, client, invitation):
        with campaign_operation(
            invitation.campaign, actor=invitation.campaign.owner
        ) as act:
            act.archive()
        assert answer(client, invitation, "accept").status_code == 404
