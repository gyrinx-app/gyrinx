"""
Tests for the StateMachine descriptor and per-model transition tables.
"""

import threading

import pytest
from django.db import connection, models

from gyrinx.state_machine import (
    STATUS_MAX_LENGTH,
    InvalidStateTransition,
    StateMachine,
)
from gyrinx.models import Base


# Test model that uses StateMachine
class StateMachineTestModel(Base):
    """A test model for verifying StateMachine behavior."""

    states = StateMachine(
        states=[
            ("PENDING", "Pending"),
            ("RUNNING", "Running"),
            ("DONE", "Done"),
            ("FAILED", "Failed"),
        ],
        initial="PENDING",
        transitions={
            "PENDING": ["RUNNING", "FAILED"],
            "RUNNING": ["DONE", "FAILED"],
        },
    )

    name = models.CharField(max_length=100, default="test")

    class Meta:
        app_label = "tasks"


@pytest.fixture(scope="session", autouse=True)
def _ensure_state_machine_test_tables(django_db_setup, django_db_blocker):
    """Create tables for test-only models when running with --migrations.

    With --nomigrations (the default), syncdb creates tables for all discovered
    models including test models. With --migrations, only migrated tables are
    created, so this fixture fills the gap.
    """
    with django_db_blocker.unblock():
        table_names = connection.introspection.table_names()
        if "tasks_statemachinetestmodel" not in table_names:
            with connection.schema_editor() as schema_editor:
                schema_editor.create_model(StateMachineTestModel)
                schema_editor.create_model(
                    StateMachineTestModel.states.transition_model
                )


# =============================================================================
# State Configuration Tests
# =============================================================================


@pytest.mark.django_db
def test_model_has_status_field():
    """Verify status field exists with db_index."""
    field = StateMachineTestModel._meta.get_field("status")
    assert field is not None
    assert field.db_index is True


@pytest.mark.django_db
def test_initial_state_set_on_create():
    """New instance should have initial state."""
    obj = StateMachineTestModel.objects.create()
    assert obj.status == "PENDING"
    assert obj.states.current == "PENDING"


@pytest.mark.django_db
def test_explicit_status_preserved():
    """Explicitly set status should be preserved."""
    obj = StateMachineTestModel.objects.create(status="RUNNING")
    assert obj.status == "RUNNING"
    assert obj.states.current == "RUNNING"


@pytest.mark.django_db
def test_states_accessible_via_descriptor():
    """States should be accessible via class-level descriptor."""
    descriptor = StateMachineTestModel.states
    assert descriptor.states == [
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("DONE", "Done"),
        ("FAILED", "Failed"),
    ]


@pytest.mark.django_db
def test_transitions_accessible_via_descriptor():
    """Transitions should be accessible via class-level descriptor."""
    descriptor = StateMachineTestModel.states
    expected = {
        "PENDING": ["RUNNING", "FAILED"],
        "RUNNING": ["DONE", "FAILED"],
    }
    assert descriptor.transitions == expected


@pytest.mark.django_db
def test_initial_state_accessible_via_descriptor():
    """Initial state should be accessible via class-level descriptor."""
    descriptor = StateMachineTestModel.states
    assert descriptor.initial == "PENDING"


# =============================================================================
# Transition Validation Tests
# =============================================================================


@pytest.mark.django_db
def test_can_transition_to_valid_state():
    """can_transition_to() returns True for valid transitions."""
    obj = StateMachineTestModel.objects.create()
    assert obj.states.can_transition_to("RUNNING") is True
    assert obj.states.can_transition_to("FAILED") is True


@pytest.mark.django_db
def test_cannot_transition_to_invalid_state():
    """can_transition_to() returns False for invalid transitions."""
    obj = StateMachineTestModel.objects.create()
    assert obj.states.can_transition_to("DONE") is False


@pytest.mark.django_db
def test_cannot_transition_to_same_state():
    """Self-transitions are blocked unless explicitly allowed."""
    obj = StateMachineTestModel.objects.create()
    assert obj.states.can_transition_to("PENDING") is False


@pytest.mark.django_db
def test_get_valid_transitions_from_pending():
    """Check all valid transitions from PENDING."""
    obj = StateMachineTestModel.objects.create()
    valid = obj.states.get_valid_transitions()
    assert set(valid) == {"RUNNING", "FAILED"}


@pytest.mark.django_db
def test_get_valid_transitions_from_running():
    """Check all valid transitions from RUNNING."""
    obj = StateMachineTestModel.objects.create(status="RUNNING")
    valid = obj.states.get_valid_transitions()
    assert set(valid) == {"DONE", "FAILED"}


@pytest.mark.django_db
def test_terminal_states_have_no_transitions():
    """DONE and FAILED have no outbound transitions."""
    obj = StateMachineTestModel.objects.create(status="DONE")
    assert obj.states.get_valid_transitions() == []

    obj.status = "FAILED"
    assert obj.states.get_valid_transitions() == []


@pytest.mark.django_db
def test_is_terminal_property():
    """is_terminal property should be True for terminal states."""
    obj = StateMachineTestModel.objects.create()
    assert obj.states.is_terminal is False

    obj.status = "DONE"
    assert obj.states.is_terminal is True

    obj.status = "FAILED"
    assert obj.states.is_terminal is True


# =============================================================================
# State Transition Execution Tests
# =============================================================================


@pytest.mark.django_db
def test_transition_to_valid_state_succeeds():
    """transition_to() updates status on valid transition."""
    obj = StateMachineTestModel.objects.create()
    obj.states.transition_to("RUNNING")
    assert obj.status == "RUNNING"
    assert obj.states.current == "RUNNING"


@pytest.mark.django_db
def test_transition_to_invalid_state_raises():
    """transition_to() raises exception on invalid transition."""
    obj = StateMachineTestModel.objects.create()
    with pytest.raises(InvalidStateTransition) as exc_info:
        obj.states.transition_to("DONE")

    assert exc_info.value.from_status == "PENDING"
    assert exc_info.value.to_status == "DONE"
    assert set(exc_info.value.allowed) == {"RUNNING", "FAILED"}


@pytest.mark.django_db
def test_transition_creates_record():
    """transition_to() creates a transition record."""
    obj = StateMachineTestModel.objects.create()
    transition = obj.states.transition_to("RUNNING")

    assert transition is not None
    assert transition.pk is not None


@pytest.mark.django_db
def test_transition_records_from_status():
    """Transition record captures previous status."""
    obj = StateMachineTestModel.objects.create()
    transition = obj.states.transition_to("RUNNING")

    assert transition.from_status == "PENDING"


@pytest.mark.django_db
def test_transition_records_to_status():
    """Transition record captures new status."""
    obj = StateMachineTestModel.objects.create()
    transition = obj.states.transition_to("RUNNING")

    assert transition.to_status == "RUNNING"


@pytest.mark.django_db
def test_transition_records_timestamp():
    """Transition record has auto-set timestamp."""
    obj = StateMachineTestModel.objects.create()
    transition = obj.states.transition_to("RUNNING")

    assert transition.transitioned_at is not None


@pytest.mark.django_db
def test_transition_accepts_metadata():
    """transition_to(metadata={...}) stores metadata."""
    obj = StateMachineTestModel.objects.create()
    metadata = {"worker_id": "worker-1", "attempt": 1}
    transition = obj.states.transition_to("RUNNING", metadata=metadata)

    assert transition.metadata == metadata


@pytest.mark.django_db
def test_multiple_transitions_create_multiple_records():
    """Each transition creates a new record."""
    obj = StateMachineTestModel.objects.create()
    obj.states.transition_to("RUNNING")
    obj.states.transition_to("DONE")

    assert obj.states.history.count() == 2


@pytest.mark.django_db
def test_history_returns_all_transitions():
    """history returns all transitions for object."""
    obj = StateMachineTestModel.objects.create()
    obj.states.transition_to("RUNNING")
    obj.states.transition_to("DONE")

    transitions = list(obj.states.history)
    assert len(transitions) == 2
    # Should be ordered by transitioned_at descending
    assert transitions[0].to_status == "DONE"
    assert transitions[1].to_status == "RUNNING"


@pytest.mark.django_db
def test_history_first_returns_latest():
    """history.first() returns most recent transition."""
    obj = StateMachineTestModel.objects.create()
    obj.states.transition_to("RUNNING")
    obj.states.transition_to("DONE")

    latest = obj.states.history.first()
    assert latest.to_status == "DONE"


@pytest.mark.django_db
def test_history_empty_when_no_transitions():
    """history is empty if no transitions."""
    obj = StateMachineTestModel.objects.create()
    assert obj.states.history.count() == 0
    assert obj.states.history.first() is None


@pytest.mark.django_db
def test_display_property():
    """display returns human-readable label."""
    obj = StateMachineTestModel.objects.create()
    assert obj.states.display == "Pending"

    obj.status = "RUNNING"
    assert obj.states.display == "Running"


# =============================================================================
# Transition Model Tests
# =============================================================================


@pytest.mark.django_db
def test_transition_str():
    """Transition __str__ shows transition."""
    obj = StateMachineTestModel.objects.create()
    transition = obj.states.transition_to("RUNNING")

    str_repr = str(transition)
    assert "PENDING" in str_repr
    assert "RUNNING" in str_repr


@pytest.mark.django_db
def test_transition_links_to_instance():
    """Transition links correctly to the model instance."""
    obj = StateMachineTestModel.objects.create()
    transition = obj.states.transition_to("RUNNING")

    assert transition.instance == obj
    assert transition.instance_id == obj.pk


@pytest.mark.django_db
def test_transition_with_save_false():
    """transition_to(save=False) should not save the model."""
    obj = StateMachineTestModel.objects.create()

    # Use save=False
    obj.states.transition_to("RUNNING", save=False)

    # Refresh from database - status should still be PENDING
    obj.refresh_from_db()
    assert obj.status == "PENDING"


@pytest.mark.django_db
def test_transition_metadata_defaults_to_empty_dict():
    """Metadata should default to empty dict."""
    obj = StateMachineTestModel.objects.create()
    transition = obj.states.transition_to("RUNNING")

    assert transition.metadata == {}


# =============================================================================
# Dynamic Model Creation Tests
# =============================================================================


@pytest.mark.django_db
def test_transition_model_created():
    """StateMachine creates a transition model dynamically."""
    # Access via descriptor instead of self-import
    transition_model = StateMachineTestModel.states.transition_model

    assert transition_model is not None
    assert transition_model.__name__ == "StateMachineTestModelStateTransition"
    assert transition_model._meta.app_label == "tasks"


@pytest.mark.django_db
def test_transition_model_accessible_via_descriptor():
    """Transition model is accessible via class descriptor."""
    descriptor = StateMachineTestModel.states
    assert descriptor.transition_model is not None
    assert (
        descriptor.transition_model.__name__ == "StateMachineTestModelStateTransition"
    )


# =============================================================================
# Configuration Validation Tests
# =============================================================================


def test_invalid_initial_state_raises():
    """StateMachine should reject invalid initial state."""
    with pytest.raises(ValueError) as exc_info:
        StateMachine(
            states=[("READY", "Ready"), ("DONE", "Done")],
            initial="INVALID",
            transitions={"READY": ["DONE"]},
        )
    assert "Initial state 'INVALID' not found in states" in str(exc_info.value)


def test_invalid_transition_source_raises():
    """StateMachine should reject transition from non-existent state."""
    with pytest.raises(ValueError) as exc_info:
        StateMachine(
            states=[("READY", "Ready"), ("DONE", "Done")],
            initial="READY",
            transitions={"INVALID": ["DONE"]},
        )
    assert "Transition source 'INVALID' not in states" in str(exc_info.value)


def test_invalid_transition_target_raises():
    """StateMachine should reject transition to non-existent state."""
    with pytest.raises(ValueError) as exc_info:
        StateMachine(
            states=[("READY", "Ready"), ("DONE", "Done")],
            initial="READY",
            transitions={"READY": ["INVALID"]},
        )
    assert "Transition target 'INVALID' not in states" in str(exc_info.value)


def test_state_longer_than_the_status_column_raises():
    """A state too long for the status column should be rejected at declaration.

    Without this the column only objects at write time, far from the
    declaration that caused it.
    """
    too_long = "X" * (STATUS_MAX_LENGTH + 1)
    with pytest.raises(ValueError) as exc_info:
        StateMachine(
            states=[("READY", "Ready"), (too_long, "Too long")],
            initial="READY",
            transitions={"READY": [too_long]},
        )
    assert f"is {STATUS_MAX_LENGTH + 1} characters" in str(exc_info.value)


def test_state_exactly_at_the_limit_is_allowed():
    """The limit is inclusive — a state that exactly fills the column is fine."""
    exactly = "X" * STATUS_MAX_LENGTH
    sm = StateMachine(
        states=[("READY", "Ready"), (exactly, "At the limit")],
        initial="READY",
        transitions={"READY": [exactly]},
    )
    assert sm.initial == "READY"


# =============================================================================
# Concurrency
# =============================================================================


@pytest.mark.django_db(transaction=True)
def test_concurrent_transitions_from_the_same_status_apply_once():
    """Two simultaneous transitions from the same starting status: one wins.

    Both threads hold an instance read before either transitions, which is the
    stale-read the row lock exists to catch. Before the lock, both validated
    against their own in-memory PENDING, both passed, and both applied — leaving
    a last-writer-wins status and two transition records describing incompatible
    histories. Now the second reads the first's committed status under the lock
    and is rejected.
    """
    obj = StateMachineTestModel.objects.create()
    stale_instances = [
        StateMachineTestModel.objects.get(pk=obj.pk),
        StateMachineTestModel.objects.get(pk=obj.pk),
    ]

    rejected = []

    def transition(instance):
        def run():
            try:
                instance.states.transition_to("RUNNING")
            except InvalidStateTransition as e:
                rejected.append(e)
            finally:
                # Each thread has its own connection; leaving it open strands it.
                connection.close()

        return run

    threads = [threading.Thread(target=transition(i)) for i in stale_instances]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    stuck = [t for t in threads if t.is_alive()]
    assert not stuck, f"{len(stuck)} thread(s) did not finish within 15s (deadlock?)"

    obj.refresh_from_db()
    assert obj.status == "RUNNING"
    assert len(rejected) == 1, "exactly one transition should have been rejected"
    assert obj.states.history.count() == 1, "only the winning transition is recorded"


@pytest.mark.django_db
def test_transition_validates_against_the_database_not_the_instance():
    """A stale instance is judged on the row's committed status, not its own.

    The sequential half of the concurrency guarantee, and the cheaper test: an
    instance holding a status the database has since moved past must not be
    allowed to transition as though nothing had changed.
    """
    obj = StateMachineTestModel.objects.create()
    stale = StateMachineTestModel.objects.get(pk=obj.pk)

    obj.states.transition_to("RUNNING")

    assert stale.status == "PENDING"  # stale in memory
    with pytest.raises(InvalidStateTransition) as exc_info:
        stale.states.transition_to("RUNNING")

    # Reports the committed status, not the stale one it was asked from.
    assert exc_info.value.from_status == "RUNNING"
