"""Integration tests for ListAction tracking across all spend_credits pathways."""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError

from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import List, ListFighter, ListFighterEquipmentAssignment

User = get_user_model()


# ============================================================================
# Fighter Hiring Tests
# ============================================================================


@pytest.mark.django_db
def test_fighter_hire_campaign_mode_creates_action(
    user, content_house, content_fighter, make_campaign
):
    """Test that hiring a fighter in campaign mode creates a ListAction."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
    )

    # Create initial action so future actions will be tracked
    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    fighter_cost = content_fighter.cost_for_house(content_house)

    # Capture before values
    before_rating = lst.rating_current
    before_credits = lst.credits_current

    # Hire the fighter using the model directly (simulating the view)
    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    # Simulate what the view does
    lst.spend_credits(fighter_cost, description=f"Hiring {fighter.name}")

    lst.create_action(
        user=user,
        action_type=ListActionType.ADD_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=fighter.id,
        description=f"Hired {fighter.name} ({fighter_cost}¢)",
        list_fighter=fighter,
        rating_delta=fighter_cost,
        stash_delta=0,
        credits_delta=-fighter_cost,
        rating_before=before_rating,
        stash_before=0,
        credits_before=before_credits,
    )

    # Verify action was created
    action = ListAction.objects.latest_for_list(lst.id)
    assert action is not None
    assert action.applied is True
    assert action.action_type == ListActionType.ADD_FIGHTER
    assert action.list_fighter == fighter

    # Verify values align
    lst.refresh_from_db()
    assert action.rating_before == before_rating
    assert action.rating_after == lst.rating_current
    assert action.rating_delta == fighter_cost
    assert action.credits_before == before_credits
    assert action.credits_after == lst.credits_current
    assert action.credits_delta == -fighter_cost


@pytest.mark.django_db
def test_fighter_hire_stash_sets_stash_delta(
    user, content_house, content_fighter, make_campaign
):
    """Test that hiring a stash fighter sets stash_delta instead of rating_delta."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
    )

    # Create initial action
    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    # Create stash fighter
    stash_fighter_template = content_fighter
    stash_fighter_template.is_stash = True
    stash_fighter_template.save()

    fighter_cost = stash_fighter_template.cost_for_house(content_house)

    before_stash = lst.stash_current
    before_credits = lst.credits_current

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=stash_fighter_template,
        name="Stash",
    )

    lst.spend_credits(fighter_cost, description=f"Hiring {fighter.name}")

    lst.create_action(
        user=user,
        action_type=ListActionType.ADD_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=fighter.id,
        description=f"Hired {fighter.name} ({fighter_cost}¢)",
        list_fighter=fighter,
        rating_delta=0,  # Stash fighter
        stash_delta=fighter_cost,
        credits_delta=-fighter_cost,
        rating_before=lst.rating_current,
        stash_before=before_stash,
        credits_before=before_credits,
    )

    action = ListAction.objects.latest_for_list(lst.id)
    assert action.stash_delta == fighter_cost
    assert action.rating_delta == 0
    lst.refresh_from_db()
    assert action.stash_after == lst.stash_current


@pytest.mark.django_db
def test_fighter_hire_list_building_mode_creates_action(
    user, content_house, content_fighter
):
    """Test that hiring a fighter in list building mode creates a ListAction."""
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=None,  # List building mode
    )

    # Create initial action
    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    fighter_cost = content_fighter.cost_for_house(content_house)
    before_rating = lst.rating_current

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    # No spend_credits call in list building mode
    lst.create_action(
        user=user,
        action_type=ListActionType.ADD_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=fighter.id,
        description=f"Hired {fighter.name} ({fighter_cost}¢)",
        list_fighter=fighter,
        rating_delta=fighter_cost,
        stash_delta=0,
        credits_delta=0,  # No credits in list building
        rating_before=before_rating,
        stash_before=0,
        credits_before=0,
    )

    action = ListAction.objects.latest_for_list(lst.id)
    assert action is not None
    assert action.credits_delta == 0
    lst.refresh_from_db()
    assert action.rating_after == lst.rating_current


@pytest.mark.django_db
def test_fighter_hire_values_align(user, content_house, content_fighter, make_campaign):
    """Test that action before/after values align with list values."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
        rating_current=500,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    fighter_cost = content_fighter.cost_for_house(content_house)

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    lst.spend_credits(fighter_cost, description=f"Hiring {fighter.name}")

    lst.create_action(
        user=user,
        action_type=ListActionType.ADD_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=fighter.id,
        description=f"Hired {fighter.name} ({fighter_cost}¢)",
        list_fighter=fighter,
        rating_delta=fighter_cost,
        stash_delta=0,
        credits_delta=-fighter_cost,
        rating_before=500,
        stash_before=0,
        credits_before=1000,
    )

    action = ListAction.objects.latest_for_list(lst.id)
    lst.refresh_from_db()

    # Verify alignment
    assert action.rating_before == 500
    assert action.rating_after == 500 + fighter_cost
    assert action.rating_after == lst.rating_current
    assert action.credits_before == 1000
    assert action.credits_after == 1000 - fighter_cost
    assert action.credits_after == lst.credits_current


@pytest.mark.django_db
def test_fighter_hire_insufficient_credits_no_action(
    user, content_house, content_fighter, make_campaign
):
    """Test that insufficient credits prevents action creation via rollback."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=10,  # Not enough
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    initial_action_count = ListAction.objects.filter(list=lst).count()

    fighter_cost = content_fighter.cost_for_house(content_house)

    # This should raise DjangoValidationError
    with pytest.raises(DjangoValidationError):
        lst.spend_credits(fighter_cost, description="Hiring fighter")

    # No new action should be created
    assert ListAction.objects.filter(list=lst).count() == initial_action_count


# ============================================================================
# Equipment Purchase Tests
# ============================================================================


@pytest.mark.django_db
def test_equipment_purchase_creates_action(
    user,
    content_house,
    content_fighter,
    make_campaign,
    make_list_fighter,
    make_equipment,
):
    """Test that purchasing equipment creates a ListAction."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    fighter = make_list_fighter(lst, "Test Fighter")
    equipment = make_equipment("Test Weapon", cost=100)

    before_rating = lst.rating_current
    before_credits = lst.credits_current

    # Create assignment
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    total_cost = assignment.cost_int()
    lst.spend_credits(total_cost, description=f"Buying {equipment.name}")

    lst.create_action(
        user=user,
        action_type=ListActionType.ADD_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=f"Bought {equipment.name} for {fighter.name} ({total_cost}¢)",
        list_fighter=fighter,
        list_fighter_equipment_assignment=assignment,
        rating_delta=total_cost,
        stash_delta=0,
        credits_delta=-total_cost,
        rating_before=before_rating,
        stash_before=0,
        credits_before=before_credits,
    )

    action = ListAction.objects.latest_for_list(lst.id)
    assert action is not None
    assert action.action_type == ListActionType.ADD_EQUIPMENT
    assert action.list_fighter_equipment_assignment == assignment

    lst.refresh_from_db()
    assert action.rating_after == lst.rating_current
    assert action.credits_after == lst.credits_current


@pytest.mark.django_db
def test_equipment_to_stash_sets_stash_delta(
    user, content_house, make_campaign, make_equipment
):
    """Test that purchasing equipment for stash fighter sets stash_delta."""
    from gyrinx.content.models import ContentFighter

    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    # Create stash fighter
    stash_fighter_template, _ = ContentFighter.objects.get_or_create(
        house=content_house,
        is_stash=True,
        defaults={"type": "Stash", "base_cost": 0},
    )

    stash = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=stash_fighter_template,
        name="Stash",
    )

    equipment = make_equipment("Test Weapon", cost=100)

    before_stash = lst.stash_current
    before_credits = lst.credits_current

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash,
        content_equipment=equipment,
    )

    total_cost = assignment.cost_int()
    lst.spend_credits(total_cost, description=f"Buying {equipment.name}")

    lst.create_action(
        user=user,
        action_type=ListActionType.ADD_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=f"Bought {equipment.name} for stash ({total_cost}¢)",
        list_fighter=stash,
        list_fighter_equipment_assignment=assignment,
        rating_delta=0,
        stash_delta=total_cost,
        credits_delta=-total_cost,
        rating_before=0,
        stash_before=before_stash,
        credits_before=before_credits,
    )

    action = ListAction.objects.latest_for_list(lst.id)
    assert action.stash_delta == total_cost
    assert action.rating_delta == 0

    lst.refresh_from_db()
    assert action.stash_after == lst.stash_current


@pytest.mark.django_db
def test_equipment_purchase_values_align(
    user, content_house, make_campaign, make_list_fighter, make_equipment
):
    """Test that equipment purchase action values align with list values."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
        rating_current=500,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    fighter = make_list_fighter(lst, "Test Fighter")
    equipment = make_equipment("Test Weapon", cost=100)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    total_cost = assignment.cost_int()
    lst.spend_credits(total_cost, description=f"Buying {equipment.name}")

    lst.create_action(
        user=user,
        action_type=ListActionType.ADD_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=f"Bought {equipment.name} ({total_cost}¢)",
        list_fighter=fighter,
        list_fighter_equipment_assignment=assignment,
        rating_delta=total_cost,
        stash_delta=0,
        credits_delta=-total_cost,
        rating_before=500,
        stash_before=0,
        credits_before=1000,
    )

    action = ListAction.objects.latest_for_list(lst.id)
    lst.refresh_from_db()

    # Verify perfect alignment
    assert action.rating_before + action.rating_delta == action.rating_after
    assert action.rating_after == lst.rating_current
    assert action.credits_before + action.credits_delta == action.credits_after
    assert action.credits_after == lst.credits_current


@pytest.mark.django_db
def test_equipment_purchase_insufficient_credits(
    user, content_house, make_campaign, make_list_fighter, make_equipment
):
    """Test that insufficient credits rolls back equipment purchase."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=10,  # Not enough
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    fighter = make_list_fighter(lst, "Test Fighter")
    equipment = make_equipment("Expensive Weapon", cost=100)

    initial_action_count = ListAction.objects.filter(list=lst).count()
    initial_assignment_count = ListFighterEquipmentAssignment.objects.count()

    # Simulate the transaction
    from django.db import transaction

    with pytest.raises(DjangoValidationError):
        with transaction.atomic():
            assignment = ListFighterEquipmentAssignment.objects.create(
                list_fighter=fighter,
                content_equipment=equipment,
            )
            total_cost = assignment.cost_int()
            lst.spend_credits(total_cost, description=f"Buying {equipment.name}")

    # Verify rollback - no new action or assignment
    assert ListAction.objects.filter(list=lst).count() == initial_action_count
    assert ListFighterEquipmentAssignment.objects.count() == initial_assignment_count


@pytest.mark.django_db
def test_equipment_purchase_transaction_integrity(
    user, content_house, make_campaign, make_list_fighter, make_equipment
):
    """Test that equipment assignment and action are created together."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    fighter = make_list_fighter(lst, "Test Fighter")
    equipment = make_equipment("Test Weapon", cost=100)

    from django.db import transaction

    with transaction.atomic():
        assignment = ListFighterEquipmentAssignment.objects.create(
            list_fighter=fighter,
            content_equipment=equipment,
        )
        total_cost = assignment.cost_int()
        lst.spend_credits(total_cost, description=f"Buying {equipment.name}")

        lst.create_action(
            user=user,
            action_type=ListActionType.ADD_EQUIPMENT,
            subject_app="core",
            subject_type="ListFighterEquipmentAssignment",
            subject_id=assignment.id,
            description=f"Bought {equipment.name} ({total_cost}¢)",
            list_fighter=fighter,
            list_fighter_equipment_assignment=assignment,
            rating_delta=total_cost,
            stash_delta=0,
            credits_delta=-total_cost,
            rating_before=lst.rating_current,
            stash_before=0,
            credits_before=lst.credits_current,
        )

    # Both should exist
    assert ListFighterEquipmentAssignment.objects.filter(id=assignment.id).exists()
    action = ListAction.objects.latest_for_list(lst.id)
    assert action.list_fighter_equipment_assignment == assignment


# ============================================================================
# Weapon Accessory Tests
# ============================================================================


@pytest.mark.django_db
def test_accessory_purchase_creates_action(
    user, content_house, make_campaign, make_list_fighter, make_weapon_with_accessory
):
    """Test that purchasing a weapon accessory creates a ListAction."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    fighter = make_list_fighter(lst, "Test Fighter")
    weapon, accessory = make_weapon_with_accessory(cost=50, accessory_cost=25)

    # Create weapon assignment
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
    )

    before_rating = lst.rating_current
    before_credits = lst.credits_current

    # Calculate accessory cost
    accessory_cost = assignment.accessory_cost_int(accessory)

    # Purchase accessory
    lst.spend_credits(accessory_cost, description=f"Buying {accessory.name}")
    assignment.weapon_accessories_field.add(accessory)

    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=f"Bought {accessory.name} for {weapon.name} on {fighter.name} ({accessory_cost}¢)",
        list_fighter_equipment_assignment=assignment,
        rating_delta=accessory_cost,
        stash_delta=0,
        credits_delta=-accessory_cost,
        rating_before=before_rating,
        stash_before=0,
        credits_before=before_credits,
    )

    action = ListAction.objects.latest_for_list(lst.id)
    assert action is not None
    assert action.action_type == ListActionType.UPDATE_EQUIPMENT

    lst.refresh_from_db()
    assert action.rating_after == lst.rating_current
    assert action.credits_after == lst.credits_current


@pytest.mark.django_db
def test_accessory_stash_tracking(
    user, content_house, make_campaign, make_weapon_with_accessory
):
    """Test that accessories on stash weapons set stash_delta."""
    from gyrinx.content.models import ContentFighter

    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    stash_fighter_template, _ = ContentFighter.objects.get_or_create(
        house=content_house,
        is_stash=True,
        defaults={"type": "Stash", "base_cost": 0},
    )

    stash = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=stash_fighter_template,
        name="Stash",
    )

    weapon, accessory = make_weapon_with_accessory(cost=50, accessory_cost=25)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash,
        content_equipment=weapon,
    )

    before_stash = lst.stash_current
    before_credits = lst.credits_current

    accessory_cost = assignment.accessory_cost_int(accessory)
    lst.spend_credits(accessory_cost, description=f"Buying {accessory.name}")
    assignment.weapon_accessories_field.add(accessory)

    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=f"Bought {accessory.name} ({accessory_cost}¢)",
        list_fighter_equipment_assignment=assignment,
        rating_delta=0,
        stash_delta=accessory_cost,
        credits_delta=-accessory_cost,
        rating_before=0,
        stash_before=before_stash,
        credits_before=before_credits,
    )

    action = ListAction.objects.latest_for_list(lst.id)
    assert action.stash_delta == accessory_cost
    assert action.rating_delta == 0


@pytest.mark.django_db
def test_accessory_values_align(
    user, content_house, make_campaign, make_list_fighter, make_weapon_with_accessory
):
    """Test that accessory action values align with list values."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
        rating_current=500,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    fighter = make_list_fighter(lst, "Test Fighter")
    weapon, accessory = make_weapon_with_accessory(cost=50, accessory_cost=25)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
    )

    accessory_cost = assignment.accessory_cost_int(accessory)
    lst.spend_credits(accessory_cost, description=f"Buying {accessory.name}")
    assignment.weapon_accessories_field.add(accessory)

    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=f"Bought {accessory.name} ({accessory_cost}¢)",
        list_fighter_equipment_assignment=assignment,
        rating_delta=accessory_cost,
        stash_delta=0,
        credits_delta=-accessory_cost,
        rating_before=500,
        stash_before=0,
        credits_before=1000,
    )

    action = ListAction.objects.latest_for_list(lst.id)
    lst.refresh_from_db()

    assert action.rating_before + action.rating_delta == action.rating_after
    assert action.rating_after == lst.rating_current
    assert action.credits_before + action.credits_delta == action.credits_after
    assert action.credits_after == lst.credits_current


@pytest.mark.django_db
def test_accessory_insufficient_credits_rollback(
    user, content_house, make_campaign, make_list_fighter, make_weapon_with_accessory
):
    """Test that insufficient credits rolls back accessory purchase."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=10,  # Not enough
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    fighter = make_list_fighter(lst, "Test Fighter")
    weapon, accessory = make_weapon_with_accessory(cost=5, accessory_cost=25)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
    )

    initial_action_count = ListAction.objects.filter(list=lst).count()

    from django.db import transaction

    accessory_cost = assignment.accessory_cost_int(accessory)

    with pytest.raises(DjangoValidationError):
        with transaction.atomic():
            lst.spend_credits(accessory_cost, description=f"Buying {accessory.name}")
            assignment.weapon_accessories_field.add(accessory)

    # No new action should be created
    assert ListAction.objects.filter(list=lst).count() == initial_action_count
    # Accessory should not be added
    assert not assignment.weapon_accessories_field.filter(id=accessory.id).exists()


# ============================================================================
# Weapon Profile Tests
# ============================================================================


@pytest.mark.django_db
def test_profile_purchase_creates_action(
    user, content_house, make_campaign, make_list_fighter, make_weapon_with_profile
):
    """Test that purchasing a weapon profile creates a ListAction."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    fighter = make_list_fighter(lst, "Test Fighter")
    weapon, profile = make_weapon_with_profile(cost=50, profile_cost=30)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
    )

    before_rating = lst.rating_current
    before_credits = lst.credits_current

    # Calculate profile cost
    from gyrinx.content.models import VirtualWeaponProfile

    virtual_profile = VirtualWeaponProfile(profile=profile)
    profile_cost = assignment.profile_cost_int(virtual_profile)

    lst.spend_credits(profile_cost, description=f"Buying {profile.name}")
    assignment.weapon_profiles_field.add(profile)

    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=f"Bought {profile.name} for {weapon.name} on {fighter.name} ({profile_cost}¢)",
        list_fighter_equipment_assignment=assignment,
        rating_delta=profile_cost,
        stash_delta=0,
        credits_delta=-profile_cost,
        rating_before=before_rating,
        stash_before=0,
        credits_before=before_credits,
    )

    action = ListAction.objects.latest_for_list(lst.id)
    assert action is not None
    assert action.action_type == ListActionType.UPDATE_EQUIPMENT

    lst.refresh_from_db()
    assert action.rating_after == lst.rating_current
    assert action.credits_after == lst.credits_current


@pytest.mark.django_db
def test_profile_stash_tracking(
    user, content_house, make_campaign, make_weapon_with_profile
):
    """Test that profiles on stash weapons set stash_delta."""
    from gyrinx.content.models import ContentFighter

    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    stash_fighter_template, _ = ContentFighter.objects.get_or_create(
        house=content_house,
        is_stash=True,
        defaults={"type": "Stash", "base_cost": 0},
    )

    stash = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=stash_fighter_template,
        name="Stash",
    )

    weapon, profile = make_weapon_with_profile(cost=50, profile_cost=30)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash,
        content_equipment=weapon,
    )

    before_stash = lst.stash_current
    before_credits = lst.credits_current

    from gyrinx.content.models import VirtualWeaponProfile

    virtual_profile = VirtualWeaponProfile(profile=profile)
    profile_cost = assignment.profile_cost_int(virtual_profile)

    lst.spend_credits(profile_cost, description=f"Buying {profile.name}")
    assignment.weapon_profiles_field.add(profile)

    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=f"Bought {profile.name} ({profile_cost}¢)",
        list_fighter_equipment_assignment=assignment,
        rating_delta=0,
        stash_delta=profile_cost,
        credits_delta=-profile_cost,
        rating_before=0,
        stash_before=before_stash,
        credits_before=before_credits,
    )

    action = ListAction.objects.latest_for_list(lst.id)
    assert action.stash_delta == profile_cost
    assert action.rating_delta == 0


@pytest.mark.django_db
def test_profile_values_align(
    user, content_house, make_campaign, make_list_fighter, make_weapon_with_profile
):
    """Test that profile action values align with list values."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
        rating_current=500,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    fighter = make_list_fighter(lst, "Test Fighter")
    weapon, profile = make_weapon_with_profile(cost=50, profile_cost=30)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
    )

    from gyrinx.content.models import VirtualWeaponProfile

    virtual_profile = VirtualWeaponProfile(profile=profile)
    profile_cost = assignment.profile_cost_int(virtual_profile)

    lst.spend_credits(profile_cost, description=f"Buying {profile.name}")
    assignment.weapon_profiles_field.add(profile)

    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=f"Bought {profile.name} ({profile_cost}¢)",
        list_fighter_equipment_assignment=assignment,
        rating_delta=profile_cost,
        stash_delta=0,
        credits_delta=-profile_cost,
        rating_before=500,
        stash_before=0,
        credits_before=1000,
    )

    action = ListAction.objects.latest_for_list(lst.id)
    lst.refresh_from_db()

    assert action.rating_before + action.rating_delta == action.rating_after
    assert action.rating_after == lst.rating_current
    assert action.credits_before + action.credits_delta == action.credits_after
    assert action.credits_after == lst.credits_current


@pytest.mark.django_db
def test_profile_insufficient_credits_rollback(
    user, content_house, make_campaign, make_list_fighter, make_weapon_with_profile
):
    """Test that insufficient credits rolls back profile purchase."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=10,  # Not enough
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    fighter = make_list_fighter(lst, "Test Fighter")
    weapon, profile = make_weapon_with_profile(cost=5, profile_cost=30)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
    )

    initial_action_count = ListAction.objects.filter(list=lst).count()

    from django.db import transaction
    from gyrinx.content.models import VirtualWeaponProfile

    virtual_profile = VirtualWeaponProfile(profile=profile)
    profile_cost = assignment.profile_cost_int(virtual_profile)

    with pytest.raises(DjangoValidationError):
        with transaction.atomic():
            lst.spend_credits(profile_cost, description=f"Buying {profile.name}")
            assignment.weapon_profiles_field.add(profile)

    assert ListAction.objects.filter(list=lst).count() == initial_action_count
    assert not assignment.weapon_profiles_field.filter(id=profile.id).exists()


# ============================================================================
# Equipment Upgrade Tests
# ============================================================================


@pytest.mark.django_db
def test_upgrade_purchase_creates_action(
    user, content_house, make_campaign, make_list_fighter, make_equipment_with_upgrades
):
    """Test that purchasing equipment upgrades creates a ListAction."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    fighter = make_list_fighter(lst, "Test Fighter")
    equipment, upgrade = make_equipment_with_upgrades(cost=50, upgrade_cost=20)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    before_rating = lst.rating_current
    before_credits = lst.credits_current

    # Add upgrade
    old_cost = assignment.cost_int()
    assignment.upgrades_field.add(upgrade)
    assignment.refresh_from_db()
    new_cost = assignment.cost_int()
    cost_difference = new_cost - old_cost

    lst.spend_credits(cost_difference, description="Buying upgrade")

    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=f"Bought upgrade ({cost_difference}¢)",
        list_fighter_equipment_assignment=assignment,
        rating_delta=cost_difference,
        stash_delta=0,
        credits_delta=-cost_difference,
        rating_before=before_rating,
        stash_before=0,
        credits_before=before_credits,
    )

    action = ListAction.objects.latest_for_list(lst.id)
    assert action is not None
    assert action.action_type == ListActionType.UPDATE_EQUIPMENT

    lst.refresh_from_db()
    assert action.rating_after == lst.rating_current
    assert action.credits_after == lst.credits_current


@pytest.mark.django_db
def test_upgrade_removal_creates_action_with_negative_delta(
    user, content_house, make_campaign, make_list_fighter, make_equipment_with_upgrades
):
    """Test that removing upgrades creates action with negative cost_difference."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    fighter = make_list_fighter(lst, "Test Fighter")
    equipment, upgrade = make_equipment_with_upgrades(cost=50, upgrade_cost=20)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    # Add upgrade first
    assignment.upgrades_field.add(upgrade)
    assignment.refresh_from_db()
    # Clear any cached properties to get fresh cost calculation
    if hasattr(assignment, "upgrade_cost_int_cached"):
        del assignment.upgrade_cost_int_cached

    # Update list rating to reflect current actual cost (fighter + equipment + upgrade)
    lst.rating_current = fighter.cost_int()
    lst.save()
    before_rating = lst.rating_current

    # Remove upgrade
    old_cost = assignment.cost_int()
    assignment.upgrades_field.clear()
    assignment.refresh_from_db()
    # Clear cached properties again after removal
    if hasattr(assignment, "upgrade_cost_int_cached"):
        del assignment.upgrade_cost_int_cached
    new_cost = assignment.cost_int()
    cost_difference = new_cost - old_cost  # Should be negative

    # No spend_credits call when removing upgrades

    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=f"Removed upgrades from {equipment.name}",
        list_fighter_equipment_assignment=assignment,
        rating_delta=cost_difference,  # Negative
        stash_delta=0,
        credits_delta=0,  # No credits spent when removing
        rating_before=before_rating,
        stash_before=0,
        credits_before=lst.credits_current,
    )

    action = ListAction.objects.latest_for_list(lst.id)
    assert action.rating_delta < 0  # Negative for removal
    assert action.credits_delta == 0  # No credits refunded


@pytest.mark.django_db
def test_upgrade_stash_tracking(
    user, content_house, make_campaign, make_equipment_with_upgrades
):
    """Test that upgrades on stash equipment set stash_delta."""
    from gyrinx.content.models import ContentFighter

    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    stash_fighter_template, _ = ContentFighter.objects.get_or_create(
        house=content_house,
        is_stash=True,
        defaults={"type": "Stash", "base_cost": 0},
    )

    stash = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=stash_fighter_template,
        name="Stash",
    )

    equipment, upgrade = make_equipment_with_upgrades(cost=50, upgrade_cost=20)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash,
        content_equipment=equipment,
    )

    before_stash = lst.stash_current
    before_credits = lst.credits_current

    old_cost = assignment.cost_int()
    assignment.upgrades_field.add(upgrade)
    assignment.refresh_from_db()
    new_cost = assignment.cost_int()
    cost_difference = new_cost - old_cost

    lst.spend_credits(cost_difference, description="Buying upgrade")

    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=f"Bought upgrade ({cost_difference}¢)",
        list_fighter_equipment_assignment=assignment,
        rating_delta=0,
        stash_delta=cost_difference,
        credits_delta=-cost_difference,
        rating_before=0,
        stash_before=before_stash,
        credits_before=before_credits,
    )

    action = ListAction.objects.latest_for_list(lst.id)
    assert action.stash_delta == cost_difference
    assert action.rating_delta == 0


@pytest.mark.django_db
def test_upgrade_values_align(
    user, content_house, make_campaign, make_list_fighter, make_equipment_with_upgrades
):
    """Test that upgrade action values align with list values."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
        rating_current=500,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    fighter = make_list_fighter(lst, "Test Fighter")
    equipment, upgrade = make_equipment_with_upgrades(cost=50, upgrade_cost=20)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    old_cost = assignment.cost_int()
    assignment.upgrades_field.add(upgrade)
    assignment.refresh_from_db()
    new_cost = assignment.cost_int()
    cost_difference = new_cost - old_cost

    lst.spend_credits(cost_difference, description="Buying upgrade")

    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=f"Bought upgrade ({cost_difference}¢)",
        list_fighter_equipment_assignment=assignment,
        rating_delta=cost_difference,
        stash_delta=0,
        credits_delta=-cost_difference,
        rating_before=500,
        stash_before=0,
        credits_before=1000,
    )

    action = ListAction.objects.latest_for_list(lst.id)
    lst.refresh_from_db()

    assert action.rating_before + action.rating_delta == action.rating_after
    assert action.rating_after == lst.rating_current
    assert action.credits_before + action.credits_delta == action.credits_after
    assert action.credits_after == lst.credits_current


@pytest.mark.django_db
def test_upgrade_insufficient_credits_rollback(
    user, content_house, make_campaign, make_list_fighter, make_equipment_with_upgrades
):
    """Test that insufficient credits rolls back upgrade purchase."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=10,  # Not enough
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    fighter = make_list_fighter(lst, "Test Fighter")
    equipment, upgrade = make_equipment_with_upgrades(cost=5, upgrade_cost=20)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    initial_action_count = ListAction.objects.filter(list=lst).count()

    from django.db import transaction

    old_cost = assignment.cost_int()

    with pytest.raises(DjangoValidationError):
        with transaction.atomic():
            assignment.upgrades_field.add(upgrade)
            assignment.refresh_from_db()
            # Clear cached properties to get fresh cost calculation
            if hasattr(assignment, "upgrade_cost_int_cached"):
                del assignment.upgrade_cost_int_cached
            new_cost = assignment.cost_int()
            cost_difference = new_cost - old_cost
            lst.spend_credits(cost_difference, description="Buying upgrade")

    assert ListAction.objects.filter(list=lst).count() == initial_action_count
    # Upgrade should be rolled back
    assignment.refresh_from_db()
    assert upgrade not in assignment.upgrades_field.all()


# ============================================================================
# Vehicle Purchase Tests
# ============================================================================


@pytest.mark.django_db
def test_vehicle_to_stash_creates_one_action(
    user, content_house, make_campaign, make_vehicle_equipment
):
    """Test that vehicle purchase to stash creates ONE action."""
    from gyrinx.content.models import ContentFighter

    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    stash_fighter_template, _ = ContentFighter.objects.get_or_create(
        house=content_house,
        is_stash=True,
        defaults={"type": "Stash", "base_cost": 0},
    )

    stash = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=stash_fighter_template,
        name="Stash",
    )

    vehicle_equipment, vehicle_fighter = make_vehicle_equipment(cost=200)

    initial_action_count = ListAction.objects.filter(list=lst).count()

    vehicle_cost = vehicle_fighter.cost_for_house(content_house)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash,
        content_equipment=vehicle_equipment,
    )

    lst.spend_credits(vehicle_cost, description=f"Buying {vehicle_equipment.name}")

    lst.create_action(
        user=user,
        action_type=ListActionType.ADD_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=f"Purchased {vehicle_equipment.name} ({vehicle_cost}¢)",
        list_fighter_equipment_assignment=assignment,
        rating_delta=0,
        stash_delta=vehicle_cost,
        credits_delta=-vehicle_cost,
        rating_before=0,
        stash_before=0,
        credits_before=1000,
    )

    # Only ONE new action should be created
    assert ListAction.objects.filter(list=lst).count() == initial_action_count + 1


@pytest.mark.django_db
def test_vehicle_with_crew_creates_two_actions(
    user, content_house, content_fighter, make_campaign, make_vehicle_equipment
):
    """Test that vehicle + crew purchase creates TWO actions."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    vehicle_equipment, vehicle_fighter = make_vehicle_equipment(cost=200)

    initial_action_count = ListAction.objects.filter(list=lst).count()

    vehicle_cost = vehicle_fighter.cost_for_house(content_house)
    crew_cost = content_fighter.cost_for_house(content_house)
    total_cost = vehicle_cost + crew_cost

    # Create crew
    crew = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Crew Member",
    )

    # Create vehicle assignment
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=crew,
        content_equipment=vehicle_equipment,
    )

    lst.spend_credits(total_cost, description=f"Buying {vehicle_equipment.name}")

    # Create TWO actions
    lst.create_action(
        user=user,
        action_type=ListActionType.ADD_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=crew.id,
        description=f"Purchased {vehicle_equipment.name} and crew {crew.name} ({total_cost}¢)",
        list_fighter=crew,
        rating_delta=crew_cost,
        stash_delta=0,
        credits_delta=-crew_cost,
        rating_before=0,
        stash_before=0,
        credits_before=1000,
    )

    lst.create_action(
        user=user,
        action_type=ListActionType.ADD_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=f"Purchased {vehicle_equipment.name} and crew {crew.name} ({total_cost}¢)",
        list_fighter=crew,
        list_fighter_equipment_assignment=assignment,
        rating_delta=vehicle_cost,
        stash_delta=0,
        credits_delta=-vehicle_cost,
        rating_before=0,
        stash_before=0,
        credits_before=1000 - crew_cost,  # After first action
    )

    # TWO new actions should be created
    assert ListAction.objects.filter(list=lst).count() == initial_action_count + 2

    # Verify action types
    actions = ListAction.objects.filter(list=lst).order_by("-created")[:2]
    assert actions[0].action_type == ListActionType.ADD_EQUIPMENT
    assert actions[1].action_type == ListActionType.ADD_FIGHTER


@pytest.mark.django_db
def test_vehicle_crew_action_has_crew_cost_delta(
    user, content_house, content_fighter, make_campaign, make_vehicle_equipment
):
    """Test that the crew action tracks crew cost correctly."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    vehicle_equipment, vehicle_fighter = make_vehicle_equipment(cost=200)

    vehicle_cost = vehicle_fighter.cost_for_house(content_house)
    crew_cost = content_fighter.cost_for_house(content_house)
    total_cost = vehicle_cost + crew_cost

    crew = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Crew Member",
    )

    _assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=crew,
        content_equipment=vehicle_equipment,
    )

    lst.spend_credits(total_cost, description=f"Buying {vehicle_equipment.name}")

    lst.create_action(
        user=user,
        action_type=ListActionType.ADD_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=crew.id,
        description=f"Purchased crew {crew.name}",
        list_fighter=crew,
        rating_delta=crew_cost,
        stash_delta=0,
        credits_delta=-crew_cost,
        rating_before=0,
        stash_before=0,
        credits_before=1000,
    )

    crew_action = ListAction.objects.filter(
        list=lst, action_type=ListActionType.ADD_FIGHTER
    ).latest("created")

    assert crew_action.rating_delta == crew_cost
    assert crew_action.credits_delta == -crew_cost


@pytest.mark.django_db
def test_vehicle_equipment_action_has_vehicle_cost_delta(
    user, content_house, content_fighter, make_campaign, make_vehicle_equipment
):
    """Test that the vehicle action tracks vehicle cost correctly."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    vehicle_equipment, vehicle_fighter = make_vehicle_equipment(cost=200)

    vehicle_cost = vehicle_fighter.cost_for_house(content_house)
    crew_cost = content_fighter.cost_for_house(content_house)
    total_cost = vehicle_cost + crew_cost

    crew = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Crew Member",
    )

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=crew,
        content_equipment=vehicle_equipment,
    )

    lst.spend_credits(total_cost, description=f"Buying {vehicle_equipment.name}")

    # Create crew action first
    lst.create_action(
        user=user,
        action_type=ListActionType.ADD_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=crew.id,
        description="Crew action",
        list_fighter=crew,
        rating_delta=crew_cost,
        stash_delta=0,
        credits_delta=-crew_cost,
        rating_before=0,
        stash_before=0,
        credits_before=1000,
    )

    # Create vehicle action
    lst.create_action(
        user=user,
        action_type=ListActionType.ADD_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description="Vehicle action",
        list_fighter=crew,
        list_fighter_equipment_assignment=assignment,
        rating_delta=vehicle_cost,
        stash_delta=0,
        credits_delta=-vehicle_cost,
        rating_before=crew_cost,  # After crew action
        stash_before=0,
        credits_before=1000 - crew_cost,
    )

    vehicle_action = ListAction.objects.filter(
        list=lst, action_type=ListActionType.ADD_EQUIPMENT
    ).latest("created")

    assert vehicle_action.rating_delta == vehicle_cost
    assert vehicle_action.credits_delta == -vehicle_cost


@pytest.mark.django_db
def test_vehicle_both_actions_have_correct_before_values(
    user, content_house, content_fighter, make_campaign, make_vehicle_equipment
):
    """Test that both vehicle actions have correct before values."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
        rating_current=100,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    vehicle_equipment, vehicle_fighter = make_vehicle_equipment(cost=200)

    vehicle_cost = vehicle_fighter.cost_for_house(content_house)
    crew_cost = content_fighter.cost_for_house(content_house)
    total_cost = vehicle_cost + crew_cost

    crew = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Crew Member",
    )

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=crew,
        content_equipment=vehicle_equipment,
    )

    lst.spend_credits(total_cost, description=f"Buying {vehicle_equipment.name}")

    # Crew action
    lst.create_action(
        user=user,
        action_type=ListActionType.ADD_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=crew.id,
        description="Crew",
        list_fighter=crew,
        rating_delta=crew_cost,
        stash_delta=0,
        credits_delta=-crew_cost,
        rating_before=100,
        stash_before=0,
        credits_before=1000,
    )

    # Vehicle action (after crew)
    lst.create_action(
        user=user,
        action_type=ListActionType.ADD_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description="Vehicle",
        list_fighter=crew,
        list_fighter_equipment_assignment=assignment,
        rating_delta=vehicle_cost,
        stash_delta=0,
        credits_delta=-vehicle_cost,
        rating_before=100 + crew_cost,  # After crew action applied
        stash_before=0,
        credits_before=1000 - crew_cost,
    )

    actions = ListAction.objects.filter(list=lst).order_by("-created")[:2]
    vehicle_action = actions[0]  # Most recent
    crew_action = actions[1]

    # Crew action should have original before values
    assert crew_action.rating_before == 100
    assert crew_action.credits_before == 1000

    # Vehicle action should have before values AFTER crew action
    assert vehicle_action.rating_before == crew_action.rating_after
    assert vehicle_action.credits_before == crew_action.credits_after


@pytest.mark.django_db
def test_vehicle_values_align_across_both_actions(
    user, content_house, content_fighter, make_campaign, make_vehicle_equipment
):
    """Test value alignment across both vehicle actions."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
        rating_current=100,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    vehicle_equipment, vehicle_fighter = make_vehicle_equipment(cost=200)

    vehicle_cost = vehicle_fighter.cost_for_house(content_house)
    crew_cost = content_fighter.cost_for_house(content_house)
    total_cost = vehicle_cost + crew_cost

    crew = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Crew Member",
    )

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=crew,
        content_equipment=vehicle_equipment,
    )

    lst.spend_credits(total_cost, description=f"Buying {vehicle_equipment.name}")

    lst.create_action(
        user=user,
        action_type=ListActionType.ADD_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=crew.id,
        description="Crew",
        list_fighter=crew,
        rating_delta=crew_cost,
        stash_delta=0,
        credits_delta=-crew_cost,
        rating_before=100,
        stash_before=0,
        credits_before=1000,
    )

    lst.create_action(
        user=user,
        action_type=ListActionType.ADD_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description="Vehicle",
        list_fighter=crew,
        list_fighter_equipment_assignment=assignment,
        rating_delta=vehicle_cost,
        stash_delta=0,
        credits_delta=-vehicle_cost,
        rating_before=100 + crew_cost,
        stash_before=0,
        credits_before=1000 - crew_cost,
    )

    lst.refresh_from_db()
    vehicle_action = ListAction.objects.filter(
        list=lst, action_type=ListActionType.ADD_EQUIPMENT
    ).latest("created")

    # Final list values should match vehicle action after values
    assert vehicle_action.rating_after == lst.rating_current
    assert vehicle_action.credits_after == lst.credits_current


@pytest.mark.django_db
def test_vehicle_insufficient_credits_no_actions(
    user, content_house, content_fighter, make_campaign, make_vehicle_equipment
):
    """Test that insufficient credits prevents both vehicle actions."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=10,  # Not enough
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    vehicle_equipment, vehicle_fighter = make_vehicle_equipment(cost=200)

    initial_action_count = ListAction.objects.filter(list=lst).count()

    vehicle_cost = vehicle_fighter.cost_for_house(content_house)
    crew_cost = content_fighter.cost_for_house(content_house)
    total_cost = vehicle_cost + crew_cost

    from django.db import transaction

    with pytest.raises(DjangoValidationError):
        with transaction.atomic():
            crew = ListFighter.objects.create(
                list=lst,
                owner=user,
                content_fighter=content_fighter,
                name="Crew Member",
            )
            _assignment = ListFighterEquipmentAssignment.objects.create(
                list_fighter=crew,
                content_equipment=vehicle_equipment,
            )
            lst.spend_credits(
                total_cost, description=f"Buying {vehicle_equipment.name}"
            )

    # No new actions
    assert ListAction.objects.filter(list=lst).count() == initial_action_count


# ============================================================================
# Transaction Integrity Tests
# ============================================================================


@pytest.mark.django_db
def test_action_applied_false_if_list_update_fails(user, content_house, make_campaign):
    """Test that action.applied=False if list update fails."""
    from unittest.mock import patch

    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    # Mock list.save() to fail
    with patch.object(List, "save", side_effect=Exception("Save failed")):
        action = lst.create_action(
            user=user,
            action_type=ListActionType.ADD_FIGHTER,
            description="Test action",
            rating_delta=100,
            rating_before=0,
            stash_before=0,
            credits_before=1000,
        )

        # Action should exist but not be applied
        assert action is not None
        assert action.applied is False


@pytest.mark.django_db
def test_action_exists_even_if_update_fails(user, content_house, make_campaign):
    """Test that action persists even if list update fails (audit trail)."""
    from unittest.mock import patch

    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=1000,
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    initial_count = ListAction.objects.filter(list=lst).count()

    with patch.object(List, "save", side_effect=Exception("Save failed")):
        lst.create_action(
            user=user,
            action_type=ListActionType.ADD_FIGHTER,
            description="Test action",
            rating_delta=100,
            rating_before=0,
            stash_before=0,
            credits_before=1000,
        )

    # Action was created despite failure
    assert ListAction.objects.filter(list=lst).count() == initial_count + 1


@pytest.mark.django_db
def test_latest_action_check_prevents_orphaned_actions(user, content_house):
    """Test that create_action returns None if no latest_action exists."""
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=None,
    )

    # No initial action, so latest_action is None
    result = lst.create_action(
        user=user,
        action_type=ListActionType.ADD_FIGHTER,
        description="Test action",
        rating_delta=100,
        rating_before=0,
        stash_before=0,
        credits_before=0,
    )

    # Should return None
    assert result is None
    # No action should be created
    assert ListAction.objects.filter(list=lst).count() == 0


@pytest.mark.django_db
def test_atomic_rollback_leaves_no_partial_state(
    user, content_house, make_campaign, make_list_fighter, make_equipment
):
    """Test that atomic rollback prevents partial state."""
    campaign = make_campaign("Test Campaign")
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
        credits_current=10,  # Insufficient
    )

    ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="Initial action",
    )

    fighter = make_list_fighter(lst, "Test Fighter")
    equipment = make_equipment("Expensive Weapon", cost=100)

    initial_rating = lst.rating_current
    initial_credits = lst.credits_current
    initial_action_count = ListAction.objects.filter(list=lst).count()
    initial_assignment_count = ListFighterEquipmentAssignment.objects.count()

    from django.db import transaction

    with pytest.raises(DjangoValidationError):
        with transaction.atomic():
            assignment = ListFighterEquipmentAssignment.objects.create(
                list_fighter=fighter,
                content_equipment=equipment,
            )
            total_cost = assignment.cost_int()

            lst.spend_credits(total_cost, description=f"Buying {equipment.name}")

            lst.create_action(
                user=user,
                action_type=ListActionType.ADD_EQUIPMENT,
                subject_app="core",
                subject_type="ListFighterEquipmentAssignment",
                subject_id=assignment.id,
                description=f"Bought {equipment.name} ({total_cost}¢)",
                list_fighter=fighter,
                list_fighter_equipment_assignment=assignment,
                rating_delta=total_cost,
                stash_delta=0,
                credits_delta=-total_cost,
                rating_before=initial_rating,
                stash_before=0,
                credits_before=initial_credits,
            )

    # Everything should be rolled back
    lst.refresh_from_db()
    assert lst.rating_current == initial_rating
    assert lst.credits_current == initial_credits
    assert ListAction.objects.filter(list=lst).count() == initial_action_count
    assert ListFighterEquipmentAssignment.objects.count() == initial_assignment_count
