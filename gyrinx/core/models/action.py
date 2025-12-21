import logging
from functools import cached_property

from django.contrib.auth import get_user_model
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.core.models.base import AppBase
from gyrinx.core.models.history_aware_manager import HistoryAwareManager

logger = logging.getLogger(__name__)
User = get_user_model()

pylist = list  # Alias for type hinting JSONField to use list type


class ListActionType(models.TextChoices):
    """Enumeration of possible action types."""

    CREATE = "CREATE", "Create"
    CLONE = "CLONE", "Clone"
    ADD_FIGHTER = "ADD_FIGHTER", "Add Fighter"
    REMOVE_FIGHTER = "REMOVE_FIGHTER", "Remove Fighter"
    UPDATE_FIGHTER = "UPDATE_FIGHTER", "Update Fighter"
    ADD_EQUIPMENT = "ADD_EQUIPMENT", "Add Equipment"
    REMOVE_EQUIPMENT = "REMOVE_EQUIPMENT", "Remove Equipment"
    UPDATE_EQUIPMENT = "UPDATE_EQUIPMENT", "Update Equipment"
    CAMPAIGN_START = "CAMPAIGN_START", "Campaign Start"
    CAPTURE_FIGHTER = "CAPTURE_FIGHTER", "Capture Fighter"
    SELL_FIGHTER = "SELL_FIGHTER", "Sell Fighter"
    RETURN_FIGHTER = "RETURN_FIGHTER", "Return Fighter"
    RELEASE_FIGHTER = "RELEASE_FIGHTER", "Release Fighter"
    UPDATE_CREDITS = "UPDATE_CREDITS", "Update Credits"
    CONTENT_COST_CHANGE = "CONTENT_COST_CHANGE", "Content Cost Change"


class ListActionQuerySet(models.QuerySet):
    """Custom QuerySet for ListAction model."""

    def latest_for_list(self, list_id):
        """Get the latest action for a given list."""
        return self.filter(list_id=list_id).order_by("-created").first()


class ListActionManager(HistoryAwareManager):
    """Custom manager for ListAction model using ListActionQuerySet."""

    pass


class ListAction(AppBase):
    """
    ListAction tracks user actions performed on lists and objects within those lists.

    The key use of ListAction is for performant cost tracking.

    NOTE: In future, it would be good to refactor this to have a "Prepare" and "Apply" step, so that this
          model owns all business logic around what goes into an action. Right now, the caller has to know
          a bit too much about the internals of the list action. This refactor would also extend to `create_action`
          on the List, which is really more of a transact-on-list method.
    """

    class Meta:
        verbose_name = "list action"
        verbose_name_plural = "list actions"
        ordering = ["-created"]

        indexes = [
            models.Index(
                fields=["list_id", "-created", "-id"], name="list_created_id_desc_idx"
            )
        ]

    objects = ListActionManager.from_queryset(ListActionQuerySet)()

    # Core fields

    list = models.ForeignKey(
        "List",
        on_delete=models.CASCADE,
        related_name="actions",
        null=False,
        blank=False,
        db_index=True,
    )

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="list_actions",
        help_text="The user who performed this action",
        null=True,
        blank=True,
        db_index=True,
    )

    applied = models.BooleanField(
        default=False,
        help_text="Whether this action has been applied to the list.",
        db_index=True,
    )

    action_type = models.CharField(
        max_length=50,
        choices=ListActionType.choices,
        null=False,
        blank=False,
        db_index=True,
    )

    subject_app = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="The app that the model subject_type belongs to. First argument of apps.get_model.",
    )

    subject_type = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="The model type of the subject involved in the action. Second argument of apps.get_model.",
    )

    subject_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="The UUID of the subject involved in the action.",
    )

    description = models.TextField(
        null=True,
        blank=True,
        help_text="A textual description of the action performed. May be user-facing.",
    )

    # Cost tracking fields

    rating_delta = models.IntegerField(
        null=False,
        blank=True,
        default=0,
        help_text="Credits transacted during this action into list rating.",
    )

    stash_delta = models.IntegerField(
        null=False,
        blank=True,
        default=0,
        help_text="Credits transacted during this action into list stash.",
    )

    credits_delta = models.IntegerField(
        null=False,
        blank=True,
        default=0,
        help_text="Credits transacted during this action overall.",
    )

    rating_before = models.IntegerField(
        null=False,
        blank=True,
        default=0,
        help_text="The list rating before this action was performed.",
    )

    @cached_property
    def rating_after(self) -> int:
        """Calculate the rating after this action was performed."""
        return self.rating_before + self.rating_delta

    stash_before = models.IntegerField(
        null=False,
        blank=True,
        default=0,
        help_text="The list stash value before this action was performed.",
    )

    @cached_property
    def stash_after(self) -> int:
        """Calculate the stash after this action was performed."""
        return self.stash_before + self.stash_delta

    credits_before = models.IntegerField(
        null=False,
        blank=True,
        default=0,
        help_text="The list credits before this action was performed.",
    )

    @cached_property
    def credits_after(self) -> int:
        """Calculate the credits after this action was performed."""
        return self.credits_before + self.credits_delta

    @cached_property
    def wealth_after(self) -> int:
        """Calculate the total wealth after this action was performed."""
        return self.rating_after + self.stash_after + self.credits_after

    # Extra relationships for easier querying

    list_fighter = models.ForeignKey(
        "ListFighter",
        on_delete=models.SET_NULL,
        related_name="actions",
        null=True,
        blank=True,
        help_text="The ListFighter involved in this action, if applicable.",
    )

    list_fighter_equipment_assignment = models.ForeignKey(
        "ListFighterEquipmentAssignment",
        on_delete=models.SET_NULL,
        related_name="actions",
        null=True,
        blank=True,
        help_text="The ListFighterEquipmentAssignment involved in this action, if applicable.",
    )

    # Tracking

    history = HistoricalRecords()
