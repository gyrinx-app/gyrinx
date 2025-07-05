import pytest
from django.contrib.auth.models import User

from gyrinx.content.models import ContentFighter, ContentHouse
from gyrinx.core.forms.list import ListFighterForm
from gyrinx.core.models import List
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
        name="Gang Leader",
        house=gang_house,
        category=FighterCategoryChoices.LEADER,
        cost=100,
    )
    gang_ganger = ContentFighter.objects.create(
        name="Gang Ganger",
        house=gang_house,
        category=FighterCategoryChoices.GANGER,
        cost=50,
    )
    # Create a fighter from another house (not used but needed for realistic test)
    ContentFighter.objects.create(
        name="Other Leader",
        house=other_house,
        category=FighterCategoryChoices.LEADER,
        cost=100,
    )
    generic_champion = ContentFighter.objects.create(
        name="Generic Champion",
        house=generic_house,
        category=FighterCategoryChoices.CHAMPION,
        cost=75,
    )

    # Create fighters with non-standard categories
    gang_specialist = ContentFighter.objects.create(
        name="Gang Specialist",
        house=gang_house,
        category=FighterCategoryChoices.SPECIALIST,
        cost=80,
    )
    generic_bounty_hunter = ContentFighter.objects.create(
        name="Generic Bounty Hunter",
        house=generic_house,
        category=FighterCategoryChoices.BOUNTY_HUNTER,
        cost=150,
    )

    # Create form instance
    form = ListFighterForm(instance=gang_list.fighters.model(list=gang_list))

    # Get the choices from the form field
    choices = form.fields["content_fighter"].widget.choices

    # Convert choices to a list for easier testing
    # Skip the empty option
    choice_list = []
    for group_name, group_choices in choices[1:]:
        for fighter_id, fighter_label in group_choices:
            choice_list.append((group_name, fighter_id, fighter_label))

    # Verify the ordering
    # First group should be gang's house with standard categories
    assert choice_list[0][0] == "Gang House"
    assert choice_list[0][1] in [gang_leader.id, gang_ganger.id]
    assert choice_list[1][0] == "Gang House"
    assert choice_list[1][1] in [gang_leader.id, gang_ganger.id]

    # Second group should be gang's house with non-standard categories
    assert choice_list[2][0] == "Gang House (Other)"
    assert choice_list[2][1] == gang_specialist.id

    # Third group should be generic house with standard categories
    assert choice_list[3][0] == "Generic House"
    assert choice_list[3][1] == generic_champion.id

    # Fourth group should be generic house with non-standard categories
    assert choice_list[4][0] == "Generic House (Other)"
    assert choice_list[4][1] == generic_bounty_hunter.id


@pytest.mark.django_db
def test_fighter_ordering_standard_vs_nonstandard():
    """Test that non-standard fighter categories are sorted to bottom within each house."""
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

    # Create a mix of standard and non-standard fighters
    # Standard categories
    leader = ContentFighter.objects.create(
        name="Leader",
        house=gang_house,
        category=FighterCategoryChoices.LEADER,
        cost=100,
    )
    champion = ContentFighter.objects.create(
        name="Champion",
        house=gang_house,
        category=FighterCategoryChoices.CHAMPION,
        cost=80,
    )
    ganger = ContentFighter.objects.create(
        name="Ganger",
        house=gang_house,
        category=FighterCategoryChoices.GANGER,
        cost=50,
    )
    juve = ContentFighter.objects.create(
        name="Juve",
        house=gang_house,
        category=FighterCategoryChoices.JUVE,
        cost=30,
    )
    prospect = ContentFighter.objects.create(
        name="Prospect",
        house=gang_house,
        category=FighterCategoryChoices.PROSPECT,
        cost=40,
    )
    crew = ContentFighter.objects.create(
        name="Crew",
        house=gang_house,
        category=FighterCategoryChoices.CREW,
        cost=35,
    )
    brute = ContentFighter.objects.create(
        name="Brute",
        house=gang_house,
        category=FighterCategoryChoices.BRUTE,
        cost=70,
    )
    hanger_on = ContentFighter.objects.create(
        name="Hanger-on",
        house=gang_house,
        category=FighterCategoryChoices.HANGER_ON,
        cost=60,
    )

    # Non-standard categories
    hired_gun = ContentFighter.objects.create(
        name="Hired Gun",
        house=generic_house,
        category=FighterCategoryChoices.HIRED_GUN,
        cost=120,
    )
    bounty_hunter = ContentFighter.objects.create(
        name="Bounty Hunter",
        house=generic_house,
        category=FighterCategoryChoices.BOUNTY_HUNTER,
        cost=150,
    )
    house_agent = ContentFighter.objects.create(
        name="House Agent",
        house=generic_house,
        category=FighterCategoryChoices.HOUSE_AGENT,
        cost=130,
    )
    specialist = ContentFighter.objects.create(
        name="Specialist",
        house=gang_house,
        category=FighterCategoryChoices.SPECIALIST,
        cost=90,
    )

    # Create form instance
    form = ListFighterForm(instance=gang_list.fighters.model(list=gang_list))

    # Get the choices from the form field
    choices = form.fields["content_fighter"].widget.choices

    # Extract all fighter IDs in order
    fighter_ids_in_order = []
    for group_name, group_choices in choices[1:]:  # Skip empty option
        for fighter_id, fighter_label in group_choices:
            fighter_ids_in_order.append(fighter_id)

    # Standard category fighters should come before non-standard
    standard_fighter_ids = {
        leader.id,
        champion.id,
        ganger.id,
        juve.id,
        prospect.id,
        crew.id,
        brute.id,
        hanger_on.id,
    }
    non_standard_fighter_ids = {
        hired_gun.id,
        bounty_hunter.id,
        house_agent.id,
        specialist.id,
    }

    # Find positions of standard and non-standard fighters
    standard_positions = [
        i for i, fid in enumerate(fighter_ids_in_order) if fid in standard_fighter_ids
    ]
    non_standard_positions = [
        i
        for i, fid in enumerate(fighter_ids_in_order)
        if fid in non_standard_fighter_ids
    ]

    # All standard fighters should appear before non-standard fighters
    if standard_positions and non_standard_positions:
        assert max(standard_positions) < min(non_standard_positions)
