import pytest
from django.urls import reverse

from gyrinx.content.models import ContentAttribute, ContentAttributeValue
from gyrinx.core.models.list import ListAttributeAssignment


@pytest.mark.django_db
def test_manage_attributes_page(client, user, make_list):
    """Test that the manage attributes page shows all attributes."""
    client.force_login(user)
    lst = make_list("Test Gang")

    alignment = ContentAttribute.objects.create(name="Alignment", is_single_select=True)
    ContentAttributeValue.objects.create(attribute=alignment, name="Law Abiding")

    alliance = ContentAttribute.objects.create(name="Alliance", is_single_select=True)
    corpse_guild = ContentAttributeValue.objects.create(
        attribute=alliance, name="Corpse Guild"
    )

    # Set one attribute
    ListAttributeAssignment.objects.create(list=lst, attribute_value=corpse_guild)

    response = client.get(reverse("core:list-attributes-manage", args=[lst.id]))
    assert response.status_code == 200
    content = response.content.decode()

    # Both attributes should appear on the manage page
    assert "Alignment" in content
    assert "Alliance" in content
    assert "Corpse Guild" in content
    assert "Not set" in content  # Alignment has no value


@pytest.mark.django_db
def test_manage_attributes_requires_login(client, make_list):
    """Test that the manage attributes page requires login."""
    lst = make_list("Test Gang")
    response = client.get(reverse("core:list-attributes-manage", args=[lst.id]))
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_manage_attributes_requires_owner(client, user, make_user, make_list):
    """Test that only the list owner can access the manage attributes page."""
    lst = make_list("Test Gang")
    other_user = make_user("otheruser", "password")
    client.force_login(other_user)

    response = client.get(reverse("core:list-attributes-manage", args=[lst.id]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_edit_attribute_requires_owner(client, user, make_user, make_list):
    """Test that only the list owner can edit attributes."""
    lst = make_list("Test Gang")
    alignment = ContentAttribute.objects.create(name="Alignment", is_single_select=True)

    other_user = make_user("otheruser", "password")
    client.force_login(other_user)

    response = client.get(
        reverse("core:list-attribute-edit", args=[lst.id, alignment.id])
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_list_view_only_shows_set_attributes(client, user, make_list):
    """Test that the list detail only shows attributes with values set."""
    client.force_login(user)
    lst = make_list("Test Gang")

    alignment = ContentAttribute.objects.create(name="Alignment", is_single_select=True)
    ContentAttributeValue.objects.create(attribute=alignment, name="Law Abiding")

    alliance = ContentAttribute.objects.create(name="Alliance", is_single_select=True)
    corpse_guild = ContentAttributeValue.objects.create(
        attribute=alliance, name="Corpse Guild"
    )

    # Only set Alliance
    ListAttributeAssignment.objects.create(list=lst, attribute_value=corpse_guild)

    response = client.get(reverse("core:list", args=[lst.id]))
    content = response.content.decode()

    # Alliance should be shown (it has a value)
    assert "Alliance" in content
    assert "Corpse Guild" in content

    # Alignment should NOT be shown in the list view (no value set)
    # But "Not set" should not appear since we hide unset attributes
    assert "Not set" not in content

    # Should show "Add Alignment" with a link to edit that attribute
    edit_url = reverse("core:list-attribute-edit", args=[lst.id, alignment.id])
    assert edit_url in content
    assert f">{alignment.name}</a>" in content


@pytest.mark.django_db
def test_list_view_shows_manage_link(client, user, make_list):
    """Test that the list view shows a manage/add link."""
    client.force_login(user)
    lst = make_list("Test Gang")

    ContentAttribute.objects.create(name="Alignment", is_single_select=True)

    response = client.get(reverse("core:list", args=[lst.id]))
    content = response.content.decode()

    # When no attributes are set, should show "Add" preview and "Manage" link
    assert "Add" in content
    assert "Alignment" in content
    assert reverse("core:list-attributes-manage", args=[lst.id]) in content


@pytest.mark.django_db
def test_list_view_shows_or_n_more_for_many_unset_attributes(client, user, make_list):
    """Test that >3 unset attributes shows 'or N more...' after the first 3."""
    client.force_login(user)
    lst = make_list("Test Gang")

    # Alphabetical order: Affiliation, Allegiance, Alignment, Alliance
    for name in ["Affiliation", "Alignment", "Alliance", "Allegiance"]:
        ContentAttribute.objects.create(name=name, is_single_select=True)

    response = client.get(reverse("core:list", args=[lst.id]))
    content = response.content.decode()

    # First 3 alphabetically should be linked
    assert "Affiliation" in content
    assert "Allegiance" in content
    assert "Alignment" in content
    # 4th (Alliance) should be counted in "or N more..."
    assert "or 1 more..." in content


@pytest.mark.django_db
def test_list_view_shows_separator_for_two_unset_attributes(client, user, make_list):
    """Test that exactly 2 unset attributes shows 'or' separator."""
    client.force_login(user)
    lst = make_list("Test Gang")

    ContentAttribute.objects.create(name="Alignment", is_single_select=True)
    ContentAttribute.objects.create(name="Alliance", is_single_select=True)

    response = client.get(reverse("core:list", args=[lst.id]))
    content = response.content.decode()

    assert "Add" in content
    assert "Alignment" in content
    assert "Alliance" in content
    # Should use "or" separator, not comma
    assert "or" in content


@pytest.mark.django_db
def test_edit_attribute_return_url(client, user, make_list):
    """Test that editing from manage page returns to manage page."""
    client.force_login(user)
    lst = make_list("Test Gang")

    alignment = ContentAttribute.objects.create(name="Alignment", is_single_select=True)
    law_abiding = ContentAttributeValue.objects.create(
        attribute=alignment, name="Law Abiding"
    )

    manage_url = reverse("core:list-attributes-manage", args=[lst.id])
    edit_url = reverse("core:list-attribute-edit", args=[lst.id, alignment.id])

    # GET with return_url
    response = client.get(f"{edit_url}?return_url={manage_url}")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Back to attributes" in content

    # POST with return_url should redirect to manage page
    response = client.post(
        f"{edit_url}",
        {"values": law_abiding.id, "return_url": manage_url},
    )
    assert response.status_code == 302
    assert manage_url in response.url


@pytest.mark.django_db
def test_set_and_unset_attributes_properties(make_list):
    """Test the set_attributes and unset_attributes model properties."""
    lst = make_list("Test Gang")

    alignment = ContentAttribute.objects.create(name="Alignment", is_single_select=True)
    ContentAttributeValue.objects.create(attribute=alignment, name="Law Abiding")

    alliance = ContentAttribute.objects.create(name="Alliance", is_single_select=True)
    corpse_guild = ContentAttributeValue.objects.create(
        attribute=alliance, name="Corpse Guild"
    )

    # Set one attribute
    ListAttributeAssignment.objects.create(list=lst, attribute_value=corpse_guild)

    assert len(lst.set_attributes) == 1
    assert lst.set_attributes[0]["name"] == "Alliance"

    assert len(lst.unset_attributes) == 1
    assert lst.unset_attributes[0]["name"] == "Alignment"
