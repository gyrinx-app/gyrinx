"""Task routing, retry settings and optional schedules."""

import re
import zoneinfo
from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings

# Five numeric cron fields support wildcards, ranges, lists and steps.
CRON_FIELD_PATTERN = r"(\*|[0-9]+(-[0-9]+)?(,[0-9]+(-[0-9]+)?)*)(\/[0-9]+)?"
CRON_PATTERN = re.compile(rf"^{CRON_FIELD_PATTERN}(\s+{CRON_FIELD_PATTERN}){{4}}$")


def validate_cron_expression(schedule: str) -> None:
    """Validate five-field numeric cron syntax, raising ValueError on a format mismatch.

    This checks syntax, not each field's permitted numeric range.
    """
    if not CRON_PATTERN.match(schedule):
        raise ValueError(
            f"Invalid cron expression: '{schedule}'. "
            f"Expected 5 space-separated fields (minute hour day-of-month month day-of-week). "
            f"Example: '0 3 * * *' (daily at 3am) or '*/10 * * * *' (every 10 minutes)"
        )


def validate_timezone(timezone: str) -> None:
    """Resolve an IANA timezone, raising ValueError if the zone is unknown."""
    try:
        zoneinfo.ZoneInfo(timezone)
    except zoneinfo.ZoneInfoNotFoundError:
        raise ValueError(
            f"Invalid timezone: '{timezone}'. "
            f"Must be a valid IANA timezone (e.g., 'UTC', 'Europe/London', 'America/New_York')"
        ) from None


@dataclass
class PausedTaskConsumer:
    """Keywords carrying a task's exact paused-run authorisation."""

    run_id_kwarg: str = "backfill_id"
    generation_kwarg: str = "pause_generation"


@dataclass
class TaskRoute:
    """Routing and delivery configuration for a task.

    Use schedule and schedule_timezone for periodic delivery. A paused_consumer
    or exclusive_write requires write_scope. Exclusive delivery drains that
    scope and holds admission across the task's transactions.
    """

    func: Callable
    ack_deadline: int = 300
    min_retry_delay: int = 10
    max_retry_delay: int = 600
    schedule: str | None = None
    schedule_timezone: str = "UTC"
    write_scope: str | None = None
    paused_consumer: PausedTaskConsumer | None = None
    exclusive_write: bool = False

    def __post_init__(self):
        """Validate schedules and require a scope for write-admission options."""
        if self.schedule is not None:
            validate_cron_expression(self.schedule)
            validate_timezone(self.schedule_timezone)
        if self.paused_consumer is not None and not self.write_scope:
            raise ValueError("paused_consumer requires write_scope")
        if self.exclusive_write and not self.write_scope:
            raise ValueError("exclusive_write requires write_scope")

    @property
    def _underlying_func(self) -> Callable:
        """Unwrap a Django Task to its function, or return a raw function unchanged."""
        if hasattr(self.func, "func"):
            return self.func.func
        return self.func

    @property
    def name(self) -> str:
        """Task function name (e.g., 'send_welcome_email')."""
        return self._underlying_func.__name__

    @property
    def path(self) -> str:
        """Full module path (e.g., 'n23.core.tasks.send_welcome_email')."""
        func = self._underlying_func
        return f"{func.__module__}.{func.__name__}"

    @property
    def topic_name(self) -> str:
        """Build the Pub/Sub topic as {environment}--gyrinx.tasks--{function path}."""
        env = getattr(settings, "TASKS_ENVIRONMENT", "dev")
        return f"{env}--gyrinx.tasks--{self.path}"

    @property
    def scheduler_job_name(self) -> str:
        """Build the environment-prefixed Scheduler job name with dots replaced by hyphens.

        Raise ValueError when the route has no schedule.
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
