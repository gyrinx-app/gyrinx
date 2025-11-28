import json
import logging

import pytest

from gyrinx import tracker


@pytest.fixture
def caplog_json(caplog):
    """Fixture that parses JSON logs from caplog.

    Explicitly adds caplog's handler to the gyrinx.tracker logger
    since the parent gyrinx logger has propagate=False.
    """
    logger = logging.getLogger("gyrinx.tracker")
    # Add caplog's handler directly to the logger
    logger.addHandler(caplog.handler)
    original_level = logger.level
    logger.setLevel(logging.INFO)

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
    yield caplog

    # Cleanup
    logger.removeHandler(caplog.handler)
    logger.setLevel(original_level)


def test_track_basic_event(caplog_json):
    """Test tracking a basic event."""
    tracker.track("test_event")

    logs = caplog_json.get_json_logs()
    assert len(logs) == 1
    assert logs[0] == {"event": "test_event", "n": 1}


def test_track_event_with_count(caplog_json):
    """Test tracking an event with custom count."""
    tracker.track("test_event", n=5)

    logs = caplog_json.get_json_logs()
    assert len(logs) == 1
    assert logs[0] == {"event": "test_event", "n": 5}


def test_track_event_with_value(caplog_json):
    """Test tracking an event with distribution value."""
    tracker.track("response_time", value=123.45)

    logs = caplog_json.get_json_logs()
    assert len(logs) == 1
    assert logs[0] == {"event": "response_time", "n": 1, "value": 123.45}


def test_track_event_with_labels(caplog_json):
    """Test tracking an event with multiple labels."""
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


def test_track_stat_config_fallback_use_case(caplog_json):
    """Test the specific use case from ContentModStatApplyMixin."""
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
    tracker.track("event1")
    tracker.track("event2", n=2)
    tracker.track("event3", value=3.0)

    logs = caplog_json.get_json_logs()
    assert len(logs) == 3
    assert logs[0] == {"event": "event1", "n": 1}
    assert logs[1] == {"event": "event2", "n": 2}
    assert logs[2] == {"event": "event3", "n": 1, "value": 3.0}
