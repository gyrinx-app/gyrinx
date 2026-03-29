"""
Tests for ruleline() and skilline() query counts.

Verifies that pack-aware prefetch optimizations work correctly,
eliminating N+1 query patterns when these methods are called on
fighters with pack-aware content.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gyrinx.content.models import (
    ContentFighter,
    ContentHouse,
    ContentRule,
    ContentSkill,
    ContentSkillCategory,
)
from gyrinx.core.models.list import List, ListFighter
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem
from gyrinx.models import FighterCategoryChoices

User = get_user_model()


def _add_to_pack(pack, content_obj):
    """Helper to add content to a pack via CustomContentPackItem."""
    ct = ContentType.objects.get_for_model(content_obj)
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=content_obj.pk
    )


@pytest.fixture
def pack_query_test_data(db):
    """Set up test data with pack content for query counting."""
    user = User.objects.create_user(username="packtest", password="testpass")

    house = ContentHouse.objects.create(name="Pack Test House")

    # Create a content pack and subscribe a list to it
    pack = CustomContentPack.objects.create(name="Test Pack", owner=user, listed=True)

    # Create base-game rules (not in any pack)
    base_rule1 = ContentRule.objects.create(name="Base Rule 1")
    base_rule2 = ContentRule.objects.create(name="Base Rule 2")

    # Create pack-only rules
    pack_rule1 = ContentRule.objects.create(name="Pack Rule 1")
    pack_rule2 = ContentRule.objects.create(name="Pack Rule 2")
    _add_to_pack(pack, pack_rule1)
    _add_to_pack(pack, pack_rule2)

    # Create base-game skills
    skill_cat = ContentSkillCategory.objects.create(name="Combat")
    base_skill1 = ContentSkill.objects.create(name="Base Skill 1", category=skill_cat)

    # Create pack-only skills
    pack_skill1 = ContentSkill.objects.create(name="Pack Skill 1", category=skill_cat)
    _add_to_pack(pack, pack_skill1)

    # Create fighter template with both base and pack rules/skills
    fighter_template = ContentFighter.objects.create(
        type="Ganger",
        house=house,
        category=FighterCategoryChoices.GANGER,
        base_cost=50,
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
    fighter_template.rules.add(base_rule1, base_rule2, pack_rule1)
    fighter_template.skills.add(base_skill1, pack_skill1)

    # Create list subscribed to the pack
    gang_list = List.objects.create(
        name="Pack Test Gang", content_house=house, owner=user
    )
    gang_list.packs.add(pack)

    # Create multiple fighters to expose N+1 patterns
    fighters = []
    for i in range(5):
        f = ListFighter.objects.create(
            name=f"Fighter {i + 1}",
            list=gang_list,
            content_fighter=fighter_template,
        )
        fighters.append(f)

    # Add a custom rule to one fighter
    fighters[0].custom_rules.add(base_rule2)
    # Add a skill to one fighter
    fighters[1].skills.add(base_skill1)

    # Clean cached values
    gang_list.facts_from_db(update=True)

    return {
        "user": user,
        "list": gang_list,
        "fighters": fighters,
        "pack": pack,
        "base_rules": [base_rule1, base_rule2],
        "pack_rules": [pack_rule1, pack_rule2],
        "base_skills": [base_skill1],
        "pack_skills": [pack_skill1],
    }


def _load_list_with_packs(gang_list):
    """Load a list with pack-aware fighter prefetches (as the view does)."""
    packs = CustomContentPack.objects.filter(
        subscribed_lists__id=gang_list.id, archived=False
    )
    return List.objects.with_related_data(with_fighters=True, packs=packs).get(
        id=gang_list.id
    )


@pytest.mark.django_db
def test_ruleline_zero_queries_with_prefetch(pack_query_test_data):
    """With pack-aware prefetch, ruleline() should issue zero additional queries."""
    gang_list = pack_query_test_data["list"]
    num_fighters = len(pack_query_test_data["fighters"])

    loaded_list = _load_list_with_packs(gang_list)
    fighters = list(loaded_list.listfighter_set.all())
    assert len(fighters) == num_fighters

    with CaptureQueriesContext(connection) as context:
        for fighter in fighters:
            result = fighter.ruleline
            assert len(result) > 0, f"Fighter {fighter.name} should have rules"

    query_count = len(context.captured_queries)
    print(f"\nruleline() queries for {num_fighters} fighters: {query_count}")

    assert query_count == 0, (
        f"Expected 0 queries with pack-aware prefetch, got {query_count}"
    )


@pytest.mark.django_db
def test_skilline_zero_queries_with_prefetch(pack_query_test_data):
    """With pack-aware prefetch, skilline() should issue zero additional queries."""
    gang_list = pack_query_test_data["list"]
    num_fighters = len(pack_query_test_data["fighters"])

    loaded_list = _load_list_with_packs(gang_list)
    fighters = list(loaded_list.listfighter_set.all())

    with CaptureQueriesContext(connection) as context:
        for fighter in fighters:
            result = fighter.skilline()
            assert len(result) > 0, f"Fighter {fighter.name} should have skills"

    query_count = len(context.captured_queries)
    print(f"\nskilline() queries for {num_fighters} fighters: {query_count}")

    assert query_count == 0, (
        f"Expected 0 queries with pack-aware prefetch, got {query_count}"
    )


@pytest.mark.django_db
def test_ruleline_correctness_with_packs(pack_query_test_data):
    """Verify ruleline() returns correct results including pack content."""
    gang_list = pack_query_test_data["list"]

    loaded_list = _load_list_with_packs(gang_list)
    fighter = list(loaded_list.listfighter_set.all())[0]
    rules = fighter.ruleline
    rule_names = [r.value for r in rules]

    # Should include base rules assigned to the fighter template
    assert "Base Rule 1" in rule_names
    assert "Base Rule 2" in rule_names

    # Should include pack rule assigned to the fighter template
    # (because the list is subscribed to the pack)
    assert "Pack Rule 1" in rule_names


@pytest.mark.django_db
def test_skilline_correctness_with_packs(pack_query_test_data):
    """Verify skilline() returns correct results including pack content."""
    gang_list = pack_query_test_data["list"]

    loaded_list = _load_list_with_packs(gang_list)
    fighter = list(loaded_list.listfighter_set.all())[0]
    skills = fighter.skilline()

    # Should include base skill
    assert "Base Skill 1" in skills

    # Should include pack skill (because list is subscribed)
    assert "Pack Skill 1" in skills


@pytest.mark.django_db
def test_ruleline_excludes_unsubscribed_pack_content(pack_query_test_data):
    """Verify ruleline() excludes pack content when list is not subscribed."""
    gang_list = pack_query_test_data["list"]

    # Remove pack subscription
    gang_list.packs.clear()

    loaded_list = _load_list_with_packs(gang_list)
    fighter = list(loaded_list.listfighter_set.all())[0]
    rules = fighter.ruleline
    rule_names = [r.value for r in rules]

    # Should still include base rules
    assert "Base Rule 1" in rule_names
    assert "Base Rule 2" in rule_names

    # Should NOT include pack rules (not subscribed)
    assert "Pack Rule 1" not in rule_names


@pytest.mark.django_db
def test_ruleline_without_packs_prefetch_still_includes_pack_content(
    pack_query_test_data,
):
    """Without packs parameter in prefetch, ruleline() must still include
    pack rules via fallback queries. The list is subscribed to the pack,
    so pack content should always appear regardless of how the fighter was loaded."""
    gang_list = pack_query_test_data["list"]

    # Load WITHOUT packs parameter — no pack-aware prefetch
    loaded_list = List.objects.with_related_data(with_fighters=True).get(
        id=gang_list.id
    )
    fighter = list(loaded_list.listfighter_set.all())[0]
    rules = fighter.ruleline
    rule_names = [r.value for r in rules]

    # Must include base rules
    assert "Base Rule 1" in rule_names
    assert "Base Rule 2" in rule_names

    # Must ALSO include pack rules (list is subscribed — fallback queries)
    assert "Pack Rule 1" in rule_names


@pytest.mark.django_db
def test_skilline_without_packs_prefetch_still_includes_pack_content(
    pack_query_test_data,
):
    """Without packs parameter in prefetch, skilline() must still include
    pack skills via fallback queries."""
    gang_list = pack_query_test_data["list"]

    loaded_list = List.objects.with_related_data(with_fighters=True).get(
        id=gang_list.id
    )
    fighter = list(loaded_list.listfighter_set.all())[0]
    skills = fighter.skilline()

    assert "Base Skill 1" in skills
    assert "Pack Skill 1" in skills
