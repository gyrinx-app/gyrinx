import pytest
from django.urls import reverse

from gyrinx.content.models import (
    ContentEquipmentUpgrade,
    ContentFighter,
    ContentWeaponAccessory,
)
from gyrinx.core.models.campaign import Campaign, CampaignAction
from gyrinx.core.models.list import List, ListFighter, ListFighterEquipmentAssignment


@pytest.mark.django_db
def test_sell_equipment_requires_stash_fighter(
    client, user, make_list, make_list_fighter, make_equipment
):
    """Test that only stash fighters can sell equipment."""
    client.force_login(user)

    # Create a campaign list with regular fighter
    campaign = Campaign.objects.create(name="Test Campaign", owner=user)
    lst = make_list("Test List", campaign=campaign, status=List.CAMPAIGN_MODE)
    fighter = make_list_fighter(lst, "Regular Fighter")

    # Add equipment
    equipment = make_equipment("Test Gun", cost=50)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    # Try to access sell page
    url = reverse(
        "core:list-fighter-equipment-sell", args=[lst.id, fighter.id, assignment.id]
    )
    response = client.get(url)

    # Should redirect with error message
    assert response.status_code == 302
    assert response.url == reverse(
        "core:list-fighter-gear-edit", args=[lst.id, fighter.id]
    )


@pytest.fixture
def make_stash_fighter(user, content_house):
    """Create a stash fighter for testing."""

    def _make_stash_fighter(list_):
        # Create stash content fighter
        stash_content = ContentFighter.objects.create(
            type="Stash",
            category="STASH",
            base_cost=0,
            is_stash=True,
            house=content_house,
        )

        # Create stash list fighter
        return ListFighter.objects.create(
            name="Gang Stash",
            content_fighter=stash_content,
            list=list_,
        )

    return _make_stash_fighter


@pytest.mark.django_db
def test_sell_equipment_requires_campaign_mode(
    client, user, make_list, make_stash_fighter, make_equipment
):
    """Test that equipment can only be sold in campaign mode."""
    client.force_login(user)

    # Create non-campaign list with stash fighter
    lst = make_list("Test List", status=List.LIST_BUILDING)
    stash = make_stash_fighter(lst)

    # Add equipment
    equipment = make_equipment("Test Gun", cost=50)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash,
        content_equipment=equipment,
    )

    # Try to access sell page
    url = reverse(
        "core:list-fighter-equipment-sell", args=[lst.id, stash.id, assignment.id]
    )
    response = client.get(url)

    # Should redirect with error message
    assert response.status_code == 302
    assert response.url == reverse(
        "core:list-fighter-gear-edit", args=[lst.id, stash.id]
    )


@pytest.mark.django_db
def test_sell_equipment_selection_form(
    client, user, make_list, make_stash_fighter, make_equipment
):
    """Test the equipment sell selection form displays correctly."""
    client.force_login(user)

    # Create campaign list with stash fighter
    campaign = Campaign.objects.create(name="Test Campaign", owner=user)
    lst = make_list("Test List", campaign=campaign, status=List.CAMPAIGN_MODE)
    stash = make_stash_fighter(lst)

    # Add equipment with upgrade
    equipment = make_equipment("Test Gun", cost=50)
    upgrade = ContentEquipmentUpgrade.objects.create(
        name="Extended Mag",
        equipment=equipment,
        cost=10,
    )

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash,
        content_equipment=equipment,
    )
    assignment.upgrades_field.add(upgrade)

    # Access sell page
    url = reverse(
        "core:list-fighter-equipment-sell", args=[lst.id, stash.id, assignment.id]
    )
    response = client.get(url + "?sell_assign=" + str(assignment.id))

    assert response.status_code == 200
    assert "Select Sale Price Method" in response.content.decode()
    assert "Test Gun" in response.content.decode()
    assert "60¢" in response.content.decode()  # 50 + 10 for upgrade


@pytest.mark.django_db
def test_sell_equipment_with_dice_roll_auto(
    client, user, make_list, make_stash_fighter, make_equipment
):
    """Test selling equipment with automatic dice roll pricing."""
    client.force_login(user)

    # Create campaign list with stash fighter
    campaign = Campaign.objects.create(name="Test Campaign", owner=user)
    lst = make_list("Test List", campaign=campaign, status=List.CAMPAIGN_MODE)
    stash = make_stash_fighter(lst)

    # Add equipment
    equipment = make_equipment("Test Gun", cost=50)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash,
        content_equipment=equipment,
    )

    # Initial credits
    initial_credits = lst.credits_current

    # Submit selection form
    url = reverse(
        "core:list-fighter-equipment-sell", args=[lst.id, stash.id, assignment.id]
    )
    response = client.post(
        url + "?sell_assign=" + str(assignment.id),
        {
            "step": "selection",
            "0-price_method": "roll_auto",
        },
    )

    assert response.status_code == 302
    assert "step=confirm" in response.url

    # Confirm sale
    response = client.post(
        url,
        {
            "step": "confirm",
        },
        follow=True,
    )

    # Check that equipment was deleted
    assert not ListFighterEquipmentAssignment.objects.filter(id=assignment.id).exists()

    # Check credits were added
    lst.refresh_from_db()
    assert lst.credits_current > initial_credits
    assert lst.credits_current <= initial_credits + 50  # Max possible with dice
    assert lst.credits_current >= initial_credits + 5  # Min possible (5¢ minimum)

    # Check campaign action was created
    action = CampaignAction.objects.filter(campaign=campaign, list=lst).first()
    assert action is not None
    assert action.dice_count == 1
    assert len(action.dice_results) == 1
    assert "Sold equipment from stash" in action.description


@pytest.mark.django_db
def test_sell_equipment_with_dice_roll_manual(
    client, user, make_list, make_stash_fighter, make_equipment
):
    """Test selling equipment with manually rolled dice for cost."""
    client.force_login(user)

    # Create campaign list with stash fighter
    campaign = Campaign.objects.create(name="Test Campaign", owner=user)
    lst = make_list("Test List", campaign=campaign, status=List.CAMPAIGN_MODE)
    stash = make_stash_fighter(lst)

    # Add equipment
    equipment = make_equipment("Test Gun", cost=50)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash,
        content_equipment=equipment,
    )

    # Initial credits
    initial_credits = lst.credits_current

    # Submit selection form with manual D6 roll of 4
    url = reverse(
        "core:list-fighter-equipment-sell", args=[lst.id, stash.id, assignment.id]
    )
    response = client.post(
        url + "?sell_assign=" + str(assignment.id),
        {
            "step": "selection",
            "0-price_method": "roll_manual",
            "0-roll_manual_d6": "4",
        },
    )

    assert response.status_code == 302
    assert "step=confirm" in response.url

    # Confirm sale
    response = client.post(
        url,
        {
            "step": "confirm",
        },
        follow=True,
    )

    # Check that equipment was deleted
    assert not ListFighterEquipmentAssignment.objects.filter(id=assignment.id).exists()

    # Check credits were added (50 - 4×10 = 10¢)
    lst.refresh_from_db()
    assert lst.credits_current == initial_credits + 10

    # Check campaign action was created with correct D6 result
    action = CampaignAction.objects.filter(campaign=campaign, list=lst).first()
    assert action is not None
    assert action.dice_count == 1
    assert action.dice_results == [4]
    assert "Sold equipment from stash" in action.description


@pytest.mark.django_db
def test_sell_equipment_with_manual_price(
    client, user, make_list, make_stash_fighter, make_equipment
):
    """Test selling equipment with manual pricing."""
    client.force_login(user)

    # Create campaign list with stash fighter
    campaign = Campaign.objects.create(name="Test Campaign", owner=user)
    lst = make_list("Test List", campaign=campaign, status=List.CAMPAIGN_MODE)
    stash = make_stash_fighter(lst)

    # Add equipment
    equipment = make_equipment("Test Gun", cost=50)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash,
        content_equipment=equipment,
    )

    # Initial credits
    initial_credits = lst.credits_current

    # Submit selection form with manual price
    url = reverse(
        "core:list-fighter-equipment-sell", args=[lst.id, stash.id, assignment.id]
    )
    response = client.post(
        url + "?sell_assign=" + str(assignment.id),
        {
            "step": "selection",
            "0-price_method": "price_manual",
            "0-price_manual_value": "25",
        },
    )

    assert response.status_code == 302

    # Confirm sale
    response = client.post(
        url,
        {
            "step": "confirm",
        },
        follow=True,
    )

    # Check credits were added exactly
    lst.refresh_from_db()
    assert lst.credits_current == initial_credits + 25

    # Check campaign action
    action = CampaignAction.objects.filter(campaign=campaign, list=lst).first()
    assert action is not None
    assert action.dice_count == 0  # No dice for manual price
    assert "Test Gun (25¢)" in action.description


@pytest.mark.django_db
def test_sell_weapon_profiles_individually(
    client, user, make_list, make_stash_fighter, make_equipment, make_weapon_profile
):
    """Test selling individual weapon profiles."""
    client.force_login(user)

    # Create campaign list with stash fighter
    campaign = Campaign.objects.create(name="Test Campaign", owner=user)
    lst = make_list("Test List", campaign=campaign, status=List.CAMPAIGN_MODE)
    stash = make_stash_fighter(lst)

    # Add weapon with multiple profiles
    weapon = make_equipment("Multi-weapon", cost=30)
    profile1 = make_weapon_profile(weapon, name="Mode 1", cost=10)
    profile2 = make_weapon_profile(weapon, name="Mode 2", cost=20)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash,
        content_equipment=weapon,
    )
    assignment.weapon_profiles_field.add(profile1, profile2)

    # Sell only profile2
    url = reverse(
        "core:list-fighter-equipment-sell", args=[lst.id, stash.id, assignment.id]
    )
    response = client.post(
        url + f"?sell_profile={profile2.id}",
        {
            "step": "selection",
            "0-price_method": "price_manual",
            "0-price_manual_value": "15",
        },
    )

    assert response.status_code == 302

    # Confirm sale
    response = client.post(
        url,
        {
            "step": "confirm",
        },
        follow=True,
    )

    # Check that assignment still exists but profile2 is removed
    assignment.refresh_from_db()
    assert assignment.weapon_profiles_field.filter(id=profile1.id).exists()
    assert not assignment.weapon_profiles_field.filter(id=profile2.id).exists()

    # Check credits
    lst.refresh_from_db()
    assert lst.credits_earned == 15


@pytest.mark.django_db
def test_sell_accessories_individually(
    client, user, make_list, make_stash_fighter, make_equipment
):
    """Test selling individual weapon accessories."""
    client.force_login(user)

    # Create campaign list with stash fighter
    campaign = Campaign.objects.create(name="Test Campaign", owner=user)
    lst = make_list("Test List", campaign=campaign, status=List.CAMPAIGN_MODE)
    stash = make_stash_fighter(lst)

    # Add weapon with accessories
    weapon = make_equipment("Test Weapon", cost=30)
    accessory1 = ContentWeaponAccessory.objects.create(name="Scope", cost=15)
    accessory2 = ContentWeaponAccessory.objects.create(name="Laser", cost=10)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash,
        content_equipment=weapon,
    )
    assignment.weapon_accessories_field.add(accessory1, accessory2)

    # Sell only accessory1
    url = reverse(
        "core:list-fighter-equipment-sell", args=[lst.id, stash.id, assignment.id]
    )
    response = client.post(
        url + f"?sell_accessory={accessory1.id}",
        {
            "step": "selection",
            "0-price_method": "roll_auto",
        },
    )

    assert response.status_code == 302

    # Confirm sale
    response = client.post(
        url,
        {
            "step": "confirm",
        },
        follow=True,
    )

    # Check that assignment still exists but accessory1 is removed
    assignment.refresh_from_db()
    assert not assignment.weapon_accessories_field.filter(id=accessory1.id).exists()
    assert assignment.weapon_accessories_field.filter(id=accessory2.id).exists()


@pytest.mark.django_db
def test_sell_summary_page(client, user, make_list, make_stash_fighter, make_equipment):
    """Test the sale summary page shows correct information."""
    client.force_login(user)

    # Create campaign list with stash fighter
    campaign = Campaign.objects.create(name="Test Campaign", owner=user)
    lst = make_list("Test List", campaign=campaign, status=List.CAMPAIGN_MODE)
    stash = make_stash_fighter(lst)

    # Add equipment
    equipment = make_equipment("Test Gun", cost=50)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash,
        content_equipment=equipment,
    )

    # Complete the sale flow
    url = reverse(
        "core:list-fighter-equipment-sell", args=[lst.id, stash.id, assignment.id]
    )

    # Step 1: Selection
    response = client.post(
        url + "?sell_assign=" + str(assignment.id),
        {
            "step": "selection",
            "0-price_method": "price_manual",
            "0-price_manual_value": "30",
        },
    )

    # Step 2: Confirm
    response = client.post(
        url,
        {
            "step": "confirm",
        },
    )

    assert response.status_code == 302
    assert "step=summary" in response.url

    # Step 3: View summary
    response = client.get(url + "?step=summary")

    assert response.status_code == 200
    assert "Sale Complete" in response.content.decode()
    assert "30¢ has been added to your gang's credits" in response.content.decode()
    assert "Test Gun" in response.content.decode()
