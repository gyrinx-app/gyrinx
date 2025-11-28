import json
import logging
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger("gyrinx.tracker")


def track(event: str, n: int = 1, value: Optional[float] = None, **labels: Any) -> None:
    """
    Emit a structured log event.

    In production, StructuredLogHandler formats this as JSON for Cloud Logging.
    In development, logs as JSON string to console.

    Args:
        event: Event name (e.g. 'stat_config_fallback_used')
        n: Count increment (default=1)
        value: Optional numeric value (e.g. for distributions)
        **labels: Arbitrary key=value metadata

    Example:
        track("stat_config_fallback_used", stat_name="ammo", model_type="ContentModStatApply")
    """
    payload = {
        "event": event,
        "n": n,
    }
    if value is not None:
        payload["value"] = value

    # Filter labels to only JSON-serializable values
    if labels:
        filtered_labels = {}
        for key, val in labels.items():
            try:
                # Side-effect test for JSON serializability
                json.dumps(val)
                filtered_labels[key] = val
            except (TypeError, ValueError):
                # Not JSON serializable, try to extract ID
                if hasattr(val, "id"):
                    filtered_labels[key] = str(val.id)
                elif isinstance(val, UUID):
                    filtered_labels[key] = str(val)
                else:
                    # Log that we're dropping this label
                    logger.debug(
                        f"Dropping non-serializable label '{key}' with type {type(val).__name__} for event '{event}'"
                    )
        payload["labels"] = filtered_labels

    # Always use Python logging - handler determines format
    logger.info(json.dumps(payload))
