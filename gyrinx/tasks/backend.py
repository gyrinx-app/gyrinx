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

from gyrinx.tasks.registry import get_task
from gyrinx.tracker import track

logger = logging.getLogger(__name__)


class PubSubBackend(BaseTaskBackend):
    """
    Task backend that publishes to per-task Pub/Sub topics.

    Each registered task gets its own topic, allowing independent
    configuration of retry policies and ack deadlines.

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
    # To support get_result: store results in database or Cloud Storage
    supports_get_result = False
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

        Args:
            task: The Task instance to enqueue
            args: Positional arguments for the task
            kwargs: Keyword arguments for the task

        Returns:
            TaskResult with the task ID

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

        # Serialize message
        message_data = {
            "task_id": task_id,
            "task_name": task_name,
            "args": list(args),
            "kwargs": dict(kwargs),
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            data = json.dumps(message_data).encode("utf-8")
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"Task arguments for '{task_name}' are not JSON-serializable. "
                "Ensure args/kwargs contain only JSON-serializable types "
                "(dict, list, str, int, float, bool, None)."
            ) from e

        try:
            future = self.publisher.publish(topic_path, data)
            # Wait for publish confirmation; 10s is generous for Pub/Sub RTT
            message_id = future.result(timeout=10)

            enqueued_at = datetime.now(timezone.utc)

            track(
                "task_published",
                task_id=task_id,
                task_name=task_name,
                topic=route.topic_name,
                message_id=message_id,
            )

            return TaskResult(
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

        except Exception as e:
            logger.error(
                f"Failed to publish task: {e}",
                extra={
                    "task_id": task_id,
                    "task_name": task_name,
                },
                exc_info=True,
            )
            raise
