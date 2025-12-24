"""
Task route configuration.

Defines the TaskRoute class used to register tasks with their configuration.
"""

from dataclasses import dataclass
from typing import Callable

from django.conf import settings


@dataclass
class TaskRoute:
    """
    Configuration for a registered task.

    Args:
        func: The task function (decorated with Django's @task) or raw function
        ack_deadline: Seconds before Pub/Sub retries if no ack (10-600, default 300)
        min_retry_delay: Minimum retry backoff in seconds (default 10)
        max_retry_delay: Maximum retry backoff in seconds (default 600)
        schedule: Optional cron expression for scheduled execution (e.g., "0 3 * * *")
        schedule_timezone: Timezone for the schedule (default "UTC")

    Example:
        # On-demand only
        TaskRoute(send_welcome_email)

        # On-demand with custom retry
        TaskRoute(generate_report, ack_deadline=600, min_retry_delay=30)

        # Scheduled (runs daily at 3am UTC)
        TaskRoute(cleanup_old_data, schedule="0 3 * * *")

        # Scheduled with timezone
        TaskRoute(send_daily_report, schedule="0 9 * * *", schedule_timezone="Europe/London")
    """

    func: Callable
    ack_deadline: int = 300
    min_retry_delay: int = 10
    max_retry_delay: int = 600
    schedule: str | None = None
    schedule_timezone: str = "UTC"

    @property
    def _underlying_func(self) -> Callable:
        """Get the underlying function, unwrapping Django Task objects if needed."""
        # Django's @task decorator wraps functions in a Task object
        # which has a .func attribute containing the original function
        if hasattr(self.func, "func"):
            return self.func.func
        return self.func

    @property
    def name(self) -> str:
        """Task function name (e.g., 'send_welcome_email')."""
        return self._underlying_func.__name__

    @property
    def path(self) -> str:
        """Full module path (e.g., 'gyrinx.core.tasks.send_welcome_email')."""
        func = self._underlying_func
        return f"{func.__module__}.{func.__name__}"

    @property
    def topic_name(self) -> str:
        """
        Pub/Sub topic name with environment prefix.

        Format: {env}--gyrinx.tasks--{full.module.path}
        Example: prod--gyrinx.tasks--gyrinx.core.tasks.send_welcome_email
        """
        env = getattr(settings, "TASKS_ENVIRONMENT", "dev")
        return f"{env}--gyrinx.tasks--{self.path}"

    @property
    def scheduler_job_name(self) -> str:
        """
        Cloud Scheduler job name with environment prefix.

        Format: {env}--gyrinx-scheduler--{full.module.path}
        Example: prod--gyrinx-scheduler--gyrinx.core.tasks.cleanup_old_data

        Raises:
            ValueError: If the task has no schedule configured.
        """
        if not self.schedule:
            raise ValueError(f"Task {self.name} has no schedule configured")
        env = getattr(settings, "TASKS_ENVIRONMENT", "dev")
        return f"{env}--gyrinx-scheduler--{self.path}"

    @property
    def is_scheduled(self) -> bool:
        """Return True if this task has a schedule configured."""
        return self.schedule is not None

    def __repr__(self) -> str:
        return f"TaskRoute({self.name}, ack_deadline={self.ack_deadline})"
