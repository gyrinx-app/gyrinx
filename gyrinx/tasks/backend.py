"""
Pub/Sub backend for Django Tasks.

This backend publishes tasks to per-task Google Cloud Pub/Sub topics.
Push subscriptions deliver messages back to the same Cloud Run service.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from django.conf import settings
from django.tasks import TaskResult
from django.tasks.backends.base import BaseTaskBackend
from django.tasks.base import TaskResultStatus
from django.tasks.signals import task_enqueued

from gyrinx.tasks.registry import get_task
from gyrinx.tracker import track

logger = logging.getLogger(__name__)


class PubSubBackend(BaseTaskBackend):
    """
    Task backend that publishes to per-task Pub/Sub topics.

    Each registered task gets its own topic, allowing independent
    configuration of retry policies and ack deadlines.

    IMPORTANT: This backend uses fire-and-forget publishing for low latency.
    Messages are published without waiting for Pub/Sub confirmation. A callback
    handles success/failure tracking via track(). This means message loss is
    possible on network issues, but the tradeoff is that enqueue() returns
    immediately without blocking the calling thread.

    Configuration in settings.py:
        TASKS = {
            "default": {
                "BACKEND": "gyrinx.tasks.backend.PubSubBackend",
                "OPTIONS": {
                    "project_id": "my-gcp-project",
                },
            }
        }
    """

    # Backend capabilities
    # To support defer: add run_after to message, use Pub/Sub scheduled delivery
    supports_defer = False
    # To support async: use aiohttp or async Pub/Sub client in aenqueue()
    supports_async_task = False
    # Results are stored in database via TaskExecution model
    supports_get_result = True
    # To support priority: use separate topics per priority level
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
        """Lazy initialization of Pub/Sub publisher client."""
        if self._publisher is None:
            from google.cloud import pubsub_v1

            self._publisher = pubsub_v1.PublisherClient()
        return self._publisher

    def enqueue(self, task, args, kwargs):
        """
        Publish task to its dedicated Pub/Sub topic.

        This method returns immediately after initiating the publish (fire-and-forget).
        A callback tracks success/failure via track(). We don't wait for Pub/Sub
        confirmation because blocking the request thread causes slow page loads
        when multiple tasks are enqueued.

        Args:
            task: The Task instance to enqueue
            args: Positional arguments for the task
            kwargs: Keyword arguments for the task

        Returns:
            TaskResult with the task ID (status is READY, though publish may still be in flight)

        Raises:
            ValueError: If task is not registered in registry.py
        """
        task_id = str(uuid.uuid4())
        task_name = task.func.__name__

        # Look up in registry to get topic name
        route = get_task(task_name)
        if not route:
            raise ValueError(
                f"Task '{task_name}' not registered. Add it to gyrinx/tasks/registry.py"
            )

        topic_path = self.publisher.topic_path(self.project_id, route.topic_name)

        # Compute enqueued_at once for consistency between message and database
        enqueued_at = datetime.now(timezone.utc)

        # Serialize message
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

        # Create TaskResult for signal (and return value)
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

        # Send signal to create TaskExecution record
        task_enqueued.send(sender=type(self), task_result=task_result)

        # Publish without waiting - use callback for tracking
        future = self.publisher.publish(topic_path, data)

        def on_publish_complete(f):
            """Callback to track publish success/failure."""
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

        # Return immediately - publish happens async
        return task_result

    def get_result(self, result_id):
        """
        Retrieve task result from the database.

        Args:
            result_id: The task ID (TaskResult.id, not our internal UUID)

        Returns:
            TaskResult instance with current status and results, or None if not found
        """
        from gyrinx.tasks.models import TaskExecution

        try:
            execution = TaskExecution.objects.get(task_id=result_id)
        except TaskExecution.DoesNotExist:
            return None

        # Map TaskExecution status to TaskResultStatus
        status_map = {
            "READY": TaskResultStatus.READY,
            "RUNNING": TaskResultStatus.RUNNING,
            "SUCCESSFUL": TaskResultStatus.SUCCESSFUL,
            "FAILED": TaskResultStatus.FAILED,
        }

        # Build errors list if failed
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
