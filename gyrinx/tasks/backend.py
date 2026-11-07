"""
Pub/Sub backend for Django Tasks.

This backend publishes tasks to per-task Google Cloud Pub/Sub topics.
Push subscriptions deliver messages back to the same Cloud Run service.
"""

import json
import logging
import uuid
from datetime import UTC, datetime

from django.conf import settings
from django.tasks import TaskResult
from django.tasks.backends.base import BaseTaskBackend
from django.tasks.base import TaskResultStatus
from django.tasks.signals import task_enqueued

from gyrinx.tasks.registry import get_task
from gyrinx.tracker import track

logger = logging.getLogger(__name__)


class PubSubBackend(BaseTaskBackend):
    """Publish tasks to per-task topics with optional confirmation.

    Each route has independent retry and acknowledgement settings. A callback
    records publish results. Most routes return a READY TaskResult before
    confirmation; confirm_publish routes wait before returning.
    Configure project_id in backend OPTIONS or GCP_PROJECT_ID.
    """

    supports_defer = False
    supports_async_task = False
    supports_get_result = True
    supports_priority = False

    def __init__(self, alias, params):
        super().__init__(alias, params)
        options = params.get("OPTIONS", {})
        self.project_id = options.get("project_id") or getattr(
            settings, "GCP_PROJECT_ID", None
        )
        self._publisher = None

    @property
    def publisher(self):
        """Create the Pub/Sub publisher on first access and reuse it."""
        if self._publisher is None:
            from google.cloud import pubsub_v1

            self._publisher = pubsub_v1.PublisherClient()
        return self._publisher

    def enqueue(self, task, args, kwargs):
        """Publish task arguments and return a READY result.

        Create TaskExecution through task_enqueued before publishing. Track the
        publish result in a callback. Confirmed routes wait for publication.
        Raise ValueError for unregistered tasks or non-JSON arguments.
        """
        task_id = str(uuid.uuid4())
        task_name = task.func.__name__

        route = get_task(task_name)
        if not route:
            raise ValueError(
                f"Task '{task_name}' not registered. Add "
                f"TaskRoute({task_name}) to the task_routes list in the "
                f"tasks.py module that declares it."
            )

        topic_path = self.publisher.topic_path(self.project_id, route.topic_name)

        # Use one timestamp for the message and its execution record.
        enqueued_at = datetime.now(UTC)

        message_data = {
            "task_id": task_id,
            "task_name": task_name,
            "args": list(args),
            "kwargs": dict(kwargs),
            "enqueued_at": enqueued_at.isoformat(),
        }

        try:
            data = json.dumps(message_data).encode("utf-8")
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"Task arguments for '{task_name}' are not JSON-serializable. "
                "Ensure args/kwargs contain only JSON-serializable types "
                "(dict, list, str, int, float, bool, None)."
            ) from e

        task_result = TaskResult(
            task=task,
            id=task_id,
            status=TaskResultStatus.READY,
            enqueued_at=enqueued_at,
            started_at=None,
            finished_at=None,
            last_attempted_at=None,
            args=list(args),
            kwargs=dict(kwargs),
            backend=self.alias,
            errors=[],
            worker_ids=[],
        )

        task_enqueued.send(sender=type(self), task_result=task_result)

        future = self.publisher.publish(topic_path, data)

        def on_publish_complete(f):
            """Track publish success or log and track failure."""
            try:
                message_id = f.result()
                track(
                    "task_published",
                    task_id=task_id,
                    task_name=task_name,
                    topic=route.topic_name,
                    message_id=message_id,
                )
            except Exception as e:
                logger.error(
                    f"Failed to publish task: {e}",
                    extra={"task_id": task_id, "task_name": task_name},
                    exc_info=True,
                )
                track(
                    "task_publish_failed",
                    task_id=task_id,
                    task_name=task_name,
                    error=str(e),
                )

        future.add_done_callback(on_publish_complete)

        # A failed continuation must leave the current task unacknowledged.
        # Confirmation can time out after a publish succeeds, so these routes
        # must also tolerate duplicate deliveries.
        if route.confirm_publish:
            future.result(timeout=10)

        return task_result

    def get_result(self, result_id):
        """Build a TaskResult from its external task ID, or return None when absent."""
        from gyrinx.tasks.models import TaskExecution

        try:
            execution = TaskExecution.objects.get(task_id=result_id)
        except TaskExecution.DoesNotExist:
            return None

        status_map = {
            "READY": TaskResultStatus.READY,
            "RUNNING": TaskResultStatus.RUNNING,
            "SUCCESSFUL": TaskResultStatus.SUCCESSFUL,
            "FAILED": TaskResultStatus.FAILED,
        }

        errors = []
        if execution.is_failed and execution.error_message:
            errors = [execution.error_message]

        return TaskResult(
            task=None,  # We don't have the task object when retrieving results
            id=execution.task_id,
            status=status_map.get(execution.status, TaskResultStatus.READY),
            enqueued_at=execution.enqueued_at,
            started_at=execution.started_at,
            finished_at=execution.finished_at,
            last_attempted_at=execution.started_at,
            args=execution.args,
            kwargs=execution.kwargs,
            backend=self.alias,
            errors=errors,
            worker_ids=[],
        )
