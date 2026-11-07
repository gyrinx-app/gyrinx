import hashlib
import hmac
import json
import logging
import re
from enum import Enum

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from gyrinx.analytics.nouns import Edition, edition_for_noun, noun_choices
from gyrinx.base_models import AppBase
from gyrinx.client_ip import get_client_ip
from gyrinx.tracker import track

logger = logging.getLogger(__name__)
SENSITIVE_CONTEXT_KEY = re.compile(
    r"(^|_)(password|passphrase|secret|token|session_key|session_id|authorization|cookie)($|_)",
    re.IGNORECASE,
)


def redact_sensitive_context(value):
    """Avoid persisting caller-supplied bearer secrets in event context."""
    if isinstance(value, dict):
        return {
            key: "[redacted]"
            if SENSITIVE_CONTEXT_KEY.search(str(key))
            else redact_sensitive_context(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_sensitive_context(item) for item in value]
    return value


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

    # Click tracking
    CLICK = "click", "Click"


class EventField(models.TextChoices):
    """Fields (or groups of fields) that can be modified in events."""

    # User-related fields
    PASSWORD = "password", "Password"
    EMAIL = "email", "Email"
    MFA = "mfa", "Multi-Factor Authentication"
    SESSION = "session", "Session"

    # Fighter-related fields
    INFO = "info", "Info"
    STATS = "stats", "Stats"


class Event(AppBase):
    """
    Model to track user actions throughout the application.

    Each event represents a single action taken by a user on an object,
    with structured data for analysis and unstructured data for flexibility.
    """

    # Core event data
    noun = models.CharField(
        max_length=50,
        choices=noun_choices,
        help_text="The type of object being acted upon",
    )
    verb = models.CharField(
        max_length=50, choices=EventVerb.choices, help_text="The action being performed"
    )

    # Derive the edition from the registered noun when saving.
    edition = models.CharField(
        max_length=20,
        choices=Edition.choices,
        default=Edition.UNKNOWN,
        db_index=True,
        help_text="The edition (or the platform) the action happened in",
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

    session_fingerprint = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="One-way identifier used to link events from the same session.",
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
        db_table = "core_event"
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
        """Derive a missing or unknown edition, save the event and attempt stream logging."""
        # Derive missing editions on every save, including direct model writes.
        # Preserve an explicit, known edition.
        if not self.edition or self.edition == Edition.UNKNOWN:
            self.edition = edition_for_noun(self.noun)

        self.context = redact_sensitive_context(self.context)

        super().save(*args, **kwargs)

        try:
            # Nouns belong to one edition, so event names need no edition prefix.
            track(
                f"event_{self.verb}_{self.noun}",
                n=1,
                value=None,
                id=str(self.id),
                noun=self.noun,
                verb=self.verb,
                edition=self.edition,
                user_id=str(self.owner_id) if self.owner_id else None,
                username=self.owner.username if self.owner else None,
                object_id=str(self.object_id) if self.object_id else None,
                object_type=self.object_type.model if self.object_type else None,
                ip_address=self.ip_address,
                session_fingerprint=self.session_fingerprint,
                field=self.field,
                context=self.context,
            )
        except Exception as exc:
            # Preserve the stored event if stream logging fails.
            logger.error(
                "Failed to log event to stream",
                extra={"error_type": type(exc).__name__},
            )


def ensure_json_serializable(data):
    """Convert containers recursively, enums to values and unsupported objects to strings."""
    if isinstance(data, dict):
        return {k: ensure_json_serializable(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple)):
        return [ensure_json_serializable(item) for item in data]
    elif isinstance(data, (str, int, float, bool, type(None))):
        return data
    elif isinstance(data, Enum):
        return data.value
    else:
        try:
            json.dumps(data)
            return data
        except TypeError, ValueError:
            return str(data)


# Use broad crawler patterns to exclude automated traffic from engagement.
# Some device names may also match the bot pattern.
BOT_USER_AGENT_RE = re.compile(
    r"bot|crawler|spider|slurp|read-aloud|bingpreview|facebookexternalhit",
    re.IGNORECASE,
)


def is_bot_request(request):
    """True if the request's User-Agent identifies a crawler."""
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    return bool(BOT_USER_AGENT_RE.search(user_agent))


def fingerprint_session(session_key):
    """Correlate events in one session without retaining its bearer token."""
    if not session_key:
        return None
    return hmac.new(
        settings.SECRET_KEY.encode(), session_key.encode(), hashlib.sha256
    ).hexdigest()


def log_event(
    user, noun, verb, object=None, request=None, ip_address=None, field=None, **context
):
    """Record a non-crawler event and return it, or None on failure.

    Derive its edition from the registered noun. Read session and IP data from
    the optional request, honour an explicit IP and convert context to JSON-safe
    values. Convert UUID-backed object keys through to_uuid when available.
    """
    try:
        # Suppress only engagement events. A caller controls User-Agent, so it
        # must never suppress sign-ins, account changes, or other writes.
        if (
            request is not None
            and verb in (EventVerb.VIEW, EventVerb.CLICK)
            and is_bot_request(request)
        ):
            return None

        session_fingerprint = None
        if (
            request
            and hasattr(request, "session")
            and hasattr(request.session, "session_key")
        ):
            session_fingerprint = fingerprint_session(request.session.session_key)

        if not ip_address and request:
            ip_address = get_client_ip(request)

        event_data = {
            "owner": user,
            "noun": noun,
            "verb": verb,
            "ip_address": ip_address,
            "session_fingerprint": session_fingerprint,
            "field": field,
            "context": ensure_json_serializable(context),
        }

        if object:
            # Convert UUID-backed keys before writing the UUID relation column.
            object_id = object.pk
            as_uuid = getattr(object_id, "to_uuid", None)
            event_data["object_id"] = object_id if as_uuid is None else as_uuid()
            event_data["object_type"] = ContentType.objects.get_for_model(object)

        return Event.objects.create(**event_data)
    except Exception as exc:
        logger.error(
            "Failed to log event: %s %s",
            noun,
            verb,
            extra={
                "user_id": getattr(user, "id", None),
                "noun": noun,
                "verb": verb,
                # Database exceptions can echo parameters, and context can
                # contain credentials if a caller used an unrecognised key.
                "error_type": type(exc).__name__,
            },
        )
        return None
