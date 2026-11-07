"""TaskExecution fields, lifecycle transitions and stored results."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from gyrinx.state_machine import InvalidStateTransition
from gyrinx.tasks.models import TaskExecution

pytestmark = pytest.mark.core


def make_task_id():
    """Generate a unique task ID for tests."""
    return f"test-task-{uuid.uuid4()}"


@pytest.mark.django_db
def test_task_execution_has_uuid_pk():

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.pk is not None
    assert len(str(execution.pk)) == 36


@pytest.mark.django_db
def test_task_execution_has_timestamps():

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.created is not None
    assert execution.modified is not None


@pytest.mark.django_db
def test_task_execution_has_state_machine():

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert hasattr(execution.states, "transition_to")
    assert hasattr(execution.states, "can_transition_to")
    assert hasattr(execution.states, "history")


@pytest.mark.django_db
def test_has_correct_states():

    descriptor = TaskExecution.states
    states = [s[0] for s in descriptor.states]
    assert "READY" in states
    assert "RUNNING" in states
    assert "SUCCESSFUL" in states
    assert "FAILED" in states


@pytest.mark.django_db
def test_initial_state_is_ready():

    descriptor = TaskExecution.states
    assert descriptor.initial == "READY"


@pytest.mark.django_db
def test_transitions_from_ready():

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    valid = execution.states.get_valid_transitions()
    assert set(valid) == {"RUNNING", "FAILED"}


@pytest.mark.django_db
def test_transitions_from_running():

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

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        status="SUCCESSFUL",
        enqueued_at=timezone.now(),
    )
    assert execution.states.get_valid_transitions() == []


@pytest.mark.django_db
def test_no_transitions_from_failed():

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        status="FAILED",
        enqueued_at=timezone.now(),
    )
    assert execution.states.get_valid_transitions() == []


@pytest.mark.django_db
def test_task_name_field():

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="my_important_task",
        enqueued_at=timezone.now(),
    )
    assert execution.task_name == "my_important_task"


@pytest.mark.django_db
def test_args_field_defaults_to_empty_list():

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.args == []


@pytest.mark.django_db
def test_args_field_stores_list():

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        args=["arg1", 42, True],
        enqueued_at=timezone.now(),
    )
    assert execution.args == ["arg1", 42, True]


@pytest.mark.django_db
def test_kwargs_field_defaults_to_empty_dict():

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.kwargs == {}


@pytest.mark.django_db
def test_kwargs_field_stores_dict():

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        kwargs={"key1": "value1", "key2": 42},
        enqueued_at=timezone.now(),
    )
    assert execution.kwargs == {"key1": "value1", "key2": 42}


@pytest.mark.django_db
def test_return_value_field_nullable():

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.return_value is None


@pytest.mark.django_db
def test_return_value_field_stores_json():

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        return_value={"result": "success", "count": 42},
        enqueued_at=timezone.now(),
    )
    assert execution.return_value == {"result": "success", "count": 42}


@pytest.mark.django_db
def test_error_message_field_blank():

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.error_message == ""


@pytest.mark.django_db
def test_error_traceback_field_blank():

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.error_traceback == ""


@pytest.mark.django_db
def test_timing_fields():

    now = timezone.now()
    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=now,
    )
    assert execution.enqueued_at == now
    assert execution.started_at is None
    assert execution.finished_at is None


@pytest.mark.django_db
def test_create_task_in_ready_state():

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    assert execution.status == "READY"


@pytest.mark.django_db
def test_mark_running():

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


@pytest.mark.django_db
def test_is_complete_property():

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

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    execution.mark_failed(error_message="Error")
    assert execution.is_complete is True


@pytest.mark.django_db
def test_is_success_property():

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

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    execution.mark_running()
    execution.started_at = timezone.now() - timedelta(seconds=5)
    execution.save()
    execution.mark_successful()

    duration = execution.duration
    assert duration is not None
    assert duration.total_seconds() >= 0


@pytest.mark.django_db
def test_duration_none_if_not_finished():

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

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    execution.finished_at = timezone.now()
    assert execution.duration is None


@pytest.mark.django_db
def test_str_representation():

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    str_repr = str(execution)
    assert "test_task" in str_repr
    assert "READY" in str_repr
    assert execution.task_id in str_repr


@pytest.mark.django_db
def test_cannot_transition_successful_to_running():

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

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    execution.mark_failed(error_message="Error")

    with pytest.raises(InvalidStateTransition):
        execution.states.transition_to("RUNNING")


@pytest.mark.django_db
def test_full_lifecycle_creates_transitions():

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    execution.mark_running()
    execution.mark_successful()

    transitions = list(execution.states.history)
    assert len(transitions) == 2

    assert transitions[0].from_status == "RUNNING"
    assert transitions[0].to_status == "SUCCESSFUL"

    assert transitions[1].from_status == "READY"
    assert transitions[1].to_status == "RUNNING"


@pytest.mark.django_db
def test_state_history_returns_transitions():

    execution = TaskExecution.objects.create(
        task_id=make_task_id(),
        task_name="test_task",
        enqueued_at=timezone.now(),
    )
    execution.mark_running()

    transitions = execution.states.history.all()
    assert transitions.count() == 1
