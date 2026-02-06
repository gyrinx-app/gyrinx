import pytest
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType

from gyrinx.content.models.house import ContentHouse
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem


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
    """Test that toggling off 'your packs' shows listed packs."""
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


# --- History tracking ---


@pytest.mark.django_db
def test_pack_create_records_history(client, group_user):
    """Test that creating a pack via view creates a history record with the correct user."""
    client.force_login(group_user)
    response = client.post(
        "/packs/new/",
        {"name": "History Test Pack", "summary": "Testing history", "description": ""},
    )
    assert response.status_code == 302

    pack = CustomContentPack.objects.get(name="History Test Pack")
    history = pack.history.all()

    assert history.count() == 1
    assert history[0].history_type == "+"
    assert history[0].history_user == group_user
    assert history[0].name == "History Test Pack"


@pytest.mark.django_db
def test_pack_edit_records_history(client, group_user, pack):
    """Test that editing a pack via view creates a history record with the correct user."""
    client.force_login(group_user)
    initial_count = pack.history.count()

    response = client.post(
        f"/pack/{pack.id}/edit/",
        {
            "name": "Updated History Pack",
            "summary": "Updated summary",
            "description": "Updated desc",
        },
    )
    assert response.status_code == 302

    pack.refresh_from_db()
    history = pack.history.all()

    assert history.count() == initial_count + 1
    assert history[0].history_type == "~"
    assert history[0].history_user == group_user
    assert history[0].name == "Updated History Pack"


@pytest.mark.django_db
def test_pack_edit_no_change_still_records_history(client, group_user, pack):
    """Test that submitting the edit form without changes still creates a history record."""
    client.force_login(group_user)
    initial_count = pack.history.count()

    response = client.post(
        f"/pack/{pack.id}/edit/",
        {
            "name": pack.name,
            "summary": pack.summary,
            "description": pack.description,
        },
    )
    assert response.status_code == 302

    history = pack.history.all()
    assert history.count() == initial_count + 1
    assert history[0].history_user == group_user


@pytest.mark.django_db
def test_pack_item_history_tracked(group_user):
    """Test that pack item creation records history."""
    pack = CustomContentPack.objects.create(name="Item History Pack", owner=group_user)
    house = ContentHouse.objects.all_content().create(name="History House")
    ct = ContentType.objects.get_for_model(ContentHouse)

    item = CustomContentPackItem(
        pack=pack, content_type=ct, object_id=house.pk, owner=group_user
    )
    item.save_with_user(user=group_user)

    history = item.history.all()
    assert history.count() == 1
    assert history[0].history_type == "+"
    assert history[0].history_user == group_user


# --- Activity views ---


@pytest.mark.django_db
def test_pack_detail_shows_activity_section(client, group_user, pack):
    """Test that the pack detail page includes an activity section."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert b"Activity" in response.content


@pytest.mark.django_db
def test_pack_detail_shows_recent_activity(client, group_user, pack):
    """Test that the pack detail page shows recent history records."""
    client.force_login(group_user)
    # Edit the pack to create an update history record
    client.post(
        f"/pack/{pack.id}/edit/",
        {"name": "Activity Test", "summary": "", "description": ""},
    )
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert b"Updated" in response.content
    assert b"pack" in response.content


@pytest.mark.django_db
def test_pack_activity_page_loads(client, group_user, pack):
    """Test that the pack activity page loads."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/activity/")
    assert response.status_code == 200
    assert b"Activity" in response.content


@pytest.mark.django_db
def test_pack_activity_page_requires_group(client, pack, make_user):
    """Test that the activity page requires group membership."""
    non_member = make_user("nonmember", "password")
    client.force_login(non_member)
    response = client.get(f"/pack/{pack.id}/activity/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_pack_activity_page_respects_visibility(
    client, group_user, custom_content_group, make_user
):
    """Test that the activity page respects pack visibility rules."""
    unlisted = CustomContentPack.objects.create(
        name="Secret Pack", listed=False, owner=group_user
    )
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    response = client.get(f"/pack/{unlisted.id}/activity/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_pack_activity_includes_item_history(client, group_user, pack):
    """Test that the activity page shows both pack and item history records."""
    house = ContentHouse.objects.all_content().create(name="Activity House")
    ct = ContentType.objects.get_for_model(ContentHouse)
    item = CustomContentPackItem(
        pack=pack, content_type=ct, object_id=house.pk, owner=group_user
    )
    item.save_with_user(user=group_user)

    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/activity/")
    assert response.status_code == 200
    content = response.content.decode()
    # Should show pack creation and item addition with resolved name
    assert "Created pack" in content
    assert "Added item" in content
    assert "Activity House (House)" in content


@pytest.mark.django_db
def test_pack_activity_shows_field_changes(client, group_user, pack):
    """Test that update records show which fields changed."""
    client.force_login(group_user)
    # Edit the pack to change name and listed flag
    client.post(
        f"/pack/{pack.id}/edit/",
        {
            "name": "Renamed Pack",
            "summary": pack.summary,
            "description": pack.description,
            "listed": "",  # unchecked = False
        },
    )
    response = client.get(f"/pack/{pack.id}/activity/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Name set to Renamed Pack" in content
    assert "Listed set to no" in content


@pytest.mark.django_db
def test_pack_activity_textfield_changes_say_updated(client, group_user, pack):
    """Test that TextField changes show 'updated' without the value."""
    client.force_login(group_user)
    client.post(
        f"/pack/{pack.id}/edit/",
        {
            "name": pack.name,
            "summary": "Brand new summary",
            "description": pack.description,
        },
    )
    response = client.get(f"/pack/{pack.id}/activity/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Summary updated" in content
    # Should NOT contain the actual text content
    assert "Brand new summary" not in content


@pytest.mark.django_db
def test_pack_activity_shows_view_all_link(client, group_user, pack):
    """Test that the detail page shows a 'View all' link when activity exists."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert f"/pack/{pack.id}/activity/".encode() in response.content
