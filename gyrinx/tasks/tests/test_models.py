"""
Tests for the TaskExecution model.
"""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from gyrinx.core.models.state_machine import InvalidStateTransition
from gyrinx.tasks.models import TaskExecution


def make_task_id():
    """Generate a unique task ID for tests."""
    return f"test-task-{uuid.uuid4()}"


# =============================================================================
# Model Inheritance Tests
# =============================================================================


@pytest.mark.django_db
def test_task_execution_has_uuid_pk():
    """TaskExecution should have UUID primary key from Base."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.pk is not None
    # UUID format check
    assert len(str(execution.pk)) == 36


@pytest.mark.django_db
def test_task_execution_has_timestamps():
    """TaskExecution should have created and modified from Base."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.created is not None
    assert execution.modified is not None


@pytest.mark.django_db
def test_task_execution_has_state_machine():
    """TaskExecution should have state machine via states property."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    # Should have state machine methods via states accessor
    assert hasattr(execution.states, "transition_to")
    assert hasattr(execution.states, "can_transition_to")
    assert hasattr(execution.states, "history")


# =============================================================================
# State Configuration Tests
# =============================================================================


@pytest.mark.django_db
def test_has_correct_states():
    """TaskExecution should have READY, RUNNING, SUCCESSFUL, FAILED states."""
    descriptor = TaskExecution.states
    states = [s[0] for s in descriptor.states]
    assert "READY" in states
    assert "RUNNING" in states
    assert "SUCCESSFUL" in states
    assert "FAILED" in states


@pytest.mark.django_db
def test_initial_state_is_ready():
    """Initial state should be READY."""
    descriptor = TaskExecution.states
    assert descriptor.initial == "READY"


@pytest.mark.django_db
def test_transitions_from_ready():
    """READY can transition to RUNNING and FAILED."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    valid = execution.states.get_valid_transitions()
    assert set(valid) == {"RUNNING", "FAILED"}


@pytest.mark.django_db
def test_transitions_from_running():
    """RUNNING can transition to SUCCESSFUL and FAILED."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        status="RUNNING",
        enqueued_at=timezone.now(),
    )
    valid = execution.states.get_valid_transitions()
    assert set(valid) == {"SUCCESSFUL", "FAILED"}


@pytest.mark.django_db
def test_no_transitions_from_successful():
    """SUCCESSFUL is a terminal state."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        status="SUCCESSFUL",
        enqueued_at=timezone.now(),
    )
    assert execution.states.get_valid_transitions() == []


@pytest.mark.django_db
def test_no_transitions_from_failed():
    """FAILED is a terminal state."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        status="FAILED",
        enqueued_at=timezone.now(),
    )
    assert execution.states.get_valid_transitions() == []


# =============================================================================
# Field Tests
# =============================================================================


@pytest.mark.django_db
def test_task_name_field():
    """task_name field should store task name."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="my_important_task",
        enqueued_at=timezone.now(),
    )
    assert execution.task_name == "my_important_task"


@pytest.mark.django_db
def test_args_field_defaults_to_empty_list():
    """args field should default to empty list."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.args == []


@pytest.mark.django_db
def test_args_field_stores_list():
    """args field should store list of arguments."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        args=["arg1", 42, True],
        enqueued_at=timezone.now(),
    )
    assert execution.args == ["arg1", 42, True]


@pytest.mark.django_db
def test_kwargs_field_defaults_to_empty_dict():
    """kwargs field should default to empty dict."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.kwargs == {}


@pytest.mark.django_db
def test_kwargs_field_stores_dict():
    """kwargs field should store dict of keyword arguments."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        kwargs={"key1": "value1", "key2": 42},
        enqueued_at=timezone.now(),
    )
    assert execution.kwargs == {"key1": "value1", "key2": 42}


@pytest.mark.django_db
def test_return_value_field_nullable():
    """return_value field should be nullable."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.return_value is None


@pytest.mark.django_db
def test_return_value_field_stores_json():
    """return_value field should store JSON-serializable values."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        return_value={"result": "success", "count": 42},
        enqueued_at=timezone.now(),
    )
    assert execution.return_value == {"result": "success", "count": 42}


@pytest.mark.django_db
def test_error_message_field_blank():
    """error_message field should allow blank."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.error_message == ""


@pytest.mark.django_db
def test_error_traceback_field_blank():
    """error_traceback field should allow blank."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.error_traceback == ""


@pytest.mark.django_db
def test_timing_fields():
    """Timing fields should be set correctly."""
    now = timezone.now()
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=now,
    )
    assert execution.enqueued_at == now
    assert execution.started_at is None
    assert execution.finished_at is None


# =============================================================================
# Task State Lifecycle Tests
# =============================================================================


@pytest.mark.django_db
def test_create_task_in_ready_state():
    """New tasks should start as READY."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.status == "READY"


@pytest.mark.django_db
def test_mark_running():
    """mark_running() should update status and started_at."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    execution.mark_running()

    assert execution.status == "RUNNING"
    assert execution.started_at is not None


@pytest.mark.django_db
def test_mark_running_with_metadata():
    """mark_running() should store metadata in transition."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    execution.mark_running(metadata={"message_id": "msg-123"})

    transition = execution.states.history.first()
    assert transition.metadata == {"message_id": "msg-123"}


@pytest.mark.django_db
def test_mark_successful():
    """mark_successful() should update status, finished_at, and return_value."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    execution.mark_running()
    execution.mark_successful(return_value={"result": "ok"})

    assert execution.status == "SUCCESSFUL"
    assert execution.finished_at is not None
    assert execution.return_value == {"result": "ok"}


@pytest.mark.django_db
def test_mark_successful_without_return_value():
    """mark_successful() should work without return_value."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    execution.mark_running()
    execution.mark_successful()

    assert execution.status == "SUCCESSFUL"
    assert execution.return_value is None


@pytest.mark.django_db
def test_mark_failed_from_ready():
    """mark_failed() should work from READY state."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    execution.mark_failed(error_message="Invalid arguments")

    assert execution.status == "FAILED"
    assert execution.error_message == "Invalid arguments"


@pytest.mark.django_db
def test_mark_failed_from_running():
    """mark_failed() should work from RUNNING state."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    execution.mark_running()
    execution.mark_failed(
        error_message="Task crashed",
        error_traceback="Traceback (most recent call last):\n...",
    )

    assert execution.status == "FAILED"
    assert execution.finished_at is not None
    assert execution.error_message == "Task crashed"
    assert "Traceback" in execution.error_traceback


# =============================================================================
# Convenience Property Tests
# =============================================================================


@pytest.mark.django_db
def test_is_complete_property():
    """is_complete should be True for SUCCESSFUL/FAILED."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.is_complete is False

    execution.mark_running()
    assert execution.is_complete is False

    execution.mark_successful()
    assert execution.is_complete is True


@pytest.mark.django_db
def test_is_complete_for_failed():
    """is_complete should be True for FAILED."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    execution.mark_failed(error_message="Error")
    assert execution.is_complete is True


@pytest.mark.django_db
def test_is_success_property():
    """is_success should be True only for SUCCESSFUL."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.is_success is False

    execution.mark_running()
    assert execution.is_success is False

    execution.mark_successful()
    assert execution.is_success is True


@pytest.mark.django_db
def test_is_failed_property():
    """is_failed should be True only for FAILED."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.is_failed is False

    execution.mark_failed(error_message="Error")
    assert execution.is_failed is True


@pytest.mark.django_db
def test_duration_property():
    """duration should return timedelta when finished."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    execution.mark_running()
    # Simulate some time passing
    execution.started_at = timezone.now() - timedelta(seconds=5)
    execution.save()
    execution.mark_successful()

    duration = execution.duration
    assert duration is not None
    assert duration.total_seconds() >= 0


@pytest.mark.django_db
def test_duration_none_if_not_finished():
    """duration should return None if task not finished."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.duration is None

    execution.mark_running()
    assert execution.duration is None


@pytest.mark.django_db
def test_duration_none_if_not_started():
    """duration should return None if task not started."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    # Force finished_at without started_at (edge case)
    execution.finished_at = timezone.now()
    assert execution.duration is None


# =============================================================================
# String Representation Tests
# =============================================================================


@pytest.mark.django_db
def test_str_representation():
    """__str__ should show task name, status, and ID."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    str_repr = str(execution)
    assert "test_task" in str_repr
    assert "READY" in str_repr
    assert execution.task_id in str_repr


# =============================================================================
# Invalid Transition Tests
# =============================================================================


@pytest.mark.django_db
def test_cannot_transition_successful_to_running():
    """Cannot transition from SUCCESSFUL to any other state."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    execution.mark_running()
    execution.mark_successful()

    with pytest.raises(InvalidStateTransition):
        execution.states.transition_to("RUNNING")


@pytest.mark.django_db
def test_cannot_transition_failed_to_running():
    """Cannot transition from FAILED to any other state."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    execution.mark_failed(error_message="Error")

    with pytest.raises(InvalidStateTransition):
        execution.states.transition_to("RUNNING")


# =============================================================================
# State Transitions Tracking Tests
# =============================================================================


@pytest.mark.django_db
def test_full_lifecycle_creates_transitions():
    """Full task lifecycle should create transition records."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    execution.mark_running()
    execution.mark_successful()

    transitions = list(execution.states.history)
    assert len(transitions) == 2

    # Most recent first (RUNNING -> SUCCESSFUL)
    assert transitions[0].from_status == "RUNNING"
    assert transitions[0].to_status == "SUCCESSFUL"

    # Earlier (READY -> RUNNING)
    assert transitions[1].from_status == "READY"
    assert transitions[1].to_status == "RUNNING"


@pytest.mark.django_db
def test_state_history_returns_transitions():
    """states.history should return QuerySet of transitions."""
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    execution.mark_running()

    # Access via states.history
    transitions = execution.states.history.all()
    assert transitions.count() == 1
