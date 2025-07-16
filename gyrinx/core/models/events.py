import json
import logging
from enum import Enum

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
    SECURITY_THREAT = "security_threat", "Security Threat"


class EventVerb(models.TextChoices):
    """Verbs representing actions that can be taken."""

    # CRUD
    CREATE = "create", "Create"
    UPDATE = "update", "Update"
    DELETE = "delete", "Delete"
    VIEW = "view", "View"

    # Deletion
    ARCHIVE = "archive", "Archive"
    RESTORE = "restore", "Restore"

    # Forms & Submissions
    SUBMIT = "submit", "Submit"
    CONFIRM = "confirm", "Confirm"

    # User actions
    JOIN = "join", "Join"
    LEAVE = "leave", "Leave"

    # Assignment
    ASSIGN = "assign", "Assign"
    UNASSIGN = "unassign", "Unassign"

    # Activation
    ACTIVATE = "activate", "Activate"
    DEACTIVATE = "deactivate", "Deactivate"

    # Approvals
    APPROVE = "approve", "Approve"
    REJECT = "reject", "Reject"

    # IO
    IMPORT = "import", "Import"
    EXPORT = "export", "Export"

    # Modification
    ADD = "add", "Add"
    REMOVE = "remove", "Remove"
    CLONE = "clone", "Clone"
    RESET = "reset", "Reset"

    # Accounts
    LOGIN = "login", "Login"
    LOGOUT = "logout", "Logout"
    SIGNUP = "signup", "Signup"

    # Security
    BLOCK = "block", "Block"


class EventField(models.TextChoices):
    """Fields (or groups of fields) that can be modified in events."""

    # User-related fields
    PASSWORD = "password", "Password"
    EMAIL = "email", "Email"
    MFA = "mfa", "Multi-Factor Authentication"
    SESSION = "session", "Session"

    # Fighter-related fields
    INFO = "info", "Info"


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

    session_id = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        help_text="Session ID of the user when the action was taken",
    )

    # Field being modified (for UPDATE events)
    field = models.CharField(
        max_length=50,
        choices=EventField.choices,
        null=True,
        blank=True,
        help_text="The field being modified for UPDATE events",
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

        try:
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
                "session_id": self.session_id,
                "field": self.field,
                "context": self.context,
            }

            logger.info(
                f"USER_EVENT: {self.verb} {self.noun}",
                extra={"event_data": json.dumps(event_data)},
            )
        except Exception:
            # If logging fails, don't crash - just log the error
            logger.exception("Failed to log event to stream")


def ensure_json_serializable(data):
    """
    Recursively ensure all data is JSON serializable.

    Converts non-serializable objects to strings or other JSON-safe types.
    """
    if isinstance(data, dict):
        return {k: ensure_json_serializable(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple)):
        return [ensure_json_serializable(item) for item in data]
    elif isinstance(data, (str, int, float, bool, type(None))):
        return data
    elif isinstance(data, Enum):
        # For Enums, use their value
        return data.value
    else:
        # For any other type, convert to string representation
        try:
            # Try to serialize to JSON first to check if it's already serializable
            json.dumps(data)
            return data
        except (TypeError, ValueError):
            # If not serializable, convert to string
            return str(data)


def get_client_ip(request):
    """
    Extract the client's real IP address from the request.

    When running behind a proxy or load balancer (like Google Cloud Run),
    the real client IP is passed in headers like X-Forwarded-For.

    Args:
        request: Django HttpRequest object

    Returns:
        str: The client's IP address, or None if not available
    """
    if not request:
        return None

    # Check X-Forwarded-For header first
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        # X-Forwarded-For can contain multiple IPs: "client-ip, proxy1, proxy2"
        # The first IP is the original client
        ip = x_forwarded_for.split(",")[0].strip()
        return ip

    # Check X-Real-IP header (used by some proxies)
    x_real_ip = request.META.get("HTTP_X_REAL_IP")
    if x_real_ip:
        return x_real_ip.strip()

    # Fall back to REMOTE_ADDR if no proxy headers are present
    return request.META.get("REMOTE_ADDR")


def log_event(
    user, noun, verb, object=None, request=None, ip_address=None, field=None, **context
):
    """
    Utility function to easily log events throughout the application.

    Args:
        user: The User performing the action
        noun: EventNoun choice representing what's being acted upon
        verb: EventVerb choice representing the action
        object: Optional Django model instance being acted upon
        request: Optional HttpRequest object to extract session ID and IP address
        ip_address: Optional IP address (overrides request extraction)
        field: Optional EventField choice for UPDATE events
        **context: Additional context data to store in the JSON field

    Returns:
        Event: The created Event instance, or None if an error occurred

    Example:
        log_event(
            user=request.user,
            noun=EventNoun.LIST,
            verb=EventVerb.CREATE,
            object=list_instance,
            request=request,
            list_name=list_instance.name,
            fighter_count=list_instance.fighters.count()
        )
    """
    try:
        # Extract session ID from request if available
        session_id = None
        if (
            request
            and hasattr(request, "session")
            and hasattr(request.session, "session_key")
        ):
            session_id = request.session.session_key

        # Extract IP address from request if not explicitly provided
        if not ip_address and request:
            ip_address = get_client_ip(request)

        event_data = {
            "owner": user,
            "noun": noun,
            "verb": verb,
            "ip_address": ip_address,
            "session_id": session_id,
            "field": field,
            "context": ensure_json_serializable(context),
        }

        if object:
            event_data["object_id"] = object.pk
            event_data["object_type"] = ContentType.objects.get_for_model(object)

        return Event.objects.create(**event_data)
    except Exception as e:
        # Log the error but don't crash the application
        logger.error(
            f"Failed to log event: {noun} {verb}",
            exc_info=True,
            extra={
                "user_id": getattr(user, "id", None),
                "noun": noun,
                "verb": verb,
                "error": str(e),
                "context": context,
            },
        )
        return None
