"""
Auto-provision Pub/Sub infrastructure for registered tasks.

This module creates Pub/Sub topics and push subscriptions on Cloud Run startup.
All subscriptions point to the same /tasks/pubsub/ endpoint; routing is handled
by the task_name field in the message payload.
"""

import logging
import os

from django.conf import settings
from google.api_core.exceptions import AlreadyExists
from google.cloud import pubsub_v1
from google.protobuf import duration_pb2

from gyrinx.tasks.registry import get_all_tasks
from gyrinx.tracker import track

logger = logging.getLogger(__name__)


def get_service_url() -> str:
    """
    Get the Cloud Run service URL for push subscriptions.

    Cloud Run sets CLOUD_RUN_SERVICE_URL automatically. Falls back to
    localhost for local development testing.
    """
    return os.getenv("CLOUD_RUN_SERVICE_URL", "http://localhost:8000")


def provision_task_infrastructure():
    """
    Create Pub/Sub topics and push subscriptions for all registered tasks.

    This is idempotent - safe to run on every Cloud Run startup. Existing
    topics are skipped; existing subscriptions are updated with current config.

    Topics: {env}--gyrinx.tasks--{task.path}
    Subscriptions: {topic_name}-sub -> /tasks/pubsub/
    """
    project_id = getattr(settings, "GCP_PROJECT_ID", None)
    if not project_id:
        logger.warning("GCP_PROJECT_ID not set, skipping task provisioning")
        return

    env = getattr(settings, "TASKS_ENVIRONMENT", "prod")
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
        except Exception as e:
            logger.error(f"Failed to provision {route.name}: {e}", exc_info=True)
            track("task_provisioning_failed", task_name=route.name, error=str(e))


def _provision_task(
    publisher: pubsub_v1.PublisherClient,
    subscriber: pubsub_v1.SubscriberClient,
    project_id: str,
    route,
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
