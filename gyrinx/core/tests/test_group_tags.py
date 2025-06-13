import pytest
from django.contrib.auth.models import User, Group, AnonymousUser
from django.template import Context, Template

from gyrinx.core.templatetags.group_tags import in_group


@pytest.mark.django_db
def test_in_group_filter_with_member():
    """Test that in_group returns True when user is in the group."""
    user = User.objects.create_user(username="testuser", password="testpass")
    group = Group.objects.create(name="Campaigns Alpha")
    user.groups.add(group)

    assert in_group(user, "Campaigns Alpha") is True


@pytest.mark.django_db
def test_in_group_filter_with_non_member():
    """Test that in_group returns False when user is not in the group."""
    user = User.objects.create_user(username="testuser", password="testpass")
    Group.objects.create(name="Campaigns Alpha")  # Group exists but user not in it

    assert in_group(user, "Campaigns Alpha") is False


@pytest.mark.django_db
def test_in_group_filter_with_nonexistent_group():
    """Test that in_group returns False when group doesn't exist."""
    user = User.objects.create_user(username="testuser", password="testpass")

    assert in_group(user, "Nonexistent Group") is False


@pytest.mark.django_db
def test_in_group_filter_with_anonymous_user():
    """Test that in_group returns False for anonymous users."""
    anonymous_user = AnonymousUser()
    Group.objects.create(name="Campaigns Alpha")

    assert in_group(anonymous_user, "Campaigns Alpha") is False


@pytest.mark.django_db
def test_in_group_filter_with_none_user():
    """Test that in_group returns False when user is None."""
    Group.objects.create(name="Campaigns Alpha")

    assert in_group(None, "Campaigns Alpha") is False


@pytest.mark.django_db
def test_in_group_filter_in_template():
    """Test that the in_group filter works correctly in templates."""
    user = User.objects.create_user(username="testuser", password="testpass")
    group = Group.objects.create(name="Campaigns Alpha")
    user.groups.add(group)

    template = Template(
        "{% load group_tags %}"
        '{% if user|in_group:"Campaigns Alpha" %}VISIBLE{% else %}HIDDEN{% endif %}'
    )
    context = Context({"user": user})
    result = template.render(context)

    assert result == "VISIBLE"


@pytest.mark.django_db
def test_in_group_filter_in_template_non_member():
    """Test that the in_group filter hides content for non-members in templates."""
    user = User.objects.create_user(username="testuser", password="testpass")
    Group.objects.create(name="Campaigns Alpha")  # Group exists but user not in it

    template = Template(
        "{% load group_tags %}"
        '{% if user|in_group:"Campaigns Alpha" %}VISIBLE{% else %}HIDDEN{% endif %}'
    )
    context = Context({"user": user})
    result = template.render(context)

    assert result == "HIDDEN"


@pytest.mark.django_db
def test_campaigns_link_visible_for_group_members(client):
    """Test that the Campaigns link is visible for group members."""
    user = User.objects.create_user(username="testuser", password="testpass")
    group = Group.objects.create(name="Campaigns Alpha")
    user.groups.add(group)

    client.login(username="testuser", password="testpass")
    response = client.get("/")

    assert response.status_code == 200
    assert b'href="/campaigns/"' in response.content
    assert b">Campaigns</a>" in response.content


@pytest.mark.django_db
def test_campaigns_link_visible_for_all_authenticated_users(client):
    """Test that the Campaigns link is visible for all authenticated users."""
    User.objects.create_user(username="testuser", password="testpass")
    # User exists but not in the Campaigns Alpha group

    client.login(username="testuser", password="testpass")
    response = client.get("/")

    assert response.status_code == 200
    assert b'href="/campaigns/"' in response.content
    assert b">Campaigns</a>" in response.content


@pytest.mark.django_db
def test_campaigns_link_visible_for_anonymous_users(client):
    """Test that the Campaigns link is visible for anonymous users."""
    response = client.get("/")

    assert response.status_code == 200
    assert b">Campaigns</a>" in response.content
