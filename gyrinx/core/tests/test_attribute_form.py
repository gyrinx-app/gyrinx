"""Tests for ListAttributeForm."""

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from gyrinx.content.models import (
    ContentAttribute,
    ContentAttributeValue,
    ContentHouse,
)
from gyrinx.core.forms.attribute import ListAttributeForm
from gyrinx.core.models.campaign import Campaign, CampaignAction
from gyrinx.core.models.list import List, ListAttributeAssignment

User = get_user_model()


@pytest.fixture
def user():
    """Create a test user."""
    return User.objects.create_user(username="testuser", password="testpass123")


@pytest.fixture
def house():
    """Create a test house."""
    return ContentHouse.objects.create(name="Test House")


@pytest.fixture
def list_obj(user, house):
    """Create a test list."""
    return List.objects.create(
        name="Test List",
        owner=user,
        content_house=house,
    )


@pytest.fixture
def campaign(user):
    """Create a test campaign."""
    return Campaign.objects.create(
        name="Test Campaign",
        owner=user,
    )


@pytest.fixture
def campaign_list(user, house, campaign):
    """Create a test list in campaign mode."""
    list_obj = List.objects.create(
        name="Campaign List",
        owner=user,
        content_house=house,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )
    return list_obj


@pytest.fixture
def single_select_attribute():
    """Create a single-select attribute."""
    return ContentAttribute.objects.create(
        name="Allegiance",
        is_single_select=True,
    )


@pytest.fixture
def multi_select_attribute():
    """Create a multi-select attribute."""
    return ContentAttribute.objects.create(
        name="Traits",
        is_single_select=False,
    )


@pytest.fixture
def single_values(single_select_attribute):
    """Create values for single-select attribute."""
    return [
        ContentAttributeValue.objects.create(
            attribute=single_select_attribute,
            name="Loyalist",
        ),
        ContentAttributeValue.objects.create(
            attribute=single_select_attribute,
            name="Outlaw",
        ),
    ]


@pytest.fixture
def multi_values(multi_select_attribute):
    """Create values for multi-select attribute."""
    return [
        ContentAttributeValue.objects.create(
            attribute=multi_select_attribute,
            name="Fast",
        ),
        ContentAttributeValue.objects.create(
            attribute=multi_select_attribute,
            name="Tough",
        ),
        ContentAttributeValue.objects.create(
            attribute=multi_select_attribute,
            name="Sneaky",
        ),
    ]


@pytest.mark.django_db
def test_single_select_save(list_obj, single_select_attribute, single_values):
    """Test saving a single-select attribute assignment."""
    form = ListAttributeForm(
        data={"values": single_values[0].pk},
        list_obj=list_obj,
        attribute=single_select_attribute,
    )

    assert form.is_valid()
    form.save()

    # Check that assignment was created
    assignments = ListAttributeAssignment.objects.filter(
        list=list_obj,
        attribute_value__attribute=single_select_attribute,
        archived=False,
    )
    assert assignments.count() == 1
    assert assignments.first().attribute_value == single_values[0]


@pytest.mark.django_db
def test_single_select_update(list_obj, single_select_attribute, single_values):
    """Test updating a single-select attribute assignment."""
    # Create initial assignment
    ListAttributeAssignment.objects.create(
        list=list_obj,
        attribute_value=single_values[0],
        archived=False,
    )

    # Update to different value
    form = ListAttributeForm(
        data={"values": single_values[1].pk},
        list_obj=list_obj,
        attribute=single_select_attribute,
    )

    assert form.is_valid()
    form.save()

    # Check that old assignment is archived and new one created
    assignments = ListAttributeAssignment.objects.filter(
        list=list_obj,
        attribute_value__attribute=single_select_attribute,
    )
    assert assignments.count() == 2

    # Old assignment should be archived
    old_assignment = assignments.get(attribute_value=single_values[0])
    assert old_assignment.archived is True

    # New assignment should be active
    new_assignment = assignments.get(attribute_value=single_values[1])
    assert new_assignment.archived is False


@pytest.mark.django_db
def test_multi_select_save(list_obj, multi_select_attribute, multi_values):
    """Test saving multi-select attribute assignments."""
    form = ListAttributeForm(
        data={"values": [multi_values[0].pk, multi_values[2].pk]},
        list_obj=list_obj,
        attribute=multi_select_attribute,
    )

    assert form.is_valid()
    form.save()

    # Check that assignments were created
    assignments = ListAttributeAssignment.objects.filter(
        list=list_obj,
        attribute_value__attribute=multi_select_attribute,
        archived=False,
    )
    assert assignments.count() == 2
    assigned_values = set(assignments.values_list("attribute_value", flat=True))
    assert assigned_values == {multi_values[0].pk, multi_values[2].pk}


@pytest.mark.django_db
def test_campaign_action_single_select(
    campaign_list, single_select_attribute, single_values, user
):
    """Test that campaign action is logged for single-select."""
    request = RequestFactory().get("/")
    request.user = user

    form = ListAttributeForm(
        data={"values": single_values[0].pk},
        list_obj=campaign_list,
        attribute=single_select_attribute,
        request=request,
    )

    assert form.is_valid()
    form.save()

    # Check campaign action was created
    action = CampaignAction.objects.get(
        campaign=campaign_list.campaign,
        list=campaign_list,
    )
    assert action.user == user
    assert (
        f"Updated {single_select_attribute.name}: {single_values[0].name}"
        in action.description
    )


@pytest.mark.django_db
def test_campaign_action_multi_select(
    campaign_list, multi_select_attribute, multi_values, user
):
    """Test that campaign action is logged for multi-select."""
    request = RequestFactory().get("/")
    request.user = user

    form = ListAttributeForm(
        data={"values": [multi_values[0].pk, multi_values[1].pk]},
        list_obj=campaign_list,
        attribute=multi_select_attribute,
        request=request,
    )

    assert form.is_valid()
    form.save()

    # Check campaign action was created
    action = CampaignAction.objects.get(
        campaign=campaign_list.campaign,
        list=campaign_list,
    )
    assert action.user == user
    assert f"Updated {multi_select_attribute.name}:" in action.description
    assert multi_values[0].name in action.description
    assert multi_values[1].name in action.description


@pytest.mark.django_db
def test_campaign_action_clear_values(
    campaign_list, single_select_attribute, single_values, user
):
    """Test campaign action when clearing values."""
    # First set a value
    ListAttributeAssignment.objects.create(
        list=campaign_list,
        attribute_value=single_values[0],
        archived=False,
    )

    request = RequestFactory().get("/")
    request.user = user

    # Clear the value
    form = ListAttributeForm(
        data={"values": ""},  # Empty selection
        list_obj=campaign_list,
        attribute=single_select_attribute,
        request=request,
    )

    assert form.is_valid()
    form.save()

    # Check campaign action was created
    action = CampaignAction.objects.get(
        campaign=campaign_list.campaign,
        list=campaign_list,
    )
    assert f"Updated {single_select_attribute.name}: None" in action.description


@pytest.mark.django_db
def test_archived_list_validation(list_obj, single_select_attribute, single_values):
    """Test that form validation prevents modifying archived lists."""
    list_obj.archived = True
    list_obj.save()

    form = ListAttributeForm(
        data={"values": single_values[0].pk},
        list_obj=list_obj,
        attribute=single_select_attribute,
    )

    assert not form.is_valid()
    assert "Cannot modify attributes for an archived list" in str(form.errors)


@pytest.mark.django_db
def test_reactivate_archived_assignment(
    list_obj, single_select_attribute, single_values
):
    """Test that archived assignments are reactivated when re-selected."""
    # Create an archived assignment
    assignment = ListAttributeAssignment.objects.create(
        list=list_obj,
        attribute_value=single_values[0],
        archived=True,
    )

    # Re-select the same value
    form = ListAttributeForm(
        data={"values": single_values[0].pk},
        list_obj=list_obj,
        attribute=single_select_attribute,
    )

    assert form.is_valid()
    form.save()

    # Check that the assignment was reactivated
    assignment.refresh_from_db()
    assert assignment.archived is False

    # Should not create duplicate
    assert (
        ListAttributeAssignment.objects.filter(
            list=list_obj,
            attribute_value=single_values[0],
        ).count()
        == 1
    )
