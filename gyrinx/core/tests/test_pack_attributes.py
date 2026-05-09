"""Tests for custom gang attributes in content packs."""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from gyrinx.content.models.attribute import ContentAttribute, ContentAttributeValue
from gyrinx.core.models.pack import CustomContentPackItem


def _add_to_pack(pack, obj):
    ct = ContentType.objects.get_for_model(type(obj))
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=obj.pk, owner=pack.owner
    )


@pytest.fixture
def pack_attribute(pack):
    attr = ContentAttribute.objects.create(name="Alignment", is_single_select=True)
    _add_to_pack(pack, attr)
    return attr


@pytest.fixture
def pack_attribute_value(pack, pack_attribute):
    value = ContentAttributeValue.objects.create(
        attribute=pack_attribute, name="Law Abiding"
    )
    _add_to_pack(pack, value)
    return value


# --- Pack creation UI ---


@pytest.mark.django_db
def test_pack_detail_shows_attributes_section(client, user, pack):
    client.force_login(user)
    response = client.get(reverse("core:pack", args=[pack.id]))
    assert response.status_code == 200
    assert b"Gang Attribute Values" in response.content


@pytest.mark.django_db
def test_pack_detail_shows_attribute_with_value(
    client, user, pack, pack_attribute, pack_attribute_value
):
    client.force_login(user)
    response = client.get(reverse("core:pack", args=[pack.id]))
    assert response.status_code == 200
    assert b"Alignment" in response.content
    assert b"Law Abiding" in response.content


@pytest.mark.django_db
def test_pack_attribute_create_form(client, user, pack):
    client.force_login(user)
    response = client.post(
        reverse("core:pack-add-item", args=(pack.id, "attribute")),
        data={"name": "Alliance", "is_single_select": "on"},
    )
    assert response.status_code in (302, 200)
    assert ContentAttribute.objects.all_content().filter(name="Alliance").exists()


@pytest.mark.django_db
def test_pack_attribute_value_create_form(client, user, pack, pack_attribute):
    client.force_login(user)
    response = client.post(
        reverse("core:pack-add-item", args=(pack.id, "attribute-value")),
        data={"name": "Outlaw", "attribute": str(pack_attribute.id)},
    )
    assert response.status_code in (302, 200)
    assert (
        ContentAttributeValue.objects.all_content()
        .filter(name="Outlaw", attribute=pack_attribute)
        .exists()
    )


@pytest.mark.django_db
def test_pack_attribute_global_uniqueness(client, user, pack):
    """Attribute names are globally unique — cannot create one matching a
    library attribute."""
    ContentAttribute.objects.create(name="Alignment")
    client.force_login(user)
    response = client.post(
        reverse("core:pack-add-item", args=(pack.id, "attribute")),
        data={"name": "alignment"},
    )
    assert response.status_code == 200  # form re-renders with error
    assert b"already exists" in response.content


# --- Archive cascade ---


@pytest.mark.django_db
def test_archiving_attribute_cascades_to_values(
    client, user, pack, pack_attribute, pack_attribute_value
):
    """Archiving a pack-scoped attribute also archives its values."""
    client.force_login(user)
    attr_ct = ContentType.objects.get_for_model(ContentAttribute)
    attr_item = CustomContentPackItem.objects.get(
        pack=pack, content_type=attr_ct, object_id=pack_attribute.pk
    )
    response = client.post(
        reverse("core:pack-delete-item", args=(pack.id, attr_item.id))
    )
    assert response.status_code == 302

    value_ct = ContentType.objects.get_for_model(ContentAttributeValue)
    value_item = CustomContentPackItem.objects.get(
        pack=pack, content_type=value_ct, object_id=pack_attribute_value.pk
    )
    assert value_item.archived
    attr_item.refresh_from_db()
    assert attr_item.archived


@pytest.mark.django_db
def test_restoring_attribute_restores_values(
    client, user, pack, pack_attribute, pack_attribute_value
):
    client.force_login(user)
    attr_ct = ContentType.objects.get_for_model(ContentAttribute)
    attr_item = CustomContentPackItem.objects.get(
        pack=pack, content_type=attr_ct, object_id=pack_attribute.pk
    )
    # Archive first.
    client.post(reverse("core:pack-delete-item", args=(pack.id, attr_item.id)))

    response = client.post(
        reverse("core:pack-restore-item", args=(pack.id, attr_item.id))
    )
    assert response.status_code == 302

    value_ct = ContentType.objects.get_for_model(ContentAttributeValue)
    value_item = CustomContentPackItem.objects.get(
        pack=pack, content_type=value_ct, object_id=pack_attribute_value.pk
    )
    assert not value_item.archived


# --- Subscribed list visibility ---


@pytest.mark.django_db
def test_subscribed_list_sees_pack_attribute(
    user, pack, pack_attribute, pack_attribute_value, make_list
):
    lst = make_list("Sub List")
    lst.packs.add(pack)
    visible = list(
        ContentAttribute.objects.with_packs(lst.packs.all()).filter(name="Alignment")
    )
    assert pack_attribute in visible

    visible_values = list(
        ContentAttributeValue.objects.with_packs(lst.packs.all()).filter(
            attribute=pack_attribute
        )
    )
    assert pack_attribute_value in visible_values


@pytest.mark.django_db
def test_unsubscribed_list_does_not_see_pack_attribute(
    user, pack, pack_attribute, make_list
):
    lst = make_list("Solo List")
    visible = list(
        ContentAttribute.objects.with_packs(lst.packs.all()).filter(name="Alignment")
    )
    assert pack_attribute not in visible


@pytest.mark.django_db
def test_list_attributes_view_includes_pack_attribute(
    client, user, pack, pack_attribute, pack_attribute_value, make_list
):
    """A subscribed list's attribute-edit page lists pack attribute values."""
    client.force_login(user)
    lst = make_list("Sub List")
    lst.packs.add(pack)

    response = client.get(
        reverse("core:list-attribute-edit", args=(lst.id, pack_attribute.id))
    )
    assert response.status_code == 200
    assert b"Law Abiding" in response.content


@pytest.mark.django_db
def test_unsubscribed_list_cannot_edit_pack_attribute(
    client, user, pack, pack_attribute, make_list
):
    client.force_login(user)
    lst = make_list("Solo List")
    response = client.get(
        reverse("core:list-attribute-edit", args=(lst.id, pack_attribute.id))
    )
    assert response.status_code == 404


# --- Multi-pack safety ---


@pytest.mark.django_db
def test_multi_pack_value_visibility(
    user, make_pack, pack_attribute, pack_attribute_value, make_list
):
    """Adding a pack-scoped attribute value to one pack doesn't leak to a
    list subscribed to a different pack."""
    other_pack = make_pack("Other Pack")

    other_lst = make_list("Other Sub")
    other_lst.packs.add(other_pack)

    visible_values = list(
        ContentAttributeValue.objects.with_packs(other_lst.packs.all()).filter(
            attribute=pack_attribute
        )
    )
    assert pack_attribute_value not in visible_values


# --- House restriction ---


@pytest.mark.django_db
def test_pack_attribute_restricted_to_house(
    client, user, pack, content_house, make_list, make_content_house
):
    """A pack-scoped attribute restricted to house A should not appear on a
    list belonging to house B, but should appear on a list in house A."""
    other_house = make_content_house("Other House")
    attr = ContentAttribute.objects.create(name="Alliance", is_single_select=False)
    attr.restricted_to.add(content_house)
    _add_to_pack(pack, attr)

    # List in matching house — should see it.
    matching_list = make_list("Matching")
    matching_list.packs.add(pack)
    matching_attrs = [a["name"] for a in matching_list.all_attributes]
    assert "Alliance" in matching_attrs

    # List in another house — should not see it.
    other_list = make_list("Other House List", content_house=other_house)
    other_list.packs.add(pack)
    other_attrs = [a["name"] for a in other_list.all_attributes]
    assert "Alliance" not in other_attrs
