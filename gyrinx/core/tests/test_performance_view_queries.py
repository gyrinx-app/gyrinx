"""
Tests for the ListPerformanceView to track query counts and ensure they don't increase.
"""

import json
import re
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.content.models import (
    ContentAttribute,
    ContentAttributeValue,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentHouse,
    ContentWeaponProfile,
)
from gyrinx.content.models_.expansion import (
    ContentEquipmentListExpansion,
    ContentEquipmentListExpansionItem,
    ContentEquipmentListExpansionRuleByAttribute,
    ContentEquipmentListExpansionRuleByHouse,
)
from gyrinx.core.models.list import (
    List,
    ListAttributeAssignment,
    ListFighter,
    ListFighterEquipmentAssignment,
)
from gyrinx.models import FighterCategoryChoices

User = get_user_model()


# Prepare snapshot for fixture file
def normalize_sql_uuids(sql):
    """Replace UUIDs in SQL with numbered placeholders for consistent comparison."""

    # Pattern to match UUIDs (8-4-4-4-12 format)
    uuid_pattern = r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"

    uuid_map = {}
    uuid_counter = 1

    def replace_uuid(match):
        nonlocal uuid_counter
        uuid = match.group(0)
        if uuid not in uuid_map:
            uuid_map[uuid] = f"UUID-{uuid_counter}"
            uuid_counter += 1
        return uuid_map[uuid]

    return re.sub(uuid_pattern, replace_uuid, sql, flags=re.IGNORECASE)


@pytest.fixture
def performance_test_data(db):
    """Set up test data for performance testing."""
    # Create user
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create house
    house = ContentHouse.objects.create(
        name="Test House",
        can_buy_any=False,
        can_hire_any=False,
    )

    # Create attribute and values
    attribute = ContentAttribute.objects.create(name="Alliance")
    attribute_value = ContentAttributeValue.objects.create(
        attribute=attribute,
        name="Test Alliance",
    )

    # Create list with attribute
    gang_list = List.objects.create(
        name="Test Gang",
        content_house=house,
        owner=user,
    )

    # Assign attribute to list
    ListAttributeAssignment.objects.create(
        list=gang_list,
        attribute_value=attribute_value,
    )

    # Create equipment category
    equipment_category = ContentEquipmentCategory.objects.create(
        name="Weapons",
        group="EQUIPMENT",  # Need to provide a valid group choice
    )

    # Create equipment items
    equipment1 = ContentEquipment.objects.create(
        name="Lasgun",
        cost=15,
        category=equipment_category,
    )

    equipment2 = ContentEquipment.objects.create(
        name="Autogun",
        cost=10,
        category=equipment_category,
    )

    equipment3 = ContentEquipment.objects.create(
        name="Chainsword",
        cost=25,
        category=equipment_category,
    )

    # Create weapon profiles for equipment
    ContentWeaponProfile.objects.create(
        equipment=equipment1,
        name="",  # Standard profile
        range_short="18",
        range_long="24",
        strength="3",
        damage="1",
        cost=0,
    )

    ContentWeaponProfile.objects.create(
        equipment=equipment2,
        name="",  # Standard profile
        range_short="8",
        range_long="24",
        strength="3",
        damage="1",
        cost=0,
    )

    ContentWeaponProfile.objects.create(
        equipment=equipment3,
        name="",  # Standard profile
        range_short="-",
        range_long="E",
        strength="4",
        damage="1",
        cost=0,
    )

    # Create fighter template
    fighter_template = ContentFighter.objects.create(
        type="Ganger",
        house=house,
        category=FighterCategoryChoices.GANGER,
        base_cost=50,
        movement="5",
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

    # Create 3 fighters
    fighter1 = ListFighter.objects.create(
        name="Fighter One",
        list=gang_list,
        content_fighter=fighter_template,
    )

    fighter2 = ListFighter.objects.create(
        name="Fighter Two",
        list=gang_list,
        content_fighter=fighter_template,
    )

    fighter3 = ListFighter.objects.create(
        name="Fighter Three",
        list=gang_list,
        content_fighter=fighter_template,
    )

    # Assign equipment to fighters
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter1,
        content_equipment=equipment1,
    )

    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter2,
        content_equipment=equipment2,
    )

    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter3,
        content_equipment=equipment3,
    )

    # Create expansion that applies to the house and attribute
    # First create rules
    house_rule = ContentEquipmentListExpansionRuleByHouse.objects.create(house=house)

    attribute_rule = ContentEquipmentListExpansionRuleByAttribute.objects.create(
        attribute=attribute  # Need to specify the attribute
    )
    attribute_rule.attribute_values.add(attribute_value)

    # Create expansion
    expansion = ContentEquipmentListExpansion.objects.create(
        name="Test Expansion",
    )
    expansion.rules.add(house_rule, attribute_rule)

    # Add equipment to expansion with different costs
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=equipment1,
        cost=12,  # Reduced cost in expansion
    )

    return {
        "user": user,
        "list": gang_list,
        "fighters": [fighter1, fighter2, fighter3],
        "equipment": [equipment1, equipment2, equipment3],
        "expansion": expansion,
    }


@pytest.mark.django_db
def test_performance_view_query_count(performance_test_data):
    """Test that the performance view query count doesn't increase."""
    client = Client()
    gang_list = performance_test_data["list"]

    # We could log in here if needed
    # client.login(username="testuser", password="testpass")

    url = reverse("core:list-performance", kwargs={"id": gang_list.id})

    snapshot_file = Path(__file__).parent / "fixtures" / "performance_view_queries.json"
    snapshot_file_latest = (
        Path(__file__).parent / "fixtures" / "performance_view_queries_latest.json"
    )

    print(f"Using snapshot file: {snapshot_file}")

    # Try to read existing snapshot
    existing_snapshot = None
    try:
        with open(snapshot_file, "r") as f:
            existing_snapshot = json.load(f)
            expected_count = existing_snapshot.get("query_count", None)
    except FileNotFoundError:
        print(f"\nNo existing snapshot found at {snapshot_file}")

    # Capture queries
    with CaptureQueriesContext(connection) as context:
        response = client.get(url)

    assert response.status_code == 200

    # Get the actual query count
    actual_query_count = len(context.captured_queries)

    # Log queries for debugging
    print(f"\nQuery count: {actual_query_count}")
    if expected_count is not None:
        print(f"Expected: {expected_count}")

    latest_queries = [
        {
            "sql": normalize_sql_uuids(query["sql"]),
            "time": str(query["time"]),
        }
        for query in context.captured_queries
    ]
    query_snapshot = {
        "query_count": actual_query_count,
        "queries": latest_queries,
    }

    matches = []
    if existing_snapshot:
        matches = [
            latest_queries[i]["sql"] == existing_query["sql"]
            for i, existing_query in enumerate(existing_snapshot["queries"])
            if i < len(latest_queries)
        ]

        # Find index of first mismatch
        first_mismatch_index = next(
            (i for i, match in enumerate(matches) if not match), None
        )
        if first_mismatch_index is not None:
            print(f"\nFirst mismatch at index {first_mismatch_index}:")
            print(f"Latest: {latest_queries[first_mismatch_index]}")
            print(f"Expected: {existing_snapshot['queries'][first_mismatch_index]}")

    # Try to read existing snapshot
    if not existing_snapshot or not all(matches):
        # Write new snapshot
        with open(snapshot_file_latest, "w") as f:
            json.dump(query_snapshot, f, indent=2)
        print(f"\nCreated updated query snapshot with {actual_query_count} queries")
        print(f"Snapshot written to {snapshot_file_latest}")
        print(
            "To update the fixture, rename this file to 'performance_view_queries.json':"
        )
        print(f"  mv {snapshot_file_latest} {snapshot_file}")

    assert all(matches), f"Not all queries match the expected snapshot: {matches}"

    # Assert query count hasn't increased
    assert actual_query_count <= expected_count, (
        f"Query count increased from {expected_count} to {actual_query_count}"
    )


@pytest.mark.django_db
def test_performance_view_query_patterns(performance_test_data):
    """Test that the performance view uses expected query patterns."""
    client = Client()
    gang_list = performance_test_data["list"]

    # We could log in here if needed
    # client.login(username="testuser", password="testpass")

    url = reverse("core:list-performance", kwargs={"id": gang_list.id})

    # Capture queries
    with CaptureQueriesContext(connection) as context:
        response = client.get(url)

    assert response.status_code == 200

    total_query_count = len(context.captured_queries)
    duplication_threshold = total_query_count // 5
    queries = [q["sql"] for q in context.captured_queries]

    # Check for expected query patterns
    # Should have queries for:
    # 1. List with related data
    # 2. Attributes
    # 3. Fighters
    # 4. Equipment assignments

    # Check that we're using select_related/prefetch_related appropriately
    list_queries = [q for q in queries if "core_list" in q]
    assert len(list_queries) > 0, "Should have queries for the list"

    # Check for N+1 query patterns (multiple similar queries)
    query_patterns = {}
    for query in queries:
        # Extract table name from query
        if "FROM" in query:
            parts = query.split("FROM")[1].split()
            if parts:
                table = parts[0].strip('"').strip()
                query_patterns[table] = query_patterns.get(table, 0) + 1

    # Check for potential N+1 issues
    for table, count in query_patterns.items():
        if count > duplication_threshold:  # Arbitrary threshold for similar queries
            print(f"Warning: {count} queries to table {table} - potential N+1 issue")
