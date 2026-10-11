"""A cycle's number and identity survive manual progression and renaming."""

import pytest
from django.contrib.auth.models import User

from n26.core.cycles import current_cycle, rename_cycle, start_cycle
from n26.core.models import CampaignEvent
from n26.core.operations import Refusal
from n26.library.authoring import create_campaign_type
from n26.tests.sandbox.actions import found_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def campaign(default_pack):
    owner = User.objects.create_user("cycle-arbitrator")
    return found_campaign(
        "Ashfall", create_campaign_type("Cycle campaign"), owner=owner
    )


def test_renaming_keeps_the_cycle_identity(campaign):
    cycle = start_cycle(campaign, actor=campaign.owner, name="Ashfall")
    rename_cycle(cycle, actor=campaign.owner, name="The Long Night")
    assert current_cycle(campaign).pk == cycle.pk
    assert cycle.number == 1
    assert cycle.label == "Cycle 1 · The Long Night"
    assert (
        CampaignEvent.objects.filter(
            campaign=campaign, kind=CampaignEvent.Kind.CYCLE_RENAMED
        ).count()
        == 1
    )


def test_progression_requires_the_current_identity(campaign):
    cycle = start_cycle(campaign, actor=campaign.owner)
    next_cycle = start_cycle(campaign, actor=campaign.owner, previous=str(cycle.pk))
    assert next_cycle.number == 2
    cycle.refresh_from_db()
    assert cycle.ended is not None
    with pytest.raises(Refusal, match="current cycle changed"):
        start_cycle(campaign, actor=campaign.owner, previous=str(cycle.pk))
    assert campaign.cycles.count() == 2


def test_only_the_arbitrator_can_manage_cycles(campaign):
    player = User.objects.create_user("cycle-player")
    with pytest.raises(Refusal, match="arbitrator"):
        start_cycle(campaign, actor=player)
    assert not campaign.cycles.exists()


def test_an_ended_cycle_cannot_be_renamed(campaign):
    cycle = start_cycle(campaign, actor=campaign.owner)
    start_cycle(campaign, actor=campaign.owner, previous=str(cycle.pk))
    with pytest.raises(Refusal, match="ended"):
        rename_cycle(cycle, actor=campaign.owner, name="Earlier")
