"""
Tests for the generic StateMachineMixin and StateTransition model.
"""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import models

from gyrinx.core.models.state_machine import (
    InvalidStateTransition,
    StateMachineMixin,
    StateTransition,
)
from gyrinx.models import Base


# Test model that uses StateMachineMixin
class TestStateMachineModel(StateMachineMixin, Base):
    """A test model for verifying StateMachineMixin behavior."""

    STATES = [
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("DONE", "Done"),
        ("FAILED", "Failed"),
    ]
    INITIAL_STATE = "PENDING"
    TRANSITIONS = {
        "PENDING": ["RUNNING", "FAILED"],
        "RUNNING": ["DONE", "FAILED"],
    }

    name = models.CharField(max_length=100, default="test")

    class Meta:
        app_label = "core"


# =============================================================================
# State Configuration Tests
# =============================================================================


@pytest.mark.django_db
def test_model_has_status_field():
    """Verify status field exists with db_index."""
    field = TestStateMachineModel._meta.get_field("status")
    assert field is not None
    assert field.db_index is True


@pytest.mark.django_db
def test_initial_state_set_on_create():
    """New instance should have INITIAL_STATE."""
    obj = TestStateMachineModel.objects.create()
    assert obj.status == "PENDING"


@pytest.mark.django_db
def test_explicit_status_preserved():
    """Explicitly set status should be preserved."""
    obj = TestStateMachineModel.objects.create(status="RUNNING")
    assert obj.status == "RUNNING"


@pytest.mark.django_db
def test_states_are_accessible():
    """STATES class attribute should be available."""
    assert TestStateMachineModel.STATES == [
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("DONE", "Done"),
        ("FAILED", "Failed"),
    ]


@pytest.mark.django_db
def test_transitions_are_accessible():
    """TRANSITIONS class attribute should be available."""
    expected = {
        "PENDING": ["RUNNING", "FAILED"],
        "RUNNING": ["DONE", "FAILED"],
    }
    assert TestStateMachineModel.TRANSITIONS == expected


@pytest.mark.django_db
def test_get_state_choices():
    """get_state_choices() should return STATES."""
    choices = TestStateMachineModel.get_state_choices()
    assert choices == TestStateMachineModel.STATES


# =============================================================================
# Transition Validation Tests
# =============================================================================


@pytest.mark.django_db
def test_can_transition_to_valid_state():
    """can_transition_to() returns True for valid transitions."""
    obj = TestStateMachineModel.objects.create()
    assert obj.can_transition_to("RUNNING") is True
    assert obj.can_transition_to("FAILED") is True


@pytest.mark.django_db
def test_cannot_transition_to_invalid_state():
    """can_transition_to() returns False for invalid transitions."""
    obj = TestStateMachineModel.objects.create()
    assert obj.can_transition_to("DONE") is False


@pytest.mark.django_db
def test_cannot_transition_to_same_state():
    """Self-transitions are blocked unless explicitly allowed."""
    obj = TestStateMachineModel.objects.create()
    assert obj.can_transition_to("PENDING") is False


@pytest.mark.django_db
def test_valid_transitions_from_pending():
    """Check all valid transitions from PENDING."""
    valid = TestStateMachineModel.get_valid_transitions("PENDING")
    assert set(valid) == {"RUNNING", "FAILED"}


@pytest.mark.django_db
def test_valid_transitions_from_running():
    """Check all valid transitions from RUNNING."""
    valid = TestStateMachineModel.get_valid_transitions("RUNNING")
    assert set(valid) == {"DONE", "FAILED"}


@pytest.mark.django_db
def test_terminal_states_have_no_transitions():
    """DONE and FAILED have no outbound transitions."""
    assert TestStateMachineModel.get_valid_transitions("DONE") == []
    assert TestStateMachineModel.get_valid_transitions("FAILED") == []


@pytest.mark.django_db
def test_is_terminal_property():
    """is_terminal property should be True for terminal states."""
    obj = TestStateMachineModel.objects.create()
    assert obj.is_terminal is False

    obj.status = "DONE"
    assert obj.is_terminal is True

    obj.status = "FAILED"
    assert obj.is_terminal is True


# =============================================================================
# State Transition Execution Tests
# =============================================================================


@pytest.mark.django_db
def test_transition_to_valid_state_succeeds():
    """transition_to() updates status on valid transition."""
    obj = TestStateMachineModel.objects.create()
    obj.transition_to("RUNNING")
    assert obj.status == "RUNNING"


@pytest.mark.django_db
def test_transition_to_invalid_state_raises():
    """transition_to() raises exception on invalid transition."""
    obj = TestStateMachineModel.objects.create()
    with pytest.raises(InvalidStateTransition) as exc_info:
        obj.transition_to("DONE")

    assert exc_info.value.from_status == "PENDING"
    assert exc_info.value.to_status == "DONE"
    assert set(exc_info.value.allowed) == {"RUNNING", "FAILED"}


@pytest.mark.django_db
def test_transition_creates_record():
    """transition_to() creates StateTransition record."""
    obj = TestStateMachineModel.objects.create()
    transition = obj.transition_to("RUNNING")

    assert transition is not None
    assert isinstance(transition, StateTransition)
    assert transition.pk is not None


@pytest.mark.django_db
def test_transition_records_from_status():
    """Transition record captures previous status."""
    obj = TestStateMachineModel.objects.create()
    transition = obj.transition_to("RUNNING")

    assert transition.from_status == "PENDING"


@pytest.mark.django_db
def test_transition_records_to_status():
    """Transition record captures new status."""
    obj = TestStateMachineModel.objects.create()
    transition = obj.transition_to("RUNNING")

    assert transition.to_status == "RUNNING"


@pytest.mark.django_db
def test_transition_records_timestamp():
    """Transition record has auto-set timestamp."""
    obj = TestStateMachineModel.objects.create()
    transition = obj.transition_to("RUNNING")

    assert transition.transitioned_at is not None


@pytest.mark.django_db
def test_transition_accepts_metadata():
    """transition_to(metadata={...}) stores metadata."""
    obj = TestStateMachineModel.objects.create()
    metadata = {"worker_id": "worker-1", "attempt": 1}
    transition = obj.transition_to("RUNNING", metadata=metadata)

    assert transition.metadata == metadata


@pytest.mark.django_db
def test_multiple_transitions_create_multiple_records():
    """Each transition creates a new record."""
    obj = TestStateMachineModel.objects.create()
    obj.transition_to("RUNNING")
    obj.transition_to("DONE")

    transitions = obj.get_transitions()
    assert transitions.count() == 2


@pytest.mark.django_db
def test_get_transitions_returns_all():
    """get_transitions() returns all transitions for object."""
    obj = TestStateMachineModel.objects.create()
    obj.transition_to("RUNNING")
    obj.transition_to("DONE")

    transitions = list(obj.get_transitions())
    assert len(transitions) == 2
    # Should be ordered by transitioned_at descending
    assert transitions[0].to_status == "DONE"
    assert transitions[1].to_status == "RUNNING"


@pytest.mark.django_db
def test_get_latest_transition():
    """get_latest_transition() returns most recent transition."""
    obj = TestStateMachineModel.objects.create()
    obj.transition_to("RUNNING")
    obj.transition_to("DONE")

    latest = obj.get_latest_transition()
    assert latest.to_status == "DONE"


@pytest.mark.django_db
def test_get_latest_transition_returns_none_when_no_transitions():
    """get_latest_transition() returns None if no transitions."""
    obj = TestStateMachineModel.objects.create()
    assert obj.get_latest_transition() is None


@pytest.mark.django_db
def test_status_display_property():
    """status_display returns human-readable label."""
    obj = TestStateMachineModel.objects.create()
    assert obj.status_display == "Pending"

    obj.status = "RUNNING"
    assert obj.status_display == "Running"


# =============================================================================
# StateTransition Model Tests
# =============================================================================


@pytest.mark.django_db
def test_state_transition_str():
    """StateTransition __str__ shows transition."""
    obj = TestStateMachineModel.objects.create()
    transition = obj.transition_to("RUNNING")

    str_repr = str(transition)
    assert "PENDING" in str_repr
    assert "RUNNING" in str_repr


@pytest.mark.django_db
def test_state_transition_str_initial():
    """StateTransition __str__ shows (initial) for first transition without from_status."""
    content_type = ContentType.objects.get_for_model(TestStateMachineModel)
    transition = StateTransition.objects.create(
        content_type=content_type,
        object_id="00000000-0000-0000-0000-000000000001",
        from_status="",
        to_status="READY",
    )

    str_repr = str(transition)
    assert "(initial)" in str_repr
    assert "READY" in str_repr


@pytest.mark.django_db
def test_state_transition_generic_relation():
    """StateTransition links correctly via GenericForeignKey."""
    obj = TestStateMachineModel.objects.create()
    transition = obj.transition_to("RUNNING")

    # Verify content_type and object_id
    content_type = ContentType.objects.get_for_model(TestStateMachineModel)
    assert transition.content_type == content_type
    assert transition.object_id == obj.pk


@pytest.mark.django_db
def test_transition_with_save_false():
    """transition_to(save=False) should not save the model."""
    obj = TestStateMachineModel.objects.create()

    # Use save=False
    obj.transition_to("RUNNING", save=False)

    # Refresh from database - status should still be PENDING
    obj.refresh_from_db()
    assert obj.status == "PENDING"


@pytest.mark.django_db
def test_transition_metadata_defaults_to_empty_dict():
    """Metadata should default to empty dict."""
    obj = TestStateMachineModel.objects.create()
    transition = obj.transition_to("RUNNING")

    assert transition.metadata == {}
