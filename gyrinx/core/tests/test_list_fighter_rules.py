import pytest
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from gyrinx.content.models import ContentFighter, ContentHouse, ContentRule
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem
from gyrinx.core.models import List, ListFighter

User = get_user_model()


@pytest.mark.django_db
def test_list_fighter_ruleline_respects_disabled_rules(client):
    """Test that disabled rules are not included in the ruleline."""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    # Create some rules
    rule1 = ContentRule.objects.create(name="Rule 1")
    rule2 = ContentRule.objects.create(name="Rule 2")
    rule3 = ContentRule.objects.create(name="Rule 3")

    # Create a fighter with rules
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
    )
    content_fighter.rules.add(rule1, rule2, rule3)

    # Create a list and list fighter
    lst = List.objects.create(name="Test List", content_house=house, owner=user)
    list_fighter = ListFighter.objects.create(
        name="Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Initially, all rules should be present
    ruleline_names = [r.value for r in list_fighter.ruleline]
    assert "Rule 1" in ruleline_names
    assert "Rule 2" in ruleline_names
    assert "Rule 3" in ruleline_names

    # Disable rule2
    list_fighter.disabled_rules.add(rule2)

    # Clear the cached property by deleting it from the instance
    if hasattr(list_fighter, "ruleline"):
        delattr(list_fighter, "ruleline")

    # Now rule2 should not be in the ruleline
    ruleline_names = [r.value for r in list_fighter.ruleline]
    assert "Rule 1" in ruleline_names
    assert "Rule 2" not in ruleline_names
    assert "Rule 3" in ruleline_names


@pytest.mark.django_db
def test_list_fighter_ruleline_includes_custom_rules(client):
    """Test that custom rules are included in the ruleline."""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    # Create some rules
    rule1 = ContentRule.objects.create(name="Default Rule")
    custom_rule = ContentRule.objects.create(name="Custom Rule")

    # Create a fighter with one default rule
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
    )
    content_fighter.rules.add(rule1)

    # Create a list and list fighter
    lst = List.objects.create(name="Test List", content_house=house, owner=user)
    list_fighter = ListFighter.objects.create(
        name="Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Add custom rule
    list_fighter.custom_rules.add(custom_rule)

    # Clear the cached property
    if hasattr(list_fighter, "_ruleline"):
        del list_fighter._ruleline

    # Both rules should be present
    ruleline_names = [r.value for r in list_fighter.ruleline]
    assert "Default Rule" in ruleline_names
    assert "Custom Rule" in ruleline_names

    # Custom rule should be marked as modded
    custom_rule_display = next(
        r for r in list_fighter.ruleline if r.value == "Custom Rule"
    )
    assert custom_rule_display.modded


@pytest.mark.django_db
def test_edit_list_fighter_rules_view(client):
    """Test the rules editing view."""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")

    # Create some rules
    default_rule = ContentRule.objects.create(name="Default Rule")
    ContentRule.objects.create(name="Other Rule")

    # Create a fighter with a default rule
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
    )
    content_fighter.rules.add(default_rule)

    # Create a list and list fighter
    lst = List.objects.create(name="Test List", content_house=house, owner=user)
    list_fighter = ListFighter.objects.create(
        name="Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Access the rules edit page
    url = reverse("core:list-fighter-rules-edit", args=[lst.id, list_fighter.id])
    response = client.get(url)

    assert response.status_code == 200
    assert "Default Rule" in response.content.decode()
    assert "Other Rule" in response.content.decode()


@pytest.mark.django_db
def test_toggle_list_fighter_rule(client):
    """Test toggling (enabling/disabling) a default rule."""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")
    default_rule = ContentRule.objects.create(name="Default Rule")

    # Create a fighter with a default rule
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
    )
    content_fighter.rules.add(default_rule)

    # Create a list and list fighter
    lst = List.objects.create(name="Test List", content_house=house, owner=user)
    list_fighter = ListFighter.objects.create(
        name="Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Toggle the rule (disable it)
    url = reverse(
        "core:list-fighter-rule-toggle", args=[lst.id, list_fighter.id, default_rule.id]
    )
    response = client.post(url)

    assert response.status_code == 302
    assert list_fighter.disabled_rules.filter(id=default_rule.id).exists()

    # Toggle again (enable it)
    response = client.post(url)

    assert response.status_code == 302
    assert not list_fighter.disabled_rules.filter(id=default_rule.id).exists()


@pytest.mark.django_db
def test_add_custom_rule(client):
    """Test adding a custom rule to a fighter."""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")
    custom_rule = ContentRule.objects.create(name="Custom Rule")

    # Create a fighter
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
    )

    # Create a list and list fighter
    lst = List.objects.create(name="Test List", content_house=house, owner=user)
    list_fighter = ListFighter.objects.create(
        name="Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Add custom rule
    url = reverse("core:list-fighter-rule-add", args=[lst.id, list_fighter.id])
    response = client.post(url, {"rule_id": custom_rule.id})

    assert response.status_code == 302
    assert list_fighter.custom_rules.filter(id=custom_rule.id).exists()


@pytest.mark.django_db
def test_remove_custom_rule(client):
    """Test removing a custom rule from a fighter."""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")
    custom_rule = ContentRule.objects.create(name="Custom Rule")

    # Create a fighter
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
    )

    # Create a list and list fighter
    lst = List.objects.create(name="Test List", content_house=house, owner=user)
    list_fighter = ListFighter.objects.create(
        name="Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Add custom rule first
    list_fighter.custom_rules.add(custom_rule)

    # Remove custom rule
    url = reverse(
        "core:list-fighter-rule-remove", args=[lst.id, list_fighter.id, custom_rule.id]
    )
    response = client.post(url)

    assert response.status_code == 302
    assert not list_fighter.custom_rules.filter(id=custom_rule.id).exists()


@pytest.mark.django_db
def test_clone_fighter_preserves_rule_overrides(client):
    """Test that cloning a fighter preserves rule overrides."""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    # Create rules
    default_rule = ContentRule.objects.create(name="Default Rule")
    disabled_rule = ContentRule.objects.create(name="Disabled Rule")
    custom_rule = ContentRule.objects.create(name="Custom Rule")

    # Create a fighter with rules
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
    )
    content_fighter.rules.add(default_rule, disabled_rule)

    # Create a list and list fighter
    lst = List.objects.create(name="Test List", content_house=house, owner=user)
    list_fighter = ListFighter.objects.create(
        name="Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Set up rule overrides
    list_fighter.disabled_rules.add(disabled_rule)
    list_fighter.custom_rules.add(custom_rule)

    # Clone the fighter
    clone = list_fighter.clone()

    # Verify rule overrides are preserved
    assert clone.disabled_rules.filter(id=disabled_rule.id).exists()
    assert clone.custom_rules.filter(id=custom_rule.id).exists()


@pytest.mark.django_db
def test_rules_edit_pagination(client):
    """Test pagination in the rules edit view."""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")

    # Create many rules to test pagination
    for i in range(25):
        ContentRule.objects.create(name=f"Rule {i:02d}")

    # Create a fighter
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
    )

    # Create a list and list fighter
    lst = List.objects.create(name="Test List", content_house=house, owner=user)
    list_fighter = ListFighter.objects.create(
        name="Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Access the rules edit page
    url = reverse("core:list-fighter-rules-edit", args=[lst.id, list_fighter.id])
    response = client.get(url)

    assert response.status_code == 200
    # Should show pagination controls
    assert "pagination" in response.content.decode()
    assert "page-link" in response.content.decode()

    # Test page 2
    response = client.get(url + "?page=2")
    assert response.status_code == 200
    assert "Rule 20" in response.content.decode()  # Should be on page 2
    assert "Rule 00" not in response.content.decode()  # Should not be on page 2

    # Test search with pagination reset
    response = client.get(url + "?q=Rule+01&page=5")
    # Should redirect to page 1 since search results won't have 5 pages
    assert response.status_code == 302
    assert response.url == url + "?q=Rule+01"


@pytest.mark.django_db
def test_add_rule_with_invalid_uuid(client):
    """Test adding a rule with invalid UUID."""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
    )

    # Create a list and list fighter
    lst = List.objects.create(name="Test List", content_house=house, owner=user)
    list_fighter = ListFighter.objects.create(
        name="Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Try to add a rule with invalid UUID
    url = reverse("core:list-fighter-rule-add", args=[lst.id, list_fighter.id])
    response = client.post(url, {"rule_id": "invalid-uuid"})

    assert response.status_code == 302
    # Should redirect back to edit page
    assert response.url == reverse(
        "core:list-fighter-rules-edit", args=[lst.id, list_fighter.id]
    )

    # Verify no rule was added
    assert list_fighter.custom_rules.count() == 0


@pytest.mark.django_db
def test_ruleline_includes_pack_default_rules():
    """Test that pack rules assigned as defaults on a ContentFighter appear in ruleline."""
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    # Create a pack with a custom rule
    pack = CustomContentPack.objects.create(name="Test Pack", owner=user, listed=True)
    pack_rule = _create_pack_rule(user, pack, rule_name="Pack Default Rule")

    # Create a content fighter IN the pack with the pack rule as a default
    content_fighter = ContentFighter.objects.create(
        type="Pack Fighter", house=house, category="GANGER"
    )
    ct = ContentType.objects.get_for_model(ContentFighter)
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=content_fighter.pk, owner=user
    )
    content_fighter.rules.add(pack_rule)

    # Create a list subscribed to the pack with a fighter using that content fighter
    lst = List.objects.create(name="Test List", content_house=house, owner=user)
    lst.packs.add(pack)
    list_fighter = ListFighter.objects.create(
        name="Fighter", content_fighter=content_fighter, list=lst, owner=user
    )

    # The pack rule should appear in the ruleline
    ruleline_names = [r.value for r in list_fighter.ruleline]
    assert "Pack Default Rule" in ruleline_names


@pytest.mark.django_db
def test_rules_edit_shows_pack_default_rules(client):
    """Test that pack rules assigned as defaults show in the rules edit view."""
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    # Create a pack with a custom rule
    pack = CustomContentPack.objects.create(name="Test Pack", owner=user, listed=True)
    pack_rule = _create_pack_rule(user, pack, rule_name="Pack Default Rule")

    # Create a content fighter with the pack rule as a default
    content_fighter = ContentFighter.objects.create(
        type="Pack Fighter", house=house, category="GANGER"
    )
    content_fighter.rules.add(pack_rule)

    # Create a list subscribed to the pack
    lst = List.objects.create(name="Test List", content_house=house, owner=user)
    lst.packs.add(pack)
    list_fighter = ListFighter.objects.create(
        name="Fighter", content_fighter=content_fighter, list=lst, owner=user
    )

    url = reverse("core:list-fighter-rules-edit", args=[lst.id, list_fighter.id])
    response = client.get(url)
    assert response.status_code == 200
    # Pack default rule should appear in the default rules section
    assert "Pack Default Rule" in response.content.decode()


def _create_pack_rule(user, pack, rule_name="Pack Rule"):
    """Helper to create a rule associated with a content pack."""
    rule = ContentRule.objects.create(name=rule_name, description="A rule from a pack")
    ct = ContentType.objects.get_for_model(ContentRule)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ct,
        object_id=rule.pk,
        owner=user,
    )
    return rule


@pytest.mark.django_db
def test_add_pack_rule_to_fighter(client):
    """Test adding a rule from a subscribed content pack to a fighter."""
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
    )

    # Create a pack with a rule
    pack = CustomContentPack.objects.create(name="Test Pack", owner=user, listed=True)
    pack_rule = _create_pack_rule(user, pack)

    # Create a list subscribed to the pack
    lst = List.objects.create(name="Test List", content_house=house, owner=user)
    lst.packs.add(pack)

    list_fighter = ListFighter.objects.create(
        name="Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Add pack rule - should succeed, not 404
    url = reverse("core:list-fighter-rule-add", args=[lst.id, list_fighter.id])
    response = client.post(url, {"rule_id": pack_rule.id})

    assert response.status_code == 302
    # Use the through table to verify the M2M link exists, since the default
    # ContentRule manager excludes pack content from queryset results.
    through_model = ListFighter.custom_rules.through
    assert through_model.objects.filter(
        listfighter_id=list_fighter.id, contentrule_id=pack_rule.id
    ).exists()


@pytest.mark.django_db
def test_remove_pack_rule_from_fighter(client):
    """Test removing a pack rule from a fighter."""
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
    )

    # Create a pack with a rule
    pack = CustomContentPack.objects.create(name="Test Pack", owner=user, listed=True)
    pack_rule = _create_pack_rule(user, pack)

    # Create a list subscribed to the pack
    lst = List.objects.create(name="Test List", content_house=house, owner=user)
    lst.packs.add(pack)

    list_fighter = ListFighter.objects.create(
        name="Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Add the rule first
    list_fighter.custom_rules.add(pack_rule)

    # Remove pack rule - should succeed, not 404
    url = reverse(
        "core:list-fighter-rule-remove", args=[lst.id, list_fighter.id, pack_rule.id]
    )
    response = client.post(url)

    assert response.status_code == 302
    # Use the through table since the default manager excludes pack content
    through_model = ListFighter.custom_rules.through
    assert not through_model.objects.filter(
        listfighter_id=list_fighter.id, contentrule_id=pack_rule.id
    ).exists()


@pytest.mark.django_db
def test_add_pack_rule_without_subscription_404(client):
    """Test that adding a pack rule without a subscription returns 404."""
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
    )

    # Create a pack with a rule but do NOT subscribe the list
    pack = CustomContentPack.objects.create(name="Test Pack", owner=user, listed=True)
    pack_rule = _create_pack_rule(user, pack)

    lst = List.objects.create(name="Test List", content_house=house, owner=user)
    list_fighter = ListFighter.objects.create(
        name="Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Try to add pack rule without subscription - should 404
    url = reverse("core:list-fighter-rule-add", args=[lst.id, list_fighter.id])
    response = client.post(url, {"rule_id": pack_rule.id})

    assert response.status_code == 404
    # Use the through table since the default manager excludes pack content
    through_model = ListFighter.custom_rules.through
    assert not through_model.objects.filter(
        listfighter_id=list_fighter.id, contentrule_id=pack_rule.id
    ).exists()


@pytest.mark.django_db
def test_pack_rules_visible_in_edit_view(client):
    """Test that pack rules appear in the rules edit view when subscribed."""
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
    )

    # Create a pack with a rule
    pack = CustomContentPack.objects.create(name="Test Pack", owner=user, listed=True)
    _create_pack_rule(user, pack, rule_name="My Pack Rule")

    # Create a list subscribed to the pack
    lst = List.objects.create(name="Test List", content_house=house, owner=user)
    lst.packs.add(pack)

    list_fighter = ListFighter.objects.create(
        name="Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    url = reverse("core:list-fighter-rules-edit", args=[lst.id, list_fighter.id])
    response = client.get(url)

    assert response.status_code == 200
    assert "My Pack Rule" in response.content.decode()


@pytest.mark.django_db
def test_ruleline_excludes_rules_from_unsubscribed_packs():
    """Rules from packs the list does NOT subscribe to should not appear in the ruleline."""
    user = User.objects.create_user(username="rulepackuser", password="testpass")
    house = ContentHouse.objects.create(name="Rule Pack House")

    # Create two packs.
    pack_subscribed = CustomContentPack.objects.create(
        name="Subscribed Pack", owner=user
    )
    pack_other = CustomContentPack.objects.create(name="Other Pack", owner=user)

    # Create a rule in each pack.
    rule_subscribed = ContentRule.objects.create(name="Subscribed Rule")
    rule_other = ContentRule.objects.create(name="Other Pack Rule")
    rule_ct = ContentType.objects.get_for_model(ContentRule)
    CustomContentPackItem.objects.create(
        pack=pack_subscribed,
        content_type=rule_ct,
        object_id=rule_subscribed.pk,
        owner=user,
    )
    CustomContentPackItem.objects.create(
        pack=pack_other,
        content_type=rule_ct,
        object_id=rule_other.pk,
        owner=user,
    )

    # Create a content fighter with both rules assigned.
    content_fighter = ContentFighter.objects.create(
        type="Multi Pack Fighter", house=house, category="GANGER"
    )
    content_fighter.rules.add(rule_subscribed, rule_other)

    # Create a list subscribed to only one pack.
    lst = List.objects.create(name="Scoped List", content_house=house, owner=user)
    lst.packs.add(pack_subscribed)

    list_fighter = ListFighter.objects.create(
        name="Scoped Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    ruleline_names = [r.value for r in list_fighter.ruleline]
    assert "Subscribed Rule" in ruleline_names
    assert "Other Pack Rule" not in ruleline_names


@pytest.mark.django_db
def test_rules_edit_default_rules_excludes_unsubscribed_packs(client):
    """Default rules on the rules edit page should only show rules from subscribed packs."""
    user = User.objects.create_user(username="ruleedituser", password="testpass")
    house = ContentHouse.objects.create(name="Rule Edit House")

    pack_subscribed = CustomContentPack.objects.create(
        name="Subscribed Pack", owner=user
    )
    pack_other = CustomContentPack.objects.create(name="Other Pack", owner=user)

    rule_subscribed = ContentRule.objects.create(name="Visible Default Rule")
    rule_other = ContentRule.objects.create(name="Hidden Default Rule")
    rule_ct = ContentType.objects.get_for_model(ContentRule)
    CustomContentPackItem.objects.create(
        pack=pack_subscribed,
        content_type=rule_ct,
        object_id=rule_subscribed.pk,
        owner=user,
    )
    CustomContentPackItem.objects.create(
        pack=pack_other,
        content_type=rule_ct,
        object_id=rule_other.pk,
        owner=user,
    )

    content_fighter = ContentFighter.objects.create(
        type="Default Rule Fighter", house=house, category="GANGER"
    )
    content_fighter.rules.add(rule_subscribed, rule_other)

    lst = List.objects.create(name="Default Rule List", content_house=house, owner=user)
    lst.packs.add(pack_subscribed)

    list_fighter = ListFighter.objects.create(
        name="Default Rule Guy",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-rules-edit", args=[lst.id, list_fighter.id])
    response = client.get(url)
    content = response.content.decode()

    assert response.status_code == 200
    # Subscribed pack rule should show as a default rule.
    assert "Visible Default Rule" in content
    # Unsubscribed pack rule should NOT show.
    assert "Hidden Default Rule" not in content


@pytest.mark.django_db
def test_pack_custom_rules_appear_in_ruleline():
    """Pack rules added as custom rules should appear in the fighter's ruleline."""
    user = User.objects.create_user(username="custompackrule", password="testpass")
    house = ContentHouse.objects.create(name="Custom Rule House")

    pack = CustomContentPack.objects.create(name="Custom Rule Pack", owner=user)
    pack_rule = ContentRule.objects.create(name="Pack Custom Rule")
    rule_ct = ContentType.objects.get_for_model(ContentRule)
    CustomContentPackItem.objects.create(
        pack=pack, content_type=rule_ct, object_id=pack_rule.pk, owner=user
    )

    content_fighter = ContentFighter.objects.create(
        type="Custom Rule Fighter", house=house, category="GANGER"
    )

    lst = List.objects.create(name="Custom Rule List", content_house=house, owner=user)
    lst.packs.add(pack)

    list_fighter = ListFighter.objects.create(
        name="Custom Rule Guy",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    list_fighter.custom_rules.add(pack_rule)

    ruleline_names = [r.value for r in list_fighter.ruleline]
    assert "Pack Custom Rule" in ruleline_names


@pytest.mark.django_db
def test_disabling_pack_rule_removes_from_ruleline():
    """Disabling a pack rule assigned to a ContentFighter should remove it from the ruleline."""
    user = User.objects.create_user(username="disablepackrule", password="testpass")
    house = ContentHouse.objects.create(name="Disable Rule House")

    pack = CustomContentPack.objects.create(name="Disable Rule Pack", owner=user)
    pack_rule = ContentRule.objects.create(name="Disableable Pack Rule")
    rule_ct = ContentType.objects.get_for_model(ContentRule)
    CustomContentPackItem.objects.create(
        pack=pack, content_type=rule_ct, object_id=pack_rule.pk, owner=user
    )

    content_fighter = ContentFighter.objects.create(
        type="Disable Rule Fighter", house=house, category="GANGER"
    )
    content_fighter.rules.add(pack_rule)

    lst = List.objects.create(name="Disable Rule List", content_house=house, owner=user)
    lst.packs.add(pack)

    list_fighter = ListFighter.objects.create(
        name="Disable Rule Guy",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Rule should appear before disabling.
    assert "Disableable Pack Rule" in [r.value for r in list_fighter.ruleline]

    # Disable it.
    list_fighter.disabled_rules.add(pack_rule)

    # Clear cached property if any, re-fetch.
    list_fighter = ListFighter.objects.get(pk=list_fighter.pk)
    assert "Disableable Pack Rule" not in [r.value for r in list_fighter.ruleline]


@pytest.mark.django_db
def test_pack_custom_rules_appear_on_rules_edit_page(client):
    """Pack rules added as custom rules should appear in the User-added Rules section."""
    user = User.objects.create_user(username="customedituser", password="testpass")
    house = ContentHouse.objects.create(name="Custom Edit House")

    pack = CustomContentPack.objects.create(name="Custom Edit Pack", owner=user)
    pack_rule = ContentRule.objects.create(name="User Added Pack Rule")
    rule_ct = ContentType.objects.get_for_model(ContentRule)
    CustomContentPackItem.objects.create(
        pack=pack, content_type=rule_ct, object_id=pack_rule.pk, owner=user
    )

    content_fighter = ContentFighter.objects.create(
        type="Custom Edit Fighter", house=house, category="GANGER"
    )

    lst = List.objects.create(name="Custom Edit List", content_house=house, owner=user)
    lst.packs.add(pack)

    list_fighter = ListFighter.objects.create(
        name="Custom Edit Guy",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    list_fighter.custom_rules.add(pack_rule)

    client.force_login(user)
    url = reverse("core:list-fighter-rules-edit", args=[lst.id, list_fighter.id])
    response = client.get(url)
    content = response.content.decode()

    assert response.status_code == 200
    # The rule should appear in the User-added Rules section, not just in the
    # Add Rules search. If custom_rules.all() filters it out, we'd see the
    # empty state instead.
    assert "No user-added rules" not in content
    assert "User Added Pack Rule" in content
