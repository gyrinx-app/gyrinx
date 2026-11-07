"""Platform maintenance tasks registered with the durable task framework."""

import logging

from django.db import connection, transaction
from django.tasks import task

from gyrinx.maintenance.models import Backfill
from gyrinx.tasks import TaskRoute

logger = logging.getLogger(__name__)

SESSION_SCRUB_OPERATION = "scrub_event_sessions"
SESSION_SCRUB_BATCH_SIZE = 5000
FIRST_UUID = "00000000-0000-0000-0000-000000000000"


def count_legacy_session_keys():
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM core_event WHERE session_id IS NOT NULL")
        return cursor.fetchone()[0]


@task
def scrub_event_sessions(backfill_id: str, batch_size: int = SESSION_SCRUB_BATCH_SIZE):
    """Clear one ordered batch and enqueue a continuation after commit.

    The Backfill row lock serialises duplicate deliveries. Cursor and UPDATE
    commit together, so replay cannot skip or recount a partially cleared
    batch. The trigger installed by analytics.0003 prevents new raw values.
    """
    continue_needed = False
    try:
        with transaction.atomic():
            backfill = Backfill.objects.select_for_update().get(pk=backfill_id)
            if (
                backfill.operation != SESSION_SCRUB_OPERATION
                or backfill.status != Backfill.Status.RUNNING
            ):
                return

            summary = dict(backfill.summary)
            if "total" not in summary:
                summary["total"] = count_legacy_session_keys()
            summary["deliveries"] = summary.get("deliveries", 0) + 1
            max_deliveries = (summary["total"] + batch_size - 1) // batch_size + 10
            if summary["deliveries"] > max_deliveries:
                backfill.status = Backfill.Status.FAILED
                backfill.error = "Too many task deliveries without completion."
                backfill.summary = summary
                backfill.save(update_fields=["summary", "status", "error", "modified"])
                return
            last_id = summary.get("cursor") or FIRST_UUID
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH batch AS (
                        SELECT id FROM core_event
                        WHERE session_id IS NOT NULL AND id > %s::uuid
                        ORDER BY id LIMIT %s
                    )
                    UPDATE core_event AS event SET session_id = NULL
                    FROM batch WHERE event.id = batch.id
                    RETURNING event.id
                    """,
                    [last_id, batch_size],
                )
                cleared_ids = [row[0] for row in cursor.fetchall()]

            summary["batches"] = summary.get("batches", 0) + 1
            summary["cleared"] = summary.get("cleared", 0) + len(cleared_ids)
            summary["remaining"] = max(0, summary["total"] - summary["cleared"])
            if cleared_ids:
                summary["cursor"] = str(max(cleared_ids))
            else:
                summary["remaining"] = count_legacy_session_keys()
                backfill.status = (
                    Backfill.Status.DONE
                    if summary["remaining"] == 0
                    else Backfill.Status.FAILED
                )
                if summary["remaining"]:
                    backfill.error = "Rows remained before the recorded cursor."
            backfill.summary = summary
            backfill.save(update_fields=["summary", "status", "error", "modified"])
            continue_needed = bool(cleared_ids)
    except Exception as exc:
        logger.exception("Legacy Event session scrub failed")
        Backfill.objects.filter(pk=backfill_id, status=Backfill.Status.RUNNING).update(
            status=Backfill.Status.FAILED, error=str(exc)
        )
        return

    # Enqueue after the progress commit. If publication fails, let the task
    # framework redeliver this batch so the chain cannot strand a RUNNING row.
    if continue_needed:
        scrub_event_sessions.enqueue(backfill_id=backfill_id, batch_size=batch_size)


task_routes = [TaskRoute(scrub_event_sessions, ack_deadline=300, confirm_publish=True)]
