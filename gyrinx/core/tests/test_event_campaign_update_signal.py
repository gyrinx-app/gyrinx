"""Test that Events with campaign_id update the campaign's modified timestamp."""

from datetime import timedelta

import pytest
from django.utils import timezone

from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.events import Event, EventNoun, EventVerb, log_event


@pytest.mark.django_db
def test_event_with_campaign_id_updates_campaign_modified(user):
    """Test that creating an event with campaign_id updates the campaign's modified timestamp."""
    # Create a campaign with an old modified timestamp
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
        summary="Test campaign for event signal",
    )

    # Force the campaign to have an old modified timestamp
    old_modified = timezone.now() - timedelta(hours=2)
    Campaign.objects.filter(id=campaign.id).update(modified=old_modified)

    # Refresh from DB to get the updated timestamp
    campaign.refresh_from_db()
    assert campaign.modified < timezone.now() - timedelta(hours=1)

    # Create an event with campaign_id in context
    event = Event.objects.create(
        owner=campaign.owner,
        noun=EventNoun.BATTLE,
        verb=EventVerb.CREATE,
        context={
            "campaign_id": str(campaign.id),
            "campaign_name": campaign.name,
            "battle_name": "Test Battle",
        },
    )

    # Refresh the campaign from DB
    campaign.refresh_from_db()

    # The campaign's modified timestamp should now match the event's created timestamp
    assert campaign.modified == event.created


@pytest.mark.django_db
def test_event_without_campaign_id_does_not_update_campaign(user):
    """Test that events without campaign_id don't update any campaign."""
    # Create a campaign
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
        summary="Test campaign for event signal",
    )

    # Force the campaign to have an old modified timestamp
    old_modified = timezone.now() - timedelta(hours=2)
    Campaign.objects.filter(id=campaign.id).update(modified=old_modified)

    # Create an event without campaign_id
    Event.objects.create(
        owner=campaign.owner,
        noun=EventNoun.USER,
        verb=EventVerb.LOGIN,
        context={"some_other_data": "value"},
    )

    # Refresh the campaign from DB
    campaign.refresh_from_db()

    # The campaign's modified timestamp should not have changed
    assert campaign.modified < timezone.now() - timedelta(hours=1)


@pytest.mark.django_db
def test_event_with_empty_campaign_id_does_not_update_campaign(user):
    """Test that events with empty campaign_id don't update any campaign."""
    # Create a campaign
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
        summary="Test campaign for event signal",
    )

    # Force the campaign to have an old modified timestamp
    old_modified = timezone.now() - timedelta(hours=2)
    Campaign.objects.filter(id=campaign.id).update(modified=old_modified)

    # Create an event with empty campaign_id
    Event.objects.create(
        owner=campaign.owner,
        noun=EventNoun.CAMPAIGN,
        verb=EventVerb.UPDATE,
        context={"campaign_id": "", "other_data": "value"},
    )

    # Refresh the campaign from DB
    campaign.refresh_from_db()

    # The campaign's modified timestamp should not have changed
    assert campaign.modified < timezone.now() - timedelta(hours=1)


@pytest.mark.django_db
def test_event_with_nonexistent_campaign_id_does_not_error(user):
    """Test that events with non-existent campaign_id don't cause errors."""

    # Create an event with a non-existent campaign_id
    # This should not raise an exception
    Event.objects.create(
        owner=user,
        noun=EventNoun.CAMPAIGN,
        verb=EventVerb.UPDATE,
        context={
            "campaign_id": "00000000-0000-0000-0000-000000000000",
            "campaign_name": "Non-existent Campaign",
        },
    )
    # Test passes if no exception is raised


@pytest.mark.django_db
def test_log_event_helper_updates_campaign_modified(user):
    """Test that using the log_event helper also triggers campaign updates."""
    # Create a campaign
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
        summary="Test campaign for event signal",
    )

    # Force the campaign to have an old modified timestamp
    old_modified = timezone.now() - timedelta(hours=2)
    Campaign.objects.filter(id=campaign.id).update(modified=old_modified)

    # Use log_event helper with campaign_id
    log_event(
        user=campaign.owner,
        noun=EventNoun.CAMPAIGN_ACTION,
        verb=EventVerb.CREATE,
        request=None,
        action_name="New Action",
        campaign_id=str(campaign.id),
        campaign_name=campaign.name,
    )

    # Refresh the campaign from DB
    campaign.refresh_from_db()

    # The campaign's modified timestamp should be recent
    assert campaign.modified > timezone.now() - timedelta(seconds=5)


@pytest.mark.django_db
def test_updating_existing_event_does_not_update_campaign(user):
    """Test that updating an existing event doesn't update the campaign's modified timestamp."""
    # Create a campaign and event
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
        summary="Test campaign for event signal",
    )

    # Create an event with campaign_id
    event = Event.objects.create(
        owner=campaign.owner,
        noun=EventNoun.CAMPAIGN,
        verb=EventVerb.UPDATE,
        context={"campaign_id": str(campaign.id), "campaign_name": campaign.name},
    )

    # Force the campaign to have an old modified timestamp
    old_modified = timezone.now() - timedelta(hours=2)
    Campaign.objects.filter(id=campaign.id).update(modified=old_modified)

    # Update the existing event
    event.context["updated_field"] = "new_value"
    event.save()

    # Refresh the campaign from DB
    campaign.refresh_from_db()

    # The campaign's modified timestamp should not have changed
    assert campaign.modified < timezone.now() - timedelta(hours=1)


@pytest.mark.django_db
def test_view_events_do_not_update_campaign_modified(user):
    """Test that VIEW events don't update the campaign's modified timestamp."""
    # Create a campaign
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
        summary="Test campaign for event signal",
    )

    # Force the campaign to have an old modified timestamp
    old_modified = timezone.now() - timedelta(hours=2)
    Campaign.objects.filter(id=campaign.id).update(modified=old_modified)

    # Refresh from DB to get the updated timestamp
    campaign.refresh_from_db()
    assert campaign.modified < timezone.now() - timedelta(hours=1)

    # Create a VIEW event with campaign_id in context
    Event.objects.create(
        owner=campaign.owner,
        noun=EventNoun.CAMPAIGN,
        verb=EventVerb.VIEW,  # This should be filtered out
        context={
            "campaign_id": str(campaign.id),
            "campaign_name": campaign.name,
        },
    )

    # Refresh the campaign from DB
    campaign.refresh_from_db()

    # The campaign's modified timestamp should not have changed
    assert campaign.modified < timezone.now() - timedelta(hours=1)
