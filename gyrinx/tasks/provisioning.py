"""
Auto-provision Pub/Sub and Cloud Scheduler infrastructure for registered tasks.

This module creates:
- Pub/Sub topics and push subscriptions for all registered tasks
- Cloud Scheduler jobs for tasks with a schedule configured

All subscriptions point to the same /tasks/pubsub/ endpoint; routing is handled
by the task_name field in the message payload. Scheduled tasks publish to the
same topics, reusing the existing push handler.

Orphan cleanup: When scheduled tasks are removed from the registry, this module
detects and deletes the corresponding Cloud Scheduler jobs to prevent stale
jobs from running.
"""

import json
import logging
import os

from django.conf import settings
from google.api_core.exceptions import AlreadyExists, NotFound
from google.cloud import pubsub_v1, scheduler_v1
from google.protobuf import duration_pb2

from gyrinx.tasks.registry import get_all_tasks
from gyrinx.tasks.route import TaskRoute
from gyrinx.tracker import track

logger = logging.getLogger(__name__)

# Prefix used for scheduler job names to identify jobs managed by this system
SCHEDULER_JOB_PREFIX = "gyrinx-scheduler"


def get_service_url() -> str:
    """
    Get the Cloud Run service URL for push subscriptions.

    CLOUD_RUN_SERVICE_URL must be set manually in production (Cloud Run does
    not set this automatically). Falls back to localhost for local development.
    """
    return os.getenv("CLOUD_RUN_SERVICE_URL", "http://localhost:8000")


def provision_task_infrastructure():
    """
    Create Pub/Sub topics, subscriptions, and Cloud Scheduler jobs.

    This is idempotent - safe to run on every Cloud Run startup. Existing
    resources are skipped or updated with current config.

    Creates:
    - Topics: {env}--gyrinx.tasks--{task.path}
    - Subscriptions: {topic_name}-sub -> /tasks/pubsub/
    - Scheduler jobs: {env}--gyrinx-scheduler--{task.path} (for scheduled tasks)

    Also cleans up orphaned scheduler jobs that no longer have a corresponding
    task in the registry.
    """
    project_id = getattr(settings, "GCP_PROJECT_ID", None)
    if not project_id:
        logger.warning("GCP_PROJECT_ID not set, skipping task provisioning")
        return

    env = getattr(settings, "TASKS_ENVIRONMENT", "dev")
    service_url = get_service_url()
    push_endpoint = f"{service_url}/tasks/pubsub/"

    # Service account for Pub/Sub to authenticate push requests
    service_account = os.getenv(
        "TASKS_SERVICE_ACCOUNT",
        f"pubsub-invoker@{project_id}.iam.gserviceaccount.com",
    )

    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()

    tasks = get_all_tasks()
    logger.info(f"Provisioning {len(tasks)} tasks (env={env})")

    for route in tasks:
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

    # Provision Cloud Scheduler jobs for scheduled tasks
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

    # Create topic if it doesn't exist
    try:
        publisher.create_topic(request={"name": topic_path})
        logger.info(f"Created topic: {route.topic_name}")
    except AlreadyExists:
        logger.debug(f"Topic exists: {route.topic_name}")

    # Configure push subscription with OIDC authentication
    # Audience must be the base service URL (not the full endpoint path)
    # to match what the view expects in CLOUD_RUN_SERVICE_URL
    push_config = pubsub_v1.types.PushConfig(
        push_endpoint=push_endpoint,
        oidc_token=pubsub_v1.types.PushConfig.OidcToken(
            service_account_email=service_account,
            audience=service_url,
        ),
    )

    # Configure retry policy from task route settings
    retry_policy = pubsub_v1.types.RetryPolicy(
        minimum_backoff=duration_pb2.Duration(seconds=route.min_retry_delay),
        maximum_backoff=duration_pb2.Duration(seconds=route.max_retry_delay),
    )

    # Create subscription or update if it exists
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
        # Update existing subscription with current configuration
        subscriber.update_subscription(
            request={
                "subscription": {
                    "name": subscription_path,
                    "push_config": push_config,
                    "ack_deadline_seconds": route.ack_deadline,
                    "retry_policy": retry_policy,
                },
                "update_mask": {
                    "paths": ["push_config", "ack_deadline_seconds", "retry_policy"]
                },
            }
        )
        logger.debug(f"Updated subscription: {subscription_name}")


def _provision_scheduled_tasks(
    project_id: str,
    publisher: pubsub_v1.PublisherClient,
    tasks: list[TaskRoute],
):
    """
    Provision Cloud Scheduler jobs for tasks with schedules configured.

    Cloud Scheduler jobs publish to the task's Pub/Sub topic on their cron
    schedule. The existing push handler receives and executes them like any
    other task.

    Also cleans up orphaned scheduler jobs that no longer have a corresponding
    scheduled task in the registry.
    """
    location = getattr(settings, "SCHEDULER_LOCATION", "europe-west2")
    env = getattr(settings, "TASKS_ENVIRONMENT", "dev")
    scheduled_tasks = [t for t in tasks if t.is_scheduled]

    scheduler = scheduler_v1.CloudSchedulerClient()

    # Clean up orphaned scheduler jobs first
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
    """
    Delete Cloud Scheduler jobs that no longer have a corresponding task.

    This prevents stale jobs from running after a scheduled task is removed
    from the registry. Only jobs with our naming prefix are considered.
    """
    parent = f"projects/{project_id}/locations/{location}"
    job_prefix = f"{env}--{SCHEDULER_JOB_PREFIX}--"

    # Build set of expected job names from current scheduled tasks
    expected_job_names = {route.scheduler_job_name for route in scheduled_tasks}

    try:
        # List all jobs in the location
        for job in scheduler.list_jobs(
            request=scheduler_v1.ListJobsRequest(parent=parent)
        ):
            # Extract job ID from full name (projects/.../locations/.../jobs/JOB_ID)
            job_id = job.name.split("/")[-1]

            # Only consider jobs with our prefix
            if not job_id.startswith(job_prefix):
                continue

            # Delete if not in expected set
            if job_id not in expected_job_names:
                try:
                    scheduler.delete_job(
                        request=scheduler_v1.DeleteJobRequest(name=job.name)
                    )
                    logger.info(f"Deleted orphaned scheduler job: {job_id}")
                    track("scheduler_job_deleted", job_name=job_id, reason="orphaned")
                except NotFound:
                    # Job was already deleted (race condition), that's fine
                    pass
                except Exception as e:
                    logger.error(f"Failed to delete orphaned job {job_id}: {e}")
                    track(
                        "scheduler_job_delete_failed",
                        job_name=job_id,
                        error=str(e),
                    )

    except Exception as e:
        # Don't fail provisioning if cleanup fails - log and continue
        logger.warning(f"Failed to list scheduler jobs for cleanup: {e}")
        track("scheduler_cleanup_failed", error=str(e))


def _provision_scheduler_job(
    scheduler: scheduler_v1.CloudSchedulerClient,
    publisher: pubsub_v1.PublisherClient,
    project_id: str,
    location: str,
    route: TaskRoute,
):
    """
    Create or update a Cloud Scheduler job for a single scheduled task.

    The job publishes to the task's Pub/Sub topic with a message format
    compatible with the existing push handler.
    """
    job_name = (
        f"projects/{project_id}/locations/{location}/jobs/{route.scheduler_job_name}"
    )
    topic_path = publisher.topic_path(project_id, route.topic_name)

    # Build message payload compatible with push handler.
    # Note: Unlike backend.enqueue(), we omit enqueued_at since this is a
    # static template reused for every execution. The Pub/Sub message ID
    # provides uniqueness for each delivery (logged in the handler).
    message_data = json.dumps(
        {
            "task_id": f"scheduled-{route.name}",
            "task_name": route.name,
            "args": [],
            "kwargs": {},
        }
    ).encode("utf-8")

    # Retry configuration for Cloud Scheduler (separate from Pub/Sub retries).
    # This controls retries when Scheduler fails to publish to Pub/Sub.
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
        # Update existing job with current configuration
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
        # Parent location doesn't exist - this shouldn't happen with valid config
        logger.error(
            f"Location {location} not found. "
            f"Check SCHEDULER_LOCATION setting matches your GCP region."
        )
        raise
