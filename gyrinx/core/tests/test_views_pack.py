import pytest
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from gyrinx.content.models.equipment import ContentEquipment, ContentEquipmentCategory
from gyrinx.content.models.fighter import ContentFighter
from gyrinx.content.models.house import ContentHouse
from gyrinx.content.models.metadata import ContentRule
from gyrinx.content.models.weapon import ContentWeaponTrait
from gyrinx.content.models.statline import (
    ContentStat,
    ContentStatline,
    ContentStatlineStat,
    ContentStatlineType,
    ContentStatlineTypeStat,
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
def test_add_rule_save_and_add_another(client, group_user, pack):
    """Test that 'Save and Add Another' redirects back to the add form."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/rule/",
        {
            "name": "Rule One",
            "description": "First rule",
            "save_and_add_another": "",
        },
    )
    assert response.status_code == 302
    assert response.url == f"/pack/{pack.id}/add/rule/"

    # Verify the rule was still created
    rule = ContentRule.objects.all_content().get(name="Rule One")
    assert rule.description == "First rule"

    # Verify pack item was created
    ct = ContentType.objects.get_for_model(ContentRule)
    assert CustomContentPackItem.objects.filter(
        pack=pack, content_type=ct, object_id=rule.pk
    ).exists()


@pytest.mark.django_db
def test_add_rule_save_and_add_another_shows_message(client, group_user, pack):
    """Test that 'Save and Add Another' displays a success message."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/rule/",
        {
            "name": "Rule With Message",
            "description": "A rule",
            "save_and_add_another": "",
        },
        follow=True,
    )
    assert response.status_code == 200
    messages_list = list(response.context["messages"])
    assert len(messages_list) == 1
    assert "Rule With Message" in str(messages_list[0])
    assert "saved" in str(messages_list[0])


@pytest.mark.django_db
def test_add_rule_normal_submit_redirects_to_pack(client, group_user, pack):
    """Test that normal submit (without save_and_add_another) goes to pack detail."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/rule/",
        {"name": "Normal Rule", "description": "Normal"},
    )
    assert response.status_code == 302
    assert response.url == f"/pack/{pack.id}"


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
def test_add_house_form_loads(client, group_user, pack):
    """Test that the add house form page loads."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/add/house/")
    assert response.status_code == 200
    assert b"Add House" in response.content


@pytest.mark.django_db
def test_add_house_creates_house_and_item(client, group_user, pack):
    """Test that submitting the add house form creates a house and pack item."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/house/",
        {"name": "My Custom House"},
    )
    assert response.status_code == 302
    assert response.url == f"/pack/{pack.id}"

    house = ContentHouse.objects.all_content().get(name="My Custom House")
    ct = ContentType.objects.get_for_model(ContentHouse)
    assert CustomContentPackItem.objects.filter(
        pack=pack, content_type=ct, object_id=house.pk
    ).exists()


@pytest.mark.django_db
def test_add_house_requires_name(client, group_user, pack):
    """Test that the name field is required."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/house/",
        {"name": ""},
    )
    assert response.status_code == 200  # Re-renders form with errors


@pytest.mark.django_db
def test_add_house_requires_login(client, pack):
    """Test that adding a house requires login."""
    response = client.get(f"/pack/{pack.id}/add/house/")
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_add_house_requires_ownership(client, pack, custom_content_group, make_user):
    """Test that only the pack owner can add houses."""
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    response = client.get(f"/pack/{pack.id}/add/house/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_add_house_requires_group(client, pack, make_user):
    """Test that adding a house requires Custom Content group."""
    non_member = make_user("nonmember", "password")
    client.force_login(non_member)
    response = client.get(f"/pack/{pack.id}/add/house/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_pack_detail_shows_add_house_button(client, group_user, pack):
    """Test that the pack detail shows an Add button for houses to the owner."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert f"/pack/{pack.id}/add/house/".encode() in response.content


# --- Pack item CRUD (Houses) - Edit/Delete ---


@pytest.fixture
def pack_house(pack, group_user):
    """A house added to a pack."""
    house = ContentHouse.objects.all_content().create(name="Test House")
    ct = ContentType.objects.get_for_model(ContentHouse)
    item = CustomContentPackItem(
        pack=pack, content_type=ct, object_id=house.pk, owner=group_user
    )
    item.save_with_user(user=group_user)
    return item


@pytest.mark.django_db
def test_pack_detail_shows_house_items(client, group_user, pack, pack_house):
    """Test that houses added to a pack appear in the detail view."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert b"Test House" in response.content


@pytest.mark.django_db
def test_edit_house_form_loads(client, group_user, pack, pack_house):
    """Test that the edit house form loads with existing data."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/item/{pack_house.id}/edit/")
    assert response.status_code == 200
    assert b"Edit House" in response.content
    assert b"Test House" in response.content


@pytest.mark.django_db
def test_edit_house_updates_content(client, group_user, pack, pack_house):
    """Test that submitting the edit form updates the house."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/item/{pack_house.id}/edit/",
        {"name": "Updated House"},
    )
    assert response.status_code == 302
    assert response.url == f"/pack/{pack.id}"

    house = ContentHouse.objects.all_content().get(pk=pack_house.object_id)
    assert house.name == "Updated House"


@pytest.mark.django_db
def test_edit_house_requires_ownership(
    client, pack, pack_house, custom_content_group, make_user
):
    """Test that only the pack owner can edit houses."""
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    response = client.get(f"/pack/{pack.id}/item/{pack_house.id}/edit/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_delete_house_confirmation_loads(client, group_user, pack, pack_house):
    """Test that the delete confirmation page loads."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/item/{pack_house.id}/delete/")
    assert response.status_code == 200
    assert b"Archive House" in response.content
    assert b"Test House" in response.content


@pytest.mark.django_db
def test_delete_house_archives_item_and_preserves_content(
    client, group_user, pack, pack_house
):
    """Test that removing a house archives the pack item and preserves the content."""
    house_pk = pack_house.object_id
    client.force_login(group_user)
    response = client.post(f"/pack/{pack.id}/item/{pack_house.id}/delete/")
    assert response.status_code == 302
    assert response.url == f"/pack/{pack.id}"

    pack_house.refresh_from_db()
    assert pack_house.archived is True
    assert pack_house.archived_at is not None
    assert ContentHouse.objects.all_content().filter(pk=house_pk).exists()


@pytest.mark.django_db
def test_delete_house_requires_ownership(
    client, pack, pack_house, custom_content_group, make_user
):
    """Test that only the pack owner can delete houses."""
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    response = client.post(f"/pack/{pack.id}/item/{pack_house.id}/delete/")
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
def test_activity_shows_weapon_profile_added(client, group_user, pack, pack_weapon):
    """Test that adding a weapon profile shows in the activity feed."""
    from gyrinx.content.models.weapon import ContentWeaponProfile

    equip = pack_weapon.content_object
    profile = ContentWeaponProfile(
        equipment=equip,
        name="Overcharge",
        cost=10,
    )
    profile._history_user = group_user
    profile.save()

    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/activity/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Overcharge profile (Test Autopistol)" in content


@pytest.mark.django_db
def test_activity_shows_weapon_not_equipment(client, group_user, pack, pack_weapon):
    """Test that weapon items show 'Weapon' not 'Equipment' in activity."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/activity/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Test Autopistol (Weapon)" in content
    assert "Test Autopistol (Equipment)" not in content


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
    """Test that the add fighter form page loads (Step 1 — basic info, no stats)."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/add/fighter/")
    assert response.status_code == 200
    assert b"Add Fighter" in response.content
    # Stat inputs should NOT be on Step 1 (they're on Step 2 now)
    assert b"stat_movement" not in response.content


@pytest.mark.django_db
def test_add_fighter_step1_redirects_to_step2(
    client, group_user, pack, fighter_statline_type, content_house
):
    """Test that Step 1 POST redirects to Step 2 with query params."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/fighter/",
        {
            "type": "Test Champion",
            "category": "CHAMPION",
            "house": str(content_house.pk),
            "base_cost": "100",
        },
    )
    assert response.status_code == 302
    assert f"/pack/{pack.id}/add/fighter/stats/" in response.url
    assert "type=Test+Champion" in response.url
    assert "category=CHAMPION" in response.url


@pytest.mark.django_db
def test_add_fighter_step2_shows_stat_inputs(
    client, group_user, pack, fighter_statline_type, content_house
):
    """Test that Step 2 shows stat inputs for the selected category."""
    client.force_login(group_user)
    response = client.get(
        f"/pack/{pack.id}/add/fighter/stats/"
        f"?type=Test+Champion&category=CHAMPION"
        f"&house_id={content_house.pk}&base_cost=100"
    )
    assert response.status_code == 200
    assert b"stat_movement" in response.content
    assert b"stat_leadership" in response.content
    # Should show summary of Step 1 choices
    assert b"Test Champion" in response.content
    assert b"Champion" in response.content


@pytest.mark.django_db
def test_add_fighter_creates_fighter_and_statline(
    client, group_user, pack, fighter_statline_type, content_house
):
    """Test that submitting Step 2 creates fighter, pack item, and statline."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/fighter/stats/"
        f"?type=Test+Champion&category=CHAMPION"
        f"&house_id={content_house.pk}&base_cost=100",
        {
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
        f"/pack/{pack.id}/add/fighter/stats/"
        f"?type=Minimal+Fighter&category=JUVE"
        f"&house_id={content_house.pk}&base_cost=25",
        {},
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
    """Test creating a fighter with a house assigned via two-step flow."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/fighter/stats/"
        f"?type=House+Fighter&category=GANGER"
        f"&house_id={content_house.pk}&base_cost=50",
        {},
    )
    assert response.status_code == 302

    fighter = ContentFighter.objects.all_content().get(type="House Fighter")
    assert fighter.house == content_house


@pytest.mark.django_db
def test_add_fighter_form_shows_rules_field(
    client, group_user, pack, fighter_statline_type, pack_rule
):
    """Test that the rules field appears on the add fighter form."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/add/fighter/")
    content = response.content.decode()
    assert response.status_code == 200
    assert 'name="rules"' in content
    # Pack rule should appear as an option
    assert "Test Rule" in content


@pytest.mark.django_db
def test_add_fighter_with_rules(
    client, group_user, pack, fighter_statline_type, content_house, pack_rule
):
    """Test that creating a fighter with rules assigns them correctly via two-step flow."""
    rule = ContentRule.objects.all_content().get(pk=pack_rule.object_id)
    client.force_login(group_user)

    # Step 1: POST basic info with rules selected.
    response = client.post(
        f"/pack/{pack.id}/add/fighter/",
        {
            "type": "Ruled Fighter",
            "category": "GANGER",
            "house": str(content_house.pk),
            "base_cost": "50",
            "rules": [str(rule.pk)],
        },
    )
    assert response.status_code == 302
    step2_url = response.url
    assert f"rule_ids={rule.pk}" in step2_url

    # Step 2: POST stats.
    response = client.post(step2_url, {})
    assert response.status_code == 302

    fighter = ContentFighter.objects.all_content().get(type="Ruled Fighter")
    all_rules = ContentRule.objects.all_content().filter(contentfighter=fighter)
    assert rule in all_rules


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
        f"/pack/{pack.id}/add/fighter/stats/"
        f"?type=Format+Test+Fighter&category=GANGER"
        f"&house_id={content_house.pk}&base_cost=50",
        {
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
def test_add_fighter_step2_shows_placeholders(
    client, group_user, pack, fighter_statline_type, content_house
):
    """Test that Step 2 shows placeholder hints per stat."""
    client.force_login(group_user)
    response = client.get(
        f"/pack/{pack.id}/add/fighter/stats/"
        f"?type=Placeholder+Test&category=GANGER"
        f"&house_id={content_house.pk}&base_cost=50"
    )
    content = response.content.decode()
    # Movement (is_inches) should have '4"' placeholder
    assert 'placeholder="4&quot;"' in content
    # WS (is_target) should have '3+' placeholder
    assert 'placeholder="3+"' in content
    # Strength (plain) should have '3' placeholder
    assert 'placeholder="3"' in content


@pytest.mark.django_db
def test_edit_fighter_saves_pack_rules(
    client, group_user, pack, pack_fighter, pack_rule, content_house
):
    """Test that pack rules assigned to a fighter persist after editing."""
    fighter = pack_fighter.content_object
    rule = ContentRule.objects.all_content().get(pk=pack_rule.object_id)

    # Assign the pack rule to the fighter.
    fighter.rules.add(rule)
    assert (
        ContentRule.objects.all_content()
        .filter(contentfighter=fighter, pk=rule.pk)
        .exists()
    )

    # Submit the edit form with the rule selected.
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/item/{pack_fighter.id}/edit/",
        {
            "type": "Custom Ganger",
            "category": "GANGER",
            "house": str(content_house.pk),
            "base_cost": "50",
            "rules": [str(rule.pk)],
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

    # Rule should still be assigned after save.
    fighter.refresh_from_db()
    all_rules = ContentRule.objects.all_content().filter(contentfighter=fighter)
    assert rule in all_rules


@pytest.mark.django_db
def test_edit_fighter_form_preselects_pack_rules(
    client, group_user, pack, pack_fighter, pack_rule, content_house
):
    """Test that pack rules are pre-selected when loading the edit form."""
    fighter = pack_fighter.content_object
    rule = ContentRule.objects.all_content().get(pk=pack_rule.object_id)

    # Assign the pack rule to the fighter.
    fighter.rules.add(rule)

    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/item/{pack_fighter.id}/edit/")
    assert response.status_code == 200

    # The rule should appear as a selected value in the form.
    form = response.context["form"]
    rules_value = form["rules"].value()
    assert str(rule.pk) in {str(v) for v in rules_value}


# --- Editor Permissions ---


@pytest.fixture
def editor_user(custom_content_group, make_user):
    """A second user in the Custom Content group to be used as an editor."""
    editor = make_user("editor", "password")
    editor.groups.add(custom_content_group)
    return editor


@pytest.fixture
def pack_with_editor(pack, editor_user, group_user):
    """A pack that has an editor."""
    from gyrinx.core.models.pack import CustomContentPackPermission

    CustomContentPackPermission.objects.create(
        pack=pack, user=editor_user, role="editor", owner=group_user
    )
    return pack


# --- Model: can_edit / can_view ---


@pytest.mark.django_db
def test_can_edit_returns_true_for_owner(pack, group_user):
    """Test that can_edit returns True for the pack owner."""
    assert pack.can_edit(group_user) is True


@pytest.mark.django_db
def test_can_edit_returns_true_for_editor(pack_with_editor, editor_user):
    """Test that can_edit returns True for an editor."""
    assert pack_with_editor.can_edit(editor_user) is True


@pytest.mark.django_db
def test_can_edit_returns_false_for_non_editor(pack, custom_content_group, make_user):
    """Test that can_edit returns False for a non-editor user."""
    other = make_user("other", "password")
    other.groups.add(custom_content_group)
    assert pack.can_edit(other) is False


@pytest.mark.django_db
def test_can_view_returns_true_for_listed_pack(pack, custom_content_group, make_user):
    """Test that can_view returns True for any user on a listed pack."""
    other = make_user("other", "password")
    other.groups.add(custom_content_group)
    assert pack.can_view(other) is True


@pytest.mark.django_db
def test_can_view_returns_true_for_unlisted_pack_owner(group_user):
    """Test that can_view returns True for the owner of an unlisted pack."""
    unlisted = CustomContentPack.objects.create(
        name="Unlisted", listed=False, owner=group_user
    )
    assert unlisted.can_view(group_user) is True


@pytest.mark.django_db
def test_can_view_returns_true_for_unlisted_pack_editor(
    group_user,
    editor_user,
):
    """Test that can_view returns True for an editor of an unlisted pack."""
    from gyrinx.core.models.pack import CustomContentPackPermission

    unlisted = CustomContentPack.objects.create(
        name="Unlisted", listed=False, owner=group_user
    )
    CustomContentPackPermission.objects.create(
        pack=unlisted, user=editor_user, role="editor", owner=group_user
    )
    assert unlisted.can_view(editor_user) is True


@pytest.mark.django_db
def test_can_view_returns_false_for_unlisted_pack_non_editor(
    group_user,
    custom_content_group,
    make_user,
):
    """Test that can_view returns False for a non-editor on an unlisted pack."""
    other = make_user("other", "password")
    other.groups.add(custom_content_group)
    unlisted = CustomContentPack.objects.create(
        name="Unlisted", listed=False, owner=group_user
    )
    assert unlisted.can_view(other) is False


# --- Editor access ---


@pytest.mark.django_db
def test_editor_can_edit_pack(client, pack_with_editor, editor_user):
    """Test that an editor can load the edit pack form."""
    client.force_login(editor_user)
    response = client.get(f"/pack/{pack_with_editor.id}/edit/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_editor_can_save_pack_edit(client, pack_with_editor, editor_user):
    """Test that an editor can save pack edits."""
    client.force_login(editor_user)
    response = client.post(
        f"/pack/{pack_with_editor.id}/edit/",
        {"name": "Editor Updated", "summary": "New summary", "description": ""},
    )
    assert response.status_code == 302
    pack_with_editor.refresh_from_db()
    assert pack_with_editor.name == "Editor Updated"


@pytest.mark.django_db
def test_editor_cannot_change_listed(client, pack_with_editor, editor_user):
    """Test that an editor cannot change the listed status."""
    client.force_login(editor_user)
    # Submit with listed='' (unchecked), but field should be removed for editors
    response = client.post(
        f"/pack/{pack_with_editor.id}/edit/",
        {"name": pack_with_editor.name, "summary": "", "description": "", "listed": ""},
    )
    assert response.status_code == 302
    pack_with_editor.refresh_from_db()
    # Pack was listed=True, should remain True since editor can't change it
    assert pack_with_editor.listed is True


@pytest.mark.django_db
def test_editor_can_add_item(client, pack_with_editor, editor_user):
    """Test that an editor can add items to a pack."""
    client.force_login(editor_user)
    response = client.post(
        f"/pack/{pack_with_editor.id}/add/rule/",
        {"name": "Editor Rule", "description": "Added by editor"},
    )
    assert response.status_code == 302
    assert CustomContentPackItem.objects.filter(pack=pack_with_editor).exists()


@pytest.mark.django_db
def test_editor_can_edit_item(client, pack_with_editor, editor_user, pack_rule):
    """Test that an editor can edit items in a pack."""
    client.force_login(editor_user)
    response = client.post(
        f"/pack/{pack_with_editor.id}/item/{pack_rule.id}/edit/",
        {"name": "Editor Edited Rule", "description": "Edited by editor"},
    )
    assert response.status_code == 302
    rule = ContentRule.objects.all_content().get(pk=pack_rule.object_id)
    assert rule.name == "Editor Edited Rule"


@pytest.mark.django_db
def test_editor_can_delete_item(client, pack_with_editor, editor_user, pack_rule):
    """Test that an editor can archive items in a pack."""
    client.force_login(editor_user)
    response = client.post(f"/pack/{pack_with_editor.id}/item/{pack_rule.id}/delete/")
    assert response.status_code == 302
    pack_rule.refresh_from_db()
    assert pack_rule.archived is True


@pytest.mark.django_db
def test_editor_can_restore_item(client, pack_with_editor, editor_user, pack_rule):
    """Test that an editor can restore archived items."""
    # Archive first
    pack_rule._history_user = pack_with_editor.owner
    pack_rule.archive()

    client.force_login(editor_user)
    response = client.post(f"/pack/{pack_with_editor.id}/item/{pack_rule.id}/restore/")
    assert response.status_code == 302
    pack_rule.refresh_from_db()
    assert pack_rule.archived is False


@pytest.mark.django_db
def test_editor_can_view_archived_items(
    client, pack_with_editor, editor_user, pack_rule
):
    """Test that an editor can view the archived items page."""
    pack_rule._history_user = pack_with_editor.owner
    pack_rule.archive()

    client.force_login(editor_user)
    response = client.get(f"/pack/{pack_with_editor.id}/archived/rule/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_editor_can_see_unlisted_pack(
    client,
    editor_user,
    group_user,
    custom_content_group,
):
    """Test that an editor can view an unlisted pack."""
    from gyrinx.core.models.pack import CustomContentPackPermission

    unlisted = CustomContentPack.objects.create(
        name="Secret Pack", listed=False, owner=group_user
    )
    CustomContentPackPermission.objects.create(
        pack=unlisted, user=editor_user, role="editor", owner=group_user
    )

    client.force_login(editor_user)
    response = client.get(f"/pack/{unlisted.id}")
    assert response.status_code == 200


# --- Editor restrictions ---


@pytest.mark.django_db
def test_editor_cannot_access_permissions_page(
    client,
    pack_with_editor,
    editor_user,
):
    """Test that an editor cannot access the permissions management page."""
    client.force_login(editor_user)
    response = client.get(f"/pack/{pack_with_editor.id}/permissions/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_pack_detail_shows_edit_button_for_editor(
    client,
    pack_with_editor,
    editor_user,
):
    """Test that the edit button is shown for editors on the detail page."""
    client.force_login(editor_user)
    response = client.get(f"/pack/{pack_with_editor.id}")
    assert response.status_code == 200
    assert b"bi-pencil" in response.content


@pytest.mark.django_db
def test_pack_detail_hides_permissions_link_for_editor(
    client,
    pack_with_editor,
    editor_user,
):
    """Test that the permissions link is hidden for editors."""
    client.force_login(editor_user)
    response = client.get(f"/pack/{pack_with_editor.id}")
    assert response.status_code == 200
    assert b"Permissions" not in response.content


@pytest.mark.django_db
def test_pack_detail_shows_permissions_link_for_owner(
    client,
    pack_with_editor,
    group_user,
):
    """Test that the permissions link is shown for the owner."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack_with_editor.id}")
    assert response.status_code == 200
    assert b"Permissions" in response.content


# --- Permissions management page ---


@pytest.mark.django_db
def test_permissions_page_loads_for_owner(client, group_user, pack):
    """Test that the permissions page loads for the pack owner."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/permissions/")
    assert response.status_code == 200
    assert b"Permissions" in response.content


@pytest.mark.django_db
def test_permissions_page_404_for_non_owner(
    client,
    pack,
    custom_content_group,
    make_user,
):
    """Test that the permissions page returns 404 for non-owners."""
    other = make_user("other", "password")
    other.groups.add(custom_content_group)
    client.force_login(other)
    response = client.get(f"/pack/{pack.id}/permissions/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_permissions_add_editor(client, group_user, pack, editor_user):
    """Test adding an editor via the permissions page."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/permissions/",
        {"action": "add", "username": "editor"},
    )
    assert response.status_code == 302
    assert pack.permissions.filter(user=editor_user).exists()


@pytest.mark.django_db
def test_permissions_remove_editor(
    client,
    group_user,
    pack_with_editor,
    editor_user,
):
    """Test removing an editor via the permissions page."""
    perm = pack_with_editor.permissions.get(user=editor_user)
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack_with_editor.id}/permissions/",
        {"action": "remove", "permission_id": str(perm.id)},
    )
    assert response.status_code == 302
    assert not pack_with_editor.permissions.filter(user=editor_user).exists()


@pytest.mark.django_db
def test_permissions_add_nonexistent_user(client, group_user, pack):
    """Test that adding a nonexistent user shows an error."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/permissions/",
        {"action": "add", "username": "doesnotexist"},
    )
    assert response.status_code == 200
    assert b"not found" in response.content


@pytest.mark.django_db
def test_permissions_add_already_editor(
    client,
    group_user,
    pack_with_editor,
    editor_user,
):
    """Test that adding an existing editor shows an error."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack_with_editor.id}/permissions/",
        {"action": "add", "username": "editor"},
    )
    assert response.status_code == 200
    assert b"already an editor" in response.content


@pytest.mark.django_db
def test_permissions_add_owner_as_editor(client, group_user, pack):
    """Test that adding the owner as editor shows an error."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/permissions/",
        {"action": "add", "username": group_user.username},
    )
    assert response.status_code == 200
    assert b"already has full access" in response.content


@pytest.mark.django_db
def test_permissions_add_non_group_user(client, group_user, pack, make_user):
    """Test that adding a user not in the Custom Content group shows an error."""
    make_user("regular", "password")
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/permissions/",
        {"action": "add", "username": "regular"},
    )
    assert response.status_code == 200
    assert b"not in the Custom Content group" in response.content


# --- My Packs index shows editor packs ---


@pytest.mark.django_db
def test_packs_index_shows_editor_packs(
    client,
    pack_with_editor,
    editor_user,
):
    """Test that packs where the user is editor appear in My Packs."""
    client.force_login(editor_user)
    response = client.get("/packs/")
    assert response.status_code == 200
    assert b"Test Pack" in response.content


# --- Gear in packs ---


@pytest.fixture
def equipment_category():
    """A gear category for testing (must be in the gear allow-list)."""
    cat, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Gang Equipment", defaults={"group": "Gear"}
    )
    return cat


@pytest.fixture
def pack_equipment(pack, group_user, equipment_category):
    """An equipment item added to a pack."""
    equip = ContentEquipment.objects.all_content().create(
        name="Test Armour", category=equipment_category, cost="20", rarity="C"
    )
    ct = ContentType.objects.get_for_model(ContentEquipment)
    item = CustomContentPackItem(
        pack=pack, content_type=ct, object_id=equip.pk, owner=group_user
    )
    item.save_with_user(user=group_user)
    return item


@pytest.mark.django_db
def test_add_gear_form_loads(client, group_user, pack, equipment_category):
    """Test that the add gear form page loads."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/add/gear/")
    assert response.status_code == 200
    assert b"Add Gear" in response.content


@pytest.mark.django_db
def test_add_gear_creates_item(client, group_user, pack, equipment_category):
    """Test that submitting the add gear form creates equipment and pack item."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/gear/",
        {
            "name": "Custom Armour",
            "category": str(equipment_category.pk),
            "cost": "25",
            "rarity": "C",
        },
    )
    assert response.status_code == 302
    assert response.url == f"/pack/{pack.id}"

    equip = ContentEquipment.objects.all_content().get(name="Custom Armour")
    assert equip.cost == "25"
    assert equip.rarity == "C"
    assert equip.category == equipment_category

    ct = ContentType.objects.get_for_model(ContentEquipment)
    assert CustomContentPackItem.objects.filter(
        pack=pack, content_type=ct, object_id=equip.pk
    ).exists()


@pytest.mark.django_db
def test_add_gear_requires_name(client, group_user, pack, equipment_category):
    """Test that the name field is required."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/gear/",
        {
            "name": "",
            "category": str(equipment_category.pk),
            "cost": "10",
            "rarity": "C",
        },
    )
    assert response.status_code == 200  # Re-renders form with errors


@pytest.mark.django_db
def test_add_gear_requires_login(client, pack):
    """Test that adding gear requires login."""
    response = client.get(f"/pack/{pack.id}/add/gear/")
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_add_gear_requires_ownership(client, pack, custom_content_group, make_user):
    """Test that only pack editors can add gear."""
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    response = client.get(f"/pack/{pack.id}/add/gear/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_edit_gear_form_loads(client, group_user, pack, pack_equipment):
    """Test that the edit gear form loads with current values."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/item/{pack_equipment.id}/edit/")
    assert response.status_code == 200
    assert b"Test Armour" in response.content


@pytest.mark.django_db
def test_edit_gear_updates_content(
    client, group_user, pack, pack_equipment, equipment_category
):
    """Test that editing gear updates the content object."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/item/{pack_equipment.id}/edit/",
        {
            "name": "Updated Armour",
            "category": str(equipment_category.pk),
            "cost": "30",
            "rarity": "R",
        },
    )
    assert response.status_code == 302

    equip = ContentEquipment.objects.all_content().get(pk=pack_equipment.object_id)
    assert equip.name == "Updated Armour"
    assert equip.cost == "30"
    assert equip.rarity == "R"


@pytest.mark.django_db
def test_edit_gear_without_changing_name(
    client, group_user, pack, pack_equipment, equipment_category
):
    """Editing gear without changing its name should succeed."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/item/{pack_equipment.id}/edit/",
        {
            "name": "Test Armour",
            "category": str(equipment_category.pk),
            "cost": "50",
            "rarity": "R",
        },
    )
    assert response.status_code == 302

    equip = ContentEquipment.objects.all_content().get(pk=pack_equipment.object_id)
    assert equip.name == "Test Armour"
    assert equip.cost == "50"


@pytest.mark.django_db
def test_edit_gear_requires_ownership(
    client, pack, pack_equipment, custom_content_group, make_user
):
    """Test that only pack editors can edit gear."""
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    response = client.get(f"/pack/{pack.id}/item/{pack_equipment.id}/edit/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_delete_gear_confirmation_loads(client, group_user, pack, pack_equipment):
    """Test that the delete confirmation page loads."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/item/{pack_equipment.id}/delete/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_delete_gear_archives_item(client, group_user, pack, pack_equipment):
    """Test that deleting archives the pack item but preserves the content."""
    client.force_login(group_user)
    response = client.post(f"/pack/{pack.id}/item/{pack_equipment.id}/delete/")
    assert response.status_code == 302

    pack_equipment.refresh_from_db()
    assert pack_equipment.archived

    # Content object still exists.
    assert (
        ContentEquipment.objects.all_content()
        .filter(pk=pack_equipment.object_id)
        .exists()
    )


@pytest.mark.django_db
def test_restore_gear(client, group_user, pack, pack_equipment):
    """Test that restoring an archived gear item works."""
    pack_equipment.archive()
    client.force_login(group_user)
    response = client.post(f"/pack/{pack.id}/item/{pack_equipment.id}/restore/")
    assert response.status_code == 302

    pack_equipment.refresh_from_db()
    assert not pack_equipment.archived


@pytest.mark.django_db
def test_pack_detail_shows_gear_section(client, group_user, pack):
    """Test that the pack detail page shows the Gear section."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert b"Gear" in response.content


@pytest.mark.django_db
def test_pack_detail_shows_gear_item(client, group_user, pack, pack_equipment):
    """Test that gear items appear in the pack detail page."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert b"Test Armour" in response.content


@pytest.mark.django_db
def test_pack_detail_shows_add_gear_button(
    client, group_user, pack, equipment_category
):
    """Test that the Add button for gear is shown to editors."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert f"/pack/{pack.id}/add/gear/".encode() in response.content


@pytest.mark.django_db
def test_editor_can_add_gear(client, pack_with_editor, editor_user, equipment_category):
    """Test that an editor can add gear to a pack."""
    client.force_login(editor_user)
    response = client.post(
        f"/pack/{pack_with_editor.id}/add/gear/",
        {
            "name": "Editor Gear",
            "category": str(equipment_category.pk),
            "cost": "15",
            "rarity": "C",
        },
    )
    assert response.status_code == 302
    assert ContentEquipment.objects.all_content().filter(name="Editor Gear").exists()


@pytest.mark.django_db
def test_editor_can_edit_gear(
    client, pack_with_editor, editor_user, pack_equipment, equipment_category
):
    """Test that an editor can edit gear in a pack."""
    client.force_login(editor_user)
    response = client.post(
        f"/pack/{pack_with_editor.id}/item/{pack_equipment.id}/edit/",
        {
            "name": "Editor Updated",
            "category": str(equipment_category.pk),
            "cost": "50",
            "rarity": "I",
        },
    )
    assert response.status_code == 302
    equip = ContentEquipment.objects.all_content().get(pk=pack_equipment.object_id)
    assert equip.name == "Editor Updated"


@pytest.mark.django_db
def test_editor_can_delete_gear(client, pack_with_editor, editor_user, pack_equipment):
    """Test that an editor can archive gear in a pack."""
    client.force_login(editor_user)
    response = client.post(
        f"/pack/{pack_with_editor.id}/item/{pack_equipment.id}/delete/"
    )
    assert response.status_code == 302
    pack_equipment.refresh_from_db()
    assert pack_equipment.archived


@pytest.mark.django_db
def test_gear_excluded_from_base_queryset(pack_equipment):
    """Test that pack gear is excluded from the default queryset."""
    assert not ContentEquipment.objects.filter(pk=pack_equipment.object_id).exists()
    assert (
        ContentEquipment.objects.all_content()
        .filter(pk=pack_equipment.object_id)
        .exists()
    )


@pytest.mark.django_db
def test_gear_visible_via_with_packs(pack, pack_equipment):
    """Test that pack gear is included when using with_packs."""
    qs = ContentEquipment.objects.with_packs([pack])
    assert qs.filter(pk=pack_equipment.object_id).exists()


@pytest.mark.django_db
def test_add_gear_category_grouped(client, group_user, pack):
    """Test that the category dropdown shows only gear categories, grouped."""
    ContentEquipmentCategory.objects.get_or_create(
        name="Pistols", defaults={"group": "Weapons & Ammo"}
    )
    ContentEquipmentCategory.objects.get_or_create(
        name="Armour", defaults={"group": "Gear"}
    )
    ContentEquipmentCategory.objects.get_or_create(
        name="Vehicle Wargear", defaults={"group": "Vehicle & Mount"}
    )
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/add/gear/")
    assert response.status_code == 200
    content = response.content.decode()
    # Gear categories should be present.
    assert "Armour" in content
    assert "Vehicle Wargear" in content
    # Weapon categories should be excluded.
    assert ">Pistols<" not in content
    # Groups should appear as optgroup labels.
    assert "Gear" in content


@pytest.mark.django_db
def test_add_gear_cost_accepts_text(client, group_user, pack, equipment_category):
    """Test that cost accepts non-numeric text values."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/gear/",
        {
            "name": "Variable Cost Gear",
            "category": str(equipment_category.pk),
            "cost": "varies",
            "rarity": "C",
        },
    )
    assert response.status_code == 302
    equip = ContentEquipment.objects.all_content().get(name="Variable Cost Gear")
    assert equip.cost == "varies"


# --- Duplicate name validation (case-insensitive) ---


@pytest.mark.django_db
def test_add_house_rejects_duplicate_name(client, group_user, pack, content_house):
    """Adding a house whose name matches a base library house (case-insensitive) is rejected."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/house/",
        {"name": content_house.name.upper()},
    )
    assert response.status_code == 200
    assert b"already exists in the content library" in response.content


@pytest.mark.django_db
def test_add_fighter_rejects_duplicate_name(
    client, group_user, pack, content_fighter, fighter_statline_type
):
    """Adding a fighter whose type matches a base library fighter (case-insensitive) is rejected."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/fighter/",
        {
            "type": content_fighter.type.upper(),
            "category": content_fighter.category,
            "house": str(content_fighter.house_id),
            "base_cost": "100",
        },
    )
    assert response.status_code == 200
    assert b"already exists in the content library" in response.content


@pytest.mark.django_db
def test_add_rule_rejects_duplicate_name(client, group_user, pack):
    """Adding a rule whose name matches a base library rule (case-insensitive) is rejected."""
    # Create a base library rule.
    rule = ContentRule.objects.create(name="Existing Rule")
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/rule/",
        {"name": "existing rule", "description": ""},
    )
    assert response.status_code == 200
    assert b"already exists in the content library" in response.content
    rule.delete()


@pytest.mark.django_db
def test_add_gear_rejects_duplicate_name(client, group_user, pack, equipment_category):
    """Adding gear whose name matches base library equipment (case-insensitive) is rejected."""
    # Create base library equipment.
    equip = ContentEquipment.objects.create(
        name="Flak Armour", category=equipment_category, cost="20", rarity="C"
    )
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/gear/",
        {
            "name": "flak armour",
            "category": str(equipment_category.pk),
            "cost": "20",
            "rarity": "C",
        },
    )
    assert response.status_code == 200
    assert b"already exists in the content library" in response.content
    equip.delete()


@pytest.mark.django_db
def test_add_gear_allows_unique_name(client, group_user, pack, equipment_category):
    """Adding gear with a name not in the base library succeeds."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/gear/",
        {
            "name": "Totally New Gear",
            "category": str(equipment_category.pk),
            "cost": "15",
            "rarity": "C",
        },
    )
    assert response.status_code == 302
    assert (
        ContentEquipment.objects.all_content().filter(name="Totally New Gear").exists()
    )


# --- Pack gear appears in fighter equipment edit view ---


@pytest.mark.django_db
def test_pack_gear_visible_in_fighter_gear_edit(
    client, user, make_list, make_list_fighter, pack, pack_equipment
):
    """Pack gear appears in the gear edit view when the list subscribes to the pack."""
    lst = make_list("Pack Gear List")
    lst.packs.add(pack)
    fighter = make_list_fighter(lst, "Pack Tester")

    client.force_login(user)
    response = client.get(f"/list/{lst.id}/fighter/{fighter.id}/gear?filter=all")
    assert response.status_code == 200
    assert b"Test Armour" in response.content


@pytest.mark.django_db
def test_pack_gear_can_be_assigned_via_form(
    client, user, make_list, make_list_fighter, pack, pack_equipment
):
    """Pack gear can be assigned to a fighter via the POST form."""
    from gyrinx.core.models.list import ListFighterEquipmentAssignment

    lst = make_list("Assign Pack List")
    lst.packs.add(pack)
    fighter = make_list_fighter(lst, "Assign Tester")

    equipment_id = pack_equipment.object_id
    client.force_login(user)
    response = client.post(
        f"/list/{lst.id}/fighter/{fighter.id}/gear",
        {"content_equipment": str(equipment_id)},
    )
    # Successful assignment redirects
    assert response.status_code == 302, response.content.decode()[:500]

    # Assignment was created
    assert ListFighterEquipmentAssignment.objects.filter(
        list_fighter=fighter, content_equipment_id=equipment_id
    ).exists()


@pytest.mark.django_db
def test_pack_gear_displays_after_assignment(
    client, user, make_list, make_list_fighter, pack, pack_equipment
):
    """Assigned pack gear is visible on the fighter's gear page."""
    from gyrinx.core.models.list import ListFighterEquipmentAssignment

    lst = make_list("Display Pack List")
    lst.packs.add(pack)
    fighter = make_list_fighter(lst, "Display Tester")

    equipment = ContentEquipment.objects.all_content().get(pk=pack_equipment.object_id)
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    client.force_login(user)
    response = client.get(f"/list/{lst.id}/fighter/{fighter.id}/gear")
    assert response.status_code == 200
    assert b"Test Armour" in response.content


@pytest.mark.django_db
def test_pack_gear_displays_on_list_detail(
    client, user, make_list, make_list_fighter, pack, pack_equipment
):
    """Assigned pack gear is visible on the list detail page."""
    from gyrinx.core.models.list import ListFighterEquipmentAssignment

    lst = make_list("List Detail Pack")
    lst.packs.add(pack)
    fighter = make_list_fighter(lst, "Detail Tester")

    equipment = ContentEquipment.objects.all_content().get(pk=pack_equipment.object_id)
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    client.force_login(user)
    response = client.get(f"/list/{lst.id}")
    assert response.status_code == 200
    assert b"Test Armour" in response.content


@pytest.mark.django_db
def test_pack_gear_hidden_without_subscription(
    client, user, make_list, make_list_fighter, pack, pack_equipment
):
    """Pack gear does not appear when the list is not subscribed to the pack."""
    lst = make_list("No Pack List")
    fighter = make_list_fighter(lst, "No Pack Tester")

    client.force_login(user)
    response = client.get(f"/list/{lst.id}/fighter/{fighter.id}/gear?filter=all")
    assert response.status_code == 200
    assert b"Test Armour" not in response.content


# --- Weapons in packs ---


@pytest.fixture
def weapon_category():
    """A weapon category for testing."""
    cat, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Pistols", defaults={"group": "Weapons & Ammo"}
    )
    return cat


@pytest.fixture
def pack_weapon(pack, group_user, weapon_category):
    """A weapon item added to a pack with a standard profile."""
    from gyrinx.content.models.weapon import ContentWeaponProfile

    equip = ContentEquipment.objects.all_content().create(
        name="Test Autopistol",
        category=weapon_category,
        cost="10",
        rarity="C",
    )
    ContentWeaponProfile.objects.create(
        equipment=equip,
        name="",
        cost=0,
        range_short='4"',
        range_long='8"',
        strength="3",
        damage="1",
        ammo="6+",
    )
    ct = ContentType.objects.get_for_model(ContentEquipment)
    item = CustomContentPackItem(
        pack=pack, content_type=ct, object_id=equip.pk, owner=group_user
    )
    item.save_with_user(user=group_user)
    return item


@pytest.mark.django_db
def test_add_weapon_form_loads(client, group_user, pack, weapon_category):
    """Test that the add weapon form page loads."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/add/weapon/")
    assert response.status_code == 200
    assert b"Add Weapon" in response.content
    assert b"Weapon stats" in response.content


@pytest.mark.django_db
def test_add_weapon_creates_item_with_profile(
    client, group_user, pack, weapon_category
):
    """Test that submitting the add weapon form creates equipment and standard profile."""
    from gyrinx.content.models.weapon import ContentWeaponProfile

    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/weapon/",
        {
            "name": "Custom Pistol",
            "category": str(weapon_category.pk),
            "cost": "15",
            "rarity": "C",
            "wp_range_short": '4"',
            "wp_range_long": '8"',
            "wp_accuracy_short": "+1",
            "wp_accuracy_long": "",
            "wp_strength": "3",
            "wp_armour_piercing": "-1",
            "wp_damage": "1",
            "wp_ammo": "6+",
        },
    )
    assert response.status_code == 302
    assert response.url == f"/pack/{pack.id}"

    equip = ContentEquipment.objects.all_content().get(name="Custom Pistol")
    assert equip.is_weapon()

    profile = ContentWeaponProfile.objects.all_content().get(equipment=equip, name="")
    assert profile.range_short == '4"'
    assert profile.strength == "3"
    assert profile.damage == "1"
    assert profile.cost == 0

    ct = ContentType.objects.get_for_model(ContentEquipment)
    assert CustomContentPackItem.objects.filter(
        pack=pack, content_type=ct, object_id=equip.pk
    ).exists()

    # Standard profile also gets a pack item
    profile_ct = ContentType.objects.get_for_model(ContentWeaponProfile)
    assert CustomContentPackItem.objects.filter(
        pack=pack, content_type=profile_ct, object_id=profile.pk
    ).exists()


@pytest.mark.django_db
def test_add_weapon_with_traits(client, group_user, pack, weapon_category):
    """Test that weapon traits are assigned to the standard profile."""
    from gyrinx.content.models.weapon import ContentWeaponProfile, ContentWeaponTrait

    rapid_fire = ContentWeaponTrait.objects.create(name="Rapid Fire (1)")
    knockback = ContentWeaponTrait.objects.create(name="Knockback")

    client.force_login(group_user)
    client.post(
        f"/pack/{pack.id}/add/weapon/",
        {
            "name": "Traited Pistol",
            "category": str(weapon_category.pk),
            "cost": "20",
            "rarity": "C",
            "wp_range_short": '4"',
            "wp_range_long": '8"',
            "wp_strength": "3",
            "wp_damage": "1",
            "wp_ammo": "6+",
            "wp_traits": [str(rapid_fire.pk), str(knockback.pk)],
        },
    )

    equip = ContentEquipment.objects.all_content().get(name="Traited Pistol")
    profile = ContentWeaponProfile.objects.all_content().get(equipment=equip, name="")
    assert set(profile.traits.values_list("name", flat=True)) == {
        "Rapid Fire (1)",
        "Knockback",
    }


@pytest.mark.django_db
def test_edit_weapon_form_loads(client, group_user, pack, pack_weapon):
    """Test that the edit weapon form loads with profile stats."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/item/{pack_weapon.id}/edit/")
    assert response.status_code == 200
    assert b"Edit Weapon" in response.content
    assert b"Weapon stats" in response.content


@pytest.mark.django_db
def test_edit_weapon_updates_profile(client, group_user, pack, pack_weapon):
    """Test that editing a weapon updates the standard profile stats."""
    from gyrinx.content.models.weapon import ContentWeaponProfile

    equip = pack_weapon.content_object
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/item/{pack_weapon.id}/edit/",
        {
            "name": equip.name,
            "category": str(equip.category.pk),
            "cost": "15",
            "rarity": "C",
            "wp_range_short": '6"',
            "wp_range_long": '12"',
            "wp_accuracy_short": "",
            "wp_accuracy_long": "",
            "wp_strength": "4",
            "wp_armour_piercing": "",
            "wp_damage": "2",
            "wp_ammo": "4+",
        },
    )
    assert response.status_code == 302

    profile = ContentWeaponProfile.objects.get(equipment=equip, name="")
    assert profile.range_short == '6"'
    assert profile.strength == "4"
    assert profile.damage == "2"
    assert profile.ammo == "4+"


@pytest.mark.django_db
def test_pack_detail_shows_weapon_section(client, group_user, pack):
    """Test that the pack detail page shows the Weapons section."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert b"Weapons" in response.content


@pytest.mark.django_db
def test_pack_detail_shows_weapon_with_statline(client, group_user, pack, pack_weapon):
    """Test that the pack detail page shows weapon profile statlines."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}")
    assert response.status_code == 200
    assert b"Test Autopistol" in response.content
    # Statline values are shown inline (no "(Standard)" label)
    content = response.content.decode()
    assert '4"' in content  # range_short
    assert "6+" in content  # ammo


@pytest.mark.django_db
def test_add_weapon_profile(client, group_user, pack, pack_weapon):
    """Test adding an additional named profile to a weapon."""
    from gyrinx.content.models.weapon import ContentWeaponProfile

    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/item/{pack_weapon.id}/profile/add/")
    assert response.status_code == 200

    equip = pack_weapon.content_object
    response = client.post(
        f"/pack/{pack.id}/item/{pack_weapon.id}/profile/add/",
        {
            "name": "Overcharge",
            "cost": "10",
            "rarity": "C",
            "wp_range_short": '6"',
            "wp_range_long": '12"',
            "wp_strength": "5",
            "wp_damage": "2",
            "wp_ammo": "4+",
        },
    )
    assert response.status_code == 302

    assert (
        ContentWeaponProfile.objects.all_content()
        .filter(equipment=equip, name="Overcharge")
        .exists()
    )
    profile = ContentWeaponProfile.objects.all_content().get(
        equipment=equip, name="Overcharge"
    )
    assert profile.cost == 10
    assert profile.strength == "5"


@pytest.mark.django_db
def test_edit_weapon_profile(client, group_user, pack, pack_weapon):
    """Test editing a named weapon profile."""
    from gyrinx.content.models.weapon import ContentWeaponProfile

    equip = pack_weapon.content_object
    profile = ContentWeaponProfile.objects.create(
        equipment=equip,
        name="Burst",
        cost=5,
        strength="4",
        damage="1",
    )

    client.force_login(group_user)
    response = client.get(
        f"/pack/{pack.id}/item/{pack_weapon.id}/profile/{profile.id}/edit/"
    )
    assert response.status_code == 200

    response = client.post(
        f"/pack/{pack.id}/item/{pack_weapon.id}/profile/{profile.id}/edit/",
        {
            "name": "Burst",
            "cost": "10",
            "rarity": "C",
            "wp_strength": "5",
            "wp_damage": "2",
        },
    )
    assert response.status_code == 302

    profile.refresh_from_db()
    assert profile.cost == 10
    assert profile.strength == "5"
    assert profile.damage == "2"


@pytest.mark.django_db
def test_edit_weapon_profile_shows_delete_for_named(
    client, group_user, pack, pack_weapon
):
    """Test that the edit page shows a delete link for named profiles."""
    from gyrinx.content.models.weapon import ContentWeaponProfile

    equip = pack_weapon.content_object
    profile = ContentWeaponProfile.objects.create(equipment=equip, name="Burst", cost=5)

    client.force_login(group_user)
    response = client.get(
        f"/pack/{pack.id}/item/{pack_weapon.id}/profile/{profile.id}/edit/"
    )
    assert response.status_code == 200
    assert b"Delete profile" in response.content


@pytest.mark.django_db
def test_edit_weapon_profile_hides_delete_for_standard(
    client, group_user, pack, pack_weapon
):
    """Test that the edit page hides delete for the standard (unnamed) profile."""
    from gyrinx.content.models.weapon import ContentWeaponProfile

    equip = pack_weapon.content_object
    standard = ContentWeaponProfile.objects.get(equipment=equip, name="")

    client.force_login(group_user)
    response = client.get(
        f"/pack/{pack.id}/item/{pack_weapon.id}/profile/{standard.id}/edit/"
    )
    assert response.status_code == 200
    assert b"Delete profile" not in response.content


@pytest.mark.django_db
def test_delete_weapon_profile(client, group_user, pack, pack_weapon):
    """Test deleting a named weapon profile archives its pack item."""
    from gyrinx.content.models.weapon import ContentWeaponProfile

    equip = pack_weapon.content_object
    profile = ContentWeaponProfile.objects.create(
        equipment=equip,
        name="Burst",
        cost=5,
        strength="4",
    )
    # Profile needs a pack item (as created by the add-profile view)
    profile_ct = ContentType.objects.get_for_model(ContentWeaponProfile)
    profile_pack_item = CustomContentPackItem(
        pack=pack,
        content_type=profile_ct,
        object_id=profile.pk,
        owner=group_user,
    )
    profile_pack_item.save_with_user(user=group_user)

    client.force_login(group_user)
    response = client.get(
        f"/pack/{pack.id}/item/{pack_weapon.id}/profile/{profile.id}/delete/"
    )
    assert response.status_code == 200
    assert b"Delete profile" in response.content

    response = client.post(
        f"/pack/{pack.id}/item/{pack_weapon.id}/profile/{profile.id}/delete/"
    )
    assert response.status_code == 302

    # Profile still exists but its pack item is archived
    assert ContentWeaponProfile.objects.all_content().filter(id=profile.id).exists()
    profile_pack_item.refresh_from_db()
    assert profile_pack_item.archived is True


@pytest.mark.django_db
def test_cannot_delete_standard_weapon_profile(client, group_user, pack, pack_weapon):
    """Test that the standard (unnamed) profile cannot be deleted."""
    from gyrinx.content.models.weapon import ContentWeaponProfile

    equip = pack_weapon.content_object
    standard_profile = ContentWeaponProfile.objects.get(equipment=equip, name="")

    client.force_login(group_user)
    # GET should return 404.
    response = client.get(
        f"/pack/{pack.id}/item/{pack_weapon.id}/profile/{standard_profile.id}/delete/"
    )
    assert response.status_code == 404

    # POST should also return 404.
    response = client.post(
        f"/pack/{pack.id}/item/{pack_weapon.id}/profile/{standard_profile.id}/delete/"
    )
    assert response.status_code == 404

    # Standard profile should still exist.
    assert ContentWeaponProfile.objects.filter(id=standard_profile.id).exists()


@pytest.mark.django_db
def test_weapon_category_only_shows_weapons(client, group_user, pack, weapon_category):
    """Test that the weapon form only shows Weapons & Ammo categories."""
    ContentEquipmentCategory.objects.get_or_create(
        name="Armour", defaults={"group": "Gear"}
    )

    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/add/weapon/")
    assert response.status_code == 200
    # Weapon categories should appear.
    assert b"Pistols" in response.content
    # Gear categories should not.
    assert b"Armour" not in response.content


@pytest.mark.django_db
def test_weapon_shows_in_weapon_section_not_gear(
    client, group_user, pack, pack_weapon, pack_equipment
):
    """Test that weapons appear in the Weapons section, not Gear."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}")
    content = response.content.decode()

    # Find the Weapons and Gear sections.
    weapon_section_start = content.find("Weapons")

    # Test Autopistol should be in the page.
    assert "Test Autopistol" in content
    # Test Armour (gear) should also be in the page.
    assert "Test Armour" in content

    # Autopistol should appear after the Weapons heading.
    autopistol_pos = content.find("Test Autopistol")
    assert autopistol_pos > weapon_section_start


# --- PackListsView tests ---


@pytest.mark.django_db
def test_pack_lists_view_renders(client, group_user, pack, content_house, make_list):
    """The pack lists page renders with the user's lists."""
    client.force_login(group_user)
    make_list("Test Gang", content_house=content_house)
    response = client.get(f"/pack/{pack.id}/lists/")
    assert response.status_code == 200
    assert b"Test Gang" in response.content
    content = response.content.decode()
    assert "Lists" in content and "Gangs" in content


@pytest.mark.django_db
def test_pack_lists_view_shows_add_button_for_unsubscribed(
    client, group_user, pack, content_house, make_list
):
    """Unsubscribed lists show an Add button."""
    client.force_login(group_user)
    make_list("Unsubbed Gang", content_house=content_house)
    response = client.get(f"/pack/{pack.id}/lists/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Unsubbed Gang" in content
    assert f"/pack/{pack.id}/subscribe/" in content


@pytest.mark.django_db
def test_pack_lists_view_shows_remove_button_for_subscribed(
    client, group_user, pack, content_house, make_list
):
    """Subscribed lists show a Remove button."""
    client.force_login(group_user)
    lst = make_list("Subbed Gang", content_house=content_house)
    lst.packs.add(pack)
    response = client.get(f"/pack/{pack.id}/lists/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Subbed Gang" in content
    assert f"/pack/{pack.id}/unsubscribe/" in content


@pytest.mark.django_db
def test_pack_lists_view_search_filter(
    client, group_user, pack, content_house, make_list
):
    """Search filters lists by name."""
    client.force_login(group_user)
    make_list("Alpha Squad", content_house=content_house)
    make_list("Beta Team", content_house=content_house)
    response = client.get(f"/pack/{pack.id}/lists/?q=Alpha")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Alpha Squad" in content
    assert "Beta Team" not in content


@pytest.mark.django_db
def test_pack_lists_view_type_filter_list(
    client, group_user, pack, content_house, make_list, campaign
):
    """Type filter shows only list-building lists when type=list."""
    client.force_login(group_user)
    make_list("List Builder", content_house=content_house)
    # Create a campaign-mode list
    from gyrinx.core.models.list import List

    gang = make_list("Campaign Gang", content_house=content_house)
    gang.status = List.CAMPAIGN_MODE
    gang.campaign = campaign
    gang.save()

    response = client.get(f"/pack/{pack.id}/lists/?type=list")
    assert response.status_code == 200
    content = response.content.decode()
    assert "List Builder" in content
    assert "Campaign Gang" not in content


@pytest.mark.django_db
def test_pack_lists_view_type_filter_gang(
    client, group_user, pack, content_house, make_list, campaign
):
    """Type filter shows only campaign gangs when type=gang."""
    client.force_login(group_user)
    make_list("List Builder", content_house=content_house)
    from gyrinx.core.models.list import List

    gang = make_list("Campaign Gang", content_house=content_house)
    gang.status = List.CAMPAIGN_MODE
    gang.campaign = campaign
    gang.save()

    response = client.get(f"/pack/{pack.id}/lists/?type=gang")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Campaign Gang" in content
    assert "List Builder" not in content


@pytest.mark.django_db
def test_pack_lists_view_tabs_present(client, group_user, pack):
    """The page renders tabs for All, List Building, and Campaign."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/lists/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "List Building" in content
    assert "Campaign" in content


@pytest.mark.django_db
def test_pack_lists_view_pagination(client, group_user, pack, content_house, make_list):
    """The page paginates at 10 items."""
    client.force_login(group_user)
    for i in range(12):
        make_list(f"Gang {i:02d}", content_house=content_house)
    response = client.get(f"/pack/{pack.id}/lists/")
    assert response.status_code == 200
    content = response.content.decode()
    # Should show pagination
    assert "Next" in content
    # Page 2 should work
    response2 = client.get(f"/pack/{pack.id}/lists/?page=2")
    assert response2.status_code == 200


@pytest.mark.django_db
def test_pack_lists_view_excludes_other_users(
    client, group_user, pack, content_house, make_list, make_user
):
    """Only shows the current user's lists, not other users'."""
    client.force_login(group_user)
    make_list("My Gang", content_house=content_house)

    other_user = make_user("other", "password")
    from gyrinx.core.models.list import List

    List.objects.create(
        name="Other Gang",
        content_house=content_house,
        owner=other_user,
    )

    response = client.get(f"/pack/{pack.id}/lists/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "My Gang" in content
    assert "Other Gang" not in content


@pytest.mark.django_db
def test_pack_lists_view_requires_login(client, pack):
    """Anonymous users are redirected to login."""
    response = client.get(f"/pack/{pack.id}/lists/")
    assert response.status_code in (302, 404)


@pytest.mark.django_db
def test_pack_lists_view_hides_toggles(client, group_user, pack):
    """The 'Your Lists Only' and 'Archived Only' toggles should not appear."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/lists/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Your Lists Only" not in content
    assert "Archived Only" not in content
    assert "Subscribed Only" in content


@pytest.mark.django_db
def test_pack_lists_view_subscribed_filter(
    client, group_user, pack, content_house, make_list
):
    """Subscribed filter shows only lists subscribed to this pack."""
    client.force_login(group_user)
    subscribed = make_list("Subscribed Gang", content_house=content_house)
    subscribed.packs.add(pack)
    make_list("Unsubscribed Gang", content_house=content_house)

    response = client.get(f"/pack/{pack.id}/lists/?subscribed=1")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Subscribed Gang" in content
    assert "Unsubscribed Gang" not in content


# --- Custom weapon traits ---


@pytest.mark.django_db
def test_add_weapon_trait_form_loads(client, group_user, pack):
    """Test that the add weapon trait form loads."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/add/weapon-trait/")
    assert response.status_code == 200
    assert b"Add Weapon Trait" in response.content


@pytest.mark.django_db
def test_add_weapon_trait_creates_item(client, group_user, pack):
    """Test that adding a weapon trait creates a pack item."""
    from gyrinx.content.models.weapon import ContentWeaponTrait

    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/weapon-trait/",
        {"name": "Plasma", "description": "Superheated projectile."},
    )
    assert response.status_code == 302

    trait = ContentWeaponTrait.objects.all_content().get(name="Plasma")
    assert trait.description == "Superheated projectile."
    assert CustomContentPackItem.objects.filter(pack=pack, object_id=trait.pk).exists()


@pytest.mark.django_db
def test_add_weapon_trait_rejects_duplicate_base_name(client, group_user, pack):
    """Test that a pack trait cannot duplicate a base library trait name."""
    from gyrinx.content.models.weapon import ContentWeaponTrait

    ContentWeaponTrait.objects.create(name="Knockback")

    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/weapon-trait/",
        {"name": "Knockback", "description": ""},
    )
    assert response.status_code == 200
    assert b"already exists in the content library" in response.content


@pytest.mark.django_db
def test_add_weapon_trait_rejects_duplicate_within_pack(client, group_user, pack):
    """Test that duplicate trait names within the same pack are rejected."""

    # Create first trait in the pack.
    client.force_login(group_user)
    client.post(
        f"/pack/{pack.id}/add/weapon-trait/",
        {"name": "Custom Blast", "description": ""},
    )

    # Try to create a second trait with the same name.
    response = client.post(
        f"/pack/{pack.id}/add/weapon-trait/",
        {"name": "Custom Blast", "description": ""},
    )
    assert response.status_code == 200
    assert b"already exists in this Content Pack" in response.content


@pytest.mark.django_db
def test_different_packs_can_have_same_trait_name(client, group_user, pack):
    """Test that different packs can define traits with the same name."""
    from gyrinx.content.models.weapon import ContentWeaponTrait

    pack2 = CustomContentPack.objects.create(name="Other Pack", owner=group_user)

    client.force_login(group_user)
    # Create trait in first pack.
    response = client.post(
        f"/pack/{pack.id}/add/weapon-trait/",
        {"name": "Volatile", "description": ""},
    )
    assert response.status_code == 302

    # Create same-named trait in second pack.
    response = client.post(
        f"/pack/{pack2.id}/add/weapon-trait/",
        {"name": "Volatile", "description": ""},
    )
    assert response.status_code == 302

    assert ContentWeaponTrait.objects.all_content().filter(name="Volatile").count() == 2


@pytest.mark.django_db
def test_custom_trait_visible_in_weapon_profile_form(
    client, group_user, pack, weapon_category
):
    """Test that custom pack traits appear in the weapon profile traits picker."""
    from gyrinx.content.models.weapon import ContentWeaponTrait

    # Create a base trait and a pack trait.
    base_trait = ContentWeaponTrait.objects.create(name="Knockback")
    client.force_login(group_user)
    client.post(
        f"/pack/{pack.id}/add/weapon-trait/",
        {"name": "Pack Trait", "description": ""},
    )
    pack_trait = ContentWeaponTrait.objects.all_content().get(name="Pack Trait")

    # Load the add weapon form — both traits should be in the picker.
    response = client.get(f"/pack/{pack.id}/add/weapon/")
    content = response.content.decode()
    assert str(base_trait.pk) in content
    assert str(pack_trait.pk) in content


@pytest.mark.django_db
def test_pack_detail_shows_weapon_traits_section(client, group_user, pack):
    """Test that weapon traits appear as a section on the pack detail page."""

    client.force_login(group_user)
    client.post(
        f"/pack/{pack.id}/add/weapon-trait/",
        {"name": "Searing", "description": ""},
    )

    response = client.get(f"/pack/{pack.id}")
    content = response.content.decode()
    assert "Weapon Traits" in content
    assert "Searing" in content


@pytest.mark.django_db
def test_custom_trait_shows_in_weapon_traitline(
    client, group_user, pack, weapon_category
):
    """Custom pack traits assigned to weapon profiles appear in the traitline display."""
    from gyrinx.content.models.weapon import ContentWeaponProfile

    client.force_login(group_user)

    # Create a custom weapon trait in the pack.
    client.post(
        f"/pack/{pack.id}/add/weapon-trait/",
        {"name": "Jet Boost", "description": "Custom trait"},
    )
    trait = ContentWeaponTrait.objects.all_content().get(name="Jet Boost")

    # Create a weapon in the pack with the custom trait.
    client.post(
        f"/pack/{pack.id}/add/weapon/",
        {
            "name": "Trait Gun",
            "category": str(weapon_category.pk),
            "cost": "10",
            "rarity": "",
            "wp_traits": [str(trait.pk)],
        },
    )
    equipment = ContentEquipment.objects.all_content().get(name="Trait Gun")
    profile = ContentWeaponProfile.objects.all_content().get(
        equipment=equipment, name=""
    )

    # The traitline should include the custom pack trait.
    assert "Jet Boost" in profile.traitline()


@pytest.mark.django_db
def test_base_weapon_trait_model_level_uniqueness():
    """Base weapon traits enforce name uniqueness at the model level."""
    ContentWeaponTrait.objects.create(name="Knockback")
    duplicate = ContentWeaponTrait(name="Knockback")
    with pytest.raises(ValidationError) as exc_info:
        duplicate.validate_unique()
    assert "name" in exc_info.value.message_dict


# --- Two-step add-fighter flow ---


@pytest.mark.django_db
def test_add_fighter_step2_invalid_params_redirects(
    client, group_user, pack, fighter_statline_type
):
    """Accessing Step 2 without valid query params redirects to Step 1."""
    client.force_login(group_user)
    response = client.get(f"/pack/{pack.id}/add/fighter/stats/")
    assert response.status_code == 302
    assert f"/pack/{pack.id}/add/fighter/" in response.url


@pytest.mark.django_db
def test_add_fighter_step2_save_and_add_another(
    client, group_user, pack, fighter_statline_type, content_house
):
    """'Save and add another' from Step 2 redirects back to Step 1."""
    client.force_login(group_user)
    response = client.post(
        f"/pack/{pack.id}/add/fighter/stats/"
        f"?type=Another+Fighter&category=GANGER"
        f"&house_id={content_house.pk}&base_cost=50"
        f"&save_and_add_another=1",
        {"save_and_add_another": "1"},
    )
    assert response.status_code == 302
    assert f"/pack/{pack.id}/add/fighter/" in response.url
    # Fighter should have been created
    assert ContentFighter.objects.all_content().filter(type="Another Fighter").exists()


@pytest.mark.django_db
def test_get_statline_type_for_category_fallback(fighter_statline_type):
    """_get_statline_type_for_category falls back to Fighter for unmapped categories."""
    from gyrinx.core.views.pack import _get_statline_type_for_category

    # CREW is not in the default_for_categories for Fighter (as per the plan)
    result = _get_statline_type_for_category("CREW")
    assert result.name == "Fighter"


@pytest.mark.django_db
def test_get_statline_type_for_category_mapped(fighter_statline_type):
    """_get_statline_type_for_category returns the mapped type for known categories."""
    from gyrinx.core.views.pack import _get_statline_type_for_category

    # GANGER should map to Fighter via default_for_categories
    fighter_statline_type.default_for_categories = "GANGER"
    fighter_statline_type.save()
    result = _get_statline_type_for_category("GANGER")
    assert result.name == "Fighter"


@pytest.mark.django_db
def test_add_fighter_step2_uses_category_statline(
    client, group_user, pack, content_house, fighter_statline_type
):
    """Step 2 shows the correct stats for a category with a different statline type."""
    # Create a custom statline type with fewer stats for CREW.
    crew_type = ContentStatlineType.objects.create(
        name="Crew Test Type", default_for_categories="CREW"
    )
    bs_stat = ContentStat.objects.get(field_name="ballistic_skill")
    ld_stat = ContentStat.objects.get(field_name="leadership")
    ContentStatlineTypeStat.objects.create(
        statline_type=crew_type, stat=bs_stat, position=1
    )
    ContentStatlineTypeStat.objects.create(
        statline_type=crew_type, stat=ld_stat, position=2
    )

    client.force_login(group_user)
    response = client.get(
        f"/pack/{pack.id}/add/fighter/stats/"
        f"?type=Crew+Test&category=CREW"
        f"&house_id={content_house.pk}&base_cost=30"
    )
    assert response.status_code == 200
    content = response.content.decode()
    # Should show only BS and Ld, not Movement
    assert "stat_ballistic_skill" in content
    assert "stat_leadership" in content
    assert "stat_movement" not in content
