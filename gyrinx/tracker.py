import json
import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger("gyrinx.tracker")


def track(event: str, n: int = 1, value: float | None = None, **labels: Any) -> None:
    """Emit a JSON log event with an optional count, value and labels.

    Keep JSON-serialisable labels. Convert object IDs and UUID labels to
    strings; omit other unsupported values and log their types at debug level.
    """
    payload = {
        "event": event,
        "n": n,
    }
    if value is not None:
        payload["value"] = value

    if labels:
        filtered_labels = {}
        for key, val in labels.items():
            try:
                json.dumps(val)
                filtered_labels[key] = val
            except TypeError, ValueError:
                if hasattr(val, "id"):
                    filtered_labels[key] = str(val.id)
                elif isinstance(val, UUID):
                    filtered_labels[key] = str(val)
                else:
                    logger.debug(
                        f"Dropping non-serializable label '{key}' with type {type(val).__name__} for event '{event}'"
                    )
        payload["labels"] = filtered_labels

    # The configured logging handler determines the destination and outer format.
    logger.info(json.dumps(payload))
