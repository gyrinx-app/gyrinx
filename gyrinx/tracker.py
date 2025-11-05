import json
import logging
import os
from typing import Any, Optional

# Check if we're in Google Cloud environment
IS_GOOGLE_CLOUD = os.getenv("GOOGLE_CLOUD_PROJECT") is not None

if IS_GOOGLE_CLOUD:
    try:
        from google.cloud import logging as cloud_logging

        _client = cloud_logging.Client()
        _logger = _client.logger("tracker")
        _use_cloud_logging = True
    except ImportError:
        _use_cloud_logging = False
        _logger = None
else:
    _use_cloud_logging = False
    _logger = None

# Fallback to standard Python logger
_fallback_logger = logging.getLogger("gyrinx.tracker")


def track(event: str, n: int = 1, value: Optional[float] = None, **labels: Any) -> None:
    """
    Emit a structured log event to Cloud Logging or local JSON logs.

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
    if labels:
        payload["labels"] = labels

    # Filter labels to only JSON-serializable values
    if labels:
        filtered_labels = {}
        for key, val in labels.items():
            try:
                json.dumps(val)
                filtered_labels[key] = val
            except (TypeError, ValueError):
                # Not JSON serializable, try to extract ID
                if hasattr(val, "id"):
                    filtered_labels[key] = str(val.id)
                # Otherwise drop the label
        payload["labels"] = filtered_labels

    if _use_cloud_logging:
        # Google Cloud Logging
        _logger.log_struct(payload, severity="INFO")
    else:
        # Local JSON logging
        _fallback_logger.info(json.dumps(payload))
