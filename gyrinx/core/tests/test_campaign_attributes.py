import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from gyrinx.core.models.campaign import (
    CampaignAction,
    CampaignAttributeType,
    CampaignAttributeValue,
    CampaignListAttributeAssignment,
)


# --- Model Tests ---


@pytest.mark.django_db
def test_create_attribute_type(campaign):
    """Test creating a campaign attribute type."""
    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        description="The faction this gang belongs to",
        is_single_select=True,
        owner=campaign.owner,
    )

    assert attr_type.name == "Faction"
    assert attr_type.is_single_select is True
    assert "Faction" in str(attr_type)
    assert "single-select" in str(attr_type)


@pytest.mark.django_db
def test_create_attribute_value(campaign):
    """Test creating a campaign attribute value with colour."""
    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        owner=campaign.owner,
    )
    value = CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        name="Order",
        colour="#3366FF",
        owner=campaign.owner,
    )

    assert value.name == "Order"
    assert value.colour == "#3366FF"
    assert "Faction: Order" in str(value)


@pytest.mark.django_db
def test_create_attribute_value_without_colour(campaign):
    """Test creating a value without a colour."""
    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Team",
        owner=campaign.owner,
    )
    value = CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        name="Alpha",
        owner=campaign.owner,
    )

    assert value.colour == ""


@pytest.mark.django_db
def test_colour_validation(campaign):
    """Test that invalid colour codes are rejected."""
    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        owner=campaign.owner,
    )
    value = CampaignAttributeValue(
        attribute_type=attr_type,
        name="Bad",
        colour="not-a-colour",
        owner=campaign.owner,
    )

    with pytest.raises(ValidationError):
        value.full_clean()


@pytest.mark.django_db
def test_create_assignment(campaign, make_list):
    """Test creating an attribute assignment."""
    lst = make_list("Test Gang")
    campaign.lists.add(lst)

    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        owner=campaign.owner,
    )
    value = CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        name="Order",
        owner=campaign.owner,
    )

    assignment = CampaignListAttributeAssignment.objects.create(
        campaign=campaign,
        attribute_value=value,
        list=lst,
        owner=campaign.owner,
    )

    assert assignment.attribute_value == value
    assert assignment.list == lst
    assert "Order" in str(assignment)


@pytest.mark.django_db
def test_unique_type_name_per_campaign(campaign):
    """Test that attribute type names are unique per campaign."""
    CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        owner=campaign.owner,
    )

    with pytest.raises(Exception):
        CampaignAttributeType.objects.create(
            campaign=campaign,
            name="Faction",
            owner=campaign.owner,
        )


@pytest.mark.django_db
def test_unique_value_name_per_type(campaign):
    """Test that value names are unique per attribute type."""
    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        owner=campaign.owner,
    )
    CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        name="Order",
        owner=campaign.owner,
    )

    with pytest.raises(Exception):
        CampaignAttributeValue.objects.create(
            attribute_type=attr_type,
            name="Order",
            owner=campaign.owner,
        )


@pytest.mark.django_db
def test_cascade_delete_type(campaign, make_list):
    """Test that deleting an attribute type cascades to values and assignments."""
    lst = make_list("Test Gang")
    campaign.lists.add(lst)

    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        owner=campaign.owner,
    )
    value = CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        name="Order",
        owner=campaign.owner,
    )
    CampaignListAttributeAssignment.objects.create(
        campaign=campaign,
        attribute_value=value,
        list=lst,
        owner=campaign.owner,
    )

    attr_type.delete()

    assert CampaignAttributeValue.objects.count() == 0
    assert CampaignListAttributeAssignment.objects.count() == 0


@pytest.mark.django_db
def test_cascade_delete_value(campaign, make_list):
    """Test that deleting a value cascades to assignments."""
    lst = make_list("Test Gang")
    campaign.lists.add(lst)

    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        owner=campaign.owner,
    )
    value = CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        name="Order",
        owner=campaign.owner,
    )
    CampaignListAttributeAssignment.objects.create(
        campaign=campaign,
        attribute_value=value,
        list=lst,
        owner=campaign.owner,
    )

    value.delete()

    assert CampaignListAttributeAssignment.objects.count() == 0
    assert CampaignAttributeType.objects.count() == 1


# --- View Tests ---


@pytest.mark.django_db
def test_attributes_list_view(client, user, campaign):
    """Test the attributes listing page."""
    client.force_login(user)

    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        owner=user,
    )
    CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        name="Order",
        colour="#3366FF",
        owner=user,
    )

    response = client.get(reverse("core:campaign-attributes", args=(campaign.id,)))
    assert response.status_code == 200
    assert "Faction" in response.content.decode()
    assert "Order" in response.content.decode()


@pytest.mark.django_db
def test_create_attribute_type_view(client, user, campaign):
    """Test creating an attribute type via the view."""
    client.force_login(user)

    response = client.post(
        reverse("core:campaign-attribute-type-new", args=(campaign.id,)),
        {"name": "Faction", "description": "", "is_single_select": True},
    )
    assert response.status_code == 302

    assert CampaignAttributeType.objects.filter(
        campaign=campaign, name="Faction"
    ).exists()


@pytest.mark.django_db
def test_create_attribute_type_unauthorized(client, make_user, campaign):
    """Test that non-owners cannot create attribute types."""
    other_user = make_user("other", "password")
    client.force_login(other_user)

    response = client.post(
        reverse("core:campaign-attribute-type-new", args=(campaign.id,)),
        {"name": "Faction", "description": "", "is_single_select": True},
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_edit_attribute_type_view(client, user, campaign):
    """Test editing an attribute type."""
    client.force_login(user)

    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        owner=user,
    )

    response = client.post(
        reverse(
            "core:campaign-attribute-type-edit",
            args=(campaign.id, attr_type.id),
        ),
        {"name": "Team", "description": "", "is_single_select": True},
    )
    assert response.status_code == 302

    attr_type.refresh_from_db()
    assert attr_type.name == "Team"


@pytest.mark.django_db
def test_remove_attribute_type_view(client, user, campaign):
    """Test removing an attribute type."""
    client.force_login(user)

    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        owner=user,
    )

    response = client.post(
        reverse(
            "core:campaign-attribute-type-remove",
            args=(campaign.id, attr_type.id),
        ),
    )
    assert response.status_code == 302
    assert CampaignAttributeType.objects.count() == 0


@pytest.mark.django_db
def test_create_value_view(client, user, campaign):
    """Test creating an attribute value."""
    client.force_login(user)

    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        owner=user,
    )

    response = client.post(
        reverse(
            "core:campaign-attribute-value-new",
            args=(campaign.id, attr_type.id),
        ),
        {"name": "Order", "description": "", "colour": "#3366FF"},
    )
    assert response.status_code == 302

    value = CampaignAttributeValue.objects.get(name="Order")
    assert value.colour == "#3366FF"


@pytest.mark.django_db
def test_assign_attribute_as_owner(client, user, campaign, make_list):
    """Test that the campaign owner can assign attributes."""
    client.force_login(user)

    lst = make_list("Test Gang")
    campaign.lists.add(lst)

    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        is_single_select=True,
        owner=user,
    )
    value = CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        name="Order",
        owner=user,
    )

    response = client.post(
        reverse(
            "core:campaign-list-attribute-assign",
            args=(campaign.id, lst.id, attr_type.id),
        ),
        {"values": str(value.id)},
    )
    assert response.status_code == 302

    assert CampaignListAttributeAssignment.objects.filter(
        campaign=campaign,
        list=lst,
        attribute_value=value,
    ).exists()

    # Verify campaign action was logged
    assert CampaignAction.objects.filter(campaign=campaign).exists()


@pytest.mark.django_db
def test_assign_attribute_as_gang_owner(client, make_user, user, campaign, make_list):
    """Test that a gang owner can assign attributes to their own gang."""
    gang_owner = make_user("gangowner", "password")
    lst = make_list("Gang Owner's Gang", owner=gang_owner)
    campaign.lists.add(lst)

    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        is_single_select=True,
        owner=user,
    )
    value = CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        name="Chaos",
        owner=user,
    )

    client.force_login(gang_owner)

    response = client.post(
        reverse(
            "core:campaign-list-attribute-assign",
            args=(campaign.id, lst.id, attr_type.id),
        ),
        {"values": str(value.id)},
    )
    assert response.status_code == 302

    assert CampaignListAttributeAssignment.objects.filter(
        list=lst, attribute_value=value
    ).exists()


@pytest.mark.django_db
def test_assign_attribute_unauthorized(client, make_user, user, campaign, make_list):
    """Test that a non-participant cannot assign attributes."""
    other_user = make_user("other", "password")
    lst = make_list("Test Gang")
    campaign.lists.add(lst)

    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        is_single_select=True,
        owner=user,
    )
    CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        name="Order",
        owner=user,
    )

    client.force_login(other_user)

    response = client.post(
        reverse(
            "core:campaign-list-attribute-assign",
            args=(campaign.id, lst.id, attr_type.id),
        ),
        {"values": ""},
    )
    # Should redirect with error message
    assert response.status_code == 302


@pytest.mark.django_db
def test_archived_campaign_blocks_type_creation(client, user, campaign):
    """Test that attribute types cannot be created for archived campaigns."""
    client.force_login(user)
    campaign.archived = True
    campaign.save()

    response = client.post(
        reverse("core:campaign-attribute-type-new", args=(campaign.id,)),
        {"name": "Faction", "description": "", "is_single_select": True},
    )
    assert response.status_code == 302
    assert CampaignAttributeType.objects.count() == 0


@pytest.mark.django_db
def test_reassign_single_select(client, user, campaign, make_list):
    """Test that reassigning a single-select attribute replaces the previous value."""
    client.force_login(user)

    lst = make_list("Test Gang")
    campaign.lists.add(lst)

    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        is_single_select=True,
        owner=user,
    )
    order = CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        name="Order",
        owner=user,
    )
    chaos = CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        name="Chaos",
        owner=user,
    )

    # Assign "Order"
    client.post(
        reverse(
            "core:campaign-list-attribute-assign",
            args=(campaign.id, lst.id, attr_type.id),
        ),
        {"values": str(order.id)},
    )

    assert CampaignListAttributeAssignment.objects.filter(
        list=lst, attribute_value=order
    ).exists()

    # Reassign to "Chaos"
    client.post(
        reverse(
            "core:campaign-list-attribute-assign",
            args=(campaign.id, lst.id, attr_type.id),
        ),
        {"values": str(chaos.id)},
    )

    # Should only have Chaos now
    assignments = CampaignListAttributeAssignment.objects.filter(
        list=lst, attribute_value__attribute_type=attr_type
    )
    assert assignments.count() == 1
    assert assignments.first().attribute_value == chaos


@pytest.mark.django_db
def test_multi_select_allows_multiple(client, user, campaign, make_list):
    """Test that multi-select attributes allow multiple values."""
    client.force_login(user)

    lst = make_list("Test Gang")
    campaign.lists.add(lst)

    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Tags",
        is_single_select=False,
        owner=user,
    )
    tag1 = CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        name="Aggressive",
        owner=user,
    )
    tag2 = CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        name="Defensive",
        owner=user,
    )

    response = client.post(
        reverse(
            "core:campaign-list-attribute-assign",
            args=(campaign.id, lst.id, attr_type.id),
        ),
        {"values": [str(tag1.id), str(tag2.id)]},
    )
    assert response.status_code == 302

    assignments = CampaignListAttributeAssignment.objects.filter(
        list=lst, attribute_value__attribute_type=attr_type
    )
    assert assignments.count() == 2


@pytest.mark.django_db
def test_clear_assignment(client, user, campaign, make_list):
    """Test that submitting with no value clears assignments."""
    client.force_login(user)

    lst = make_list("Test Gang")
    campaign.lists.add(lst)

    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        is_single_select=True,
        owner=user,
    )
    value = CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        name="Order",
        owner=user,
    )

    # Assign
    CampaignListAttributeAssignment.objects.create(
        campaign=campaign,
        attribute_value=value,
        list=lst,
        owner=user,
    )

    # Clear by posting empty
    client.post(
        reverse(
            "core:campaign-list-attribute-assign",
            args=(campaign.id, lst.id, attr_type.id),
        ),
        {"values": ""},
    )

    assert (
        CampaignListAttributeAssignment.objects.filter(
            list=lst, attribute_value__attribute_type=attr_type
        ).count()
        == 0
    )


@pytest.mark.django_db
def test_campaign_detail_shows_attributes(client, user, campaign, make_list):
    """Test that the campaign detail page shows attribute assignments."""
    client.force_login(user)

    lst = make_list("Test Gang")
    campaign.lists.add(lst)

    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        owner=user,
    )
    value = CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        name="Order",
        colour="#3366FF",
        owner=user,
    )
    CampaignListAttributeAssignment.objects.create(
        campaign=campaign,
        attribute_value=value,
        list=lst,
        owner=user,
    )

    response = client.get(reverse("core:campaign", args=(campaign.id,)))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Attributes" in content
    assert "Faction" in content
    assert "Order" in content
