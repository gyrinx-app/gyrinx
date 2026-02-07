import pytest
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType

from gyrinx.content.models.fighter import ContentFighter
from gyrinx.content.models.house import ContentHouse
from gyrinx.content.models.metadata import ContentRule
from gyrinx.content.models.statline import (
    ContentStatline,
    ContentStatlineStat,
    ContentStatlineType,
    ContentStatlineTypeStat,
    ContentStat,
)
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem


@pytest.fixture
def custom_content_group():
    group, _ = Group.objects.get_or_create(name="Custom Content")
    return group


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


# --- Pack item CRUD (Rules) ---


@pytest.fixture
def pack_rule(pack, group_user):
    """A rule added to a pack."""
    rule = ContentRule.objects.all_content().create(
        name="Test Rule", description="A test rule description"
    )
    ct = ContentType.objects.get_for_model(ContentRule)
    item = CustomContentPackItem(
        pack=pack, content_type=ct, object_id=rule.pk, owner=group_user
    )
    item.save_with_user(user=group_user)
    return item


@pytest.mark.django_db
def test_add_rule_form_loads(client, group_user, pack):
    """Test that the add rule form page loads."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/add/rule/")
    assert response.status_code == 200
    assert b"Add Rule" in response.content


@pytest.mark.django_db
def test_add_rule_creates_rule_and_item(client, group_user, pack):
    """Test that submitting the add rule form creates a rule and pack item."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/rule/",
        {"name": "My Custom Rule", "description": "Rule description"},
    )
    assert response.status_code == 302
    assert response.url == f"/pack/{pack.id}"

    # Verify rule was created
    rule = ContentRule.objects.all_content().get(name="My Custom Rule")
    assert rule.description == "Rule description"

    # Verify pack item was created
    ct = ContentType.objects.get_for_model(ContentRule)
    assert CustomContentPackItem.objects.filter(
        pack=pack, content_type=ct, object_id=rule.pk
    ).exists()


@pytest.mark.django_db
def test_add_rule_requires_name(client, group_user, pack):
    """Test that the name field is required."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/rule/",
        {"name": "", "description": "No name rule"},
    )
    assert response.status_code == 200  # Re-renders form with errors


@pytest.mark.django_db
def test_add_rule_requires_login(client, pack):
    """Test that adding a rule requires login."""
    response = client.get(f"/pack/{pack.id}/add/rule/")
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_add_rule_requires_ownership(client, pack, custom_content_group, make_user):
    """Test that only the pack owner can add rules."""
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    response = client.get(f"/pack/{pack.id}/add/rule/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_add_rule_requires_group(client, pack, make_user):
    """Test that adding a rule requires Custom Content group."""
    non_member = make_user("nonmember", "password")
    client.force_login(non_member)
    response = client.get(f"/pack/{pack.id}/add/rule/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_pack_detail_shows_rules_section(client, group_user, pack):
    """Test that the pack detail page shows the Rules section."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert b"Rules" in response.content


@pytest.mark.django_db
def test_pack_detail_shows_add_rule_button(client, group_user, pack):
    """Test that the pack detail shows an Add button for rules to the owner."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert f"/pack/{pack.id}/add/rule/".encode() in response.content


@pytest.mark.django_db
def test_pack_detail_hides_add_button_for_non_owner(
    client, pack, custom_content_group, make_user
):
    """Test that the Add button is hidden for non-owners."""
    other_user = make_user("viewer", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert f"/pack/{pack.id}/add/rule/".encode() not in response.content


@pytest.mark.django_db
def test_pack_detail_shows_rule_items(client, group_user, pack, pack_rule):
    """Test that rules added to a pack appear in the detail view."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert b"Test Rule" in response.content


@pytest.mark.django_db
def test_edit_rule_form_loads(client, group_user, pack, pack_rule):
    """Test that the edit rule form loads with existing data."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/item/{pack_rule.id}/edit/")
    assert response.status_code == 200
    assert b"Edit Rule" in response.content
    assert b"Test Rule" in response.content


@pytest.mark.django_db
def test_edit_rule_updates_content(client, group_user, pack, pack_rule):
    """Test that submitting the edit form updates the rule."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/item/{pack_rule.id}/edit/",
        {"name": "Updated Rule", "description": "Updated description"},
    )
    assert response.status_code == 302
    assert response.url == f"/pack/{pack.id}"

    rule = ContentRule.objects.all_content().get(pk=pack_rule.object_id)
    assert rule.name == "Updated Rule"
    assert rule.description == "Updated description"


@pytest.mark.django_db
def test_edit_rule_requires_ownership(
    client, pack, pack_rule, custom_content_group, make_user
):
    """Test that only the pack owner can edit rules."""
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    response = client.get(f"/pack/{pack.id}/item/{pack_rule.id}/edit/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_delete_rule_confirmation_loads(client, group_user, pack, pack_rule):
    """Test that the delete confirmation page loads."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/item/{pack_rule.id}/delete/")
    assert response.status_code == 200
    assert b"Archive Rule" in response.content
    assert b"Test Rule" in response.content


@pytest.mark.django_db
def test_delete_rule_archives_item_and_preserves_content(
    client, group_user, pack, pack_rule
):
    """Test that removing a rule archives the pack item and preserves the content object."""
    rule_pk = pack_rule.object_id
    client.force_login(group_user)
    response = client.post(f"/pack/{pack.id}/item/{pack_rule.id}/delete/")
    assert response.status_code == 302
    assert response.url == f"/pack/{pack.id}"

    pack_rule.refresh_from_db()
    assert pack_rule.archived is True
    assert pack_rule.archived_at is not None
    # Content object is preserved
    assert ContentRule.objects.all_content().filter(pk=rule_pk).exists()


@pytest.mark.django_db
def test_delete_rule_requires_ownership(
    client, pack, pack_rule, custom_content_group, make_user
):
    """Test that only the pack owner can delete rules."""
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    response = client.post(f"/pack/{pack.id}/item/{pack_rule.id}/delete/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_add_rule_unsupported_slug_returns_404(client, group_user, pack):
    """Test that an invalid content type slug returns 404."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/add/invalid/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_add_house_slug_returns_404(client, group_user, pack):
    """Test that house slug returns 404 (no form class configured)."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/add/house/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_add_rule_tracks_history(client, group_user, pack):
    """Test that adding a rule creates history records for both item and content."""
    client.force_login(group_user)
    client.post(
        f"/pack/{pack.id}/add/rule/",
        {"name": "History Rule", "description": ""},
    )
    ct = ContentType.objects.get_for_model(ContentRule)
    item = CustomContentPackItem.objects.get(pack=pack, content_type=ct)
    assert item.history.count() == 1
    assert item.history.first().history_user == group_user

    # Content object should also have history with user tracked
    rule = ContentRule.objects.all_content().get(name="History Rule")
    assert rule.history.count() == 1
    assert rule.history.first().history_user == group_user


# --- Archive / Restore ---


@pytest.mark.django_db
def test_archive_tracks_history(client, group_user, pack, pack_rule):
    """Test that archiving a pack item creates a history record."""
    client.force_login(group_user)
    initial_count = pack_rule.history.count()
    client.post(f"/pack/{pack.id}/item/{pack_rule.id}/delete/")

    pack_rule.refresh_from_db()
    assert pack_rule.history.count() == initial_count + 1
    latest = pack_rule.history.first()
    assert latest.history_user == group_user
    assert latest.archived is True


@pytest.mark.django_db
def test_restore_pack_item(client, group_user, pack, pack_rule):
    """Test that restoring an archived pack item unarchives it."""
    client.force_login(group_user)
    # Archive first
    client.post(f"/pack/{pack.id}/item/{pack_rule.id}/delete/")
    pack_rule.refresh_from_db()
    assert pack_rule.archived is True

    # Restore
    response = client.post(f"/pack/{pack.id}/item/{pack_rule.id}/restore/")
    assert response.status_code == 302
    assert response.url == f"/pack/{pack.id}"

    pack_rule.refresh_from_db()
    assert pack_rule.archived is False
    assert pack_rule.archived_at is None


@pytest.mark.django_db
def test_restore_requires_ownership(
    client, pack, pack_rule, custom_content_group, make_user
):
    """Test that only the pack owner can restore items."""
    # Archive first (directly, since we need it archived)
    pack_rule._history_user = pack.owner
    pack_rule.archive()

    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    response = client.post(f"/pack/{pack.id}/item/{pack_rule.id}/restore/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_restore_active_item_returns_404(client, group_user, pack, pack_rule):
    """Test that restoring a non-archived item returns 404."""
    client.force_login(group_user)
    response = client.post(f"/pack/{pack.id}/item/{pack_rule.id}/restore/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_archive_already_archived_returns_404(client, group_user, pack, pack_rule):
    """Test that archiving an already-archived item returns 404."""
    client.force_login(group_user)
    # Archive first
    client.post(f"/pack/{pack.id}/item/{pack_rule.id}/delete/")
    # Try to archive again
    response = client.post(f"/pack/{pack.id}/item/{pack_rule.id}/delete/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_restore_get_returns_404(client, group_user, pack, pack_rule):
    """Test that GET on restore returns 404 (POST only)."""
    pack_rule._history_user = group_user
    pack_rule.archive()

    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/item/{pack_rule.id}/restore/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_pack_detail_hides_archived_from_main_list(client, group_user, pack, pack_rule):
    """Test that archived items don't appear in the main items list."""
    client.force_login(group_user)
    # Archive the rule
    client.post(f"/pack/{pack.id}/item/{pack_rule.id}/delete/")

    response = client.get(f"/pack/{pack.id}")
    content = response.content.decode()
    # The rule name should not appear in the main list (it's in the archived section)
    # Check that the edit link is gone (main list has edit links)
    assert f"/pack/{pack.id}/item/{pack_rule.id}/edit/" not in content


@pytest.mark.django_db
def test_pack_detail_shows_archived_link_to_owner(client, group_user, pack, pack_rule):
    """Test that the archived link appears for the owner when items are archived."""
    client.force_login(group_user)
    # Archive the rule
    client.post(f"/pack/{pack.id}/item/{pack_rule.id}/delete/")

    response = client.get(f"/pack/{pack.id}")
    content = response.content.decode()
    assert "Archived (1)" in content
    assert f"/pack/{pack.id}/archived/rule/" in content


@pytest.mark.django_db
def test_edit_archived_item_returns_404(client, group_user, pack, pack_rule):
    """Test that editing an archived item returns 404."""
    client.force_login(group_user)
    client.post(f"/pack/{pack.id}/item/{pack_rule.id}/delete/")

    response = client.get(f"/pack/{pack.id}/item/{pack_rule.id}/edit/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_add_after_archive_creates_new_item(client, group_user, pack):
    """Test that adding a rule after archiving creates a new item (not unarchive)."""
    client.force_login(group_user)
    # Create a rule
    client.post(
        f"/pack/{pack.id}/add/rule/",
        {"name": "First Rule", "description": "Will be archived"},
    )
    ct = ContentType.objects.get_for_model(ContentRule)
    item = CustomContentPackItem.objects.get(pack=pack, content_type=ct)

    # Archive it
    client.post(f"/pack/{pack.id}/item/{item.id}/delete/")
    item.refresh_from_db()
    assert item.archived is True

    # Adding a new rule creates a separate item (different content object)
    response = client.post(
        f"/pack/{pack.id}/add/rule/",
        {"name": "Second Rule", "description": "A new rule"},
    )
    assert response.status_code == 302
    # Should have 2 items - one archived, one active
    assert CustomContentPackItem.objects.filter(pack=pack, content_type=ct).count() == 2
    assert (
        CustomContentPackItem.objects.filter(
            pack=pack, content_type=ct, archived=False
        ).count()
        == 1
    )


# --- Activity with content edits ---


@pytest.mark.django_db
def test_activity_shows_content_edits(client, group_user, pack, pack_rule):
    """Test that editing a content object appears in the activity feed."""
    client.force_login(group_user)
    # Edit the rule content
    client.post(
        f"/pack/{pack.id}/item/{pack_rule.id}/edit/",
        {"name": "Renamed Rule", "description": "Updated description"},
    )

    response = client.get(f"/pack/{pack.id}/activity/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Edited item" in content
    assert "Renamed Rule" in content


@pytest.mark.django_db
def test_activity_shows_archive_change(client, group_user, pack, pack_rule):
    """Test that archiving a pack item shows 'Archived [item]' in activity."""
    client.force_login(group_user)
    client.post(f"/pack/{pack.id}/item/{pack_rule.id}/delete/")

    response = client.get(f"/pack/{pack.id}/activity/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Archived" in content
    assert "Test Rule (Rule)" in content


@pytest.mark.django_db
def test_archived_items_page_loads(client, group_user, pack, pack_rule):
    """Test that the archived items page loads with archived items."""
    client.force_login(group_user)
    client.post(f"/pack/{pack.id}/item/{pack_rule.id}/delete/")

    response = client.get(f"/pack/{pack.id}/archived/rule/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Archived Rules" in content
    assert "Test Rule" in content
    assert "Restore" in content


@pytest.mark.django_db
def test_archived_items_page_requires_ownership(
    client, pack, pack_rule, custom_content_group, make_user
):
    """Test that only the pack owner can view archived items."""
    pack_rule._history_user = pack.owner
    pack_rule.archive()

    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    response = client.get(f"/pack/{pack.id}/archived/rule/")
    assert response.status_code == 404


# --- Pack item CRUD (Fighters) ---


@pytest.fixture
def fighter_statline_type():
    """Create the Fighter ContentStatlineType with standard stats."""
    statline_type, _ = ContentStatlineType.objects.get_or_create(name="Fighter")

    # (field_name, short_name, full_name, position, is_inches, is_target)
    stat_defs = [
        ("movement", "M", "Movement", 1, True, False),
        ("weapon_skill", "WS", "Weapon Skill", 2, False, True),
        ("ballistic_skill", "BS", "Ballistic Skill", 3, False, True),
        ("strength", "S", "Strength", 4, False, False),
        ("toughness", "T", "Toughness", 5, False, False),
        ("wounds", "W", "Wounds", 6, False, False),
        ("initiative", "I", "Initiative", 7, False, True),
        ("attacks", "A", "Attacks", 8, False, False),
        ("leadership", "Ld", "Leadership", 9, False, True),
        ("cool", "Cl", "Cool", 10, False, True),
        ("willpower", "Wil", "Willpower", 11, False, True),
        ("intelligence", "Int", "Intelligence", 12, False, True),
    ]
    for field_name, short_name, full_name, position, is_inches, is_target in stat_defs:
        stat, _ = ContentStat.objects.get_or_create(
            field_name=field_name,
            defaults={
                "short_name": short_name,
                "full_name": full_name,
                "is_inches": is_inches,
                "is_target": is_target,
            },
        )
        ContentStatlineTypeStat.objects.get_or_create(
            statline_type=statline_type,
            stat=stat,
            defaults={"position": position},
        )
    return statline_type


@pytest.fixture
def pack_fighter(pack, group_user, fighter_statline_type, content_house):
    """A fighter added to a pack with a populated statline."""
    fighter = ContentFighter.objects.all_content().create(
        type="Custom Ganger",
        category="GANGER",
        house=content_house,
        base_cost=50,
    )
    ct = ContentType.objects.get_for_model(ContentFighter)
    item = CustomContentPackItem(
        pack=pack, content_type=ct, object_id=fighter.pk, owner=group_user
    )
    item.save_with_user(user=group_user)

    # Create statline
    statline = ContentStatline.objects.create(
        content_fighter=fighter, statline_type=fighter_statline_type
    )
    for type_stat in fighter_statline_type.stats.all():
        ContentStatlineStat.objects.create(
            statline=statline, statline_type_stat=type_stat, value="-"
        )

    return item


@pytest.mark.django_db
def test_add_fighter_form_loads(client, group_user, pack, fighter_statline_type):
    """Test that the add fighter form page loads with stat inputs."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/add/fighter/")
    assert response.status_code == 200
    assert b"Add Fighter" in response.content
    # Stat inputs should be present
    assert b"stat_movement" in response.content
    assert b"stat_leadership" in response.content


@pytest.mark.django_db
def test_add_fighter_creates_fighter_and_statline(
    client, group_user, pack, fighter_statline_type, content_house
):
    """Test that submitting the add form creates fighter, pack item, and statline."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/fighter/",
        {
            "type": "Test Champion",
            "category": "CHAMPION",
            "house": str(content_house.pk),
            "base_cost": "100",
            "stat_movement": '4"',
            "stat_weapon_skill": "3+",
            "stat_ballistic_skill": "4+",
            "stat_strength": "3",
            "stat_toughness": "3",
            "stat_wounds": "1",
            "stat_initiative": "4+",
            "stat_attacks": "1",
            "stat_leadership": "7+",
            "stat_cool": "7+",
            "stat_willpower": "7+",
            "stat_intelligence": "7+",
        },
    )
    assert response.status_code == 302
    assert response.url == f"/pack/{pack.id}"

    # Verify fighter was created
    fighter = ContentFighter.objects.all_content().get(type="Test Champion")
    assert fighter.category == "CHAMPION"
    assert fighter.base_cost == 100

    # Verify pack item was created
    ct = ContentType.objects.get_for_model(ContentFighter)
    assert CustomContentPackItem.objects.filter(
        pack=pack, content_type=ct, object_id=fighter.pk
    ).exists()

    # Verify statline was created with correct values
    assert hasattr(fighter, "custom_statline")
    stats = {
        s.statline_type_stat.stat.field_name: s.value
        for s in fighter.custom_statline.stats.select_related(
            "statline_type_stat__stat"
        )
    }
    assert stats["movement"] == '4"'
    assert stats["weapon_skill"] == "3+"
    assert stats["leadership"] == "7+"


@pytest.mark.django_db
def test_add_fighter_with_default_stats(
    client, group_user, pack, fighter_statline_type, content_house
):
    """Test that omitted stats default to '-'."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/fighter/",
        {
            "type": "Minimal Fighter",
            "category": "JUVE",
            "house": str(content_house.pk),
            "base_cost": "25",
        },
    )
    assert response.status_code == 302

    fighter = ContentFighter.objects.all_content().get(type="Minimal Fighter")
    assert hasattr(fighter, "custom_statline")
    stats = {
        s.statline_type_stat.stat.field_name: s.value
        for s in fighter.custom_statline.stats.select_related(
            "statline_type_stat__stat"
        )
    }
    assert all(v == "-" for v in stats.values())


@pytest.mark.django_db
def test_add_fighter_with_house(
    client, group_user, pack, fighter_statline_type, content_house
):
    """Test creating a fighter with a house assigned."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/fighter/",
        {
            "type": "House Fighter",
            "category": "GANGER",
            "house": str(content_house.pk),
            "base_cost": "50",
        },
    )
    assert response.status_code == 302

    fighter = ContentFighter.objects.all_content().get(type="House Fighter")
    assert fighter.house == content_house


@pytest.mark.django_db
def test_add_fighter_excludes_special_categories(
    client, group_user, pack, fighter_statline_type
):
    """Test that STASH, VEHICLE, GANG_TERRAIN are not in the category choices."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/add/fighter/")
    content = response.content.decode()
    assert "STASH" not in content
    assert "VEHICLE" not in content
    assert "GANG_TERRAIN" not in content
    # Normal categories should be present
    assert "LEADER" in content
    assert "GANGER" in content


@pytest.mark.django_db
def test_add_fighter_requires_type(
    client, group_user, pack, fighter_statline_type, content_house
):
    """Test that the type (name) field is required."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/fighter/",
        {
            "type": "",
            "category": "GANGER",
            "house": str(content_house.pk),
            "base_cost": "50",
        },
    )
    assert response.status_code == 200  # Re-renders form with errors


@pytest.mark.django_db
def test_edit_fighter_form_loads(client, group_user, pack, pack_fighter):
    """Test that the edit fighter form loads with stat values."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/item/{pack_fighter.id}/edit/")
    assert response.status_code == 200
    assert b"Edit Fighter" in response.content
    # Should have stat inputs
    assert b"stat_movement" in response.content
    # Should have M2M fields on edit
    assert b"skills" in response.content or b"rules" in response.content


@pytest.mark.django_db
def test_edit_fighter_updates_fields(
    client, group_user, pack, pack_fighter, content_house
):
    """Test that editing a fighter updates the fields."""
    client.force_login(group_user)
    fighter = pack_fighter.content_object

    response = client.post(
        f"/pack/{pack.id}/item/{pack_fighter.id}/edit/",
        {
            "type": "Renamed Ganger",
            "category": "CHAMPION",
            "house": str(content_house.pk),
            "base_cost": "75",
            "stat_movement": '5"',
            "stat_weapon_skill": "3+",
            "stat_ballistic_skill": "4+",
            "stat_strength": "3",
            "stat_toughness": "3",
            "stat_wounds": "1",
            "stat_initiative": "4+",
            "stat_attacks": "1",
            "stat_leadership": "7+",
            "stat_cool": "7+",
            "stat_willpower": "7+",
            "stat_intelligence": "7+",
        },
    )
    assert response.status_code == 302

    fighter.refresh_from_db()
    assert fighter.type == "Renamed Ganger"
    assert fighter.category == "CHAMPION"
    assert fighter.base_cost == 75

    # Verify stats were updated
    stats = {
        s.statline_type_stat.stat.field_name: s.value
        for s in fighter.custom_statline.stats.select_related(
            "statline_type_stat__stat"
        )
    }
    assert stats["movement"] == '5"'
    assert stats["weapon_skill"] == "3+"


@pytest.mark.django_db
def test_archive_fighter_preserves_content(client, group_user, pack, pack_fighter):
    """Test that archiving a fighter soft-deletes the pack item but keeps the fighter."""
    client.force_login(group_user)
    fighter = pack_fighter.content_object

    response = client.post(f"/pack/{pack.id}/item/{pack_fighter.id}/delete/")
    assert response.status_code == 302

    pack_fighter.refresh_from_db()
    assert pack_fighter.archived is True

    # Fighter content object should still exist
    assert ContentFighter.objects.all_content().filter(pk=fighter.pk).exists()


@pytest.mark.django_db
def test_pack_detail_shows_fighters_section(
    client, group_user, pack, fighter_statline_type
):
    """Test that the pack detail page shows the Fighters section."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert b"Fighters" in response.content


@pytest.mark.django_db
def test_pack_detail_shows_fighter(client, group_user, pack, pack_fighter):
    """Test that the pack detail page shows the fighter name."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert b"Custom Ganger" in response.content


@pytest.mark.django_db
def test_add_fighter_auto_formats_stats(
    client, group_user, pack, fighter_statline_type, content_house
):
    """Test that stat values are auto-formatted based on ContentStat config."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/fighter/",
        {
            "type": "Format Test Fighter",
            "category": "GANGER",
            "house": str(content_house.pk),
            "base_cost": "50",
            # Movement is_inches: "4" should become '4"'
            "stat_movement": "4",
            # WS is_target: "3" should become "3+"
            "stat_weapon_skill": "3",
            # Strength is plain: "3" stays "3"
            "stat_strength": "3",
            # Already-formatted values should stay as-is
            "stat_ballistic_skill": "4+",
            "stat_toughness": "3",
            "stat_wounds": "1",
            "stat_initiative": "4+",
            "stat_attacks": "1",
            "stat_leadership": "7+",
            "stat_cool": "7+",
            "stat_willpower": "7+",
            "stat_intelligence": "7+",
        },
    )
    assert response.status_code == 302

    fighter = ContentFighter.objects.all_content().get(type="Format Test Fighter")
    stats = {
        s.statline_type_stat.stat.field_name: s.value
        for s in fighter.custom_statline.stats.select_related(
            "statline_type_stat__stat"
        )
    }
    # Auto-formatted
    assert stats["movement"] == '4"'
    assert stats["weapon_skill"] == "3+"
    # Plain stat unchanged
    assert stats["strength"] == "3"
    # Already formatted stays the same
    assert stats["ballistic_skill"] == "4+"
    assert stats["leadership"] == "7+"


@pytest.mark.django_db
def test_edit_fighter_auto_formats_stats(
    client, group_user, pack, pack_fighter, content_house
):
    """Test that editing stats auto-formats values."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/item/{pack_fighter.id}/edit/",
        {
            "type": "Custom Ganger",
            "category": "GANGER",
            "house": str(content_house.pk),
            "base_cost": "50",
            # Submit bare numbers — should be auto-formatted
            "stat_movement": "5",
            "stat_weapon_skill": "4",
            "stat_ballistic_skill": "4",
            "stat_strength": "3",
            "stat_toughness": "3",
            "stat_wounds": "1",
            "stat_initiative": "4",
            "stat_attacks": "1",
            "stat_leadership": "7",
            "stat_cool": "7",
            "stat_willpower": "8",
            "stat_intelligence": "8",
        },
    )
    assert response.status_code == 302

    fighter = pack_fighter.content_object
    fighter.refresh_from_db()
    stats = {
        s.statline_type_stat.stat.field_name: s.value
        for s in fighter.custom_statline.stats.select_related(
            "statline_type_stat__stat"
        )
    }
    assert stats["movement"] == '5"'
    assert stats["weapon_skill"] == "4+"
    assert stats["initiative"] == "4+"
    assert stats["strength"] == "3"  # plain — unchanged
    assert stats["attacks"] == "1"  # plain — unchanged


@pytest.mark.django_db
def test_add_fighter_form_shows_placeholders(
    client, group_user, pack, fighter_statline_type
):
    """Test that the add fighter form shows placeholder hints per stat."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/add/fighter/")
    content = response.content.decode()
    # Movement (is_inches) should have '4"' placeholder
    assert 'placeholder="4&quot;"' in content
    # WS (is_target) should have '3+' placeholder
    assert 'placeholder="3+"' in content
    # Strength (plain) should have '3' placeholder
    assert 'placeholder="3"' in content
