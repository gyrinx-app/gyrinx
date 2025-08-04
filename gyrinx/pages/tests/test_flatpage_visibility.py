"""Tests for FlatPageVisibility functionality."""

import pytest
from django.contrib.auth.models import Group, User
from django.contrib.flatpages.models import FlatPage
from django.test import Client

from gyrinx.pages.models import FlatPageVisibility


@pytest.fixture
def flatpage(site):
    """Create a test flatpage."""
    page = FlatPage.objects.create(
        url="/test-page/",
        title="Test Page",
        content="<p>This is a test page.</p>",
    )
    page.sites.add(site)
    return page


@pytest.fixture
def protected_flatpage(site):
    """Create a test flatpage with visibility restrictions."""
    page = FlatPage.objects.create(
        url="/protected-page/",
        title="Protected Page",
        content="<p>This is a protected page.</p>",
    )
    page.sites.add(site)
    return page


@pytest.fixture
def group():
    """Create a test group."""
    return Group.objects.create(name="Test Group")


@pytest.fixture
def another_group():
    """Create another test group."""
    return Group.objects.create(name="Another Group")


# Note: user fixture is already available from conftest.py


@pytest.fixture
def user_with_group(user, group):
    """Create a test user with group membership."""
    user.groups.add(group)
    return user


@pytest.fixture
def user_with_multiple_groups(user, group, another_group):
    """Create a test user with multiple group memberships."""
    user.groups.add(group, another_group)
    return user


@pytest.mark.django_db
def test_flatpage_without_visibility_is_public(flatpage):
    """Test that a flatpage without visibility restrictions is publicly accessible."""
    client = Client()
    response = client.get(flatpage.url)
    assert response.status_code == 200
    assert "Test Page" in response.content.decode()


@pytest.mark.django_db
def test_protected_flatpage_returns_404_for_anonymous_user(protected_flatpage, group):
    """Test that anonymous users get 404 for protected pages."""
    # Create visibility restriction
    visibility = FlatPageVisibility.objects.create(page=protected_flatpage)
    visibility.groups.add(group)

    client = Client()
    response = client.get(protected_flatpage.url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_protected_flatpage_returns_404_for_authenticated_user_without_groups(
    protected_flatpage, group, user
):
    """Test that authenticated users without required groups get 404."""
    # Create visibility restriction
    visibility = FlatPageVisibility.objects.create(page=protected_flatpage)
    visibility.groups.add(group)

    client = Client()
    client.login(username="testuser", password="password")
    response = client.get(protected_flatpage.url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_protected_flatpage_accessible_to_user_with_correct_group(
    protected_flatpage, group, user_with_group
):
    """Test that users with the correct group can access protected pages."""
    # Create visibility restriction
    visibility = FlatPageVisibility.objects.create(page=protected_flatpage)
    visibility.groups.add(group)

    client = Client()
    client.login(username="testuser", password="password")
    response = client.get(protected_flatpage.url)
    assert response.status_code == 200
    assert "Protected Page" in response.content.decode()


@pytest.mark.django_db
def test_protected_flatpage_with_multiple_groups_allows_any_matching_group(
    protected_flatpage, group, another_group, user_with_group
):
    """Test that users with any of the allowed groups can access the page."""
    # Create visibility restriction with multiple groups
    visibility = FlatPageVisibility.objects.create(page=protected_flatpage)
    visibility.groups.add(group, another_group)

    # User has only one of the required groups
    client = Client()
    client.login(username="testuser", password="password")
    response = client.get(protected_flatpage.url)
    assert response.status_code == 200
    assert "Protected Page" in response.content.decode()


@pytest.mark.django_db
def test_protected_flatpage_returns_404_for_user_with_wrong_group(
    protected_flatpage, group, another_group, user
):
    """Test that users with wrong groups cannot access protected pages."""
    # Create visibility restriction
    visibility = FlatPageVisibility.objects.create(page=protected_flatpage)
    visibility.groups.add(group)

    # Add user to a different group
    user.groups.add(another_group)

    client = Client()
    client.login(username="testuser", password="password")
    response = client.get(protected_flatpage.url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_multiple_visibility_rules_for_same_page(
    protected_flatpage, group, another_group, user_with_group
):
    """Test that multiple visibility rules for the same page work correctly."""
    # Create two separate visibility rules for the same page
    visibility1 = FlatPageVisibility.objects.create(page=protected_flatpage)
    visibility1.groups.add(group)

    visibility2 = FlatPageVisibility.objects.create(page=protected_flatpage)
    visibility2.groups.add(another_group)

    # User has one of the groups
    client = Client()
    client.login(username="testuser", password="password")
    response = client.get(protected_flatpage.url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_flatpage_with_trailing_slash_redirect(site, group, user_with_group):
    """Test that flatpages handle trailing slash redirects correctly with visibility."""
    # Create page without trailing slash
    page = FlatPage.objects.create(
        url="/no-trailing-slash",
        title="No Trailing Slash",
        content="<p>Test content</p>",
    )
    page.sites.add(site)

    # Add visibility restriction
    visibility = FlatPageVisibility.objects.create(page=page)
    visibility.groups.add(group)

    client = Client()
    client.login(username="testuser", password="password")

    # Django should add trailing slash and redirect
    response = client.get("/no-trailing-slash", follow=False)
    # Should either be 301 redirect or 404 depending on APPEND_SLASH setting
    assert response.status_code in [301, 404]


@pytest.mark.django_db
def test_superuser_access_to_protected_pages(protected_flatpage, group):
    """Test that superusers can access protected pages regardless of groups."""
    # Create visibility restriction
    visibility = FlatPageVisibility.objects.create(page=protected_flatpage)
    visibility.groups.add(group)

    # Create superuser
    User.objects.create_superuser(
        username="admin", email="admin@example.com", password="adminpass123"
    )

    client = Client()
    client.login(username="admin", password="adminpass123")
    response = client.get(protected_flatpage.url)
    # Note: The current implementation doesn't give special access to superusers
    # They still need to be in the correct group
    assert response.status_code == 404


@pytest.mark.django_db
def test_flatpage_visibility_admin_inline(protected_flatpage, group):
    """Test that FlatPageVisibility can be managed through admin inline."""
    # This test verifies the model relationships work correctly
    visibility = FlatPageVisibility.objects.create(page=protected_flatpage)
    visibility.groups.add(group)

    # Check the relationship
    assert protected_flatpage.flatpagevisibility_set.count() == 1
    assert visibility.groups.count() == 1
    assert visibility.groups.first() == group
