"""
Pub/Sub push handler view.

This view receives push messages from Pub/Sub and dispatches them to the
appropriate task handlers based on the task_name in the message payload.
"""

import base64
import json
import logging
import os
import traceback
from datetime import datetime

from django.conf import settings
from django.db import OperationalError, connection
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.tasks import TaskResult
from django.tasks.base import TaskError, TaskResultStatus
from django.tasks.signals import task_finished, task_started
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from gyrinx.tasks.backend import PubSubBackend
from gyrinx.tasks.registry import get_task
from gyrinx.tracing import span, traced
from gyrinx.tracker import track

logger = logging.getLogger(__name__)


class _MockTask:
    """
    Minimal mock Task to satisfy Django's signal handler logging.

    Django's built-in task_started/task_finished signal handlers access
    task_result.task.module_path for logging. Since we're in the push handler
    and don't have access to the actual Task object, we provide this mock.
    """

    def __init__(self, name: str):
        self.module_path = name


def _build_task_result(
    task_id: str,
    task_name: str,
    args: list,
    kwargs: dict,
    status: TaskResultStatus,
    enqueued_at: datetime | None = None,
    return_value=None,
    error: Exception | None = None,
) -> TaskResult:
    """
    Build a TaskResult object for sending signals.

    The push handler needs to construct TaskResult objects to send
    task_started and task_finished signals.
    """
    now = timezone.now()

    errors = []
    if error is not None:
        exception_type = type(error)
        errors.append(
            TaskError(
                exception_class_path=f"{exception_type.__module__}.{exception_type.__qualname__}",
                traceback=traceback.format_exc(),
            )
        )

    result = TaskResult(
        task=_MockTask(task_name),  # Mock task for Django's signal handler logging
        id=task_id,
        status=status,
        enqueued_at=enqueued_at,
        started_at=now if status == TaskResultStatus.RUNNING else None,
        finished_at=now
        if status in (TaskResultStatus.SUCCESSFUL, TaskResultStatus.FAILED)
        else None,
        last_attempted_at=now,
        args=args,
        kwargs=kwargs,
        backend="default",
        errors=errors,
        worker_ids=[],
    )

    # Set return value for successful tasks
    if return_value is not None and status == TaskResultStatus.SUCCESSFUL:
        # Test if serializable before storing
        try:
            json.dumps(return_value)
            object.__setattr__(result, "_return_value", return_value)
        except (TypeError, ValueError):
            logger.debug(
                "Task return value is not JSON-serializable, not storing",
                extra={"task_id": task_id},
            )

    return result


def _verify_oidc_token(request) -> bool:
    """
    Verify the OIDC token from Pub/Sub push requests.

    In production, Pub/Sub sends an Authorization header with a JWT token
    signed by Google. We verify the token to ensure requests come from
    our Pub/Sub subscriptions, not arbitrary attackers.

    In development (DEBUG=True), authentication is skipped to allow
    local testing without GCP infrastructure.

    Returns:
        True if token is valid (or in dev mode), False otherwise.
    """
    # Skip verification in development
    if settings.DEBUG:
        return True

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        logger.warning("Missing or invalid Authorization header")
        return False

    token = auth_header[7:]

    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        # Get expected audience (our service URL)
        audience = os.getenv("CLOUD_RUN_SERVICE_URL", "")
        if not audience:
            logger.error("CLOUD_RUN_SERVICE_URL not set, cannot verify token")
            return False

        # Verify token signature and claims
        claim = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=audience,
        )

        # Optionally verify the service account email
        expected_sa = os.getenv("TASKS_SERVICE_ACCOUNT")
        if expected_sa and claim.get("email") != expected_sa:
            logger.warning(
                f"Token email mismatch: expected {expected_sa}, got {claim.get('email')}"
            )
            return False

        return True

    except Exception as e:
        logger.warning(f"OIDC token verification failed: {e}")
        return False


@csrf_exempt
@require_POST
@traced("pubsub_task_handler")
def pubsub_push_handler(request):
    """
    Handle Pub/Sub push delivery.

    Pub/Sub sends a POST with JSON body containing the message envelope.
    We decode the message, look up the task, and execute it.

    Returns:
        200: Task executed successfully (acks message)
        400: Bad request (acks message to prevent infinite retries)
        403: Unauthorized (invalid or missing OIDC token)
        429: Database at capacity (nacks message for retry with backoff)
        500: Task failed (nacks message for retry)
    """
    # Verify OIDC token (skipped in DEBUG mode)
    if not _verify_oidc_token(request):
        return HttpResponseForbidden("Unauthorized")

    # Check database connectivity before processing
    # If connection pool is exhausted, return 429 to trigger Pub/Sub retry
    try:
        connection.ensure_connection()
    except OperationalError as e:
        if "connection slots" in str(e) or "too many connections" in str(e).lower():
            logger.warning(
                "Database connection pool exhausted, returning 429 for retry",
                extra={"error": str(e)},
            )
            return HttpResponse("Database at capacity", status=429)
        raise

    # Parse the Pub/Sub envelope
    with span("parse_envelope"):
        try:
            raw_body = request.body
            # Log the raw request for debugging
            logger.info(
                "Received Pub/Sub push request",
                extra={
                    "content_type": request.content_type,
                    "body_length": len(raw_body),
                },
            )
            envelope = json.loads(raw_body)
            message = envelope.get("message", {})
            message_id = message.get("messageId", "unknown")
            logger.debug(
                "Parsed Pub/Sub envelope",
                extra={
                    "message_id": message_id,
                    "envelope_keys": list(envelope.keys()),
                    "message_keys": list(message.keys()) if message else [],
                },
            )
        except json.JSONDecodeError as e:
            # Log truncated body for debugging (avoid logging huge payloads)
            body_preview = raw_body[:500].decode("utf-8", errors="replace")
            logger.error(
                f"Invalid JSON in Pub/Sub push: {e}",
                extra={"body_preview": body_preview},
            )
            return HttpResponseBadRequest("Invalid JSON")

    # Decode the message data
    with span("decode_message", message_id=message_id):
        data_b64 = message.get("data")
        if not data_b64:
            logger.error(
                "Missing 'data' field in Pub/Sub message",
                extra={
                    "message_id": message_id,
                    "message_keys": list(message.keys()),
                    "message_attributes": message.get("attributes", {}),
                },
            )
            return HttpResponseBadRequest("Missing data field")

        try:
            data_json = base64.b64decode(data_b64).decode("utf-8")
            data = json.loads(data_json)
            logger.debug(
                "Decoded message data",
                extra={
                    "message_id": message_id,
                    "data_keys": list(data.keys()) if isinstance(data, dict) else None,
                },
            )
        except (ValueError, json.JSONDecodeError) as e:
            # Log what we tried to decode (truncated)
            data_preview = data_b64[:200] if len(data_b64) > 200 else data_b64
            logger.error(
                f"Failed to decode message data: {e}",
                extra={
                    "message_id": message_id,
                    "data_b64_preview": data_preview,
                    "data_b64_length": len(data_b64),
                },
            )
            return HttpResponseBadRequest("Invalid message data")

    # Extract task info
    task_id = data.get("task_id", "unknown")
    task_name = data.get("task_name")
    args = data.get("args", [])
    kwargs = data.get("kwargs", {})

    logger.info(
        "Processing task from Pub/Sub",
        extra={
            "message_id": message_id,
            "task_id": task_id,
            "task_name": task_name,
            "args_count": len(args) if isinstance(args, list) else None,
            "kwargs_keys": list(kwargs.keys()) if isinstance(kwargs, dict) else None,
        },
    )

    # Validate args/kwargs types (defense in depth)
    if not isinstance(args, list):
        logger.error(
            "Invalid 'args' in message payload: expected list",
            extra={
                "message_id": message_id,
                "task_name": task_name,
                "args_type": type(args).__name__,
                "args_value": str(args)[:200],
            },
        )
        return HttpResponseBadRequest("Invalid message format")

    if not isinstance(kwargs, dict):
        logger.error(
            "Invalid 'kwargs' in message payload: expected dict",
            extra={
                "message_id": message_id,
                "task_name": task_name,
                "kwargs_type": type(kwargs).__name__,
                "kwargs_value": str(kwargs)[:200],
            },
        )
        return HttpResponseBadRequest("Invalid message format")

    if not task_name:
        logger.error(
            "Missing task_name in message payload",
            extra={
                "message_id": message_id,
                "data_keys": list(data.keys()),
                "data_preview": str(data)[:500],
            },
        )
        return HttpResponseBadRequest("Missing task_name")

    # Look up the task
    with span("lookup_task", task_name=task_name, task_id=task_id):
        route = get_task(task_name)
        if not route:
            from gyrinx.tasks.registry import get_all_tasks

            registered_task_names = [t.name for t in get_all_tasks()]
            logger.error(
                f"Unknown task: {task_name}",
                extra={
                    "message_id": message_id,
                    "task_id": task_id,
                    "task_name": task_name,
                    "registered_tasks": registered_task_names,
                },
            )
            # Return 400 to ack and prevent infinite retries for unknown tasks
            # Don't include task_name in response to prevent information disclosure
            return HttpResponseBadRequest("Unknown task")

    # Execute the task
    with span("execute_task", task_name=task_name, task_id=task_id):
        # Parse enqueued_at from message if available
        enqueued_at = None
        if "enqueued_at" in data:
            try:
                from dateutil.parser import isoparse

                enqueued_at = isoparse(data["enqueued_at"])
            except (ValueError, ImportError):
                pass

        # Send task_started signal (signal handler calls mark_running)
        started_result = _build_task_result(
            task_id=task_id,
            task_name=task_name,
            args=args,
            kwargs=kwargs,
            status=TaskResultStatus.RUNNING,
            enqueued_at=enqueued_at,
        )
        task_started.send(sender=PubSubBackend, task_result=started_result)

        try:
            track(
                "task_started",
                task_id=task_id,
                task_name=task_name,
                message_id=message_id,
            )

            # Call the underlying function directly, not the Task wrapper
            result = route._underlying_func(*args, **kwargs)

            # Send task_finished signal for success (signal handler calls mark_successful)
            finished_result = _build_task_result(
                task_id=task_id,
                task_name=task_name,
                args=args,
                kwargs=kwargs,
                status=TaskResultStatus.SUCCESSFUL,
                enqueued_at=enqueued_at,
                return_value=result,
            )
            task_finished.send(sender=PubSubBackend, task_result=finished_result)

            track(
                "task_completed",
                task_id=task_id,
                task_name=task_name,
                message_id=message_id,
            )

            return HttpResponse("OK", status=200)

        except Exception as e:
            # Send task_finished signal for failure (signal handler calls mark_failed)
            failed_result = _build_task_result(
                task_id=task_id,
                task_name=task_name,
                args=args,
                kwargs=kwargs,
                status=TaskResultStatus.FAILED,
                enqueued_at=enqueued_at,
                error=e,
            )
            task_finished.send(sender=PubSubBackend, task_result=failed_result)

            track(
                "task_failed",
                task_id=task_id,
                task_name=task_name,
                message_id=message_id,
                error=str(e),
            )
            logger.error(
                f"Task {task_name} failed: {e}",
                extra={"task_id": task_id, "task_name": task_name},
                exc_info=True,
            )
            # Return 500 to nack message and trigger retry
            return HttpResponse("Task failed", status=500)
