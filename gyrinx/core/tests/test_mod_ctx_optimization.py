import pytest

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentModFighterStat,
    ContentStat,
)
from gyrinx.core.models import List, ListFighter, ListFighterEquipmentAssignment
from gyrinx.core.models.util import ModContext
from gyrinx.models import FighterCategoryChoices
from gyrinx.query import capture_queries


@pytest.mark.django_db
def test_mod_ctx_statline_uses_prefetched_stats(user, content_house):
    """Test that statline generation uses prefetched ContentStats via ModContext."""
    # Ensure we have the ContentStats we need
    ContentStat.objects.get_or_create(
        field_name="weapon_skill",
        defaults={
            "short_name": "WS",
            "full_name": "Weapon Skill",
            "is_inverted": True,
            "is_target": True,
        },
    )
    ContentStat.objects.get_or_create(
        field_name="ballistic_skill",
        defaults={
            "short_name": "BS",
            "full_name": "Ballistic Skill",
            "is_inverted": True,
            "is_target": True,
        },
    )

    # Create a fighter with some equipment that applies mods
    fighter = ContentFighter.objects.create(
        type="Test Leader",
        house=content_house,
        category=FighterCategoryChoices.LEADER,
        base_cost=100,
        movement='4"',
        weapon_skill="4+",
        ballistic_skill="3+",
        strength="3",
        toughness="3",
        wounds="2",
        initiative="4+",
        attacks="1",
        leadership="7+",
        cool="6+",
        willpower="7+",
        intelligence="8+",
    )

    # Create equipment category
    equipment_category = ContentEquipmentCategory.objects.create(
        name="Weapons",
    )

    # Create equipment with mods
    equipment = ContentEquipment.objects.create(
        name="Test Gun",
        category=equipment_category,
    )

    # Create mods
    ws_mod = ContentModFighterStat.objects.create(
        stat="weapon_skill",
        mode="improve",
        value="1",
    )
    bs_mod = ContentModFighterStat.objects.create(
        stat="ballistic_skill",
        mode="improve",
        value="1",
    )

    # Add mods directly to the equipment
    equipment.modifiers.add(ws_mod, bs_mod)

    # Create list and fighter
    test_list = List.objects.create(
        owner=user, name="Test List", content_house=content_house
    )
    list_fighter = ListFighter.objects.create(
        list=test_list,
        content_fighter=fighter,
        name="Test Fighter",
    )

    # Assign equipment to fighter
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=equipment,
    )

    # Test statline generation with query tracking
    def get_statline():
        # Clear the internal cache to force fresh queries
        if hasattr(list_fighter, "_statline_cache"):
            del list_fighter._statline_cache
        return list_fighter.statline

    # Capture queries
    statline, info = capture_queries(get_statline)

    # Count ContentStat queries
    # Note that we use "content_contentstat" to avoid matching content_contentstatline
    contentstat_queries = [
        q for q in info.queries if '"content_contentstat"' in q["sql"]
    ]

    # Should have exactly one ContentStat query that fetches all stats
    assert len(contentstat_queries) == 1, (
        f"Expected one ContentStat query, but got {len(contentstat_queries)}"
    )

    # Verify the statline was modified correctly
    ws_stat = next(s for s in statline if s.field_name == "weapon_skill")
    bs_stat = next(s for s in statline if s.field_name == "ballistic_skill")

    # WS should be improved from 4+ to 3+
    assert ws_stat.value == "3+", f"Expected WS 3+, got {ws_stat.value}"
    assert ws_stat.modded is True

    # BS should be improved from 3+ to 2+
    assert bs_stat.value == "2+", f"Expected BS 2+, got {bs_stat.value}"
    assert bs_stat.modded is True


@pytest.mark.django_db
def test_mod_ctx_apply_with_context():
    """Test that ContentModStatApplyMixin.apply() correctly uses mod_ctx."""
    # Create a ContentStat entry
    ContentStat.objects.get_or_create(
        field_name="weapon_skill",
        defaults={
            "short_name": "WS",
            "full_name": "Weapon Skill",
            "is_inverted": True,
            "is_target": True,
        },
    )

    # Create a mod
    mod = ContentModFighterStat.objects.create(
        stat="weapon_skill",
        mode="improve",
        value="1",
    )

    # Create mod context with prefetched stats
    mod_ctx = ModContext(
        all_stats={
            "weapon_skill": {
                "field_name": "weapon_skill",
                "is_inverted": True,
                "is_inches": False,
                "is_modifier": False,
                "is_target": True,
            }
        }
    )

    # Apply without context - should hit the database
    def apply_without_context():
        return mod.apply("4+")

    # Apply with context - should use cached data
    def apply_with_context():
        return mod.apply("4+", mod_ctx=mod_ctx)

    # Both should produce the same result
    result_without, info_without = capture_queries(apply_without_context)
    result_with, info_with = capture_queries(apply_with_context)

    assert result_without == "3+", f"Expected '3+', got '{result_without}'"
    assert result_with == "3+", f"Expected '3+', got '{result_with}'"

    # With context should have no ContentStat queries
    contentstat_queries_with = sum(
        1 for q in info_with.queries if "content_contentstat" in q["sql"]
    )
    contentstat_queries_without = sum(
        1 for q in info_without.queries if "content_contentstat" in q["sql"]
    )

    assert contentstat_queries_with == 0, (
        f"Expected 0 ContentStat queries with mod_ctx, got {contentstat_queries_with}"
    )
    assert contentstat_queries_without == 1, (
        f"Expected 1 ContentStat query without mod_ctx, got {contentstat_queries_without}"
    )


@pytest.mark.django_db
def test_mod_ctx_with_missing_stat():
    """Test that mod_ctx gracefully handles missing stats."""
    # Create a mod for a stat that's not in the context
    mod = ContentModFighterStat.objects.create(
        stat="some_new_stat",
        mode="improve",
        value="1",
    )

    # Create mod context without this stat
    mod_ctx = ModContext(
        all_stats={
            "weapon_skill": {
                "field_name": "weapon_skill",
                "is_inverted": True,
                "is_inches": False,
                "is_modifier": False,
                "is_target": True,
            }
        }
    )

    # Should fall back to defaults when stat is not in context
    result = mod.apply("5", mod_ctx=mod_ctx)
    assert result == "6"  # Default behavior for non-inverted stat


@pytest.mark.django_db
def test_list_fighter_statline_query_count(user, content_house):
    """Test the overall query count for ListFighter.statline with multiple mods."""
    # Create multiple ContentStats
    stats_to_create = [
        ("weapon_skill", "WS", "Weapon Skill", True, False, False, True),
        ("ballistic_skill", "BS", "Ballistic Skill", True, False, False, True),
        ("strength", "S", "Strength", False, False, False, False),
        ("toughness", "T", "Toughness", False, False, False, False),
        ("wounds", "W", "Wounds", False, False, False, False),
        ("initiative", "I", "Initiative", True, False, False, True),
        ("attacks", "A", "Attacks", False, False, False, False),
        ("leadership", "Ld", "Leadership", True, False, False, True),
        ("cool", "Cl", "Cool", True, False, False, True),
        ("willpower", "Wil", "Willpower", True, False, False, True),
        ("intelligence", "Int", "Intelligence", True, False, False, True),
    ]

    for (
        field_name,
        short_name,
        full_name,
        is_inv,
        is_inch,
        is_mod,
        is_tgt,
    ) in stats_to_create:
        ContentStat.objects.get_or_create(
            field_name=field_name,
            defaults={
                "short_name": short_name,
                "full_name": full_name,
                "is_inverted": is_inv,
                "is_inches": is_inch,
                "is_modifier": is_mod,
                "is_target": is_tgt,
            },
        )

    # Create a fighter
    fighter = ContentFighter.objects.create(
        type="Test Leader",
        house=content_house,
        category=FighterCategoryChoices.LEADER,
        base_cost=100,
        movement='5"',
        weapon_skill="4+",
        ballistic_skill="3+",
        strength="3",
        toughness="3",
        wounds="2",
        initiative="4+",
        attacks="2",
        leadership="7+",
        cool="6+",
        willpower="7+",
        intelligence="8+",
    )

    # Create equipment category
    equipment_category = ContentEquipmentCategory.objects.create(
        name="Weapons",
    )

    # Create multiple equipment items with mods
    equipment_items = []
    for i in range(3):
        equipment = ContentEquipment.objects.create(
            name=f"Test Equipment {i}",
            category=equipment_category,
        )
        equipment_items.append(equipment)

        # Add various mods
        ws_mod = ContentModFighterStat.objects.create(
            stat="weapon_skill",
            mode="improve",
            value="1",
        )
        str_mod = ContentModFighterStat.objects.create(
            stat="strength",
            mode="improve",
            value="1",
        )
        # Add mods to equipment
        equipment.modifiers.add(ws_mod, str_mod)

    # Create list and fighter
    test_list = List.objects.create(
        owner=user, name="Test List", content_house=content_house
    )
    list_fighter = ListFighter.objects.create(
        list=test_list,
        content_fighter=fighter,
        name="Test Fighter",
    )

    # Assign all equipment to fighter
    for equipment in equipment_items:
        ListFighterEquipmentAssignment.objects.create(
            list_fighter=list_fighter,
            content_equipment=equipment,
        )

    # Get statline and measure queries
    def get_fighter_statline():
        # Clear cache to ensure fresh queries
        if hasattr(list_fighter, "_statline_cache"):
            del list_fighter._statline_cache
        return list_fighter.statline

    result, info = capture_queries(get_fighter_statline)

    # Count different types of queries
    contentstat_queries = sum(
        1 for q in info.queries if "content_contentstat" in q["sql"]
    )

    # We should have at most 2 ContentStat queries (the prefetch and maybe a statline check)
    assert contentstat_queries <= 2, (
        f"Expected at most 2 ContentStat queries, got {contentstat_queries}. "
        f"This suggests the mod_ctx optimization is not working correctly."
    )

    # Verify the statline was modified correctly
    statline = result
    ws_stat = next(s for s in statline if s.field_name == "weapon_skill")
    strength_stat = next(s for s in statline if s.field_name == "strength")

    # WS should be improved from 4+ to 1+ (3 improvements)
    assert ws_stat.value == "1+", f"Expected WS 1+, got {ws_stat.value}"
    assert ws_stat.modded is True

    # Strength should be improved from 3 to 6 (3 improvements)
    assert strength_stat.value == "6", f"Expected S 6, got {strength_stat.value}"
    assert strength_stat.modded is True
