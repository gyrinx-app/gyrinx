"""Group task executions for progress reporting.

Pass a shared group_key to enqueue_in_group and poll /tasks/status.
Use an unguessable key because the status endpoint is public.
"""

import logging

from gyrinx.tasks.models import TaskExecution

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = ("SUCCESSFUL", "FAILED")


def enqueue_in_group(task, *, group_key, label="", **kwargs):
    """Enqueue a task, tag its execution with group_key and label, and return its result.

    The task_enqueued signal creates the execution synchronously. Log tagging
    failures without interrupting delivery; untagged tasks do not appear in progress.
    """
    result = task.enqueue(**kwargs)
    task_id = getattr(result, "id", None)
    if task_id:
        try:
            updated = TaskExecution.objects.filter(task_id=task_id).update(
                group_key=group_key, label=label
            )
            if not updated:
                # A missing execution cannot be tagged, but its task is still enqueued.
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
    """Return group identity, counts, completion and per-task status.

    A group is complete only when it has executions and all are successful or
    failed. Expose IDs, labels and states, excluding arguments and tracebacks
    because knowledge of the group key grants access.
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
