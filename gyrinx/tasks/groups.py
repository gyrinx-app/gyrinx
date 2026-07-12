"""Group-aware task enqueueing and status.

A single logical operation often fans out into many background task runs — e.g. starting a
campaign spawns one clone task per gang (#1222). Tag those runs with a shared ``group_key``
so the generic ``/tasks/status`` endpoint (see :mod:`gyrinx.tasks.views`) can report the
group's overall progress, and a UI can poll it.

Usage::

    from gyrinx.tasks.groups import enqueue_in_group

    for gang in gangs:
        enqueue_in_group(
            clone_gang,
            group_key=f"campaign-start:{campaign_id}",
            label=gang.name,
            gang_id=str(gang.id),
        )
"""

import logging

from gyrinx.tasks.models import TaskExecution

logger = logging.getLogger(__name__)

# Statuses that mean a task run has finished (successfully or not).
TERMINAL_STATUSES = ("SUCCESSFUL", "FAILED")


def enqueue_in_group(task, *, group_key, label="", **kwargs):
    """Enqueue ``task`` and tag its :class:`TaskExecution` with ``group_key``/``label``.

    The task framework creates the ``TaskExecution`` row synchronously (via the
    ``task_enqueued`` signal) during ``enqueue``, so by the time this returns the row exists
    and we can stamp it. Returns whatever ``task.enqueue`` returned (a ``TaskResult``), or
    ``None`` if enqueue produced no result.

    Tagging failures are swallowed: a group tag is for observability, and must never break
    the enqueue itself.
    """
    result = task.enqueue(**kwargs)
    task_id = getattr(result, "id", None)
    if task_id:
        try:
            updated = TaskExecution.objects.filter(task_id=task_id).update(
                group_key=group_key, label=label
            )
            if not updated:
                # The task_enqueued signal should have created the row synchronously; if it
                # didn't, the task still runs but won't appear in the group's status rollup.
                logger.warning(
                    "No TaskExecution row for task %s to tag with group_key=%s "
                    "(it won't show in group status)",
                    task_id,
                    group_key,
                )
        except Exception:
            logger.exception(
                "Failed to tag task %s with group_key=%s", task_id, group_key
            )
    return result


def group_status(group_key):
    """Return a JSON-serialisable status summary for all task runs in ``group_key``.

    Shape::

        {
          "group": "...",
          "complete": bool,   # at least one unit, and every unit is terminal
          "counts": {"total", "successful", "failed", "running", "ready", "pending"},
          "units": [{"task_id", "label", "status"}, ...],
        }

    Only non-sensitive fields are exposed (no args/kwargs/tracebacks) since the status
    endpoint is readable by anyone who knows the (unguessable) group key.
    """
    units = list(
        TaskExecution.objects.filter(group_key=group_key)
        .order_by("enqueued_at")
        .values("task_id", "label", "status")
    )
    counts = {
        "total": len(units),
        "successful": sum(1 for u in units if u["status"] == "SUCCESSFUL"),
        "failed": sum(1 for u in units if u["status"] == "FAILED"),
        "running": sum(1 for u in units if u["status"] == "RUNNING"),
        "ready": sum(1 for u in units if u["status"] == "READY"),
    }
    counts["pending"] = counts["running"] + counts["ready"]
    complete = bool(units) and all(u["status"] in TERMINAL_STATUSES for u in units)
    return {
        "group": group_key,
        "complete": complete,
        "counts": counts,
        "units": units,
    }
