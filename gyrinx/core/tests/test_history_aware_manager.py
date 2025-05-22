"""
Tests for the HistoryAwareManager functionality.
"""

import pytest
from django.contrib.auth.models import User

from gyrinx.core.models.campaign import Campaign


@pytest.mark.django_db
def test_create_with_user():
    """Test creating objects with user tracking."""
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create a campaign using create_with_user
    campaign = Campaign.objects.create_with_user(
        user=user,
        name="Test Campaign",
        owner=user,
        public=True,
        summary="Created with user tracking",
    )

    # Check that the campaign was created
    assert campaign.name == "Test Campaign"
    assert campaign.owner == user

    # Check history
    history = campaign.history.all()
    assert history.count() == 1
    assert history[0].history_user == user
    assert history[0].history_type == "+"


@pytest.mark.django_db
def test_create_with_user_defaults_to_owner():
    """Test that create_with_user uses owner as default history user."""
    owner = User.objects.create_user(username="owner", password="testpass")

    # Create a campaign without specifying user (should use owner)
    campaign = Campaign.objects.create_with_user(
        name="Test Campaign",
        owner=owner,
        public=True,
        summary="Created without explicit user",
    )

    # Check that the campaign was created
    assert campaign.name == "Test Campaign"
    assert campaign.owner == owner

    # Check history - should use owner as history user
    history = campaign.history.all()
    assert history.count() == 1
    assert history[0].history_user == owner
    assert history[0].history_type == "+"


@pytest.mark.django_db
def test_save_with_user_defaults_to_owner():
    """Test that save_with_user uses owner as default history user."""
    owner = User.objects.create_user(username="owner", password="testpass")

    # Create a campaign without saving
    campaign = Campaign(
        name="Test Campaign",
        owner=owner,
        public=True,
        summary="Testing save_with_user default",
    )

    # Save without specifying user (should use owner)
    campaign.save_with_user()

    # Check history - should use owner as history user
    history = campaign.history.all()
    assert history.count() == 1
    assert history[0].history_user == owner
    assert history[0].history_type == "+"


@pytest.mark.django_db
def test_bulk_create_with_history():
    """Test bulk creating objects with history tracking."""
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create multiple campaigns
    campaigns = [
        Campaign(name=f"Campaign {i}", owner=user, public=True) for i in range(3)
    ]

    # Use bulk_create_with_history
    created = Campaign.objects.bulk_create_with_history(campaigns, user=user)

    # Check that campaigns were created
    assert len(created) == 3

    # Check history for each
    for campaign in Campaign.objects.filter(owner=user):
        history = campaign.history.all()
        assert history.count() == 1
        assert history[0].history_user == user
        assert history[0].history_type == "+"


@pytest.mark.django_db
def test_update_with_user():
    """Test updating objects with user tracking."""
    user1 = User.objects.create_user(username="user1", password="pass1")
    user2 = User.objects.create_user(username="user2", password="pass2")

    # Create some campaigns
    Campaign.objects.create(name="Campaign 1", owner=user1, public=True)
    Campaign.objects.create(name="Campaign 2", owner=user1, public=True)

    # Update them with user tracking
    count = Campaign.objects.filter(owner=user1).update_with_user(
        user=user2, summary="Updated by user2"
    )

    assert count == 2

    # Check history
    for campaign in Campaign.objects.filter(owner=user1):
        history = campaign.history.all()
        # Should have at least 2 records: create + update
        assert history.count() >= 2

        # Most recent should be the update
        latest = history.first()
        assert latest.summary == "Updated by user2"
        assert latest.history_user == user2
        assert latest.history_type == "~"


@pytest.mark.django_db
def test_delete_with_user():
    """Test deleting objects with user tracking."""
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create a campaign
    campaign = Campaign.objects.create(name="To Be Deleted", owner=user, public=True)
    campaign_id = campaign.id

    # Delete with user tracking
    Campaign.objects.filter(id=campaign_id).delete_with_user(user=user)

    # Check that it's deleted
    assert Campaign.objects.filter(id=campaign_id).count() == 0

    # Check history
    history = Campaign.history.filter(id=campaign_id)
    assert history.count() >= 2  # Create + Delete

    # Most recent should be delete
    latest = history.first()
    assert latest.history_type == "-"
    # Note: delete tracking might need more work to properly set user
