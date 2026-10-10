"""Statline reconciliation keeps history without a write loop per stat."""

import threading

import pytest
from django.db import connection, connections
from django.test.utils import CaptureQueriesContext

from n23.content.models import (
    ContentStatline,
    ContentStatlineType,
    ContentStatlineTypeStat,
)
from n23.content.statlines import set_fighter_statline


@pytest.mark.django_db
@pytest.mark.parametrize("creating", [True, False])
def test_statline_write_queries_do_not_grow_with_the_grid(content_fighter, creating):
    full_type = content_fighter.custom_statline.statline_type
    type_stats = list(full_type.stats.select_related("stat"))
    small_type = ContentStatlineType.objects.create(name="Small grid")
    ContentStatlineTypeStat.objects.bulk_create(
        [
            ContentStatlineTypeStat(
                statline_type=small_type, stat=stat.stat, position=position
            )
            for position, stat in enumerate(type_stats[:3])
        ]
    )
    counts = []
    for statline_type in (small_type, full_type):
        ContentStatline.objects.filter(content_fighter=content_fighter).delete()
        stats = list(statline_type.stats.all())
        values = {stat.pk: "3" for stat in stats}
        if not creating:
            set_fighter_statline(content_fighter, statline_type)
        with CaptureQueriesContext(connection) as queries:
            statline = set_fighter_statline(content_fighter, statline_type, values)
        counts.append(len(queries))
        assert statline.stats.count() == len(stats)
        assert all(stat.value != "-" for stat in statline.stats.all())

    assert len(type_stats) > 3
    assert counts[0] == counts[1]


@pytest.mark.django_db
def test_batched_updates_keep_history_and_leave_unspecified_values_alone(
    content_fighter,
):
    statline = content_fighter.custom_statline
    stats = {
        stat.statline_type_stat.stat.field_name: stat
        for stat in statline.stats.select_related("statline_type_stat__stat")
    }
    movement = stats["movement"]
    strength = stats["strength"]
    movement_history = movement.history.count()
    strength_history = strength.history.count()
    strength_modified = strength.modified
    movement_modified = movement.modified

    returned = set_fighter_statline(
        content_fighter,
        statline.statline_type,
        {movement.statline_type_stat_id: "6"},
    )

    movement.refresh_from_db()
    strength.refresh_from_db()
    assert returned.pk == statline.pk
    assert movement.value == '6"'
    assert movement.modified > movement_modified
    assert movement.history.count() == movement_history + 1
    assert movement.history.first().value == '6"'
    assert movement.history.first().history_type == "~"
    assert strength.value == "4"
    assert strength.modified == strength_modified
    assert strength.history.count() == strength_history


@pytest.mark.django_db
def test_batched_creation_keeps_history_for_each_stat(content_fighter):
    statline_type = content_fighter.custom_statline.statline_type
    ContentStatline.objects.filter(content_fighter=content_fighter).delete()

    statline = set_fighter_statline(content_fighter, statline_type)

    assert statline.stats.count() == statline_type.stats.count()
    for stat in statline.stats.all():
        history = stat.history.get()
        assert stat.value == history.value == "-"
        assert history.history_type == "+"


@pytest.mark.django_db(transaction=True)
def test_concurrent_grid_updates_keep_one_complete_grid(content_fighter):
    statline_type = content_fighter.custom_statline.statline_type
    ids = list(statline_type.stats.values_list("pk", flat=True))
    start = threading.Barrier(2, timeout=10)
    errors = []

    def write(value):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
            start.wait()
            set_fighter_statline(
                content_fighter, statline_type, dict.fromkeys(ids, value)
            )
        except Exception as error:
            errors.append(error)
        finally:
            connections.close_all()

    writers = [threading.Thread(target=write, args=(value,)) for value in ("2", "6")]
    for writer in writers:
        writer.start()
    for writer in writers:
        writer.join(timeout=15)

    assert all(not writer.is_alive() for writer in writers)
    assert not errors, errors
    statline = ContentStatline.objects.get(content_fighter=content_fighter)
    stats = list(statline.stats.all())
    assert len(stats) == len(ids)
    assert {stat.value.strip('+"') for stat in stats} in ({"2"}, {"6"})
    assert all(stat.history.count() == 4 for stat in stats)
