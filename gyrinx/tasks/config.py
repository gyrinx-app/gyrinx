"""Shared configuration for Pub/Sub push sender identity."""

import os

from django.conf import settings


def expected_push_service_account() -> str | None:
    """Return the account used to sign Pub/Sub push tokens.

    The receiver must use the same default as subscription provisioning.
    Without an explicit account or a project ID, it cannot trust a sender.
    """
    configured = os.getenv("TASKS_SERVICE_ACCOUNT", "").strip()
    if configured:
        return configured

    project_id = getattr(settings, "GCP_PROJECT_ID", None)
    if not project_id:
        return None
    return f"pubsub-invoker@{project_id}.iam.gserviceaccount.com"
