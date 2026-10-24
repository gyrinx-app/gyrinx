"""loaddata_overwrite drops automatic many-to-many links with a missing end."""

from io import StringIO

import pytest
from django.core import serializers
from django.core.management import call_command
from django.db import connection

from n23.content.models import (
    ContentFighter,
    ContentHouse,
    ContentRule,
    ContentSkillCategory,
)
from n23.models import FighterCategoryChoices

# The command recovers from a failed TRUNCATE by running DELETE. That recovery
# needs autocommit: inside a test transaction the failed statement aborts the
# rest of the command. `manage loaddata_overwrite` runs outside a transaction.
pytestmark = pytest.mark.django_db(transaction=True)


def _quote(name):
    return connection.ops.quote_name(name)


def _delete_without_cascade(model, pk):
    """Remove one record while foreign keys are off, leaving through-table links."""
    table = _quote(model._meta.db_table)
    column = _quote(model._meta.pk.column)
    with connection.cursor() as cursor:
        cursor.execute("SET session_replication_role = 'replica';")
        try:
            cursor.execute(f"DELETE FROM {table} WHERE {column} = %s", [pk])  # nosec B608
        finally:
            cursor.execute("SET session_replication_role = 'origin';")


def _link_count(field, *, source_id=None, target_id=None):
    through = field.remote_field.through
    clauses = []
    params = []
    if source_id is not None:
        clauses.append(f"{_quote(field.m2m_column_name())} = %s")
        params.append(source_id)
    if target_id is not None:
        clauses.append(f"{_quote(field.m2m_reverse_name())} = %s")
        params.append(target_id)
    sql = f"SELECT COUNT(*) FROM {_quote(through._meta.db_table)}"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    with connection.cursor() as cursor:
        cursor.execute(sql, params)  # nosec B608
        return cursor.fetchone()[0]


def test_overwrite_drops_hidden_m2m_links_and_keeps_live_ones(tmp_path):
    kept = ContentSkillCategory.objects.create(name="Kept tree")
    removed = ContentSkillCategory.objects.create(name="Removed tree")
    house = ContentHouse.objects.create(name="Overwrite House")
    house.skill_categories.add(kept, removed)
    fighter = ContentFighter.objects.create(
        type="Overwrite Ganger",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
    )
    fighter.primary_skill_categories.add(kept, removed)
    rule = ContentRule.objects.create(name="Overwrite rule")
    fighter.rules.add(rule)

    _delete_without_cascade(ContentSkillCategory, removed.id)
    _delete_without_cascade(ContentRule, rule.id)

    house_field = ContentHouse._meta.get_field("skill_categories")
    fighter_field = ContentFighter._meta.get_field("primary_skill_categories")
    rule_field = ContentFighter._meta.get_field("rules")
    assert _link_count(house_field, source_id=house.id, target_id=removed.id) == 1
    assert _link_count(fighter_field, source_id=fighter.id, target_id=kept.id) == 1
    assert _link_count(rule_field, source_id=fighter.id, target_id=rule.id) == 1

    fixture = tmp_path / "content.json"
    fixture.write_text(serializers.serialize("json", [house, kept]))

    out = StringIO()
    call_command("loaddata_overwrite", str(fixture), stdout=out)

    assert _link_count(house_field, source_id=house.id, target_id=removed.id) == 0
    assert _link_count(house_field, source_id=house.id, target_id=kept.id) == 1
    assert list(house.skill_categories.values_list("name", flat=True)) == ["Kept tree"]
    assert _link_count(fighter_field, source_id=fighter.id, target_id=kept.id) == 1
    assert _link_count(fighter_field, source_id=fighter.id, target_id=removed.id) == 0
    assert _link_count(rule_field, source_id=fighter.id, target_id=rule.id) == 1
    text = out.getvalue()
    assert "Removed " in text
    assert "many-to-many links that pointed at a missing record." in text


def test_dry_run_leaves_hidden_m2m_links(tmp_path):
    kept = ContentSkillCategory.objects.create(name="Dry kept tree")
    removed = ContentSkillCategory.objects.create(name="Dry removed tree")
    house = ContentHouse.objects.create(name="Dry overwrite house")
    house.skill_categories.add(kept, removed)
    _delete_without_cascade(ContentSkillCategory, removed.id)

    field = ContentHouse._meta.get_field("skill_categories")
    fixture = tmp_path / "content.json"
    fixture.write_text(serializers.serialize("json", [house, kept]))

    out = StringIO()
    call_command("loaddata_overwrite", str(fixture), "--dry-run", stdout=out)

    assert _link_count(field, source_id=house.id, target_id=removed.id) == 1
    assert ContentHouse.objects.filter(pk=house.id).exists()
    assert "Removed " not in out.getvalue()
    assert "DRY RUN complete" in out.getvalue()
    # The hidden link is the case under test. Remove it before teardown so
    # the flush is not blocked by a foreign key that points nowhere.
    through = field.remote_field.through
    with connection.cursor() as cursor:
        cursor.execute(
            f"DELETE FROM {_quote(through._meta.db_table)} "  # nosec B608
            f"WHERE {_quote(field.m2m_reverse_name())} = %s",
            [removed.id],
        )
