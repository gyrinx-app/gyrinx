import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import ContentAttribute, ContentAttributeValue, ContentHouse
from gyrinx.core.models.list import List, ListAttributeAssignment

User = get_user_model()


@pytest.mark.django_db
def test_list_view_shows_attributes(client):
    """Test that attributes are displayed in the list view."""
    # Create a user and list
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    # Create a house (required for list)
    house = ContentHouse.objects.create(name="Test House")

    lst = List.objects.create(
        name="Test Gang",
        owner=user,
        content_house=house,
        public=True,
    )

    # Create an attribute and values
    alignment = ContentAttribute.objects.create(
        name="Alignment",
        is_single_select=True,
    )

    law_abiding = ContentAttributeValue.objects.create(
        attribute=alignment,
        name="Law Abiding",
        description="Follows the rules",
    )

    ContentAttributeValue.objects.create(
        attribute=alignment,
        name="Outlaw",
        description="Breaks the rules",
    )

    # Assign an attribute to the list
    ListAttributeAssignment.objects.create(
        list=lst,
        attribute_value=law_abiding,
    )

    # Visit the list detail page
    response = client.get(reverse("core:list", args=[lst.id]))

    assert response.status_code == 200
    assert "Attributes" in response.content.decode()
    assert "Alignment" in response.content.decode()
    assert "Law Abiding" in response.content.decode()
    assert "Edit" in response.content.decode()


@pytest.mark.django_db
def test_edit_attribute_form(client):
    """Test the attribute edit form."""
    # Create a user and list
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    # Create a house (required for list)
    house = ContentHouse.objects.create(name="Test House")

    lst = List.objects.create(
        name="Test Gang",
        owner=user,
        content_house=house,
        public=True,
    )

    # Create an attribute and values
    alignment = ContentAttribute.objects.create(
        name="Alignment",
        is_single_select=True,
    )

    ContentAttributeValue.objects.create(
        attribute=alignment,
        name="Law Abiding",
        description="Follows the rules",
    )

    outlaw = ContentAttributeValue.objects.create(
        attribute=alignment,
        name="Outlaw",
        description="Breaks the rules",
    )

    # Visit the attribute edit page
    response = client.get(
        reverse("core:list-attribute-edit", args=[lst.id, alignment.id])
    )

    assert response.status_code == 200
    assert "Alignment" in response.content.decode()
    assert "Law Abiding" in response.content.decode()
    assert "Outlaw" in response.content.decode()

    # Submit the form
    response = client.post(
        reverse("core:list-attribute-edit", args=[lst.id, alignment.id]),
        {"values": outlaw.id},
    )

    assert response.status_code == 302  # Redirect

    # Check that the assignment was created
    assert ListAttributeAssignment.objects.filter(
        list=lst, attribute_value=outlaw, archived=False
    ).exists()


@pytest.mark.django_db
def test_multi_select_attribute(client):
    """Test multi-select attributes."""
    # Create a user and list
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    # Create a house (required for list)
    house = ContentHouse.objects.create(name="Test House")

    lst = List.objects.create(
        name="Test Gang",
        owner=user,
        content_house=house,
        public=True,
    )

    # Create a multi-select attribute
    affiliation = ContentAttribute.objects.create(
        name="Affiliation",
        is_single_select=False,
    )

    guild = ContentAttributeValue.objects.create(
        attribute=affiliation,
        name="Guilders",
    )

    merchants = ContentAttributeValue.objects.create(
        attribute=affiliation,
        name="Merchants",
    )

    # Submit the form with multiple values
    response = client.post(
        reverse("core:list-attribute-edit", args=[lst.id, affiliation.id]),
        {"values": [guild.id, merchants.id]},
    )

    assert response.status_code == 302  # Redirect

    # Check that both assignments were created
    assert ListAttributeAssignment.objects.filter(
        list=lst, attribute_value=guild, archived=False
    ).exists()
    assert ListAttributeAssignment.objects.filter(
        list=lst, attribute_value=merchants, archived=False
    ).exists()

    # Check list view shows comma-separated values
    response = client.get(reverse("core:list", args=[lst.id]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Guilders, Merchants" in content or "Merchants, Guilders" in content
