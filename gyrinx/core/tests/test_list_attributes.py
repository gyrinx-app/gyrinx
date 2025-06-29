import pytest
from django.core.exceptions import ValidationError

from gyrinx.content.models import ContentAttribute, ContentAttributeValue
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.list import List, ListAttributeAssignment


@pytest.mark.django_db
def test_list_attribute_assignment(make_list):
    """Test assigning attributes to a list."""
    list_ = make_list("Test Gang")

    # Create attribute and values
    alignment = ContentAttribute.objects.create(
        name="Alignment",
        is_single_select=True,
    )
    law_abiding = ContentAttributeValue.objects.create(
        attribute=alignment,
        name="Law Abiding",
    )

    # Assign attribute to list
    assignment = ListAttributeAssignment.objects.create(
        list=list_,
        attribute_value=law_abiding,
    )

    assert assignment.list == list_
    assert assignment.attribute_value == law_abiding
    assert str(assignment) == "Test Gang - Alignment: Law Abiding"

    # Check through relationship
    assert list_.attributes.count() == 1
    assert list_.attributes.first() == law_abiding


@pytest.mark.django_db
def test_list_multiple_attributes(make_list):
    """Test assigning multiple attributes to a list."""
    list_ = make_list("Test Gang")

    # Create attributes
    alignment = ContentAttribute.objects.create(
        name="Alignment",
        is_single_select=True,
    )
    affiliations = ContentAttribute.objects.create(
        name="Affiliations",
        is_single_select=False,
    )

    # Create values
    law_abiding = ContentAttributeValue.objects.create(
        attribute=alignment,
        name="Law Abiding",
    )
    guild = ContentAttributeValue.objects.create(
        attribute=affiliations,
        name="Guild",
    )
    noble = ContentAttributeValue.objects.create(
        attribute=affiliations,
        name="Noble House",
    )

    # Assign attributes
    list_.attributes.add(law_abiding, guild, noble)

    assert list_.attributes.count() == 3
    assert law_abiding in list_.attributes.all()
    assert guild in list_.attributes.all()
    assert noble in list_.attributes.all()


@pytest.mark.django_db
def test_single_select_validation(make_list):
    """Test that single-select attributes can only have one value per list."""
    list_ = make_list("Test Gang")

    # Create single-select attribute
    alignment = ContentAttribute.objects.create(
        name="Alignment",
        is_single_select=True,
    )
    law_abiding = ContentAttributeValue.objects.create(
        attribute=alignment,
        name="Law Abiding",
    )
    outlaw = ContentAttributeValue.objects.create(
        attribute=alignment,
        name="Outlaw",
    )

    # Assign first value
    ListAttributeAssignment.objects.create(
        list=list_,
        attribute_value=law_abiding,
    )

    # Try to assign second value from same attribute
    assignment2 = ListAttributeAssignment(
        list=list_,
        attribute_value=outlaw,
    )

    with pytest.raises(ValidationError) as exc_info:
        assignment2.clean()

    assert "single-select" in str(exc_info.value)


@pytest.mark.django_db
def test_multi_select_allows_multiple_values(make_list):
    """Test that multi-select attributes can have multiple values per list."""
    list_ = make_list("Test Gang")

    # Create multi-select attribute
    affiliations = ContentAttribute.objects.create(
        name="Affiliations",
        is_single_select=False,
    )
    guild = ContentAttributeValue.objects.create(
        attribute=affiliations,
        name="Guild",
    )
    noble = ContentAttributeValue.objects.create(
        attribute=affiliations,
        name="Noble House",
    )

    # Assign multiple values - should work fine
    ListAttributeAssignment.objects.create(
        list=list_,
        attribute_value=guild,
    )
    ListAttributeAssignment.objects.create(
        list=list_,
        attribute_value=noble,
    )

    assert list_.attributes.count() == 2


@pytest.mark.django_db
def test_list_clone_with_attributes(make_list):
    """Test that attributes are cloned when a list is cloned."""
    list_ = make_list("Original Gang")

    # Create attributes and values
    alignment = ContentAttribute.objects.create(
        name="Alignment",
        is_single_select=True,
    )
    affiliations = ContentAttribute.objects.create(
        name="Affiliations",
        is_single_select=False,
    )

    law_abiding = ContentAttributeValue.objects.create(
        attribute=alignment,
        name="Law Abiding",
    )
    guild = ContentAttributeValue.objects.create(
        attribute=affiliations,
        name="Guild",
    )
    noble = ContentAttributeValue.objects.create(
        attribute=affiliations,
        name="Noble House",
    )

    # Assign attributes to original list
    list_.attributes.add(law_abiding, guild, noble)

    # Clone the list
    cloned_list = list_.clone(name="Cloned Gang")

    # Check cloned attributes
    assert cloned_list.attributes.count() == 3
    assert law_abiding in cloned_list.attributes.all()
    assert guild in cloned_list.attributes.all()
    assert noble in cloned_list.attributes.all()

    # Ensure they are separate assignments
    assert ListAttributeAssignment.objects.filter(list=list_).count() == 3
    assert ListAttributeAssignment.objects.filter(list=cloned_list).count() == 3
    assert ListAttributeAssignment.objects.count() == 6


@pytest.mark.django_db
def test_campaign_clone_with_attributes(make_list, user):
    """Test that attributes are cloned when creating a campaign list."""
    list_ = make_list("Original Gang")
    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)

    # Create and assign attributes
    alignment = ContentAttribute.objects.create(
        name="Alignment",
        is_single_select=True,
    )
    law_abiding = ContentAttributeValue.objects.create(
        attribute=alignment,
        name="Law Abiding",
    )
    list_.attributes.add(law_abiding)

    # Clone for campaign
    campaign_list = list_.clone(for_campaign=campaign)

    # Check attributes were cloned
    assert campaign_list.attributes.count() == 1
    assert campaign_list.attributes.first() == law_abiding
    assert campaign_list.status == List.CAMPAIGN_MODE
