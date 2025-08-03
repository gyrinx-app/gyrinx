import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentHouse,
    ContentWeaponProfile,
)
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)
from gyrinx.models import FighterCategoryChoices

User = get_user_model()


@pytest.fixture
def user():
    """Create a test user."""
    return User.objects.create_user(username="testuser", password="password")


@pytest.fixture
def house():
    """Create a test house."""
    return ContentHouse.objects.create(name="Test House", can_buy_any=False)


@pytest.fixture
def equipment_category():
    """Create a test equipment category."""
    return ContentEquipmentCategory.objects.create(
        name="Test Gear",
        group="Gear",
    )


@pytest.fixture
def weapon_category():
    """Create a test weapon category."""
    return ContentEquipmentCategory.objects.create(
        name="Test Weapons",
        group="Weapon",
    )


@pytest.fixture
def content_fighter(house):
    """Create a test content fighter."""
    return ContentFighter.objects.create(
        type="Test Champion",
        house=house,
        category=FighterCategoryChoices.CHAMPION,
        base_cost=150,
        movement="5",
        weapon_skill="3+",
        ballistic_skill="3+",
        strength="3",
        toughness="3",
        wounds="2",
        initiative="3+",
        attacks="2",
        leadership="6+",
        cool="6+",
        willpower="7+",
        intelligence="7+",
    )


@pytest.fixture
def test_list(user, house):
    """Create a test list."""
    return List.objects.create(
        owner=user,
        name="Test List",
        content_house=house,
    )


@pytest.fixture
def list_fighter(test_list, content_fighter, user):
    """Create a test list fighter."""
    return ListFighter.objects.create(
        list=test_list,
        content_fighter=content_fighter,
        name="Test Fighter",
        owner=user,
    )


@pytest.fixture
def client(user):
    """Create a logged-in test client."""
    c = Client()
    c.login(username="testuser", password="password")
    return c


# Basic Equipment Assignment Tests


@pytest.mark.django_db
def test_basic_equipment_assignment(
    client, test_list, list_fighter, equipment_category
):
    """Test basic equipment assignment without upgrades."""
    # Create equipment
    equipment = ContentEquipment.objects.create(
        name="Basic Gear",
        category=equipment_category,
        rarity="C",
        cost="20",
    )

    # Add to fighter's equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=list_fighter.content_fighter,
        equipment=equipment,
    )

    # Test assignment
    url = reverse("core:list-fighter-gear-edit", args=[test_list.id, list_fighter.id])
    response = client.post(
        url,
        {
            "content_equipment": equipment.id,
        },
    )

    assert response.status_code == 302

    # Verify assignment created
    assert ListFighterEquipmentAssignment.objects.filter(
        list_fighter=list_fighter,
        content_equipment=equipment,
    ).exists()


@pytest.mark.django_db
def test_weapon_assignment_with_profile(
    client, test_list, list_fighter, weapon_category
):
    """Test weapon assignment with weapon profile."""
    # Create weapon
    weapon = ContentEquipment.objects.create(
        name="Test Weapon",
        category=weapon_category,
        rarity="C",
        cost="25",
    )

    # Create weapon profiles
    ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Short Range",
        cost=25,
    )
    profile2 = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Long Range",
        cost=30,
    )

    # Add to fighter's equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=list_fighter.content_fighter,
        equipment=weapon,
    )

    # Test assignment with profile selection
    url = reverse(
        "core:list-fighter-weapons-edit", args=[test_list.id, list_fighter.id]
    )
    response = client.post(
        url,
        {
            "content_equipment": weapon.id,
            "weapon_profiles_field": [profile2.id],
        },
    )

    assert response.status_code == 302

    # Verify assignment with correct profile
    assignment = ListFighterEquipmentAssignment.objects.get(
        list_fighter=list_fighter,
        content_equipment=weapon,
    )
    assert assignment.weapon_profiles_field.count() == 1
    assert assignment.weapon_profiles_field.first() == profile2


# Campaign Mode Tests


@pytest.mark.django_db
def test_equipment_assignment_no_credit_check_non_campaign_mode(
    client, test_list, list_fighter, equipment_category
):
    """Test that credit checking is skipped outside of campaign mode."""
    # Ensure no campaign
    test_list.campaign = None
    test_list.credits_current = 0
    test_list.save()

    # Create equipment
    equipment = ContentEquipment.objects.create(
        name="Free Mode Gear",
        category=equipment_category,
        rarity="C",
        cost="100",
    )

    # Add to fighter's equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=list_fighter.content_fighter,
        equipment=equipment,
    )

    # Test assignment
    url = reverse("core:list-fighter-gear-edit", args=[test_list.id, list_fighter.id])
    response = client.post(
        url,
        {
            "content_equipment": equipment.id,
        },
    )

    assert response.status_code == 302

    # Verify assignment created despite zero credits
    assert ListFighterEquipmentAssignment.objects.filter(
        list_fighter=list_fighter,
        content_equipment=equipment,
    ).exists()


# Default Equipment Tests


@pytest.mark.django_db
def test_default_equipment_with_cost_override(
    client, test_list, list_fighter, equipment_category
):
    """Test that equipment assigned by default can have its cost overridden."""
    # Create equipment with a default assignment
    equipment = ContentEquipment.objects.create(
        name="Default Gear",
        category=equipment_category,
        rarity="C",
        cost="25",
    )

    # Create default assignment with cost override
    ContentFighterDefaultAssignment.objects.create(
        fighter=list_fighter.content_fighter,
        equipment=equipment,
        cost=10,  # Override the normal cost
    )

    # Check that default equipment shows up on the gear edit page
    url = reverse("core:list-fighter-gear-edit", args=[test_list.id, list_fighter.id])
    response = client.get(url)

    assert response.status_code == 200

    # The fighter should have the default equipment in its assignments
    # Default equipment is automatically assigned to fighters
    assignments = list_fighter.assignments()
    assert any(a.content_equipment == equipment for a in assignments)

    # Check if the default assignment is present and free (0 cost)
    default_assignment = next(
        (a for a in assignments if a.content_equipment == equipment), None
    )
    assert default_assignment is not None
    assert default_assignment.kind() == "default"
    # Default equipment is always free (0 cost) for the fighter
    assert default_assignment.cost_int() == 0


@pytest.mark.django_db
def test_multiple_equipment_assignments_same_item(
    client, test_list, list_fighter, equipment_category
):
    """Test that a fighter can have multiple copies of the same equipment."""
    # Create equipment that can be taken multiple times
    equipment = ContentEquipment.objects.create(
        name="Grenade",
        category=equipment_category,
        rarity="C",
        cost="10",
    )

    # Add to fighter's equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=list_fighter.content_fighter,
        equipment=equipment,
    )

    url = reverse("core:list-fighter-gear-edit", args=[test_list.id, list_fighter.id])

    # Assign first grenade
    response = client.post(
        url,
        {
            "content_equipment": equipment.id,
        },
    )
    assert response.status_code == 302

    # Assign second grenade
    response = client.post(
        url,
        {
            "content_equipment": equipment.id,
        },
    )
    assert response.status_code == 302

    # Verify both assignments exist
    assignments = ListFighterEquipmentAssignment.objects.filter(
        list_fighter=list_fighter,
        content_equipment=equipment,
    )
    assert assignments.count() == 2


# Search and Filter Tests


@pytest.mark.django_db
def test_filter_parameters_preserved_after_assignment(
    client, test_list, list_fighter, equipment_category
):
    """Test that search and filter parameters are preserved after equipment assignment."""
    # Create equipment
    equipment = ContentEquipment.objects.create(
        name="Filter Test Gear",
        category=equipment_category,
        rarity="R",
        cost="30",
    )

    # Add to fighter's equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=list_fighter.content_fighter,
        equipment=equipment,
    )

    # Assign with filters active
    url = reverse("core:list-fighter-gear-edit", args=[test_list.id, list_fighter.id])
    response = client.post(
        url + "?q=filter&al=R",
        {
            "content_equipment": equipment.id,
            "q": "filter",  # Include in POST data
            "filter": "all",
        },
    )

    assert response.status_code == 302

    # Check redirect preserves parameters
    redirect_url = response.url
    assert "q=filter" in redirect_url
    assert "flash=" in redirect_url  # Flash parameter for highlighting


@pytest.mark.django_db
def test_equipment_list_filter_vs_trading_post(
    client, test_list, list_fighter, equipment_category
):
    """Test filtering between equipment list and Trading Post items."""
    # Create Trading Post item
    ContentEquipment.objects.create(
        name="Trading Post Gear",
        category=equipment_category,
        rarity="C",
        cost="20",
    )

    # Create equipment list item
    equipment_list_gear = ContentEquipment.objects.create(
        name="Equipment List Gear",
        category=equipment_category,
        rarity="R",
        cost="40",
    )

    # Add only equipment list item to fighter
    ContentFighterEquipmentListItem.objects.create(
        fighter=list_fighter.content_fighter,
        equipment=equipment_list_gear,
    )

    # Test default (equipment list filter)
    url = reverse("core:list-fighter-gear-edit", args=[test_list.id, list_fighter.id])
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Equipment List Gear" in content
    assert "Trading Post Gear" not in content

    # Test with filter=all
    response = client.get(url, {"filter": "all"})
    content = response.content.decode()
    assert "Equipment List Gear" in content
    assert "Trading Post Gear" in content


# Edge Cases


@pytest.mark.django_db
def test_equipment_assignment_with_zero_cost(
    client, test_list, list_fighter, equipment_category
):
    """Test assigning equipment with zero cost."""
    # Create free equipment
    equipment = ContentEquipment.objects.create(
        name="Free Gear",
        category=equipment_category,
        rarity="C",
        cost="0",
    )

    # Add to fighter's equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=list_fighter.content_fighter,
        equipment=equipment,
    )

    # Test assignment
    url = reverse("core:list-fighter-gear-edit", args=[test_list.id, list_fighter.id])
    response = client.post(
        url,
        {
            "content_equipment": equipment.id,
        },
    )

    assert response.status_code == 302

    # Verify assignment created
    assignment = ListFighterEquipmentAssignment.objects.get(
        list_fighter=list_fighter,
        content_equipment=equipment,
    )
    assert assignment.cost_int() == 0


@pytest.mark.django_db
def test_equipment_reassignment_between_fighters(
    client, test_list, list_fighter, content_fighter, equipment_category, user
):
    """Test reassigning equipment from one fighter to another."""
    # Create second fighter
    fighter2 = ListFighter.objects.create(
        list=test_list,
        content_fighter=content_fighter,
        name="Fighter 2",
        owner=user,
    )

    # Create and assign equipment to first fighter
    equipment = ContentEquipment.objects.create(
        name="Transferable Gear",
        category=equipment_category,
        rarity="C",
        cost="30",
    )

    ContentFighterEquipmentListItem.objects.create(
        fighter=list_fighter.content_fighter,
        equipment=equipment,
    )

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=equipment,
    )

    # Test reassignment
    url = reverse(
        "core:list-fighter-gear-reassign",
        args=[test_list.id, list_fighter.id, assignment.id],
    )
    response = client.post(
        url,
        {
            "target_fighter": fighter2.id,
        },
    )

    assert response.status_code == 302

    # Verify equipment moved to second fighter
    assignment.refresh_from_db()
    assert assignment.list_fighter == fighter2
