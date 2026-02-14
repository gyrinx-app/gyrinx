import pytest
from django.test import Client
from django.contrib.auth import get_user_model

from gyrinx.content.models import ContentHouse
from gyrinx.core.models import List


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
