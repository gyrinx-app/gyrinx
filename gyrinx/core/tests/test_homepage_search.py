import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import ContentHouse
from gyrinx.core.models.list import List

User = get_user_model()


@pytest.mark.django_db
def test_homepage_search_with_no_results():
    """Test that homepage shows proper UI when search returns no results."""
    # Create test user
    user = User.objects.create_user(username="testuser", password="password")

    # Create test house
    house = ContentHouse.objects.create(name="Test House")

    # Create some lists
    List.objects.create(
        name="Shadow Runners",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )
    List.objects.create(
        name="Night Stalkers",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    client = Client()
    client.login(username="testuser", password="password")

    # Search for something that doesn't exist
    response = client.get(reverse("core:index"), {"q": "NonExistentGang"})

    assert response.status_code == 200

    # Check context variables
    assert response.context["has_any_lists"] is True  # User has lists
    assert response.context["search_query"] == "NonExistentGang"
    assert len(response.context["lists"]) == 0  # No results

    content = response.content.decode()

    # Check that filter is still shown
    assert 'name="q"' in content  # Search input exists
    assert 'value="NonExistentGang"' in content  # Search query is preserved

    # Check for "nothing matched" message
    assert "No lists matched your search." in content

    # Check onboarding box has updated label
    assert "Create a new list?" in content
    assert "What will you name your first List?" not in content


@pytest.mark.django_db
def test_homepage_search_with_results():
    """Test that homepage shows results when search matches."""
    # Create test user
    user = User.objects.create_user(username="testuser", password="password")

    # Create test house
    house = ContentHouse.objects.create(name="Test House")

    # Create some lists
    shadow_gang = List.objects.create(
        name="Shadow Runners",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )
    List.objects.create(
        name="Night Stalkers",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    client = Client()
    client.login(username="testuser", password="password")

    # Search for something that exists
    response = client.get(reverse("core:index"), {"q": "Shadow"})

    assert response.status_code == 200

    # Check context variables
    assert response.context["has_any_lists"] is True
    assert response.context["search_query"] == "Shadow"
    assert len(response.context["lists"]) == 1
    assert response.context["lists"][0] == shadow_gang

    content = response.content.decode()

    # Check that filter is shown
    assert 'name="q"' in content
    assert 'value="Shadow"' in content

    # Check results are shown
    assert "Shadow Runners" in content
    assert "Night Stalkers" not in content  # This one shouldn't appear

    # Should not show "nothing matched" message
    assert "No lists matched your search." not in content


@pytest.mark.django_db
def test_homepage_search_partial_match():
    """Test that homepage shows results when search partially matches."""
    # Create test user
    user = User.objects.create_user(username="testuser", password="password")

    # Create test house
    house = ContentHouse.objects.create(name="Test House")

    # Create some lists
    shadow_gang = List.objects.create(
        name="Shadow Runners",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )
    List.objects.create(
        name="Night Stalkers",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    client = Client()
    client.login(username="testuser", password="password")

    # Search for something that exists
    response = client.get(reverse("core:index"), {"q": "Shad"})

    assert response.status_code == 200

    # Check context variables
    assert response.context["has_any_lists"] is True
    assert response.context["search_query"] == "Shad"
    assert len(response.context["lists"]) == 1
    assert response.context["lists"][0] == shadow_gang

    content = response.content.decode()

    # Check that filter is shown
    assert 'name="q"' in content
    assert 'value="Shad"' in content

    # Check results are shown
    assert "Shadow Runners" in content
    assert "Night Stalkers" not in content  # This one shouldn't appear

    # Should not show "nothing matched" message
    assert "No lists matched your search." not in content


@pytest.mark.django_db
def test_homepage_no_lists_no_search():
    """Test homepage when user has no lists at all."""
    # Create test user
    User.objects.create_user(username="testuser", password="password")

    client = Client()
    client.login(username="testuser", password="password")

    response = client.get(reverse("core:index"))

    assert response.status_code == 200

    # Check context variables
    assert response.context["has_any_lists"] is False
    assert response.context["search_query"] is None
    assert len(response.context["lists"]) == 0

    content = response.content.decode()

    # Should not show filter when user has no lists
    assert 'id="search-lists"' not in content

    # Should show original onboarding message
    assert "What will you name your first List?" in content
    assert "Create a new list?" not in content
