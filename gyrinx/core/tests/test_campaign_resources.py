import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from gyrinx.core.models.campaign import (
    Campaign,
    CampaignAction,
    CampaignListResource,
    CampaignResourceType,
)
from gyrinx.core.models.list import List


@pytest.mark.django_db
def test_create_resource_type():
    """Test creating a campaign resource type."""
    user = User.objects.create_user(username="testuser", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    resource_type = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Meat",
        description="<p>Food resource for survival</p>",
        default_amount=10,
        owner=user,
    )

    assert resource_type.name == "Meat"
    assert resource_type.default_amount == 10
    assert str(resource_type) == "Test Campaign - Meat"


@pytest.mark.django_db
def test_campaign_start_allocates_resources(content_house):
    """Test that starting a campaign allocates default resources to all lists."""
    user = User.objects.create_user(username="testuser", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    # Create resource types
    meat = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Meat",
        default_amount=10,
        owner=user,
    )
    credits = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Credits",
        default_amount=100,
        owner=user,
    )

    # Create lists
    gang1 = List.objects.create(
        name="Gang One", owner=user, content_house=content_house
    )
    gang2 = List.objects.create(
        name="Gang Two", owner=user, content_house=content_house
    )
    campaign.lists.add(gang1, gang2)

    # Start campaign
    assert campaign.start_campaign()

    # Check that resources were allocated
    # Note: Lists are cloned when campaign starts
    cloned_lists = campaign.lists.all()
    assert cloned_lists.count() == 2

    for cloned_list in cloned_lists:
        meat_resource = CampaignListResource.objects.get(
            campaign=campaign, resource_type=meat, list=cloned_list
        )
        assert meat_resource.amount == 10

        credits_resource = CampaignListResource.objects.get(
            campaign=campaign, resource_type=credits, list=cloned_list
        )
        assert credits_resource.amount == 100


@pytest.mark.django_db
def test_resource_modification(content_house):
    """Test modifying a list's resource amount."""
    user = User.objects.create_user(username="testuser", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    resource_type = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Meat",
        owner=user,
    )

    list_obj = List.objects.create(
        name="Test Gang", owner=user, content_house=content_house
    )

    resource = CampaignListResource.objects.create(
        campaign=campaign,
        resource_type=resource_type,
        list=list_obj,
        amount=50,
        owner=user,
    )

    # Test positive modification
    resource.modify_amount(20, user=user)
    resource.refresh_from_db()
    assert resource.amount == 70

    # Check action log
    actions = CampaignAction.objects.filter(campaign=campaign).order_by("created")
    assert actions.count() == 1
    action = actions.first()
    assert action.campaign == campaign
    assert action.user == user
    assert action.description == "Meat Update: Test Gang gained 20 Meat (new total: 70)"

    # Test negative modification
    resource.modify_amount(-30, user=user)
    resource.refresh_from_db()
    assert resource.amount == 40

    # Check second action log
    actions = CampaignAction.objects.filter(campaign=campaign).order_by("created")
    assert actions.count() == 2
    action = actions.last()
    assert action.description == "Meat Update: Test Gang lost 30 Meat (new total: 40)"


@pytest.mark.django_db
def test_resource_cannot_go_negative(content_house):
    """Test that resources cannot be reduced below zero."""
    user = User.objects.create_user(username="testuser", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    resource_type = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Credits",
        owner=user,
    )

    list_obj = List.objects.create(
        name="Test Gang", owner=user, content_house=content_house
    )

    resource = CampaignListResource.objects.create(
        campaign=campaign,
        resource_type=resource_type,
        list=list_obj,
        amount=10,
        owner=user,
    )

    # Try to reduce below zero
    with pytest.raises(
        ValueError,
        match="Cannot reduce Credits below zero. Current: 10, Attempted change: -15",
    ):
        resource.modify_amount(-15, user=user)

    # Verify amount didn't change
    resource.refresh_from_db()
    assert resource.amount == 10


@pytest.mark.django_db
def test_resource_modification_requires_user(content_house):
    """Test that resource modification requires a user."""
    user = User.objects.create_user(username="testuser", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    resource_type = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Meat",
        owner=user,
    )

    list_obj = List.objects.create(
        name="Test Gang", owner=user, content_house=content_house
    )

    resource = CampaignListResource.objects.create(
        campaign=campaign,
        resource_type=resource_type,
        list=list_obj,
        amount=10,
        owner=user,
    )

    # Try to modify without a user
    with pytest.raises(ValueError, match="User is required for resource modifications"):
        resource.modify_amount(5, user=None)


@pytest.mark.django_db
def test_resource_type_creation_in_progress_campaign(content_house):
    """Test creating a resource type when campaign is already in progress."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    # Add lists and start campaign
    gang1 = List.objects.create(
        name="Gang One", owner=user, content_house=content_house
    )
    gang2 = List.objects.create(
        name="Gang Two", owner=user, content_house=content_house
    )
    campaign.lists.add(gang1, gang2)
    campaign.start_campaign()

    # Create resource type after campaign started
    response = client.post(
        reverse("core:campaign-resource-type-new", args=[campaign.id]),
        {
            "name": "Ammo",
            "description": "<p>Ammunition for weapons</p>",
            "default_amount": "50",
        },
    )
    assert response.status_code == 302

    # Check that resource was created
    resource_type = CampaignResourceType.objects.get(campaign=campaign, name="Ammo")
    assert resource_type.default_amount == 50

    # Check that resources were allocated to existing lists
    for cloned_list in campaign.lists.all():
        resource = CampaignListResource.objects.get(
            campaign=campaign,
            resource_type=resource_type,
            list=cloned_list,
        )
        assert resource.amount == 50


@pytest.mark.django_db
def test_resource_modify_view_permissions(content_house):
    """Test permissions for modifying resources."""
    client = Client()
    owner = User.objects.create_user(username="owner", password="testpass")
    list_owner = User.objects.create_user(username="listowner", password="testpass")
    User.objects.create_user(username="other", password="testpass")

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=owner,
        public=True,
        status=Campaign.IN_PROGRESS,
    )

    resource_type = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Credits",
        owner=owner,
    )

    list_obj = List.objects.create(
        name="Test Gang", owner=list_owner, content_house=content_house
    )
    campaign.lists.add(list_obj)

    resource = CampaignListResource.objects.create(
        campaign=campaign,
        resource_type=resource_type,
        list=list_obj,
        amount=100,
        owner=owner,
    )

    # Test campaign owner can modify
    client.login(username="owner", password="testpass")
    response = client.get(
        reverse("core:campaign-resource-modify", args=[campaign.id, resource.id])
    )
    assert response.status_code == 200

    # Test list owner can modify their own
    client.login(username="listowner", password="testpass")
    response = client.get(
        reverse("core:campaign-resource-modify", args=[campaign.id, resource.id])
    )
    assert response.status_code == 200

    # Test other user cannot modify
    client.login(username="other", password="testpass")
    response = client.get(
        reverse("core:campaign-resource-modify", args=[campaign.id, resource.id])
    )
    assert response.status_code == 302  # Redirected with error


@pytest.mark.django_db
def test_campaign_resources_view():
    """Test the campaign resources management view."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    # Create resource type
    CampaignResourceType.objects.create(
        campaign=campaign,
        name="Meat",
        description="<p>Food resource</p>",
        default_amount=10,
        owner=user,
    )

    # Test the resources view
    response = client.get(reverse("core:campaign-resources", args=[campaign.id]))
    assert response.status_code == 200
    assert "Meat" in response.content.decode()
    assert "Food resource" in response.content.decode()


@pytest.mark.django_db
def test_resource_modify_form_validation(content_house):
    """Test resource modification form validation."""
    user = User.objects.create_user(username="testuser", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    resource_type = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Credits",
        owner=user,
    )

    list_obj = List.objects.create(
        name="Test Gang", owner=user, content_house=content_house
    )

    resource = CampaignListResource.objects.create(
        campaign=campaign,
        resource_type=resource_type,
        list=list_obj,
        amount=10,
        owner=user,
    )

    # Import the form
    from gyrinx.core.forms.campaign import ResourceModifyForm

    # Test valid modification
    form = ResourceModifyForm(data={"modification": 5}, resource=resource)
    assert form.is_valid()

    # Test invalid modification (would go negative)
    form = ResourceModifyForm(data={"modification": -15}, resource=resource)
    assert not form.is_valid()
    assert "Cannot reduce Credits below zero" in str(form.errors)


@pytest.mark.django_db
def test_campaign_detail_shows_resources(content_house):
    """Test that campaign detail view shows resource summary."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    # Create resource types
    CampaignResourceType.objects.create(
        campaign=campaign,
        name="Meat",
        owner=user,
    )
    CampaignResourceType.objects.create(
        campaign=campaign,
        name="Credits",
        owner=user,
    )

    # Add a list to the campaign so resources table is shown
    from gyrinx.core.models import List

    gang = List.objects.create(
        name="Test Gang", owner=user, content_house=content_house
    )
    campaign.lists.add(gang)

    # Test the campaign detail view
    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200

    content = response.content.decode()
    # Resources section heading (simplified from "Campaign Resources")
    assert ">Resources<" in content or "Resources\n" in content
    assert "Meat" in content
    assert "Credits" in content
    assert "Manage Resources" in content


@pytest.mark.django_db
def test_campaign_detail_creates_missing_resources_in_progress(content_house):
    """Test that viewing campaign detail page creates missing resources for IN_PROGRESS campaigns."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    # Create campaign with two lists and two resource types
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    meat = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Meat",
        default_amount=10,
        owner=user,
    )
    credits = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Credits",
        default_amount=100,
        owner=user,
    )

    gang1 = List.objects.create(
        name="Gang One", owner=user, content_house=content_house
    )
    gang2 = List.objects.create(
        name="Gang Two", owner=user, content_house=content_house
    )
    campaign.lists.add(gang1, gang2)

    # Start campaign
    campaign.start_campaign()

    # Verify resources were created
    cloned_lists = list(campaign.lists.all())
    assert len(cloned_lists) == 2
    assert CampaignListResource.objects.filter(campaign=campaign).count() == 4

    # Simulate missing resources by deleting some
    # Delete meat resource for first list and credits resource for second list
    CampaignListResource.objects.filter(
        campaign=campaign, resource_type=meat, list=cloned_lists[0]
    ).delete()
    CampaignListResource.objects.filter(
        campaign=campaign, resource_type=credits, list=cloned_lists[1]
    ).delete()

    # Verify resources are missing
    assert CampaignListResource.objects.filter(campaign=campaign).count() == 2

    # View campaign detail page (this should trigger defensive fix)
    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200

    # Verify missing resources were created with default amounts
    assert CampaignListResource.objects.filter(campaign=campaign).count() == 4

    # Check that missing resources have correct default amounts
    meat_resource = CampaignListResource.objects.get(
        campaign=campaign, resource_type=meat, list=cloned_lists[0]
    )
    assert meat_resource.amount == 10  # default_amount

    credits_resource = CampaignListResource.objects.get(
        campaign=campaign, resource_type=credits, list=cloned_lists[1]
    )
    assert credits_resource.amount == 100  # default_amount


@pytest.mark.django_db
def test_campaign_detail_does_not_modify_existing_resources(content_house):
    """Test that viewing campaign detail page does not modify existing resources."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    # Create campaign with list and resource type
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    meat = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Meat",
        default_amount=10,
        owner=user,
    )

    gang = List.objects.create(name="Gang One", owner=user, content_house=content_house)
    campaign.lists.add(gang)

    # Start campaign
    campaign.start_campaign()

    # Get the cloned list
    cloned_list = campaign.lists.first()

    # Modify the resource amount
    resource = CampaignListResource.objects.get(
        campaign=campaign, resource_type=meat, list=cloned_list
    )
    resource.amount = 25  # Different from default_amount of 10
    resource.save()

    # View campaign detail page
    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200

    # Verify resource amount was NOT changed back to default
    resource.refresh_from_db()
    assert resource.amount == 25  # Should still be 25, not 10


@pytest.mark.django_db
def test_campaign_detail_does_not_create_resources_for_pre_campaign(content_house):
    """Test that defensive fix only runs for IN_PROGRESS campaigns, not PRE_CAMPAIGN."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    # Create campaign in PRE_CAMPAIGN status
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
        status=Campaign.PRE_CAMPAIGN,
    )

    CampaignResourceType.objects.create(
        campaign=campaign,
        name="Meat",
        default_amount=10,
        owner=user,
    )

    gang = List.objects.create(name="Gang One", owner=user, content_house=content_house)
    campaign.lists.add(gang)

    # View campaign detail page
    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200

    # Verify NO resources were created (should wait until campaign starts)
    assert CampaignListResource.objects.filter(campaign=campaign).count() == 0
