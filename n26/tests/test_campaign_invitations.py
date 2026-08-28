"""Asking somebody into a campaign, and their answer.

Here rather than beside the code because telling somebody reaches across to
the platform's inbox, and only these tests may.
"""

import pytest
from django.contrib.auth.models import User

from gyrinx.site.models import Notification
from n26.core.campaigns import campaign_operation
from n26.core.history import campaign_history
from n26.core.models import Campaign, CampaignParticipant

pytestmark = pytest.mark.django_db


@pytest.fixture
def arbitrator():
    return User.objects.create_user("arbitrator")


@pytest.fixture
def player():
    return User.objects.create_user("vex_ordo")


@pytest.fixture
def campaign(arbitrator):
    return Campaign.objects.create(name="Ashfall", owner=arbitrator, budget=1000)


def told(campaign):
    return [
        "".join(span.text for span in act.spans) for act in campaign_history(campaign)
    ]


class TestAsking:
    def test_the_invitation_is_written(self, campaign, arbitrator, player):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.invite(player, message="Sunday.")

        invitation = CampaignParticipant.objects.get()
        assert invitation.campaign == campaign
        assert invitation.user == player
        assert invitation.waiting
        assert invitation.message == "Sunday."
        assert invitation.invited_by == arbitrator

    def test_the_invitation_survives_the_telling(
        self, campaign, arbitrator, player, django_capture_on_commit_callbacks
    ):
        """The record is the point; the notification is how somebody hears.

        Telling happens after the commit for exactly this reason: a failure
        while telling used to poison the transaction that wrote the
        invitation, and roll it back with nothing on screen to say so.
        """
        with django_capture_on_commit_callbacks(execute=True):
            with campaign_operation(campaign, actor=arbitrator) as act:
                act.invite(player)

        assert CampaignParticipant.objects.count() == 1
        assert told(campaign) == ["invited vex_ordo"]

    def test_they_are_told(
        self, campaign, arbitrator, player, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            with campaign_operation(campaign, actor=arbitrator) as act:
                act.invite(player, message="Bring the Wardens.")

        sent = Notification.objects.get(owner=player)
        assert "Ashfall" in sent.subject
        assert sent.content == "Bring the Wardens."

    def test_asking_again_puts_the_same_question_back(
        self, campaign, arbitrator, player
    ):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.invite(player)
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.answer_invitation(player, accepted=False)
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.invite(player, message="Please?")

        invitation = CampaignParticipant.objects.get()
        assert invitation.waiting
        assert invitation.message == "Please?"
        assert invitation.answered is None

    def test_asking_somebody_who_accepted_changes_nothing(
        self, campaign, arbitrator, player
    ):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.invite(player)
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.answer_invitation(player, accepted=True)
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.invite(player, message="again")

        invitation = CampaignParticipant.objects.get()
        assert invitation.state == CampaignParticipant.State.ACCEPTED
        assert invitation.message == ""


class TestAnswering:
    def test_accepting_is_recorded_and_the_arbitrator_is_told(
        self, campaign, arbitrator, player, django_capture_on_commit_callbacks
    ):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.invite(player)

        with django_capture_on_commit_callbacks(execute=True):
            with campaign_operation(campaign, actor=player) as act:
                act.answer_invitation(player, accepted=True)

        assert CampaignParticipant.objects.get().state == (
            CampaignParticipant.State.ACCEPTED
        )
        assert "accepted the invitation" in told(campaign)
        assert Notification.objects.filter(owner=arbitrator).exists()

    def test_declining_is_recorded(self, campaign, arbitrator, player):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.invite(player)
        with campaign_operation(campaign, actor=player) as act:
            act.answer_invitation(player, accepted=False)

        invitation = CampaignParticipant.objects.get()
        assert invitation.state == CampaignParticipant.State.DECLINED
        assert invitation.answered is not None
        assert "declined the invitation" in told(campaign)

    def test_an_answer_already_given_is_not_given_twice(
        self, campaign, arbitrator, player
    ):
        """A second click on a stale page settles nothing again."""
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.invite(player)
        with campaign_operation(campaign, actor=player) as act:
            act.answer_invitation(player, accepted=True)
        with campaign_operation(campaign, actor=player) as act:
            assert act.answer_invitation(player, accepted=False) is None

        assert CampaignParticipant.objects.get().state == (
            CampaignParticipant.State.ACCEPTED
        )

    def test_somebody_never_asked_cannot_answer(self, campaign, player):
        with campaign_operation(campaign, actor=player) as act:
            assert act.answer_invitation(player, accepted=True) is None
        assert not CampaignParticipant.objects.exists()


class TestRemoving:
    def test_the_row_goes_and_the_log_keeps_it(self, campaign, arbitrator, player):
        with campaign_operation(campaign, actor=arbitrator) as act:
            participant = act.invite(player)
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.remove_participant(participant)

        assert not CampaignParticipant.objects.exists()
        assert told(campaign) == [
            "invited vex_ordo",
            "removed vex_ordo from the campaign",
        ]
