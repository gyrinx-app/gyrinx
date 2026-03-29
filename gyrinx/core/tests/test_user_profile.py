import pytest
from django.urls import reverse

from gyrinx.core.models.list import List


@pytest.mark.django_db
def test_own_profile_separates_public_and_unlisted_lists(client, user, content_house):
    """Test that the owner's profile page separates public and unlisted lists."""
    public_list = List.objects.create(
        name="My Public List",
        owner=user,
        content_house=content_house,
        public=True,
    )
    unlisted_list = List.objects.create(
        name="My Unlisted List",
        owner=user,
        content_house=content_house,
        public=False,
    )

    client.force_login(user)
    url = reverse("core:user", args=[user.username])
    response = client.get(url)
    content = response.content.decode()

    assert response.status_code == 200
    assert public_list.name in content
    assert unlisted_list.name in content
    # The public list should appear in the public section, unlisted in the unlisted section
    assert "Public lists" in content
    assert "Unlisted" in content


@pytest.mark.django_db
def test_own_profile_no_unlisted_section_when_none(client, user, content_house):
    """Test that the unlisted section doesn't appear when there are no unlisted lists."""
    List.objects.create(
        name="My Public List",
        owner=user,
        content_house=content_house,
        public=True,
    )

    client.force_login(user)
    url = reverse("core:user", args=[user.username])
    response = client.get(url)
    content = response.content.decode()

    assert response.status_code == 200
    assert "My Public List" in content
    # The unlisted section heading should not appear
    assert "bi-eye-slash" not in content


@pytest.mark.django_db
def test_other_user_cannot_see_unlisted_lists(client, user, make_user, content_house):
    """Test that other users cannot see unlisted lists on a profile."""
    List.objects.create(
        name="My Public List",
        owner=user,
        content_house=content_house,
        public=True,
    )
    List.objects.create(
        name="My Secret List",
        owner=user,
        content_house=content_house,
        public=False,
    )

    other_user = make_user("otheruser", "password")
    client.force_login(other_user)
    url = reverse("core:user", args=[user.username])
    response = client.get(url)
    content = response.content.decode()

    assert response.status_code == 200
    assert "My Public List" in content
    assert "My Secret List" not in content
    assert "bi-eye-slash" not in content


@pytest.mark.django_db
def test_anonymous_user_cannot_see_unlisted_lists(client, user, content_house):
    """Test that anonymous users cannot see unlisted lists on a profile."""
    List.objects.create(
        name="My Public List",
        owner=user,
        content_house=content_house,
        public=True,
    )
    List.objects.create(
        name="My Secret List",
        owner=user,
        content_house=content_house,
        public=False,
    )

    url = reverse("core:user", args=[user.username])
    response = client.get(url)
    content = response.content.decode()

    assert response.status_code == 200
    assert "My Public List" in content
    assert "My Secret List" not in content
    assert "bi-eye-slash" not in content
