import pytest
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import Client

from gyrinx.content.models import ContentHouse
from gyrinx.core.models import List
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem


@pytest.mark.django_db
def test_list_index_view_sql_injection_protection():
    """Test that the list index view properly validates house UUIDs and rejects SQL injection attempts."""
    client = Client()
    User = get_user_model()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.force_login(user)

    # Create a valid house
    house = ContentHouse.objects.create(name="Test House")

    # Create a list with that house
    test_list = List.objects.create(
        name="Test List",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    # Test with valid UUID - should work
    response = client.get("/lists/", {"house": str(house.id)})
    assert response.status_code == 200
    assert test_list in response.context["lists"]

    # Test with SQL injection attempt - should not cause error
    malicious_input = "NULL OR 1=CAST(CONCAT(CHR(73),CHR(56),CHR(111),CHR(78),CHR(58),CHR(71),CHR(54),CHR(108),CHR(50),CHR(116)) AS NUMERIC) /*' || CAST(CAST(CONCAT(CHR(73),CHR(56),CHR(111),CHR(78),CHR(58),CHR(89),CHR(56),CHR(65),CHR(55),CHR(107)) AS NUMERIC) AS TEXT) || '*/"

    response = client.get("/lists/", {"house": malicious_input})
    assert response.status_code == 200
    # The malicious input should be filtered out, so all lists should be shown
    assert test_list in response.context["lists"]

    # Test with multiple house filters including invalid ones
    response = client.get(
        "/lists/", {"house": [str(house.id), malicious_input, "not-a-uuid"]}
    )
    assert response.status_code == 200
    # Only the valid UUID should be used for filtering
    assert test_list in response.context["lists"]


@pytest.mark.django_db
def test_list_index_view_empty_house_filter():
    """Test that empty house filter values are handled correctly."""
    client = Client()
    User = get_user_model()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.force_login(user)

    # Create a house and list
    house = ContentHouse.objects.create(name="Test House")
    test_list = List.objects.create(
        name="Test List",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    # Test with empty string
    response = client.get("/lists/", {"house": ""})
    assert response.status_code == 200
    assert test_list in response.context["lists"]

    # Test with "all"
    response = client.get("/lists/", {"house": "all"})
    assert response.status_code == 200
    assert test_list in response.context["lists"]


@pytest.mark.django_db
def test_pack_house_appears_in_house_filter_dropdown():
    """Pack houses used by lists should appear in the house filter dropdown."""
    client = Client()
    User = get_user_model()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.force_login(user)

    # Create a pack house (house that belongs to a content pack)
    pack_house = ContentHouse.objects.all_content().create(name="Pack House")
    pack = CustomContentPack.objects.create(name="Test Pack", owner=user, listed=True)
    house_ct = ContentType.objects.get_for_model(ContentHouse)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=house_ct,
        object_id=pack_house.pk,
        owner=user,
    )

    # Verify pack house is excluded by default manager
    assert pack_house not in ContentHouse.objects.all()

    # Create a list using the pack house
    test_list = List.objects.create(
        name="Pack List",
        owner=user,
        content_house=pack_house,
        status=List.LIST_BUILDING,
    )
    test_list.packs.add(pack)

    # The pack house should appear in the houses context on the lists page
    response = client.get("/lists/")
    assert response.status_code == 200
    house_ids = [h.id for h in response.context["houses"]]
    assert pack_house.id in house_ids


@pytest.mark.django_db
def test_pack_house_list_filterable_by_house():
    """Lists with pack houses should be filterable via the house filter."""
    client = Client()
    User = get_user_model()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.force_login(user)

    # Create a pack house
    pack_house = ContentHouse.objects.all_content().create(name="Pack House")
    pack = CustomContentPack.objects.create(name="Test Pack", owner=user, listed=True)
    house_ct = ContentType.objects.get_for_model(ContentHouse)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=house_ct,
        object_id=pack_house.pk,
        owner=user,
    )

    # Create a list using the pack house
    test_list = List.objects.create(
        name="Pack List",
        owner=user,
        content_house=pack_house,
        status=List.LIST_BUILDING,
    )
    test_list.packs.add(pack)

    # Filter by the pack house ID - the list should appear
    response = client.get("/lists/", {"house": str(pack_house.id)})
    assert response.status_code == 200
    assert test_list in response.context["lists"]


@pytest.mark.django_db
def test_pack_house_visible_on_public_lists_for_other_users():
    """Pack houses from public lists should be visible to other users."""
    client = Client()
    User = get_user_model()
    owner = User.objects.create_user(username="packowner", password="testpass")
    viewer = User.objects.create_user(username="viewer", password="testpass")

    # Owner creates a pack house and public list
    pack_house = ContentHouse.objects.all_content().create(name="Pack House")
    pack = CustomContentPack.objects.create(name="Test Pack", owner=owner, listed=True)
    house_ct = ContentType.objects.get_for_model(ContentHouse)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=house_ct,
        object_id=pack_house.pk,
        owner=owner,
    )
    test_list = List.objects.create(
        name="Public Pack List",
        owner=owner,
        content_house=pack_house,
        status=List.LIST_BUILDING,
        public=True,
    )
    test_list.packs.add(pack)

    # Viewer should see the pack house in the dropdown when viewing all public lists
    client.force_login(viewer)
    response = client.get("/lists/", {"my": "0"})
    assert response.status_code == 200
    house_ids = [h.id for h in response.context["houses"]]
    assert pack_house.id in house_ids


@pytest.mark.django_db
def test_unused_pack_house_not_in_dropdown():
    """Pack houses not used by any list should not appear in the dropdown."""
    client = Client()
    User = get_user_model()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.force_login(user)

    # Create a pack house but don't assign it to any list
    pack_house = ContentHouse.objects.all_content().create(name="Unused Pack House")
    pack = CustomContentPack.objects.create(name="Test Pack", owner=user, listed=True)
    house_ct = ContentType.objects.get_for_model(ContentHouse)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=house_ct,
        object_id=pack_house.pk,
        owner=user,
    )

    # The unused pack house should NOT appear in the dropdown
    response = client.get("/lists/")
    assert response.status_code == 200
    house_ids = [h.id for h in response.context["houses"]]
    assert pack_house.id not in house_ids
