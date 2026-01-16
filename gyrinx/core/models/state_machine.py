"""
Generic State Machine Mixin for Django models.

Provides state tracking with transition validation and history recording.
"""

import logging

__all__ = ["StateTransition", "StateMachineMixin", "InvalidStateTransition"]
from typing import Any

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class StateTransition(models.Model):
    """
    Records state transitions for models using StateMachineMixin.

    Uses GenericForeignKey to work with any model that uses StateMachineMixin,
    allowing a single table to track transitions across different model types.

    Attributes:
        content_type: The ContentType of the related model
        object_id: The UUID of the related object
        content_object: The actual related object (via GenericForeignKey)
        from_status: The previous status (empty for initial state)
        to_status: The new status
        transitioned_at: Timestamp of the transition
        metadata: Optional JSON data about the transition (e.g., worker_id, error details)
    """

    id = models.BigAutoField(primary_key=True)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        db_index=True,
    )
    object_id = models.UUIDField(db_index=True)
    content_object = GenericForeignKey("content_type", "object_id")

    from_status = models.CharField(max_length=50, blank=True, db_index=True)
    to_status = models.CharField(max_length=50, db_index=True)
    transitioned_at = models.DateTimeField(default=timezone.now, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-transitioned_at"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["content_type", "to_status"]),
        ]

    def __str__(self):
        if self.from_status:
            return f"{self.from_status} -> {self.to_status} at {self.transitioned_at}"
        return f"(initial) -> {self.to_status} at {self.transitioned_at}"


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


class StateMachineMixin(models.Model):
    """
    Generic mixin for models requiring state machine behavior.

    Provides:
    - Status field with db_index for queries
    - Automatic transition tracking via StateTransition
    - State transition validation
    - Helper methods for state queries

    Usage:
        class MyModel(StateMachineMixin, Base):
            # Define allowed states
            STATES = [("PENDING", "Pending"), ("DONE", "Done")]
            INITIAL_STATE = "PENDING"

            # Define valid transitions: {from_state: [to_states]}
            TRANSITIONS = {
                "PENDING": ["DONE"],
            }

            # Add GenericRelation for reverse lookups (optional but recommended)
            state_transitions = GenericRelation(
                "core.StateTransition",
                content_type_field="content_type",
                object_id_field="object_id",
            )

    Note:
        Subclasses MUST define STATES, INITIAL_STATE, and TRANSITIONS as class attributes.
    """

    # Class attributes to be overridden by subclasses
    STATES: list[tuple[str, str]] = []  # List of (value, label) tuples
    INITIAL_STATE: str = ""  # Default initial state
    TRANSITIONS: dict[str, list[str]] = {}  # {from_state: [allowed_to_states]}

    # The status field - subclasses can override max_length if needed
    status = models.CharField(max_length=50, db_index=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """Set initial status if not set, then save."""
        if not self.status and self.INITIAL_STATE:
            self.status = self.INITIAL_STATE
        super().save(*args, **kwargs)

    @classmethod
    def get_state_choices(cls) -> list[tuple[str, str]]:
        """Return the STATES as choices for the status field."""
        return cls.STATES

    @classmethod
    def get_valid_transitions(cls, from_status: str) -> list[str]:
        """Return list of valid statuses to transition to from the given status."""
        return cls.TRANSITIONS.get(from_status, [])

    def can_transition_to(self, new_status: str) -> bool:
        """
        Check if transition to new_status is allowed from current status.

        Args:
            new_status: The target status to check

        Returns:
            True if the transition is allowed, False otherwise
        """
        valid = self.get_valid_transitions(self.status)
        return new_status in valid

    def transition_to(
        self,
        new_status: str,
        metadata: dict[str, Any] | None = None,
        save: bool = True,
    ) -> "StateTransition":
        """
        Transition to a new status, with validation and tracking.

        This method:
        1. Validates the transition is allowed
        2. Updates the status field
        3. Creates a StateTransition record
        4. Saves the model (if save=True)

        All operations are performed in a transaction for atomicity.

        Args:
            new_status: The status to transition to
            metadata: Optional dict of metadata to store with the transition
            save: Whether to save the model after transitioning (default: True)

        Returns:
            The created StateTransition record

        Raises:
            InvalidStateTransition: If the transition is not allowed
        """
        if not self.can_transition_to(new_status):
            valid = self.get_valid_transitions(self.status)
            raise InvalidStateTransition(self.status, new_status, valid)

        with transaction.atomic():
            old_status = self.status
            self.status = new_status

            if save:
                self.save(update_fields=["status", "modified"])

            # Create transition record
            transition = StateTransition.objects.create(
                content_type=ContentType.objects.get_for_model(self),
                object_id=self.pk,
                from_status=old_status,
                to_status=new_status,
                metadata=metadata or {},
            )

            logger.debug(
                "State transition: %s -> %s for %s %s",
                old_status,
                new_status,
                self.__class__.__name__,
                self.pk,
            )

            return transition

    def get_transitions(self):
        """
        Get all state transitions for this object.

        Returns:
            QuerySet of StateTransition objects ordered by transitioned_at descending
        """
        content_type = ContentType.objects.get_for_model(self)
        return StateTransition.objects.filter(
            content_type=content_type,
            object_id=self.pk,
        )

    def get_latest_transition(self) -> StateTransition | None:
        """
        Get the most recent state transition for this object.

        Returns:
            The most recent StateTransition, or None if no transitions exist
        """
        return self.get_transitions().first()

    @property
    def is_terminal(self) -> bool:
        """
        Check if the current status is a terminal state (no valid transitions out).

        Returns:
            True if there are no valid transitions from current status
        """
        return len(self.get_valid_transitions(self.status)) == 0

    @property
    def status_display(self) -> str:
        """
        Get the human-readable label for the current status.

        Returns:
            The label for the current status, or the status value if no label found
        """
        for value, label in self.STATES:
            if value == self.status:
                return label
        return self.status
