import json
import logging
import os
from unittest.mock import patch

import pytest

from gyrinx import tracker


@pytest.fixture
def mock_cloud_client():
    """Mock Google Cloud Logging client."""
    with patch("gyrinx.tracker._use_cloud_logging", True):
        with patch("gyrinx.tracker._logger") as mock_logger:
            yield mock_logger


@pytest.fixture
def caplog_json(caplog):
    """Fixture that parses JSON logs from caplog."""
    caplog.set_level(logging.INFO)

    def get_json_logs():
        logs = []
        for record in caplog.records:
            if record.name == "gyrinx.tracker":
                try:
                    logs.append(json.loads(record.message))
                except json.JSONDecodeError:
                    pass
        return logs

    caplog.get_json_logs = get_json_logs
    return caplog


def test_track_basic_event_local(caplog_json):
    """Test tracking a basic event with local logging."""
    with patch("gyrinx.tracker._use_cloud_logging", False):
        tracker.track("test_event")

    logs = caplog_json.get_json_logs()
    assert len(logs) == 1
    assert logs[0] == {"event": "test_event", "n": 1}


def test_track_event_with_count(caplog_json):
    """Test tracking an event with custom count."""
    with patch("gyrinx.tracker._use_cloud_logging", False):
        tracker.track("test_event", n=5)

    logs = caplog_json.get_json_logs()
    assert len(logs) == 1
    assert logs[0] == {"event": "test_event", "n": 5}


def test_track_event_with_value(caplog_json):
    """Test tracking an event with distribution value."""
    with patch("gyrinx.tracker._use_cloud_logging", False):
        tracker.track("response_time", value=123.45)

    logs = caplog_json.get_json_logs()
    assert len(logs) == 1
    assert logs[0] == {"event": "response_time", "n": 1, "value": 123.45}


def test_track_event_with_labels(caplog_json):
    """Test tracking an event with multiple labels."""
    with patch("gyrinx.tracker._use_cloud_logging", False):
        tracker.track("api_call", endpoint="/api/v1/fighters", method="GET", status=200)

    logs = caplog_json.get_json_logs()
    assert len(logs) == 1
    assert logs[0] == {
        "event": "api_call",
        "n": 1,
        "labels": {"endpoint": "/api/v1/fighters", "method": "GET", "status": 200},
    }


def test_track_event_with_all_parameters(caplog_json):
    """Test tracking an event with all possible parameters."""
    with patch("gyrinx.tracker._use_cloud_logging", False):
        tracker.track(
            "complex_event",
            n=3,
            value=99.9,
            user="test_user",
            action="create",
            resource="fighter",
        )

    logs = caplog_json.get_json_logs()
    assert len(logs) == 1
    assert logs[0] == {
        "event": "complex_event",
        "n": 3,
        "value": 99.9,
        "labels": {"user": "test_user", "action": "create", "resource": "fighter"},
    }


def test_track_cloud_logging_path(mock_cloud_client):
    """Test that cloud logging path calls log_struct correctly."""
    tracker.track("cloud_event", n=2, value=50.5, environment="production")

    mock_cloud_client.log_struct.assert_called_once_with(
        {
            "event": "cloud_event",
            "n": 2,
            "value": 50.5,
            "labels": {"environment": "production"},
        },
        severity="INFO",
    )


def test_environment_detection():
    """Test that environment detection works correctly."""
    # Test without GOOGLE_CLOUD_PROJECT
    with patch.dict("os.environ", {}, clear=True):
        # Access the IS_GOOGLE_CLOUD variable directly
        assert os.getenv("GOOGLE_CLOUD_PROJECT") is None

    # Test with GOOGLE_CLOUD_PROJECT
    with patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "test-project"}):
        assert os.getenv("GOOGLE_CLOUD_PROJECT") == "test-project"


def test_google_cloud_import_failure(caplog_json):
    """Test graceful handling when google-cloud-logging import fails."""
    # Test that the tracker still works even if google-cloud-logging is not available
    with patch("gyrinx.tracker._use_cloud_logging", False):
        tracker.track("test_event_import_fail")

    logs = caplog_json.get_json_logs()
    assert len(logs) == 1
    assert logs[0]["event"] == "test_event_import_fail"


def test_track_stat_config_fallback_use_case(caplog_json):
    """Test the specific use case from ContentModStatApplyMixin."""
    with patch("gyrinx.tracker._use_cloud_logging", False):
        tracker.track(
            "stat_config_fallback_used",
            stat_name="ammo",
            model_class="ContentModStatApply",
        )

    logs = caplog_json.get_json_logs()
    assert len(logs) == 1
    assert logs[0] == {
        "event": "stat_config_fallback_used",
        "n": 1,
        "labels": {"stat_name": "ammo", "model_class": "ContentModStatApply"},
    }


def test_multiple_track_calls(caplog_json):
    """Test multiple track calls produce separate log entries."""
    with patch("gyrinx.tracker._use_cloud_logging", False):
        tracker.track("event1")
        tracker.track("event2", n=2)
        tracker.track("event3", value=3.0)

    logs = caplog_json.get_json_logs()
    assert len(logs) == 3
    assert logs[0] == {"event": "event1", "n": 1}
    assert logs[1] == {"event": "event2", "n": 2}
    assert logs[2] == {"event": "event3", "n": 1, "value": 3.0}
