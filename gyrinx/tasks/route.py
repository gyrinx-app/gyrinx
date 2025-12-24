"""
Task route configuration.

Defines the TaskRoute class used to register tasks with their configuration.
"""

import re
import zoneinfo
from dataclasses import dataclass
from typing import Callable

from django.conf import settings

# Cron expression validation
# Standard cron: 5 fields (minute, hour, day-of-month, month, day-of-week)
# Each field can be: *, number, range (1-5), step (*/5), list (1,3,5), or combo
CRON_FIELD_PATTERN = r"(\*|[0-9]+(-[0-9]+)?(,[0-9]+(-[0-9]+)?)*)(\/[0-9]+)?"
CRON_PATTERN = re.compile(rf"^{CRON_FIELD_PATTERN}(\s+{CRON_FIELD_PATTERN}){{4}}$")


def validate_cron_expression(schedule: str) -> None:
    """
    Validate a cron expression format.

    Args:
        schedule: Cron expression string (5 fields)

    Raises:
        ValueError: If the cron expression is invalid
    """
    if not CRON_PATTERN.match(schedule):
        raise ValueError(
            f"Invalid cron expression: '{schedule}'. "
            f"Expected 5 space-separated fields (minute hour day-of-month month day-of-week). "
            f"Example: '0 3 * * *' (daily at 3am) or '*/10 * * * *' (every 10 minutes)"
        )


def validate_timezone(timezone: str) -> None:
    """
    Validate a timezone string against the IANA timezone database.

    Args:
        timezone: Timezone string (e.g., 'UTC', 'Europe/London')

    Raises:
        ValueError: If the timezone is not valid
    """
    try:
        zoneinfo.ZoneInfo(timezone)
    except zoneinfo.ZoneInfoNotFoundError:
        raise ValueError(
            f"Invalid timezone: '{timezone}'. "
            f"Must be a valid IANA timezone (e.g., 'UTC', 'Europe/London', 'America/New_York')"
        )


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

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.schedule is not None:
            validate_cron_expression(self.schedule)
            validate_timezone(self.schedule_timezone)

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

        Format: {env}--gyrinx-scheduler--{task-path-with-hyphens}
        Example: prod--gyrinx-scheduler--gyrinx-core-tasks-cleanup_old_data

        Cloud Scheduler job names only allow [a-zA-Z0-9_-], so dots are
        replaced with hyphens.

        Raises:
            ValueError: If the task has no schedule configured.
        """
        if not self.schedule:
            raise ValueError(f"Task {self.name} has no schedule configured")
        env = getattr(settings, "TASKS_ENVIRONMENT", "dev")
        safe_path = self.path.replace(".", "-")
        return f"{env}--gyrinx-scheduler--{safe_path}"

    @property
    def is_scheduled(self) -> bool:
        """Return True if this task has a schedule configured."""
        return self.schedule is not None

    def __repr__(self) -> str:
        parts = [f"TaskRoute({self.name}", f"ack_deadline={self.ack_deadline}"]
        if self.schedule:
            parts.append(f"schedule={self.schedule!r}")
        return ", ".join(parts) + ")"
