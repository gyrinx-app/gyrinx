"""Test equipment deletion with refund functionality."""

import pytest
from django.urls import reverse

from gyrinx.content.models import ContentEquipment, ContentEquipmentCategory
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import List


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_delete_equipment_with_refund_checked(
    client,
    user,
    make_list,
    make_list_fighter,
    make_equipment,
    settings,
    feature_flag_enabled,
):
    """Test deleting equipment with refund checkbox checked adds credits."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    # Create a campaign mode list
    lst = make_list("Test Gang", status=List.CAMPAIGN_MODE)
    lst.credits_current = 100
    lst.save(update_fields=["credits_current"])

    fighter = make_list_fighter(lst, "Fighter")

    # Get or create equipment
    basic_cat, _ = ContentEquipmentCategory.objects.get_or_create(name="Basic Weapons")
    weapon, _ = ContentEquipment.objects.get_or_create(
        name="Autogun", category=basic_cat, defaults={"cost": 15}
    )

    # Add weapon to fighter
    assignment = fighter.assign(weapon)

    # Set list rating to reflect the cost
    lst.rating_current = fighter.cost_int()
    lst.save(update_fields=["rating_current"])

    client.force_login(user)

    # Delete weapon with refund checked (checked by default)
    response = client.post(
        reverse(
            "core:list-fighter-weapon-delete", args=[lst.id, fighter.id, assignment.id]
        ),
        {"refund": "on"},
    )
    assert response.status_code == 302

    # Verify credits were added
    lst.refresh_from_db()
    assert lst.credits_current == 115  # 100 + 15

    # Verify ListAction was created with correct deltas
    if feature_flag_enabled:
        action = ListAction.objects.filter(
            list=lst, action_type=ListActionType.REMOVE_EQUIPMENT
        ).first()
        assert action is not None
        assert action.credits_delta == 15
        assert action.rating_delta == -15
        assert "refund applied" in action.description.lower()
    else:
        action = ListAction.objects.filter(
            list=lst, action_type=ListActionType.REMOVE_EQUIPMENT
        ).first()
        assert action is None


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_delete_equipment_with_refund_unchecked(
    client,
    user,
    make_list,
    make_list_fighter,
    make_equipment,
    settings,
    feature_flag_enabled,
):
    """Test deleting equipment with refund unchecked doesn't add credits."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    # Create a campaign mode list
    lst = make_list("Test Gang", status=List.CAMPAIGN_MODE)
    lst.credits_current = 100
    lst.save(update_fields=["credits_current"])

    fighter = make_list_fighter(lst, "Fighter")

    # Get or create equipment
    basic_cat, _ = ContentEquipmentCategory.objects.get_or_create(name="Basic Weapons")
    weapon, _ = ContentEquipment.objects.get_or_create(
        name="Autogun", category=basic_cat, defaults={"cost": 15}
    )

    # Add weapon to fighter
    assignment = fighter.assign(weapon)

    # Set list rating to reflect the cost
    lst.rating_current = fighter.cost_int()
    lst.save(update_fields=["rating_current"])

    client.force_login(user)

    # Delete weapon without refund (don't send the checkbox)
    response = client.post(
        reverse(
            "core:list-fighter-weapon-delete", args=[lst.id, fighter.id, assignment.id]
        ),
        # No refund parameter means unchecked
    )
    assert response.status_code == 302

    # Verify credits were NOT added
    lst.refresh_from_db()
    assert lst.credits_current == 100  # Unchanged

    # Verify ListAction was created with zero credits_delta
    if feature_flag_enabled:
        action = ListAction.objects.filter(
            list=lst, action_type=ListActionType.REMOVE_EQUIPMENT
        ).first()
        assert action is not None
        assert action.credits_delta == 0
        assert action.rating_delta == -15
        assert "refund" not in action.description.lower()
    else:
        action = ListAction.objects.filter(
            list=lst, action_type=ListActionType.REMOVE_EQUIPMENT
        ).first()
        assert action is None


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_delete_equipment_refund_only_in_campaign_mode(
    client,
    user,
    make_list,
    make_list_fighter,
    make_equipment,
    settings,
    feature_flag_enabled,
):
    """Test that refund is only applied in campaign mode."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    # Create a list building mode list
    lst = make_list("Test Gang", status=List.LIST_BUILDING)
    lst.credits_current = 100
    lst.save(update_fields=["credits_current"])

    fighter = make_list_fighter(lst, "Fighter")

    # Get or create equipment
    basic_cat, _ = ContentEquipmentCategory.objects.get_or_create(name="Basic Weapons")
    weapon, _ = ContentEquipment.objects.get_or_create(
        name="Autogun", category=basic_cat, defaults={"cost": 15}
    )

    # Add weapon to fighter
    assignment = fighter.assign(weapon)

    # Set list rating to reflect the cost
    lst.rating_current = fighter.cost_int()
    lst.save(update_fields=["rating_current"])

    client.force_login(user)

    # Try to delete weapon with refund (should be ignored in non-campaign mode)
    response = client.post(
        reverse(
            "core:list-fighter-weapon-delete", args=[lst.id, fighter.id, assignment.id]
        ),
        {"refund": "on"},
    )
    assert response.status_code == 302

    # Verify credits were NOT added (not in campaign mode)
    lst.refresh_from_db()
    assert lst.credits_current == 100  # Unchanged

    # Verify ListAction was created with zero credits_delta
    if feature_flag_enabled:
        action = ListAction.objects.filter(
            list=lst, action_type=ListActionType.REMOVE_EQUIPMENT
        ).first()
        assert action is not None
        assert action.credits_delta == 0
        assert "refund" not in action.description.lower()
    else:
        action = ListAction.objects.filter(
            list=lst, action_type=ListActionType.REMOVE_EQUIPMENT
        ).first()
        assert action is None


@pytest.mark.django_db
def test_delete_equipment_refund_when_actions_disabled(
    client, user, make_list, make_list_fighter, make_equipment
):
    """Test that refund still works when list actions are disabled (no latest_action)."""
    # Create a campaign mode list WITHOUT initial action (actions disabled)
    lst = make_list("Test Gang", status=List.CAMPAIGN_MODE, create_initial_action=False)
    lst.credits_current = 100
    lst.save(update_fields=["credits_current"])

    # Verify actions are disabled
    assert lst.latest_action is None

    fighter = make_list_fighter(lst, "Fighter")

    # Get or create equipment
    basic_cat, _ = ContentEquipmentCategory.objects.get_or_create(name="Basic Weapons")
    weapon, _ = ContentEquipment.objects.get_or_create(
        name="Autogun", category=basic_cat, defaults={"cost": 15}
    )

    # Add weapon to fighter
    assignment = fighter.assign(weapon)

    # Set list rating to reflect the cost
    lst.rating_current = fighter.cost_int()
    lst.save(update_fields=["rating_current"])

    client.force_login(user)

    # Delete weapon with refund checked
    response = client.post(
        reverse(
            "core:list-fighter-weapon-delete", args=[lst.id, fighter.id, assignment.id]
        ),
        {"refund": "on"},
    )
    assert response.status_code == 302

    # Verify credits were STILL added despite actions being disabled
    lst.refresh_from_db()
    assert lst.credits_current == 115  # 100 + 15

    # Verify no ListAction was created (actions disabled)
    action = ListAction.objects.filter(
        list=lst, action_type=ListActionType.REMOVE_EQUIPMENT
    ).first()
    assert action is None
