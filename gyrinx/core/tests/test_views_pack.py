import pytest
from django.contrib.auth.models import Group

from gyrinx.core.models.pack import CustomContentPack


@pytest.fixture
def custom_content_group():
    return Group.objects.create(name="Custom Content")


@pytest.fixture
def group_user(user, custom_content_group):
    """A user who is in the Custom Content group."""
    user.groups.add(custom_content_group)
    return user


@pytest.fixture
def pack(group_user):
    return CustomContentPack.objects.create(
        name="Test Pack",
        summary="A test pack",
        description="A detailed test pack description",
        listed=True,
        owner=group_user,
    )


# --- Nav item gating ---


@pytest.mark.django_db
def test_customisation_link_visible_for_group_members(client, group_user):
    """Test that the Customisation link is visible for group members."""
    client.force_login(group_user)
    response = client.get("/")

    assert response.status_code == 200
    assert b'href="/packs/"' in response.content
    assert b">Customisation</a>" in response.content


@pytest.mark.django_db
def test_customisation_link_hidden_for_non_members(client, user):
    """Test that the Customisation link is hidden for non-members."""
    client.force_login(user)
    response = client.get("/")

    assert response.status_code == 200
    assert b'href="/packs/"' not in response.content


@pytest.mark.django_db
def test_customisation_link_hidden_for_anonymous(client):
    """Test that the Customisation link is hidden for anonymous users."""
    response = client.get("/")

    assert response.status_code == 200
    assert b'href="/packs/"' not in response.content


# --- View access gating ---


@pytest.mark.django_db
def test_packs_index_requires_group(client, user):
    """Test that the packs index returns 404 for non-group members."""
    client.force_login(user)
    response = client.get("/packs/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_pack_detail_requires_group(client, pack, make_user):
    """Test that the pack detail returns 404 for non-group members."""
    non_member = make_user("nonmember", "password")
    client.force_login(non_member)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 404


@pytest.mark.django_db
def test_pack_create_requires_group(client, user):
    """Test that creating a pack returns 404 for non-group members."""
    client.force_login(user)
    response = client.get("/packs/new/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_pack_edit_requires_group(client, pack, make_user):
    """Test that editing a pack returns 404 for non-group members."""
    non_member = make_user("nonmember", "password")
    client.force_login(non_member)
    response = client.get(f"/pack/{pack.id}/edit/")
    assert response.status_code == 404


# --- Pack index view ---


@pytest.mark.django_db
def test_packs_index_loads(client, group_user):
    """Test that the packs index page loads."""
    client.force_login(group_user)
    response = client.get("/packs/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_packs_index_shows_own_packs(client, group_user, pack):
    """Test that the index shows the user's own packs by default."""
    client.force_login(group_user)
    response = client.get("/packs/")
    assert response.status_code == 200
    assert b"Test Pack" in response.content


@pytest.mark.django_db
def test_packs_index_hides_other_users_packs(
    client, group_user, custom_content_group, make_user
):
    """Test that the index doesn't show other users' packs by default."""
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    CustomContentPack.objects.create(name="Other Pack", listed=True, owner=other_user)
    client.force_login(group_user)
    response = client.get("/packs/")
    assert response.status_code == 200
    assert b"Other Pack" not in response.content


@pytest.mark.django_db
def test_packs_index_shows_listed_packs_when_my_off(
    client, group_user, custom_content_group, make_user
):
    """Test that toggling off 'my packs' shows listed packs."""
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    CustomContentPack.objects.create(name="Other Pack", listed=True, owner=other_user)
    client.force_login(group_user)
    response = client.get("/packs/?my=0")
    assert response.status_code == 200
    assert b"Other Pack" in response.content


@pytest.mark.django_db
def test_packs_index_search(client, group_user):
    """Test that search filters packs."""
    CustomContentPack.objects.create(name="Alpha Pack", owner=group_user)
    CustomContentPack.objects.create(name="Beta Pack", owner=group_user)
    client.force_login(group_user)
    response = client.get("/packs/?q=Alpha")
    assert response.status_code == 200
    assert b"Alpha Pack" in response.content
    assert b"Beta Pack" not in response.content


# --- Pack detail view ---


@pytest.mark.django_db
def test_pack_detail_loads(client, group_user, pack):
    """Test that the pack detail page loads."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert b"Test Pack" in response.content


@pytest.mark.django_db
def test_pack_detail_shows_edit_for_owner(client, group_user, pack):
    """Test that the edit button shows for the owner."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert b"Edit" in response.content


@pytest.mark.django_db
def test_pack_detail_hides_edit_for_non_owner(
    client, group_user, pack, custom_content_group, make_user
):
    """Test that the edit button is hidden for non-owners."""
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert b"bi-pencil" not in response.content


@pytest.mark.django_db
def test_pack_detail_shows_content_sections(client, group_user, pack):
    """Test that the detail page shows content type sections."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert b"Houses" in response.content


@pytest.mark.django_db
def test_unlisted_pack_visible_to_owner(client, group_user):
    """Test that an unlisted pack is visible to its owner."""
    unlisted = CustomContentPack.objects.create(
        name="Secret Pack", listed=False, owner=group_user
    )
    client.force_login(group_user)
    response = client.get(f"/pack/{unlisted.id}")
    assert response.status_code == 200


@pytest.mark.django_db
def test_unlisted_pack_hidden_from_others(
    client, group_user, custom_content_group, make_user
):
    """Test that an unlisted pack returns 404 for non-owners."""
    unlisted = CustomContentPack.objects.create(
        name="Secret Pack", listed=False, owner=group_user
    )
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    response = client.get(f"/pack/{unlisted.id}")
    assert response.status_code == 404


@pytest.mark.django_db
def test_unlisted_pack_hidden_from_anonymous(client, group_user):
    """Test that an unlisted pack returns 404 for anonymous users."""
    unlisted = CustomContentPack.objects.create(
        name="Secret Pack", listed=False, owner=group_user
    )
    response = client.get(f"/pack/{unlisted.id}")
    assert response.status_code == 404


# --- Pack create view ---


@pytest.mark.django_db
def test_pack_create_requires_login(client):
    """Test that creating a pack requires authentication."""
    response = client.get("/packs/new/")
    assert response.status_code == 302
    assert "/accounts/" in response.url


@pytest.mark.django_db
def test_pack_create_form_loads(client, group_user):
    """Test that the create form loads."""
    client.force_login(group_user)
    response = client.get("/packs/new/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_pack_create_success(client, group_user):
    """Test creating a pack via POST."""
    client.force_login(group_user)
    response = client.post(
        "/packs/new/",
        {"name": "New Pack", "summary": "A summary", "description": "Details"},
    )
    assert response.status_code == 302
    pack = CustomContentPack.objects.get(name="New Pack")
    assert pack.owner == group_user
    assert response.url == f"/pack/{pack.id}"


# --- Pack edit view ---


@pytest.mark.django_db
def test_pack_edit_requires_login(client, pack):
    """Test that editing a pack requires authentication."""
    response = client.get(f"/pack/{pack.id}/edit/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_pack_edit_requires_ownership(client, pack, custom_content_group, make_user):
    """Test that only the owner can edit a pack."""
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    response = client.get(f"/pack/{pack.id}/edit/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_pack_edit_form_loads(client, group_user, pack):
    """Test that the edit form loads for the owner."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/edit/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_pack_edit_success(client, group_user, pack):
    """Test editing a pack via POST."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/edit/",
        {"name": "Updated Pack", "summary": "Updated", "description": "Updated desc"},
    )
    assert response.status_code == 302
    pack.refresh_from_db()
    assert pack.name == "Updated Pack"
