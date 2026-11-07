"""Pub/Sub delivery and public task-group progress endpoints."""

import base64
import json
import logging
import os

from django.conf import settings
from django.db import OperationalError, connection
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from gyrinx.security_events import emit_pool_timeout
from gyrinx.tasks.backend import PubSubBackend
from gyrinx.tasks.executor import run_task
from gyrinx.tasks.groups import group_status
from gyrinx.tasks.registry import get_task
from gyrinx.tracing import span, traced

logger = logging.getLogger(__name__)


@require_GET
def task_group_status(request):
    """Return progress for ?group= without requiring authentication.

    Knowledge of the unguessable group key grants access. Return only task
    IDs, labels, states and aggregate counts.
    """
    group_key = request.GET.get("group", "").strip()
    if not group_key:
        return HttpResponseBadRequest("Missing required 'group' query parameter.")
    return JsonResponse(group_status(group_key))


def _verify_oidc_token(request) -> bool:
    """Validate a Google-signed token for this service, unless DEBUG is enabled.

    Require CLOUD_RUN_SERVICE_URL as the audience. When TASKS_SERVICE_ACCOUNT
    is configured, also require that email claim. Return False on any failure.
    """
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

        audience = os.getenv("CLOUD_RUN_SERVICE_URL", "")
        if not audience:
            logger.error("CLOUD_RUN_SERVICE_URL not set, cannot verify token")
            return False

        claim = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=audience,
        )

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
    """Validate a Pub/Sub envelope and execute its registered task.

    Return 200 on success, 400 for malformed or unknown tasks, 403 for failed
    authentication, 429 for database capacity, 503 for paused writes and 500
    for task failure. Pub/Sub retries non-success responses, including 400.
    """
    if not _verify_oidc_token(request):
        return HttpResponseForbidden("Unauthorized")

    try:
        connection.ensure_connection()
    except OperationalError as e:
        # Recognise both PostgreSQL capacity errors and psycopg pool checkout timeouts.
        msg = str(e).lower()
        if (
            "connection slots" in msg
            or "too many connections" in msg
            or "couldn't get a connection" in msg
        ):
            emit_pool_timeout(request)
            logger.warning(
                "Database connection pool exhausted, returning 429 for retry",
                extra={"error_type": type(e).__name__},
            )
            return HttpResponse("Database at capacity", status=429)
        raise

    with span("parse_envelope"):
        try:
            raw_body = request.body
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
            body_preview = raw_body[:500].decode("utf-8", errors="replace")
            logger.error(
                f"Invalid JSON in Pub/Sub push: {e}",
                extra={"body_preview": body_preview},
            )
            return HttpResponseBadRequest("Invalid JSON")

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
            # Keep the unknown task name out of the public response.
            return HttpResponseBadRequest("Unknown task")

    with span("execute_task", task_name=task_name, task_id=task_id):
        enqueued_at = None
        if "enqueued_at" in data:
            try:
                from dateutil.parser import isoparse

                enqueued_at = isoparse(data["enqueued_at"])
            except ValueError, ImportError:
                pass

        # Use the same lifecycle signals and execution records as local delivery.
        # Map task exceptions returned by run_task to a retryable response.
        from gyrinx.site.write_pause import task_delivery_gate

        with task_delivery_gate(route, kwargs) as admission:
            if not admission.allowed:
                response = HttpResponse("Changes are temporarily paused.", status=503)
                response["Retry-After"] = "30"
                return response
            ok, _return_value, _error = run_task(
                route._underlying_func,
                task_name=task_name,
                task_id=task_id,
                args=args,
                kwargs=kwargs,
                enqueued_at=enqueued_at,
                sender=PubSubBackend,
                track_extra={"message_id": message_id},
            )

        if ok:
            return HttpResponse("OK", status=200)

        return HttpResponse("Task failed", status=500)
