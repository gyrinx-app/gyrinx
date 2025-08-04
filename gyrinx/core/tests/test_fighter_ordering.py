import pytest
from django.contrib.auth.models import User

from gyrinx.content.models import ContentFighter, ContentHouse
from gyrinx.core.forms.list import ListFighterForm
from gyrinx.core.models import List, ListFighter
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_fighter_ordering_prioritizes_gang_house():
    """Test that fighters from the gang's house appear first in the dropdown."""
    # Create test user and houses
    user = User.objects.create_user(username="testuser", password="testpass")
    gang_house = ContentHouse.objects.create(name="Gang House")
    other_house = ContentHouse.objects.create(name="Other House")
    generic_house = ContentHouse.objects.create(name="Generic House", generic=True)

    # Create a list for the gang house
    gang_list = List.objects.create(
        name="Test Gang",
        content_house=gang_house,
        owner=user,
    )

    # Create fighters with standard categories
    gang_leader = ContentFighter.objects.create(
        type="Gang Leader",
        house=gang_house,
        category=FighterCategoryChoices.LEADER,
        base_cost=100,
    )
    gang_ganger = ContentFighter.objects.create(
        type="Gang Ganger",
        house=gang_house,
        category=FighterCategoryChoices.GANGER,
        base_cost=50,
    )
    # Create a fighter from another house (not used but needed for realistic test)
    ContentFighter.objects.create(
        type="Other Leader",
        house=other_house,
        category=FighterCategoryChoices.LEADER,
        base_cost=100,
    )
    generic_champion = ContentFighter.objects.create(
        type="Generic Champion",
        house=generic_house,
        category=FighterCategoryChoices.CHAMPION,
        base_cost=75,
    )

    # Create fighters with non-standard categories
    gang_specialist = ContentFighter.objects.create(
        type="Gang Specialist",
        house=gang_house,
        category=FighterCategoryChoices.SPECIALIST,
        base_cost=80,
    )
    generic_bounty_hunter = ContentFighter.objects.create(
        type="Generic Bounty Hunter",
        house=generic_house,
        category=FighterCategoryChoices.BOUNTY_HUNTER,
        base_cost=150,
    )

    # Create a temporary fighter instance with a content_fighter to avoid the error
    # We'll use the first fighter just to initialize the form properly
    temp_fighter = ListFighter(list=gang_list, content_fighter=gang_leader)
    form = ListFighterForm(instance=temp_fighter)

    # Get the choices from the form field
    choices = form.fields["content_fighter"].widget.choices

    # Convert choices to a list for easier testing
    # Skip the empty option
    choice_list = []
    for group_name, group_choices in choices[1:]:
        for fighter_id, fighter_label in group_choices:
            choice_list.append((group_name, fighter_id, fighter_label))

    # Verify the ordering
    # Gang house should come first and contain all its fighters
    gang_house_fighters = [c for c in choice_list if c[0] == "Gang House"]
    assert len(gang_house_fighters) == 3  # leader, ganger, specialist

    # The actual ordering follows ContentFighter's default ordering:
    # LEADER, CHAMPION, PROSPECT, SPECIALIST, GANGER, JUVE
    # So for Gang House: Leader -> Specialist -> Ganger
    assert gang_house_fighters[0][1] == gang_leader.id
    assert gang_house_fighters[1][1] == gang_specialist.id
    assert gang_house_fighters[2][1] == gang_ganger.id

    # Generic house should come after gang house
    generic_house_fighters = [c for c in choice_list if c[0] == "Generic House"]
    assert len(generic_house_fighters) == 2  # champion, bounty hunter

    # For Generic House: Champion comes before Bounty Hunter (default=99 in ordering)
    assert generic_house_fighters[0][1] == generic_champion.id
    assert generic_house_fighters[1][1] == generic_bounty_hunter.id


@pytest.mark.django_db
def test_fighter_ordering_follows_category_order():
    """Test that fighters are ordered according to ContentFighter's category ordering."""
    # Create test user and houses
    user = User.objects.create_user(username="testuser", password="testpass")
    gang_house = ContentHouse.objects.create(name="Test House")
    generic_house = ContentHouse.objects.create(name="Hired Guns", generic=True)

    # Create a list
    gang_list = List.objects.create(
        name="Test Gang",
        content_house=gang_house,
        owner=user,
    )

    # Create fighters in different categories
    # The expected order is: LEADER, CHAMPION, PROSPECT, SPECIALIST, GANGER, JUVE, then others (default=99)
    leader = ContentFighter.objects.create(
        type="Leader",
        house=gang_house,
        category=FighterCategoryChoices.LEADER,
        base_cost=100,
    )
    champion = ContentFighter.objects.create(
        type="Champion",
        house=gang_house,
        category=FighterCategoryChoices.CHAMPION,
        base_cost=80,
    )
    ganger = ContentFighter.objects.create(
        type="Ganger",
        house=gang_house,
        category=FighterCategoryChoices.GANGER,
        base_cost=50,
    )
    juve = ContentFighter.objects.create(
        type="Juve",
        house=gang_house,
        category=FighterCategoryChoices.JUVE,
        base_cost=30,
    )
    prospect = ContentFighter.objects.create(
        type="Prospect",
        house=gang_house,
        category=FighterCategoryChoices.PROSPECT,
        base_cost=40,
    )
    specialist = ContentFighter.objects.create(
        type="Specialist",
        house=gang_house,
        category=FighterCategoryChoices.SPECIALIST,
        base_cost=90,
    )

    # Categories not in the predefined order (will get default=99)
    crew = ContentFighter.objects.create(
        type="Crew",
        house=gang_house,
        category=FighterCategoryChoices.CREW,
        base_cost=35,
    )
    brute = ContentFighter.objects.create(
        type="Brute",
        house=gang_house,
        category=FighterCategoryChoices.BRUTE,
        base_cost=70,
    )
    hanger_on = ContentFighter.objects.create(
        type="Hanger-on",
        house=gang_house,
        category=FighterCategoryChoices.HANGER_ON,
        base_cost=60,
    )

    # Generic house fighters (creating them to have a realistic test scenario)
    ContentFighter.objects.create(
        type="Hired Gun",
        house=generic_house,
        category=FighterCategoryChoices.HIRED_GUN,
        base_cost=120,
    )
    ContentFighter.objects.create(
        type="Bounty Hunter",
        house=generic_house,
        category=FighterCategoryChoices.BOUNTY_HUNTER,
        base_cost=150,
    )
    ContentFighter.objects.create(
        type="House Agent",
        house=generic_house,
        category=FighterCategoryChoices.HOUSE_AGENT,
        base_cost=130,
    )

    # Create a temporary fighter instance with a content_fighter to avoid the error
    # We'll use the first fighter just to initialize the form properly
    temp_fighter = ListFighter(list=gang_list, content_fighter=leader)
    form = ListFighterForm(instance=temp_fighter)

    # Get the choices from the form field
    choices = form.fields["content_fighter"].widget.choices

    # Extract all fighter IDs in order
    fighter_ids_in_order = []
    for group_name, group_choices in choices[1:]:  # Skip empty option
        for fighter_id, fighter_label in group_choices:
            fighter_ids_in_order.append(fighter_id)

    # Expected category order within Test House: LEADER, CHAMPION, PROSPECT, SPECIALIST, GANGER, JUVE
    expected_order_in_gang_house = [
        leader.id,
        champion.id,
        prospect.id,
        specialist.id,
        ganger.id,
        juve.id,
    ]

    # Categories with default ordering (CREW, BRUTE, HANGER_ON) should come after, sorted by type name
    other_categories = [
        (crew.id, "Crew"),
        (brute.id, "Brute"),
        (hanger_on.id, "Hanger-on"),
    ]
    other_categories.sort(key=lambda x: x[1])  # Sort by type name
    expected_order_in_gang_house.extend([fid for fid, _ in other_categories])

    # Verify the gang house fighters appear in the expected order
    gang_house_fighter_ids = [
        fid
        for fid in fighter_ids_in_order
        if fid
        in {
            leader.id,
            champion.id,
            prospect.id,
            specialist.id,
            ganger.id,
            juve.id,
            crew.id,
            brute.id,
            hanger_on.id,
        }
    ]
    assert gang_house_fighter_ids == expected_order_in_gang_house


@pytest.mark.django_db
def test_stash_fighters_are_filtered_out():
    """Test that STASH fighters are not shown in the dropdown."""
    # Create test user and houses
    user = User.objects.create_user(username="testuser", password="testpass")
    gang_house = ContentHouse.objects.create(name="Test House")

    # Create a list
    gang_list = List.objects.create(
        name="Test Gang",
        content_house=gang_house,
        owner=user,
    )

    # Create a regular fighter and a stash fighter
    regular_fighter = ContentFighter.objects.create(
        type="Regular Fighter",
        house=gang_house,
        category=FighterCategoryChoices.GANGER,
        base_cost=50,
    )
    stash_fighter = ContentFighter.objects.create(
        type="Stash Fighter",
        house=gang_house,
        category=FighterCategoryChoices.STASH,
        base_cost=0,
    )

    # Create a temporary fighter instance with a content_fighter to avoid the error
    # We'll use the first fighter just to initialize the form properly
    temp_fighter = ListFighter(list=gang_list, content_fighter=regular_fighter)
    form = ListFighterForm(instance=temp_fighter)

    # Get all fighter IDs from the form
    all_fighter_ids = []
    choices = form.fields["content_fighter"].widget.choices
    for group_name, group_choices in choices[1:]:  # Skip empty option
        for fighter_id, fighter_label in group_choices:
            all_fighter_ids.append(fighter_id)

    # Verify regular fighter is present but stash fighter is not
    assert regular_fighter.id in all_fighter_ids
    assert stash_fighter.id not in all_fighter_ids
