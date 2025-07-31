import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import ContentFighter, ContentHouse, ContentRule
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
