"""Flatpage discovery and group-based access control."""

import pytest
from django.contrib.auth.models import Group, User
from django.contrib.flatpages.models import FlatPage
from django.test import Client

from gyrinx.pages.access import accessible_flatpages
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

    client = Client()
    response = client.get(flatpage.url)
    assert response.status_code == 200
    assert "Test Page" in response.content.decode()


@pytest.mark.django_db
def test_protected_flatpage_returns_404_for_anonymous_user(protected_flatpage, group):

    visibility = FlatPageVisibility.objects.create(page=protected_flatpage)
    visibility.groups.add(group)

    client = Client()
    response = client.get(protected_flatpage.url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_protected_flatpage_returns_404_for_authenticated_user_without_groups(
    protected_flatpage, group, user
):

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

    visibility = FlatPageVisibility.objects.create(page=protected_flatpage)
    visibility.groups.add(group, another_group)

    client = Client()
    client.login(username="testuser", password="password")
    response = client.get(protected_flatpage.url)
    assert response.status_code == 200
    assert "Protected Page" in response.content.decode()


@pytest.mark.django_db
def test_protected_flatpage_returns_404_for_user_with_wrong_group(
    protected_flatpage, group, another_group, user
):

    visibility = FlatPageVisibility.objects.create(page=protected_flatpage)
    visibility.groups.add(group)

    user.groups.add(another_group)

    client = Client()
    client.login(username="testuser", password="password")
    response = client.get(protected_flatpage.url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_multiple_visibility_rules_for_same_page(
    protected_flatpage, group, another_group, user_with_group
):

    visibility1 = FlatPageVisibility.objects.create(page=protected_flatpage)
    visibility1.groups.add(group)

    visibility2 = FlatPageVisibility.objects.create(page=protected_flatpage)
    visibility2.groups.add(another_group)

    client = Client()
    client.login(username="testuser", password="password")
    response = client.get(protected_flatpage.url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_flatpage_with_trailing_slash_redirect(site, group, user_with_group):

    page = FlatPage.objects.create(
        url="/no-trailing-slash",
        title="No Trailing Slash",
        content="<p>Test content</p>",
    )
    page.sites.add(site)

    visibility = FlatPageVisibility.objects.create(page=page)
    visibility.groups.add(group)

    client = Client()
    client.login(username="testuser", password="password")

    response = client.get("/no-trailing-slash", follow=False)
    # Permit the redirect or access failure according to APPEND_SLASH handling.
    assert response.status_code in [301, 404]


@pytest.mark.django_db
def test_superuser_access_to_protected_pages(protected_flatpage, group):
    """Require group membership even for superusers."""
    visibility = FlatPageVisibility.objects.create(page=protected_flatpage)
    visibility.groups.add(group)

    User.objects.create_superuser(
        username="admin", email="admin@example.com", password="adminpass123"
    )

    client = Client()
    client.login(username="admin", password="adminpass123")
    response = client.get(protected_flatpage.url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_flatpage_visibility_admin_inline(protected_flatpage, group):

    visibility = FlatPageVisibility.objects.create(page=protected_flatpage)
    visibility.groups.add(group)

    assert protected_flatpage.flatpagevisibility_set.count() == 1
    assert visibility.groups.count() == 1
    assert visibility.groups.first() == group


@pytest.mark.django_db
def test_accessible_pages_excludes_an_empty_visibility_rule(
    site, protected_flatpage, user
):
    FlatPageVisibility.objects.create(page=protected_flatpage)

    pages = accessible_flatpages(site_id=site.pk, user=user)

    assert protected_flatpage not in pages


@pytest.mark.django_db
def test_accessible_pages_allows_a_matching_rule_alongside_an_empty_rule(
    site, protected_flatpage, group, user_with_group
):
    FlatPageVisibility.objects.create(page=protected_flatpage)
    matching = FlatPageVisibility.objects.create(page=protected_flatpage)
    matching.groups.add(group)

    pages = accessible_flatpages(site_id=site.pk, user=user_with_group)

    assert protected_flatpage in pages


@pytest.mark.django_db
def test_accessible_pages_can_hide_registration_required_pages(site, flatpage, user):
    flatpage.registration_required = True
    flatpage.save(update_fields=["registration_required"])

    direct_pages = accessible_flatpages(site_id=site.pk, user=None)
    navigation_pages = accessible_flatpages(
        site_id=site.pk, user=None, include_registration_required=False
    )

    assert flatpage in direct_pages
    assert flatpage not in navigation_pages


@pytest.mark.django_db
def test_accessible_pages_are_limited_to_the_current_site(site, flatpage):
    from django.contrib.sites.models import Site

    other_site = Site.objects.create(domain="other.test", name="Other")

    assert flatpage in accessible_flatpages(site_id=site.pk, user=None)
    assert flatpage not in accessible_flatpages(site_id=other_site.pk, user=None)
