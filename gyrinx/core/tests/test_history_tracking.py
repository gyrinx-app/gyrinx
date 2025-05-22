import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import ContentHouse
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.list import List


@pytest.mark.django_db
def test_history_tracking_via_orm():
    """Test that history is tracked when models are saved via ORM."""
    # Create a user
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create a campaign
    campaign = Campaign.objects.create(
        name="Test Campaign", owner=user, public=True, summary="Initial summary"
    )

    # Check initial history
    history = campaign.history.all()
    assert history.count() == 1
    assert history[0].history_type == "+"  # Created
    assert history[0].name == "Test Campaign"
    assert history[0].summary == "Initial summary"

    # Update the campaign
    campaign.summary = "Updated summary"
    campaign.save()

    # Check history after update
    history = campaign.history.all()
    assert history.count() == 2
    assert history[0].history_type == "~"  # Changed
    assert history[0].summary == "Updated summary"
    assert history[1].history_type == "+"  # Created
    assert history[1].summary == "Initial summary"

    # Delete the campaign
    campaign.delete()

    # Check history after delete
    history = Campaign.history.all()
    assert history.count() == 3
    assert history[0].history_type == "-"  # Deleted
    assert history[0].name == "Test Campaign"


@pytest.mark.django_db
def test_history_tracking_via_view():
    """Test that history is tracked when models are saved via views."""
    client = Client()

    # Create and login a user
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    # First create a house
    house = ContentHouse.objects.create(name="Test House")

    # Create a list via view
    response = client.post(
        reverse("core:lists-new"),
        {
            "name": "Test List",
            "public": True,
            "content_house": house.id,
        },
    )

    # Check if successful (should redirect)
    assert response.status_code == 302

    # Get the created list
    list_obj = List.objects.filter(owner=user, name="Test List").first()
    assert list_obj is not None

    # Check history
    history = list_obj.history.all()
    assert history.count() == 1
    assert history[0].history_type == "+"
    assert history[0].name == "Test List"

    # Check if user was tracked by middleware
    print(f"History user: {history[0].history_user}")
    print(f"History user id: {history[0].history_user_id}")
    # This is the key test - is the middleware tracking the user?
    assert history[0].history_user == user


@pytest.mark.django_db
def test_history_user_tracking():
    """Test that history tracks which user made the change."""
    # Create a user
    user1 = User.objects.create_user(username="user1", password="pass1")

    # Create a campaign as user1
    campaign = Campaign.objects.create(
        name="Test Campaign", owner=user1, public=True, summary="Created by user1"
    )

    # Check that history doesn't have user info (this is likely the issue)
    history = campaign.history.all()
    assert history.count() == 1
    # This will likely fail - history_user is probably None
    print(f"History user: {history[0].history_user}")
    print(f"History user id: {history[0].history_user_id}")

    # The issue is likely that history_user is None when not using admin


@pytest.mark.django_db
def test_history_tracking_with_request_context():
    """Test history tracking with request context (simulating middleware)."""
    from simple_history.signals import pre_create_historical_record

    # Create a user
    user = User.objects.create_user(username="testuser", password="testpass")

    # Method 1: Set _history_user before saving
    campaign = Campaign(
        name="Test Campaign with Context",
        owner=user,
        public=True,
        summary="Created with _history_user",
    )

    # Set history user and save
    campaign._history_user = user
    campaign.save()

    # Check history
    history = campaign.history.all()
    assert history.count() == 1
    # Check if _history_user was picked up
    print(f"Method 1 - History user: {history[0].history_user}")
    print(f"Method 1 - History user id: {history[0].history_user_id}")

    # Method 2: Direct approach using signals
    def add_history_user(sender, **kwargs):
        history_instance = kwargs["history_instance"]
        history_instance.history_user = user

    # Connect signal
    pre_create_historical_record.connect(
        add_history_user, sender=Campaign.history.model
    )

    # Create another campaign
    campaign2 = Campaign.objects.create(
        name="Test Campaign with Signal",
        owner=user,
        public=True,
        summary="Created with signal",
    )

    # Disconnect signal
    pre_create_historical_record.disconnect(
        add_history_user, sender=Campaign.history.model
    )

    # Check history
    history2 = campaign2.history.all()
    assert history2.count() == 1
    assert history2[0].history_user == user
    assert history2[0].history_user_id == user.id


@pytest.mark.django_db
def test_save_with_user_method():
    """Test the save_with_user method from HistoryMixin."""
    # Create a user
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create a campaign without request context
    campaign = Campaign(
        name="Test Campaign", owner=user, public=True, summary="Testing save_with_user"
    )

    # Use save_with_user method
    campaign.save_with_user(user=user)

    # Check history
    history = campaign.history.all()
    assert history.count() == 1
    assert history[0].history_user == user
    assert history[0].history_user_id == user.id


@pytest.mark.django_db
def test_bulk_operations_history():
    """Test that bulk operations don't create history records by default."""
    # Create a house first
    house = ContentHouse.objects.create(name="Test House")

    # Create multiple lists
    lists = [
        List(name=f"Test List {i}", owner=None, content_house=house) for i in range(3)
    ]
    List.objects.bulk_create(lists)

    # Check history - bulk_create doesn't create history records by default
    assert List.history.count() == 0

    # Bulk update
    List.objects.filter(name__startswith="Test List").update(name="Updated List")

    # Still no history records for bulk update
    assert List.history.count() == 0


@pytest.mark.django_db
def test_bulk_create_with_history_method():
    """Test the bulk_create_with_history method from HistoryMixin."""
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create multiple campaigns using bulk_create_with_history
    campaigns = [
        Campaign(name=f"Campaign {i}", owner=user, public=True) for i in range(3)
    ]

    # Use the new method
    Campaign.bulk_create_with_history(campaigns, user=user)

    # Check that history was created
    created_campaigns = Campaign.objects.filter(owner=user)
    assert created_campaigns.count() == 3

    for campaign in created_campaigns:
        history = campaign.history.all()
        assert history.count() == 1
        assert history[0].history_user == user
