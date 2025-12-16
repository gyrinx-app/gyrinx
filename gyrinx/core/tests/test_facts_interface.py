"""Tests for facts interface on cost-bearing models."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gyrinx.core.models import AssignmentFacts, FighterFacts, List, ListFacts


@pytest.mark.django_db
def test_assignment_facts_returns_none_when_dirty(
    user, make_list, content_fighter, make_equipment
):
    """Test that assignment.facts() returns None when dirty=True."""
    from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment

    lst = make_list("Test List")
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=100,
        dirty=False,
    )
    equipment = make_equipment("Test Equipment", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
        rating_current=50,
        dirty=True,  # Mark as dirty
    )

    # Facts should return None when dirty
    facts = assignment.facts()
    assert facts is None


@pytest.mark.django_db
def test_assignment_facts_returns_cached_when_clean(
    user, make_list, content_fighter, make_equipment
):
    """Test that assignment.facts() returns cached values when dirty=False."""
    from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment

    lst = make_list("Test List")
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=100,
        dirty=False,
    )
    equipment = make_equipment("Test Equipment", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
        rating_current=50,
        dirty=False,  # Mark as clean
    )

    # Facts should return cached value
    facts = assignment.facts()
    assert facts is not None
    assert isinstance(facts, AssignmentFacts)
    assert facts.rating == 50


@pytest.mark.django_db
def test_assignment_facts_from_db_calculates_correctly(
    user, make_list, content_fighter, make_equipment
):
    """Test that assignment.facts_from_db() calculates correctly."""
    from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment

    lst = make_list("Test List")
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=0,
        dirty=True,
    )
    equipment = make_equipment("Test Equipment", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
        rating_current=0,
        dirty=True,
    )

    # Calculate facts from DB
    facts = assignment.facts_from_db()

    # Should match cost_int()
    assert facts.rating == assignment.cost_int()
    assert facts.rating == 50


@pytest.mark.django_db
def test_assignment_facts_from_db_clears_dirty(
    user, make_list, content_fighter, make_equipment
):
    """Test that assignment.facts_from_db() clears dirty flag."""
    from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment

    lst = make_list("Test List")
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=0,
        dirty=True,
    )
    equipment = make_equipment("Test Equipment", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
        rating_current=0,
        dirty=True,
    )

    # Calculate facts from DB
    assignment.facts_from_db()

    # Refresh from DB to verify dirty was cleared
    assignment.refresh_from_db()
    assert assignment.dirty is False
    assert assignment.rating_current == 50


@pytest.mark.django_db
def test_assignment_facts_from_db_update_flag(
    user, make_list, content_fighter, make_equipment
):
    """Test that assignment.facts_from_db(update=False) doesn't save."""
    from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment

    lst = make_list("Test List")
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=0,
        dirty=True,
    )
    equipment = make_equipment("Test Equipment", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
        rating_current=0,
        dirty=True,
    )

    # Calculate facts without updating
    facts = assignment.facts_from_db(update=False)

    # Facts should be correct
    assert facts.rating == 50

    # But DB should not be updated
    assignment.refresh_from_db()
    assert assignment.dirty is True
    assert assignment.rating_current == 0


@pytest.mark.django_db
def test_fighter_facts_returns_none_when_dirty(user, make_list, content_fighter):
    """Test that fighter.facts() returns None when dirty=True."""
    from gyrinx.core.models.list import ListFighter

    lst = make_list("Test List")
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=100,
        dirty=True,  # Mark as dirty
    )

    # Facts should return None when dirty
    facts = fighter.facts()
    assert facts is None


@pytest.mark.django_db
def test_fighter_facts_returns_cached_when_clean(
    user, make_list, content_fighter, make_equipment
):
    """Test that fighter.facts() returns cached rating when dirty=False."""
    from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment

    lst = make_list("Test List")
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=150,  # 100 base + 50 equipment
        dirty=False,  # Mark as clean
    )
    equipment = make_equipment("Test Equipment", cost="50")
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
        rating_current=50,
        dirty=False,
    )

    # Facts should return cached rating only
    facts = fighter.facts()
    assert facts is not None
    assert isinstance(facts, FighterFacts)
    assert facts.rating == 150


@pytest.mark.django_db
def test_fighter_facts_from_db_calculates_correctly(
    user, make_list, content_fighter, make_equipment
):
    """Test that fighter.facts_from_db() calculates correctly."""
    from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment

    lst = make_list("Test List")
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=0,
        dirty=True,
    )
    equipment = make_equipment("Test Equipment", cost="50")
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
        rating_current=0,
        dirty=True,
    )

    # Calculate facts from DB
    facts = fighter.facts_from_db()

    # Should match cost_int()
    assert facts.rating == fighter.cost_int()


@pytest.mark.django_db
def test_fighter_facts_from_db_clears_dirty(user, make_list, content_fighter):
    """Test that fighter.facts_from_db() clears dirty flag."""
    from gyrinx.core.models.list import ListFighter

    lst = make_list("Test List")
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=0,
        dirty=True,
    )

    # Calculate facts from DB
    fighter.facts_from_db()

    # Refresh from DB to verify dirty was cleared
    fighter.refresh_from_db()
    assert fighter.dirty is False


@pytest.mark.django_db
def test_list_facts_returns_none_when_dirty(user, content_house, make_list):
    """Test that list.facts() returns None when dirty=True."""
    lst = make_list("Test List")
    lst.dirty = True
    lst.save()

    # Facts should return None when dirty
    facts = lst.facts()
    assert facts is None


@pytest.mark.django_db
def test_list_facts_returns_cached_when_clean(user, content_house, make_list):
    """Test that list.facts() returns cached values when dirty=False."""
    lst = make_list("Test List")
    lst.rating_current = 100
    lst.stash_current = 50
    lst.credits_current = 25
    lst.dirty = False
    lst.save()

    # Facts should return cached values
    facts = lst.facts()
    assert facts is not None
    assert isinstance(facts, ListFacts)
    assert facts.rating == 100
    assert facts.stash == 50
    assert facts.credits == 25
    assert facts.wealth == 175  # rating + stash + credits


@pytest.mark.django_db
def test_list_facts_from_db_calculates_correctly(
    user, make_list, content_fighter, make_equipment
):
    """Test that list.facts_from_db() calculates correctly."""
    from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment

    lst = make_list("Test List")
    lst.credits_current = 25

    # Create fighter with equipment
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    equipment = make_equipment("Test Equipment", cost="50")
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    # Calculate facts from DB
    facts = lst.facts_from_db()

    # Should calculate correctly
    expected_rating = fighter.cost_int()
    assert facts.rating == expected_rating
    assert facts.stash == 0  # No stash fighters
    assert facts.credits == 25
    assert facts.wealth == expected_rating + 25


@pytest.mark.django_db
def test_list_facts_from_db_clears_dirty(user, content_house, make_list):
    """Test that list.facts_from_db() clears dirty flag."""
    lst = make_list("Test List")
    lst.dirty = True
    lst.save()

    # Calculate facts from DB
    lst.facts_from_db()

    # Refresh from DB to verify dirty was cleared
    lst.refresh_from_db()
    assert lst.dirty is False


@pytest.mark.django_db
def test_list_facts_from_db_separates_stash(
    user, make_list, content_house, make_content_fighter, make_equipment
):
    """Test that list.facts_from_db() separates stash from rating."""
    from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment

    lst = make_list("Test List")

    # Create regular fighter
    regular_fighter = make_content_fighter(
        type="Leader",
        category="Leader",
        house=content_house,
        base_cost=100,
        is_stash=False,
    )
    fighter1 = ListFighter.objects.create(
        name="Regular Fighter",
        content_fighter=regular_fighter,
        list=lst,
        owner=user,
    )

    # Create stash fighter
    stash_fighter_template = make_content_fighter(
        type="Stash",
        category="Crew",
        house=content_house,
        base_cost=0,
        is_stash=True,
    )
    fighter2 = ListFighter.objects.create(
        name="Stash Fighter",
        content_fighter=stash_fighter_template,
        list=lst,
        owner=user,
    )

    # Add equipment to each
    equipment = make_equipment("Test Equipment", cost="50")
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter1,
        content_equipment=equipment,
    )
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter2,
        content_equipment=equipment,
    )

    # Calculate facts
    facts = lst.facts_from_db()

    # Regular fighter goes to rating
    assert facts.rating == fighter1.cost_int()

    # Stash fighter goes to stash
    assert facts.stash == fighter2.cost_int()


@pytest.mark.django_db
def test_list_facts_wealth_property(user, content_house, make_list):
    """Test that ListFacts.wealth property calculates correctly."""
    lst = make_list("Test List")
    lst.rating_current = 100
    lst.stash_current = 50
    lst.credits_current = 25
    lst.dirty = False
    lst.save()

    facts = lst.facts()
    assert facts.wealth == 175  # 100 + 50 + 25


@pytest.mark.django_db
def test_assignment_facts_immutable(user, make_list, content_fighter, make_equipment):
    """Test that AssignmentFacts is immutable (frozen dataclass)."""
    from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment

    lst = make_list("Test List")
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        dirty=False,
    )
    equipment = make_equipment("Test Equipment", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
        rating_current=50,
        dirty=False,
    )

    facts = assignment.facts()

    # Attempting to modify should raise an error
    with pytest.raises(AttributeError):
        facts.rating = 100


@pytest.mark.django_db
def test_fighter_facts_immutable(user, make_list, content_fighter):
    """Test that FighterFacts is immutable (frozen dataclass)."""
    from gyrinx.core.models.list import ListFighter

    lst = make_list("Test List")
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=100,
        dirty=False,
    )

    facts = fighter.facts()

    # Attempting to modify should raise an error
    with pytest.raises(AttributeError):
        facts.rating = 200


@pytest.mark.django_db
def test_list_facts_immutable(user, content_house, make_list):
    """Test that ListFacts is immutable (frozen dataclass)."""
    lst = make_list("Test List")
    lst.rating_current = 100
    lst.dirty = False
    lst.save()

    facts = lst.facts()

    # Attempting to modify should raise an error
    with pytest.raises(AttributeError):
        facts.rating = 200


@pytest.mark.django_db
def test_facts_from_db_without_prefetch_uses_queries(
    user, make_list, content_fighter, make_equipment
):
    """Test that facts_from_db() issues queries when data is not prefetched."""
    from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment

    lst = make_list("Test List")

    # Create 3 fighters with equipment
    for i in range(3):
        fighter = ListFighter.objects.create(
            name=f"Fighter {i}",
            content_fighter=content_fighter,
            list=lst,
            owner=user,
        )
        equipment = make_equipment(f"Equipment {i}", cost="50")
        ListFighterEquipmentAssignment.objects.create(
            list_fighter=fighter,
            content_equipment=equipment,
        )

    # Fetch list WITHOUT prefetch
    lst_fresh = List.objects.get(id=lst.id)

    # facts_from_db() should issue queries (1 for fighters, likely more for related data)
    with CaptureQueriesContext(connection) as context:
        facts = lst_fresh.facts_from_db(update=False)

    # Should have issued queries to fetch fighters and their data
    query_count = len(context.captured_queries)
    assert query_count > 0, "Expected queries without prefetch"
    assert facts.rating > 0


@pytest.mark.django_db
def test_facts_from_db_with_prefetch_avoids_queries(
    user, make_list, content_fighter, make_equipment
):
    """Test that facts_from_db() uses prefetched data and significantly reduces queries."""
    from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment

    lst = make_list("Test List")

    # Create 3 fighters with equipment
    for i in range(3):
        fighter = ListFighter.objects.create(
            name=f"Fighter {i}",
            content_fighter=content_fighter,
            list=lst,
            owner=user,
        )
        equipment = make_equipment(f"Equipment {i}", cost="50")
        ListFighterEquipmentAssignment.objects.create(
            list_fighter=fighter,
            content_equipment=equipment,
        )

    # Measure queries WITHOUT prefetch first
    lst_fresh = List.objects.get(id=lst.id)
    with CaptureQueriesContext(connection) as context_no_prefetch:
        facts_no_prefetch = lst_fresh.facts_from_db(update=False)
    queries_without_prefetch = len(context_no_prefetch.captured_queries)

    # Now fetch WITH prefetch (as views do)
    lst_prefetched = List.objects.with_related_data(with_fighters=True).get(id=lst.id)

    # facts_from_db() should use prefetched data and significantly reduce queries
    with CaptureQueriesContext(connection) as context:
        facts = lst_prefetched.facts_from_db(update=False)

    # Should have significantly fewer queries with prefetch
    # Note: Some queries for equipment cost override lookups may remain,
    # but the main N+1 for fighters and advancements should be eliminated
    query_count = len(context.captured_queries)
    assert query_count < queries_without_prefetch, (
        f"Expected fewer queries with prefetch. "
        f"Without: {queries_without_prefetch}, With: {query_count}"
    )
    assert query_count <= 6, (
        f"Expected at most 6 queries with prefetch (equipment overrides only), got {query_count}:\n"
        + "\n".join(q["sql"] for q in context.captured_queries)
    )
    assert facts.rating == facts_no_prefetch.rating


@pytest.mark.django_db
def test_facts_from_db_with_prefetch_filters_archived(
    user, make_list, content_fighter, make_equipment
):
    """Test that facts_from_db() correctly filters archived fighters with prefetch."""
    from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment

    lst = make_list("Test List")

    # Create 2 active fighters
    for i in range(2):
        fighter = ListFighter.objects.create(
            name=f"Active Fighter {i}",
            content_fighter=content_fighter,
            list=lst,
            owner=user,
        )
        equipment = make_equipment(f"Equipment {i}", cost="100")
        ListFighterEquipmentAssignment.objects.create(
            list_fighter=fighter,
            content_equipment=equipment,
        )

    # Create 1 archived fighter
    archived_fighter = ListFighter.objects.create(
        name="Archived Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        archived=True,
    )
    archived_equipment = make_equipment("Archived Equipment", cost="50")
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=archived_fighter,
        content_equipment=archived_equipment,
    )

    # Fetch with prefetch
    lst_prefetched = List.objects.with_related_data(with_fighters=True).get(id=lst.id)

    # Calculate facts - should exclude archived fighter
    facts = lst_prefetched.facts_from_db(update=False)

    # Should only include the 2 active fighters
    # Each has 100 base cost + 100 equipment = 200 per fighter = 400 total
    assert facts.rating == 400, f"Expected rating of 400, got {facts.rating}"
