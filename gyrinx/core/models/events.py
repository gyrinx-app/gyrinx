import json
import logging
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from gyrinx.core.models.base import AppBase

logger = logging.getLogger(__name__)


class EventNoun(models.TextChoices):
    """Nouns representing objects that can be acted upon."""

    LIST = "list", "List"
    LIST_FIGHTER = "list_fighter", "List Fighter"
    CAMPAIGN = "campaign", "Campaign"
    BATTLE = "battle", "Battle"
    EQUIPMENT_ASSIGNMENT = "equipment_assignment", "Equipment Assignment"
    SKILL_ASSIGNMENT = "skill_assignment", "Skill Assignment"
    USER = "user", "User"
    UPLOAD = "upload", "Upload"
    FIGHTER_ADVANCEMENT = "fighter_advancement", "Fighter Advancement"
    CAMPAIGN_ACTION = "campaign_action", "Campaign Action"
    CAMPAIGN_RESOURCE = "campaign_resource", "Campaign Resource"
    CAMPAIGN_ASSET = "campaign_asset", "Campaign Asset"


class EventVerb(models.TextChoices):
    """Verbs representing actions that can be taken."""

    CREATE = "create", "Create"
    UPDATE = "update", "Update"
    DELETE = "delete", "Delete"
    ARCHIVE = "archive", "Archive"
    RESTORE = "restore", "Restore"
    VIEW = "view", "View"
    CLONE = "clone", "Clone"
    JOIN = "join", "Join"
    LEAVE = "leave", "Leave"
    ASSIGN = "assign", "Assign"
    UNASSIGN = "unassign", "Unassign"
    ACTIVATE = "activate", "Activate"
    DEACTIVATE = "deactivate", "Deactivate"
    SUBMIT = "submit", "Submit"
    APPROVE = "approve", "Approve"
    REJECT = "reject", "Reject"
    IMPORT = "import", "Import"
    EXPORT = "export", "Export"


class Event(AppBase):
    """
    Model to track user actions throughout the application.

    Each event represents a single action taken by a user on an object,
    with structured data for analysis and unstructured data for flexibility.
    """

    # Core event data
    noun = models.CharField(
        max_length=50,
        choices=EventNoun.choices,
        help_text="The type of object being acted upon",
    )
    verb = models.CharField(
        max_length=50, choices=EventVerb.choices, help_text="The action being performed"
    )

    # Context columns for useful additional information
    object_id = models.UUIDField(
        null=True, blank=True, help_text="UUID of the object being acted upon"
    )
    object_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Type of the object for generic relations",
    )
    object = GenericForeignKey("object_type", "object_id")

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the user when the action was taken",
    )

    # Additional unstructured context
    context = models.JSONField(
        default=dict, blank=True, help_text="Additional context data in JSON format"
    )

    class Meta:
        verbose_name = "event"
        verbose_name_plural = "events"
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["-created"]),
            models.Index(fields=["noun", "verb"]),
            models.Index(fields=["owner"]),
            models.Index(fields=["object_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.owner} {self.verb} {self.noun} at {self.created}"

    def save(self, *args, **kwargs):
        """Override save to also log the event to the log stream."""
        super().save(*args, **kwargs)

        # Log the event as JSON
        event_data = {
            "id": str(self.id),
            "timestamp": self.created.isoformat(),
            "user_id": str(self.owner_id) if self.owner_id else None,
            "username": self.owner.username if self.owner else None,
            "noun": self.noun,
            "verb": self.verb,
            "object_id": str(self.object_id) if self.object_id else None,
            "object_type": self.object_type.model if self.object_type else None,
            "ip_address": self.ip_address,
            "context": self.context,
        }

        logger.info(
            f"USER_EVENT: {self.verb} {self.noun}",
            extra={"event_data": json.dumps(event_data)},
        )


def log_event(user, noun, verb, object=None, ip_address=None, **context):
    """
    Utility function to easily log events throughout the application.

    Args:
        user: The User performing the action
        noun: EventNoun choice representing what's being acted upon
        verb: EventVerb choice representing the action
        object: Optional Django model instance being acted upon
        ip_address: Optional IP address of the request
        **context: Additional context data to store in the JSON field

    Returns:
        Event: The created Event instance

    Example:
        log_event(
            user=request.user,
            noun=EventNoun.LIST,
            verb=EventVerb.CREATE,
            object=list_instance,
            ip_address=request.META.get('REMOTE_ADDR'),
            list_name=list_instance.name,
            fighter_count=list_instance.fighters.count()
        )
    """
    event_data = {
        "owner": user,
        "noun": noun,
        "verb": verb,
        "ip_address": ip_address,
        "context": context,
    }

    if object:
        event_data["object_id"] = object.pk
        event_data["object_type"] = ContentType.objects.get_for_model(object)

    return Event.objects.create(**event_data)
