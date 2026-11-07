"""Provision per-task Pub/Sub resources and optional Cloud Scheduler jobs.

All push subscriptions deliver to /tasks/pubsub/ and task_name selects the
handler. Scheduled jobs publish to those topics. Remove managed Scheduler
jobs whose routes are no longer scheduled.
"""

import json
import logging
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from google.api_core.exceptions import Aborted, AlreadyExists, Conflict, NotFound
from google.cloud import pubsub_v1, scheduler_v1
from google.protobuf import duration_pb2

from gyrinx.tasks.registry import get_all_tasks
from gyrinx.tasks.route import TaskRoute
from gyrinx.tracker import track

logger = logging.getLogger(__name__)

SCHEDULER_JOB_PREFIX = "gyrinx-scheduler"

# Provision independent task resources concurrently to avoid serial network waits.
PROVISION_MAX_WORKERS = 8

# Concurrent container startup can conflict when updating the same subscription.
CONFLICT_RETRIES = 2


def get_service_url() -> str:
    """Return CLOUD_RUN_SERVICE_URL, falling back to localhost for development."""
    return os.getenv("CLOUD_RUN_SERVICE_URL", "http://localhost:8000")


def provision_task_infrastructure():
    """Create or update registered task topics, subscriptions and Scheduler jobs.

    Skip provisioning without GCP_PROJECT_ID. Handle each route independently
    and remove orphaned managed Scheduler jobs.
    """
    project_id = getattr(settings, "GCP_PROJECT_ID", None)
    if not project_id:
        logger.warning("GCP_PROJECT_ID not set, skipping task provisioning")
        return

    env = getattr(settings, "TASKS_ENVIRONMENT", "dev")
    service_url = get_service_url()
    push_endpoint = f"{service_url}/tasks/pubsub/"

    service_account = os.getenv(
        "TASKS_SERVICE_ACCOUNT",
        f"pubsub-invoker@{project_id}.iam.gserviceaccount.com",
    )

    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()

    tasks = get_all_tasks()
    logger.info(f"Provisioning {len(tasks)} tasks (env={env})")

    def _run(route: TaskRoute):
        try:
            _provision_task(
                publisher=publisher,
                subscriber=subscriber,
                project_id=project_id,
                route=route,
                push_endpoint=push_endpoint,
                service_url=service_url,
                service_account=service_account,
            )
            track("task_provisioned", task_name=route.name)
        except Exception as e:
            logger.error(f"Failed to provision {route.name}: {e}", exc_info=True)
            track("task_provisioning_failed", task_name=route.name, error=str(e))

    # Per-task failures are logged so the pool drains and other tasks still provision.
    with ThreadPoolExecutor(max_workers=PROVISION_MAX_WORKERS) as pool:
        list(pool.map(_run, tasks))

    _provision_scheduled_tasks(project_id=project_id, publisher=publisher, tasks=tasks)


def _provision_task(
    publisher: pubsub_v1.PublisherClient,
    subscriber: pubsub_v1.SubscriberClient,
    project_id: str,
    route: TaskRoute,
    push_endpoint: str,
    service_url: str,
    service_account: str,
):
    """Provision topic and subscription for a single task."""
    topic_path = publisher.topic_path(project_id, route.topic_name)
    subscription_name = f"{route.topic_name}-sub"
    subscription_path = subscriber.subscription_path(project_id, subscription_name)

    try:
        publisher.create_topic(request={"name": topic_path})
        logger.info(f"Created topic: {route.topic_name}")
    except AlreadyExists:
        logger.debug(f"Topic exists: {route.topic_name}")

    # Use the base service URL as the OIDC audience to match push-token verification.
    push_config = pubsub_v1.types.PushConfig(
        push_endpoint=push_endpoint,
        oidc_token=pubsub_v1.types.PushConfig.OidcToken(
            service_account_email=service_account,
            audience=service_url,
        ),
    )

    retry_policy = route_retry_policy(route)

    try:
        subscriber.create_subscription(
            request={
                "name": subscription_path,
                "topic": topic_path,
                "push_config": push_config,
                "ack_deadline_seconds": route.ack_deadline,
                "retry_policy": retry_policy,
            }
        )
        logger.info(f"Created subscription: {subscription_name}")
    except AlreadyExists:
        _update_subscription_tolerating_conflict(
            subscriber=subscriber,
            subscription_path=subscription_path,
            subscription_name=subscription_name,
            push_config=push_config,
            route=route,
        )


def _update_subscription_tolerating_conflict(
    subscriber: pubsub_v1.SubscriberClient,
    subscription_path: str,
    subscription_name: str,
    push_config,
    route: TaskRoute,
):
    """Retry concurrent subscription updates with exponential backoff and jitter.

    After retries, compare live configuration with this revision's desired
    fields. Log unresolved conflicts and track divergent configuration separately.
    """
    desired = {
        "name": subscription_path,
        "push_config": push_config,
        "ack_deadline_seconds": route.ack_deadline,
        "retry_policy": route_retry_policy(route),
    }
    request = {
        "subscription": desired,
        "update_mask": {
            "paths": ["push_config", "ack_deadline_seconds", "retry_policy"]
        },
    }

    for attempt in range(CONFLICT_RETRIES + 1):
        try:
            subscriber.update_subscription(request=request)
            logger.debug(f"Updated subscription: {subscription_name}")
            return
        except (Aborted, Conflict) as e:
            if attempt == CONFLICT_RETRIES:
                _report_unsettled_conflict(
                    subscriber=subscriber,
                    subscription_path=subscription_path,
                    subscription_name=subscription_name,
                    desired=desired,
                    route=route,
                    error=e,
                )
                return
            # nosec B311 - backoff jitter to decorrelate two containers retrying
            # in lockstep; nothing security-sensitive depends on it.
            time.sleep(0.25 * (2**attempt) + random.uniform(0, 0.25))  # nosec B311


def _diff_against_live(desired: dict, live) -> list[str]:
    """Compare only subscription fields this update controls.

    Ignore server-populated defaults outside those fields to avoid false differences.
    """
    want_push = desired["push_config"]
    want_retry = desired["retry_policy"]
    live_push, live_retry = live.push_config, live.retry_policy

    differences = []
    if live_push.push_endpoint != want_push.push_endpoint:
        differences.append("push endpoint")
    if (
        live_push.oidc_token.service_account_email
        != want_push.oidc_token.service_account_email
        or live_push.oidc_token.audience != want_push.oidc_token.audience
    ):
        differences.append("OIDC token")
    if live.ack_deadline_seconds != desired["ack_deadline_seconds"]:
        differences.append("ack deadline")
    if (
        live_retry.minimum_backoff != want_retry.minimum_backoff
        or live_retry.maximum_backoff != want_retry.maximum_backoff
    ):
        differences.append("retry backoff")
    return differences


def _report_unsettled_conflict(
    subscriber: pubsub_v1.SubscriberClient,
    subscription_path: str,
    subscription_name: str,
    desired: dict,
    route: TaskRoute,
    error: Exception,
):
    """Read back a conflicted subscription and report whether its configuration matches.

    Track divergence separately from matching updates or an unverifiable read.
    """
    try:
        live = subscriber.get_subscription(request={"subscription": subscription_path})
    except Exception as read_error:
        logger.warning(
            f"Subscription {subscription_name} is being updated concurrently and "
            f"did not settle ({error}); could not read it back to confirm its "
            f"config ({read_error})"
        )
        track("task_provisioning_conflict", task_name=route.name, verified=False)
        return

    divergent = _diff_against_live(desired, live)

    if divergent:
        # Concurrent revisions can temporarily apply different configurations during deployment.
        # Track persistent divergence separately from expected provisioning conflicts.
        logger.warning(
            f"Subscription {subscription_name} was written concurrently by another "
            f"process and now differs from this revision's config in "
            f"{', '.join(divergent)}. It will be corrected the next time a "
            f"container provisions without contention ({error})"
        )
        track(
            "task_provisioning_diverged",
            task_name=route.name,
            fields=",".join(divergent),
        )
        return

    logger.warning(
        f"Subscription {subscription_name} is being updated concurrently and did "
        f"not settle after {CONFLICT_RETRIES + 1} attempts, but the config now in "
        f"place matches what this revision wanted ({error})"
    )
    track("task_provisioning_conflict", task_name=route.name, verified=True)


def route_retry_policy(route: TaskRoute) -> pubsub_v1.types.RetryPolicy:
    """Build the Pub/Sub retry policy for a route's backoff settings."""
    return pubsub_v1.types.RetryPolicy(
        minimum_backoff=duration_pb2.Duration(seconds=route.min_retry_delay),
        maximum_backoff=duration_pb2.Duration(seconds=route.max_retry_delay),
    )


def _provision_scheduled_tasks(
    project_id: str,
    publisher: pubsub_v1.PublisherClient,
    tasks: list[TaskRoute],
):
    """Provision scheduled routes and clean up orphaned managed jobs."""
    location = getattr(settings, "SCHEDULER_LOCATION", "europe-west2")
    env = getattr(settings, "TASKS_ENVIRONMENT", "dev")
    scheduled_tasks = [t for t in tasks if t.is_scheduled]

    scheduler = scheduler_v1.CloudSchedulerClient()

    _cleanup_orphaned_scheduler_jobs(
        scheduler=scheduler,
        project_id=project_id,
        location=location,
        env=env,
        scheduled_tasks=scheduled_tasks,
    )

    if not scheduled_tasks:
        logger.debug("No scheduled tasks to provision")
        return

    logger.info(f"Provisioning {len(scheduled_tasks)} scheduled tasks")

    for route in scheduled_tasks:
        try:
            _provision_scheduler_job(
                scheduler=scheduler,
                publisher=publisher,
                project_id=project_id,
                location=location,
                route=route,
            )
        except Exception as e:
            logger.error(
                f"Failed to provision scheduler job for {route.name}: {e}",
                exc_info=True,
            )
            track(
                "scheduler_provisioning_failed",
                task_name=route.name,
                error=str(e),
            )


def _cleanup_orphaned_scheduler_jobs(
    scheduler: scheduler_v1.CloudSchedulerClient,
    project_id: str,
    location: str,
    env: str,
    scheduled_tasks: list[TaskRoute],
):
    """Delete jobs with this environment's managed prefix that have no scheduled route."""
    parent = f"projects/{project_id}/locations/{location}"
    job_prefix = f"{env}--{SCHEDULER_JOB_PREFIX}--"

    expected_job_names = {route.scheduler_job_name for route in scheduled_tasks}

    try:
        for job in scheduler.list_jobs(
            request=scheduler_v1.ListJobsRequest(parent=parent)
        ):
            job_id = job.name.split("/")[-1]

            if not job_id.startswith(job_prefix):
                continue

            if job_id not in expected_job_names:
                try:
                    scheduler.delete_job(
                        request=scheduler_v1.DeleteJobRequest(name=job.name)
                    )
                    logger.info(f"Deleted orphaned scheduler job: {job_id}")
                    track("scheduler_job_deleted", job_name=job_id, reason="orphaned")
                except NotFound:
                    pass
                except Exception as e:
                    logger.error(f"Failed to delete orphaned job {job_id}: {e}")
                    track(
                        "scheduler_job_delete_failed",
                        job_name=job_id,
                        error=str(e),
                    )

    except Exception as e:
        logger.warning(f"Failed to list scheduler jobs for cleanup: {e}")
        track("scheduler_cleanup_failed", error=str(e))


def _provision_scheduler_job(
    scheduler: scheduler_v1.CloudSchedulerClient,
    publisher: pubsub_v1.PublisherClient,
    project_id: str,
    location: str,
    route: TaskRoute,
):
    """Create or update a route's Scheduler job with a push-handler-compatible payload."""
    job_name = (
        f"projects/{project_id}/locations/{location}/jobs/{route.scheduler_job_name}"
    )
    topic_path = publisher.topic_path(project_id, route.topic_name)

    # Omit enqueued_at because Scheduler reuses this payload for every execution.
    message_data = json.dumps(
        {
            "task_id": f"scheduled-{route.name}",
            "task_name": route.name,
            "args": [],
            "kwargs": {},
        }
    ).encode("utf-8")

    # Scheduler retries publishing to Pub/Sub independently of subscription delivery retries.
    retry_config = scheduler_v1.RetryConfig(
        retry_count=3,
        min_backoff_duration=duration_pb2.Duration(seconds=5),
        max_backoff_duration=duration_pb2.Duration(seconds=300),
    )

    job = scheduler_v1.Job(
        name=job_name,
        description=f"Scheduled task: {route.name} ({route.schedule} {route.schedule_timezone})",
        pubsub_target=scheduler_v1.PubsubTarget(
            topic_name=topic_path,
            data=message_data,
        ),
        schedule=route.schedule,
        time_zone=route.schedule_timezone,
        retry_config=retry_config,
    )

    try:
        scheduler.create_job(
            request=scheduler_v1.CreateJobRequest(
                parent=f"projects/{project_id}/locations/{location}",
                job=job,
            )
        )
        logger.info(f"Created scheduler job: {route.scheduler_job_name}")
        track(
            "scheduler_job_created",
            task_name=route.name,
            schedule=route.schedule,
            timezone=route.schedule_timezone,
        )
    except AlreadyExists:
        scheduler.update_job(
            request=scheduler_v1.UpdateJobRequest(
                job=job,
                update_mask={
                    "paths": [
                        "description",
                        "pubsub_target",
                        "schedule",
                        "time_zone",
                        "retry_config",
                    ]
                },
            )
        )
        logger.debug(f"Updated scheduler job: {route.scheduler_job_name}")
    except NotFound:
        logger.error(
            f"Location {location} not found. "
            f"Check SCHEDULER_LOCATION setting matches your GCP region."
        )
        raise
