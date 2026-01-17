"""
State Machine implementation for Django models.

Provides a descriptor-based state machine that creates per-model transition tables
and a namespaced API for all state operations.

Usage:
    class MyModel(Base):
        states = StateMachine(
            states=[("PENDING", "Pending"), ("DONE", "Done")],
            initial="PENDING",
            transitions={"PENDING": ["DONE"]},
        )

    # Then use:
    obj.states.current              # Current status value
    obj.states.display              # Human-readable label
    obj.states.transition_to("DONE")
    obj.states.can_transition_to("DONE")
    obj.states.is_terminal
    obj.states.history.all()
"""

import importlib
import logging
import uuid

from django.db import models, transaction
from django.utils import timezone

from gyrinx.tracing import span

logger = logging.getLogger(__name__)

__all__ = ["StateMachine", "InvalidStateTransition"]


class InvalidStateTransition(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_status: str, to_status: str, allowed: list[str]):
        self.from_status = from_status
        self.to_status = to_status
        self.allowed = allowed
        super().__init__(
            f"Cannot transition from '{from_status}' to '{to_status}'. "
            f"Allowed transitions: {allowed}"
        )


class StateMachine:
    """
    All-in-one state machine that creates per-model transition tables.

    This descriptor:
    1. Adds a 'status' CharField to the model via contribute_to_class
    2. Creates a per-model transition table (e.g., TaskExecutionStateTransition)
    3. Provides a namespaced API via StateMachineAccessor

    Args:
        states: List of (value, label) tuples defining valid states
        initial: The initial state value for new instances
        transitions: Dict mapping from_state to list of allowed to_states
    """

    def __init__(
        self,
        states: list[tuple[str, str]],
        initial: str,
        transitions: dict[str, list[str]],
    ):
        self.states = states
        self.initial = initial
        self.transitions = transitions
        self.field_name = None
        self.module = None
        self.cls = None
        self.transition_model = None

        # Validate configuration
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate state machine configuration at creation time."""
        valid_states = [s[0] for s in self.states]

        # Validate initial state exists
        if self.initial not in valid_states:
            raise ValueError(
                f"Initial state '{self.initial}' not found in states: {valid_states}"
            )

        # Validate transition graph references only valid states
        for from_state, to_states in self.transitions.items():
            if from_state not in valid_states:
                raise ValueError(
                    f"Transition source '{from_state}' not in states: {valid_states}"
                )
            for to_state in to_states:
                if to_state not in valid_states:
                    raise ValueError(
                        f"Transition target '{to_state}' not in states: {valid_states}"
                    )

    def contribute_to_class(self, cls, name):
        """
        Called by Django's metaclass when processing model attributes.

        This method:
        1. Stores context (field name, module, class)
        2. Adds a 'status' CharField to the model
        3. Connects to class_prepared signal for deferred transition model creation
        """
        # Safety check: prevent reusing the same StateMachine instance
        if self.cls is not None:
            raise RuntimeError(
                f"StateMachine instance already used on {self.cls.__name__}. "
                "Create a new StateMachine instance for each model."
            )

        self.field_name = name
        self.module = cls.__module__
        self.cls = cls

        # Add the status field to the model
        status_field = models.CharField(
            max_length=50,
            db_index=True,
            default=self.initial,
            choices=self.states,
        )
        status_field.contribute_to_class(cls, "status")

        # Delay transition model creation until class is fully prepared
        models.signals.class_prepared.connect(self.finalize, weak=False)

    def finalize(self, sender, **kwargs):
        """
        Create the per-model transition table after class is ready.

        Called via class_prepared signal. Creates the dynamic transition model
        and replaces this StateMachine instance with a StateMachineDescriptor.
        """
        if sender is not self.cls:
            return

        # Disconnect to avoid duplicate calls
        models.signals.class_prepared.disconnect(self.finalize)

        # Create dynamic transition model
        self.transition_model = self._create_transition_model(sender)

        # Make the transition model importable from the same module
        module = importlib.import_module(self.module)
        setattr(module, self.transition_model.__name__, self.transition_model)

        # Replace self with the descriptor on the class
        setattr(sender, self.field_name, StateMachineDescriptor(self))

        logger.debug(
            "Created state machine for %s with transition model %s",
            sender.__name__,
            self.transition_model.__name__,
        )

    def _create_transition_model(self, model):
        """
        Dynamically create a transition model for the given model.

        Creates a model like TaskExecutionStateTransition with:
        - UUID primary key
        - ForeignKey to the parent model
        - from_status, to_status, transitioned_at, metadata fields
        """

        def transition_str(self):
            if self.from_status:
                return f"{self.from_status} → {self.to_status}"
            return f"(initial) → {self.to_status}"

        attrs = {
            "__module__": self.module,
            "id": models.UUIDField(
                default=uuid.uuid4,
                primary_key=True,
                editable=False,
            ),
            "instance": models.ForeignKey(
                model,
                on_delete=models.CASCADE,
                related_name="_state_transitions",
            ),
            "from_status": models.CharField(max_length=50, blank=True, db_index=True),
            "to_status": models.CharField(max_length=50, db_index=True),
            "transitioned_at": models.DateTimeField(
                default=timezone.now, db_index=True
            ),
            "metadata": models.JSONField(default=dict, blank=True),
            "__str__": transition_str,
        }

        # Create Meta class
        meta_attrs = {
            "app_label": model._meta.app_label,
            "ordering": ["-transitioned_at"],
            "verbose_name": f"{model._meta.verbose_name} state transition",
            "verbose_name_plural": f"{model._meta.verbose_name} state transitions",
        }
        attrs["Meta"] = type("Meta", (), meta_attrs)

        # Generate model name: TaskExecutionStateTransition
        model_name = f"{model._meta.object_name}StateTransition"

        return type(model_name, (models.Model,), attrs)


class StateMachineDescriptor:
    """
    Descriptor that returns a StateMachineAccessor bound to the instance.

    When accessed on the class, returns self (for introspection).
    When accessed on an instance, returns a StateMachineAccessor.
    """

    def __init__(self, state_machine: StateMachine):
        self.state_machine = state_machine

    def __get__(self, instance, owner):
        if instance is None:
            # Class-level access - return self for introspection
            return self
        return StateMachineAccessor(instance, self.state_machine)

    # Expose state machine config for introspection
    @property
    def states(self):
        return self.state_machine.states

    @property
    def initial(self):
        return self.state_machine.initial

    @property
    def transitions(self):
        return self.state_machine.transitions

    @property
    def transition_model(self):
        return self.state_machine.transition_model


class StateMachineAccessor:
    """
    Provides the instance.states.* API for state machine operations.

    This is the object returned when accessing the state machine on an instance,
    providing all state-related operations in a clean namespace.
    """

    def __init__(self, instance, state_machine: StateMachine):
        self.instance = instance
        self.sm = state_machine

    @property
    def current(self) -> str:
        """Get the current status value."""
        return self.instance.status

    @property
    def display(self) -> str:
        """Get the human-readable label for the current status."""
        for value, label in self.sm.states:
            if value == self.current:
                return label
        return self.current

    @property
    def is_terminal(self) -> bool:
        """Check if the current status is a terminal state (no valid transitions out)."""
        return len(self.sm.transitions.get(self.current, [])) == 0

    def can_transition_to(self, new_status: str) -> bool:
        """Check if transition to new_status is allowed from current status."""
        return new_status in self.sm.transitions.get(self.current, [])

    def get_valid_transitions(self) -> list[str]:
        """Get list of valid statuses to transition to from current status."""
        return self.sm.transitions.get(self.current, [])

    def transition_to(
        self,
        new_status: str,
        metadata: dict | None = None,
        save: bool = True,
    ):
        """
        Transition to a new status with validation and history tracking.

        Args:
            new_status: The status to transition to
            metadata: Optional dict of metadata to store with the transition
            save: Whether to save the model after transitioning (default: True)

        Returns:
            The created transition record

        Raises:
            InvalidStateTransition: If the transition is not allowed
        """
        if not self.can_transition_to(new_status):
            allowed = self.get_valid_transitions()
            raise InvalidStateTransition(self.current, new_status, allowed)

        old_status = self.current
        model_name = self.instance.__class__.__name__

        with span(
            "state_transition",
            model=model_name,
            instance_id=str(self.instance.pk),
            from_status=old_status,
            to_status=new_status,
        ):
            with transaction.atomic():
                self.instance.status = new_status

                if save:
                    self.instance.save(update_fields=["status", "modified"])

                # Create transition record
                transition = self.sm.transition_model.objects.create(
                    instance=self.instance,
                    from_status=old_status,
                    to_status=new_status,
                    metadata=metadata or {},
                )

                logger.debug(
                    "State transition: %s → %s for %s %s",
                    old_status,
                    new_status,
                    model_name,
                    self.instance.pk,
                )

                return transition

    @property
    def history(self):
        """
        Get a QuerySet of all transitions for this instance.

        Returns a QuerySet ordered by transitioned_at descending (most recent first).
        """
        return self.sm.transition_model.objects.filter(instance=self.instance)
