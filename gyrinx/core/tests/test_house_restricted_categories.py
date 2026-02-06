"""Tests for house-restricted equipment category filtering.

Ensures that equipment categories restricted to specific houses (via
ContentEquipmentCategory.restricted_to) are excluded from default
selections but remain available for users to opt-in via the UI.
"""

import pytest
from django.test import Client
from django.urls import reverse
from urllib.parse import urlparse, parse_qs

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentFighterEquipmentListItem,
    ContentHouse,
)
from gyrinx.core.models.list import ListFighter
from gyrinx.models import FighterCategoryChoices


@pytest.fixture
def venator_house():
    """A house with can_buy_any=True (like Venators)."""
    return ContentHouse.objects.create(name="Venator Band", can_buy_any=True)


@pytest.fixture
def squat_house():
    """A separate house (like Ironhead Squat Prospectors)."""
    return ContentHouse.objects.create(name="Ironhead Squat Prospectors")


@pytest.fixture
def ancestry_category():
    """An equipment category restricted to the squat house."""
    cat, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Ancestry",
        defaults={"group": "Gear"},
    )
    return cat


@pytest.fixture
def gear_category():
    """A normal unrestricted equipment category."""
    cat, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Personal Equipment",
        defaults={"group": "Gear"},
    )
    return cat


@pytest.fixture
def ancestry_category_restricted(ancestry_category, squat_house):
    """Set up the ancestry category as restricted to the squat house."""
    ancestry_category.restricted_to.add(squat_house)
    return ancestry_category


@pytest.fixture
def squat_charter_master(squat_house):
    """A squat fighter type whose equipment list includes ancestry items."""
    return ContentFighter.objects.create(
        type="Squat Charter Master",
        category=FighterCategoryChoices.LEADER,
        house=squat_house,
        base_cost=200,
        movement='4"',
        weapon_skill="4+",
        ballistic_skill="4+",
        strength="4",
        toughness="4",
        wounds="2",
        initiative="4+",
        attacks="2",
        leadership="6+",
        cool="6+",
        willpower="6+",
        intelligence="6+",
    )


@pytest.fixture
def venator_hunt_leader(venator_house):
    """A venator fighter type."""
    return ContentFighter.objects.create(
        type="Venator Hunt Leader",
        category=FighterCategoryChoices.LEADER,
        house=venator_house,
        base_cost=150,
        movement='5"',
        weapon_skill="4+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="2",
        initiative="4+",
        attacks="2",
        leadership="6+",
        cool="6+",
        willpower="6+",
        intelligence="6+",
    )


@pytest.fixture
def ancestry_gear(ancestry_category_restricted):
    """Equipment in the Ancestry category."""
    return ContentEquipment.objects.create(
        name="Ancestral Heirloom",
        category=ancestry_category_restricted,
        rarity="E",
        cost="100",
    )


@pytest.fixture
def normal_gear(gear_category):
    """Equipment in an unrestricted category."""
    return ContentEquipment.objects.create(
        name="Filter Plugs",
        category=gear_category,
        rarity="C",
        cost="10",
    )


@pytest.fixture
def client(user):
    """Create a logged-in test client."""
    c = Client()
    c.login(username="testuser", password="password")
    return c


@pytest.mark.django_db
def test_house_restricted_categories_excluded_from_default_redirect(
    client,
    user,
    venator_house,
    venator_hunt_leader,
    squat_charter_master,
    ancestry_gear,
    normal_gear,
    ancestry_category_restricted,
    gear_category,
    make_list,
):
    """
    When a Venator (can_buy_any) fighter with a squat legacy views gear,
    the initial redirect should exclude house-restricted categories like
    Ancestry from the default cat selection.
    """
    # Create a list with the venator house
    lst = make_list("Venator List", content_house=venator_house)

    # Create a fighter with squat legacy
    fighter = ListFighter.objects.create(
        list=lst,
        name="Squat Legacy Hunter",
        owner=user,
        content_fighter=venator_hunt_leader,
        legacy_content_fighter=squat_charter_master,
    )

    # Add ancestry gear to the squat charter master's equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=squat_charter_master,
        equipment=ancestry_gear,
    )

    # Add normal gear to the venator's equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=venator_hunt_leader,
        equipment=normal_gear,
    )

    # Visit the gear edit page - should redirect with filter=all
    url = reverse("core:list-fighter-gear-edit", args=[lst.id, fighter.id])
    response = client.get(url)

    # Should get a redirect (default_to_all redirect)
    assert response.status_code == 302

    redirect_url = response.url
    parsed = urlparse(redirect_url)
    params = parse_qs(parsed.query)

    # Should have filter=all
    assert params.get("filter") == ["all"]

    # Should have cat parameter(s) that EXCLUDE the ancestry category
    assert "cat" in params, "Should have cat parameters in redirect"
    cat_ids = params["cat"]
    assert str(ancestry_category_restricted.id) not in cat_ids
    assert str(gear_category.id) in cat_ids


@pytest.mark.django_db
def test_house_restricted_categories_still_in_dropdown(
    client,
    user,
    venator_house,
    venator_hunt_leader,
    squat_charter_master,
    ancestry_gear,
    normal_gear,
    ancestry_category_restricted,
    gear_category,
    make_list,
):
    """
    House-restricted categories should still appear in the categories
    dropdown even when excluded from the default selection. This allows
    users to opt-in.
    """
    lst = make_list("Venator List", content_house=venator_house)
    fighter = ListFighter.objects.create(
        list=lst,
        name="Squat Legacy Hunter",
        owner=user,
        content_fighter=venator_hunt_leader,
        legacy_content_fighter=squat_charter_master,
    )

    ContentFighterEquipmentListItem.objects.create(
        fighter=squat_charter_master,
        equipment=ancestry_gear,
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=venator_hunt_leader,
        equipment=normal_gear,
    )

    # Follow the initial redirect to get the actual page
    url = reverse("core:list-fighter-gear-edit", args=[lst.id, fighter.id])
    response = client.get(url)
    assert response.status_code == 302

    # Follow redirect
    response = client.get(response.url)
    assert response.status_code == 200

    # The categories context should include both categories (for the dropdown)
    categories = list(response.context["categories"])
    category_ids = {cat.id for cat in categories}
    assert ancestry_category_restricted.id in category_ids
    assert gear_category.id in category_ids


@pytest.mark.django_db
def test_house_restricted_items_not_shown_by_default(
    client,
    user,
    venator_house,
    venator_hunt_leader,
    squat_charter_master,
    ancestry_gear,
    normal_gear,
    ancestry_category_restricted,
    make_list,
):
    """
    Ancestry items should not appear on the page after the default redirect.
    Normal gear should still appear.
    """
    lst = make_list("Venator List", content_house=venator_house)
    fighter = ListFighter.objects.create(
        list=lst,
        name="Squat Legacy Hunter",
        owner=user,
        content_fighter=venator_hunt_leader,
        legacy_content_fighter=squat_charter_master,
    )

    ContentFighterEquipmentListItem.objects.create(
        fighter=squat_charter_master,
        equipment=ancestry_gear,
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=venator_hunt_leader,
        equipment=normal_gear,
    )

    # Follow the full redirect chain
    url = reverse("core:list-fighter-gear-edit", args=[lst.id, fighter.id])
    response = client.get(url)
    assert response.status_code == 302
    response = client.get(response.url)
    assert response.status_code == 200

    content = response.content.decode()
    assert "Ancestral Heirloom" not in content
    assert "Filter Plugs" in content


@pytest.mark.django_db
def test_house_restricted_items_shown_when_user_opts_in(
    client,
    user,
    venator_house,
    venator_hunt_leader,
    squat_charter_master,
    ancestry_gear,
    normal_gear,
    ancestry_category_restricted,
    gear_category,
    make_list,
):
    """
    When the user explicitly includes the restricted category in the cat
    parameter, the ancestry items should be shown.
    """
    lst = make_list("Venator List", content_house=venator_house)
    fighter = ListFighter.objects.create(
        list=lst,
        name="Squat Legacy Hunter",
        owner=user,
        content_fighter=venator_hunt_leader,
        legacy_content_fighter=squat_charter_master,
    )

    ContentFighterEquipmentListItem.objects.create(
        fighter=squat_charter_master,
        equipment=ancestry_gear,
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=venator_hunt_leader,
        equipment=normal_gear,
    )

    # Visit with explicit cat values that include the ancestry category
    url = reverse("core:list-fighter-gear-edit", args=[lst.id, fighter.id])
    response = client.get(
        url,
        {
            "filter": "all",
            "cat": [str(ancestry_category_restricted.id), str(gear_category.id)],
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Ancestral Heirloom" in content
    assert "Filter Plugs" in content


@pytest.mark.django_db
def test_no_redirect_when_house_matches_restriction(
    client,
    user,
    squat_house,
    squat_charter_master,
    ancestry_gear,
    normal_gear,
    ancestry_category_restricted,
    gear_category,
    make_list,
):
    """
    When the list's house matches the category restriction (e.g. an
    Ironhead Squat list viewing Ancestry), no cat redirect should occur
    and ancestry items should be shown normally.
    """
    lst = make_list("Squat List", content_house=squat_house)
    fighter = ListFighter.objects.create(
        list=lst,
        name="Squat Fighter",
        owner=user,
        content_fighter=squat_charter_master,
    )

    ContentFighterEquipmentListItem.objects.create(
        fighter=squat_charter_master,
        equipment=ancestry_gear,
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=squat_charter_master,
        equipment=normal_gear,
    )

    # Visit gear page - should NOT redirect with cat params since
    # the squat house matches the ancestry restriction
    url = reverse("core:list-fighter-gear-edit", args=[lst.id, fighter.id])
    response = client.get(url)

    assert response.status_code == 200

    content = response.content.decode()
    # Both items should be visible for a matching house
    assert "Ancestral Heirloom" in content
    assert "Filter Plugs" in content


@pytest.mark.django_db
def test_non_can_buy_any_house_restricted_category_redirect(
    client,
    user,
    squat_charter_master,
    venator_hunt_leader,
    ancestry_gear,
    normal_gear,
    ancestry_category_restricted,
    gear_category,
    make_list,
    make_content_house,
):
    """
    For a non-can_buy_any house with legacy fighters that bring in
    house-restricted categories, the redirect should also exclude
    those categories from the default selection.
    """
    # Create a house without can_buy_any
    other_house = make_content_house("Other House")

    # Create a fighter for this house
    other_fighter = ContentFighter.objects.create(
        type="Other Fighter",
        category=FighterCategoryChoices.LEADER,
        house=other_house,
        base_cost=100,
        movement='5"',
        weapon_skill="4+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="7+",
        cool="7+",
        willpower="7+",
        intelligence="7+",
    )

    lst = make_list("Other List", content_house=other_house)
    fighter = ListFighter.objects.create(
        list=lst,
        name="Legacy Fighter",
        owner=user,
        content_fighter=other_fighter,
        legacy_content_fighter=squat_charter_master,
    )

    ContentFighterEquipmentListItem.objects.create(
        fighter=squat_charter_master,
        equipment=ancestry_gear,
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=other_fighter,
        equipment=normal_gear,
    )

    # Visit gear page - should redirect with cat excluding ancestry
    url = reverse("core:list-fighter-gear-edit", args=[lst.id, fighter.id])
    response = client.get(url)

    assert response.status_code == 302

    parsed = urlparse(response.url)
    params = parse_qs(parsed.query)

    assert "cat" in params
    cat_ids = params["cat"]
    assert str(ancestry_category_restricted.id) not in cat_ids
    assert str(gear_category.id) in cat_ids
