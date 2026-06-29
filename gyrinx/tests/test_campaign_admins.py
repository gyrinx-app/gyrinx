import pytest

from gyrinx.core.models import Campaign


@pytest.mark.django_db
def test_campaign_is_admin(django_user_model):
    """Test the Campaign is_admin helper method."""
    # 1. Setup: Create 3 distinct users
    owner = django_user_model.objects.create_user(
        username="owner", password="testpass123"
    )
    admin_user = django_user_model.objects.create_user(
        username="admin_user", password="testpass123"
    )
    random_user = django_user_model.objects.create_user(
        username="random_user", password="testpass123"
    )

    # 2. Setup: Create a Campaign and assign the owner and secondary admin
    campaign = Campaign.objects.create(name="Necromunda Showdown", owner=owner)
    campaign.admins.add(admin_user)

    # 3. Assertions: Verify our logic returns exactly what we expect
    assert campaign.is_admin(owner) is True, "Owner should be an admin"
    assert campaign.is_admin(admin_user) is True, (
        "Users in the admins list should be admins"
    )
    assert campaign.is_admin(random_user) is False, "Random users should not be admins"
    assert campaign.is_admin(None) is False, (
        "Unauthenticated/None users should not be admins"
    )
