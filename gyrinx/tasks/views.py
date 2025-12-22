"""
Pub/Sub push handler view.

This view receives push messages from Pub/Sub and dispatches them to the
appropriate task handlers based on the task_name in the message payload.
"""

import base64
import json
import logging

from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from gyrinx.tasks.registry import get_task
from gyrinx.tracing import span, traced
from gyrinx.tracker import track

logger = logging.getLogger(__name__)


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
        500: Task failed (nacks message for retry)
    """
    # Parse the Pub/Sub envelope
    with span("parse_envelope"):
        try:
            envelope = json.loads(request.body)
            message = envelope.get("message", {})
            message_id = message.get("messageId", "unknown")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in Pub/Sub push: {e}")
            return HttpResponseBadRequest("Invalid JSON")

    # Decode the message data
    with span("decode_message", message_id=message_id):
        data_b64 = message.get("data")
        if not data_b64:
            logger.error("Missing 'data' field in Pub/Sub message")
            return HttpResponseBadRequest("Missing data field")

        try:
            data_json = base64.b64decode(data_b64).decode("utf-8")
            data = json.loads(data_json)
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"Failed to decode message data: {e}")
            return HttpResponseBadRequest("Invalid message data")

    # Extract task info
    task_id = data.get("task_id", "unknown")
    task_name = data.get("task_name")
    args = data.get("args", [])
    kwargs = data.get("kwargs", {})

    if not task_name:
        logger.error("Missing task_name in message payload")
        return HttpResponseBadRequest("Missing task_name")

    # Look up the task
    with span("lookup_task", task_name=task_name, task_id=task_id):
        route = get_task(task_name)
        if not route:
            logger.error(f"Unknown task: {task_name}")
            # Return 400 to ack and prevent infinite retries for unknown tasks
            return HttpResponseBadRequest(f"Unknown task: {task_name}")

    # Execute the task
    with span("execute_task", task_name=task_name, task_id=task_id):
        try:
            track(
                "task_started",
                task_id=task_id,
                task_name=task_name,
                message_id=message_id,
            )

            # Call the underlying function directly, not the Task wrapper
            route._underlying_func(*args, **kwargs)

            track(
                "task_completed",
                task_id=task_id,
                task_name=task_name,
                message_id=message_id,
            )

            return HttpResponse("OK", status=200)

        except Exception as e:
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
