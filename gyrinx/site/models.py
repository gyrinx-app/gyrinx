"""Shared models for write pauses, banners, impersonation, notifications and feature flags."""

import logging
import uuid
from itertools import islice

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import models
from django.db.models import Q
from django.utils import timezone
from simple_history.models import HistoricalRecords

from gyrinx.base_models import AppBase
from gyrinx.history_aware_manager import HistoryAwareManager
from gyrinx.models import Base
from gyrinx.site import icons as banner_icons

logger = logging.getLogger(__name__)

# Banner visibility differs by edition, so each edition needs a separate cache entry.
BANNER_CACHE_KEYS = {
    "n23": "site_banner_live:n23",
    "n26": "site_banner_live:n26",
}
BANNER_CACHE_TIMEOUT = 300  # 5 minutes


class WritePause(Base):
    """Persistent state for one registered domain write scope."""

    class State(models.TextChoices):
        OPEN = "OPEN", "Open"
        PAUSED = "PAUSED", "Paused"

    scope = models.SlugField(max_length=64, unique=True)
    state = models.CharField(max_length=8, choices=State, default=State.OPEN)
    generation = models.PositiveBigIntegerField(default=0)
    reason = models.TextField(blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    paused_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="write_pauses_started",
    )
    permitted_task_name = models.CharField(max_length=255, blank=True)
    permitted_run_id = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["scope"]

    def __str__(self):
        return f"{self.scope}: {self.get_state_display()}"


class Banner(AppBase):
    """Site-wide banner shown to all users on the homepage."""

    text = models.TextField(help_text="The main message text of the banner")
    cta_text = models.CharField(
        max_length=255,
        blank=True,
        help_text="Call-to-action button text (e.g., 'Learn More')",
    )
    cta_url = models.URLField(blank=True, help_text="URL that the CTA button links to")
    icon = models.CharField(
        max_length=50,
        blank=True,
        choices=banner_icons.CHOICES,
        help_text=(
            "What kind of thing the banner is saying. Each edition draws it "
            "from its own icon set — see gyrinx/site/icons.py."
        ),
    )
    colour = models.CharField(
        max_length=20,
        choices=[
            ("primary", "Primary (Blue)"),
            ("secondary", "Secondary (Gray)"),
            ("success", "Success (Green)"),
            ("danger", "Danger (Red)"),
            ("warning", "Warning (Yellow)"),
            ("info", "Info (Light Blue)"),
            ("light", "Light"),
            ("dark", "Dark"),
        ],
        default="info",
        help_text="Bootstrap colour/priority for the banner",
    )
    live_n23 = models.BooleanField(
        "live on n23",
        default=False,
        help_text=(
            "Whether this banner is currently live on the classic site. "
            "At most one banner can be live there at a time."
        ),
    )
    live_n26 = models.BooleanField(
        "live on n26",
        default=False,
        help_text=(
            "Whether this banner is currently live on the n26 edition. "
            "At most one banner can be live there at a time."
        ),
    )

    # History tracking
    history = HistoricalRecords(table_name="core_historicalbanner")

    class Meta:
        db_table = "core_banner"
        ordering = ["-modified"]
        verbose_name = "Banner"
        verbose_name_plural = "Banners"

    #: The per-edition live flags, keyed by the edition names the cache keys use.
    LIVE_FLAGS = {"n23": "live_n23", "n26": "live_n26"}

    def __str__(self):
        live = [name for name, flag in self.LIVE_FLAGS.items() if getattr(self, flag)]
        status = "LIVE " + "+".join(live) if live else "Draft"
        return f"[{status}] {self.text[:50]}..."

    @property
    def bootstrap_icon(self) -> str:
        """Return the Bootstrap Icons class, or an empty string if none is selected.

        N26 resolves the shared key through its own template filter, keeping
        edition icon names outside this model.
        """
        return banner_icons.bootstrap_class(self.icon)

    def save(self, *args, **kwargs):
        # Each side shows at most one banner: going live on a side takes
        # that side's slot from whichever banner held it.
        for flag in self.LIVE_FLAGS.values():
            if getattr(self, flag):
                Banner.objects.filter(**{flag: True}).exclude(pk=self.pk).update(
                    **{flag: False}
                )
        super().save(*args, **kwargs)
        # Clear the banner caches when any banner is saved
        for key in BANNER_CACHE_KEYS.values():
            cache.delete(key)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        # Clear the banner caches when any banner is deleted
        for key in BANNER_CACHE_KEYS.values():
            cache.delete(key)

    def clean(self):
        super().clean()
        # Ensure CTA text is provided if CTA URL is provided
        if self.cta_url and not self.cta_text:
            raise models.ValidationError(
                {"cta_text": "CTA text is required when CTA URL is provided."}
            )


class ImpersonationLog(AppBase):
    """Audit record of an admin impersonation session.

    ``owner`` (inherited from :class:`~gyrinx.models.Owned`) is the impersonator —
    the admin who started the session. ``target`` is the user who was impersonated.
    ``created`` marks the start; ``ended_at`` / ``ended_reason`` are filled in when
    the session stops (manually, on logout, on timeout, or when it is revoked
    automatically because the admin lost privileges or the target went away).

    This is an append-only audit log — like :class:`~gyrinx.analytics.models.Event`
    it does not declare ``HistoricalRecords``.
    """

    class EndedReason(models.TextChoices):
        MANUAL = "manual", "Stopped manually"
        LOGOUT = "logout", "Logged out"
        EXPIRED = "expired", "Timed out"
        REVOKED = "revoked", "Ended automatically"

    target = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="impersonated_by_sessions",
        help_text="The user who was impersonated.",
    )
    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the impersonation session ended (null while active).",
    )
    ended_reason = models.CharField(
        max_length=20,
        choices=EndedReason.choices,
        blank=True,
        help_text="Why the impersonation session ended.",
    )

    class Meta:
        db_table = "core_impersonationlog"
        verbose_name = "impersonation log"
        verbose_name_plural = "impersonation logs"
        ordering = ["-created"]

    @property
    def impersonator(self):
        """Alias for ``owner`` — the admin who started the session."""
        return self.owner

    def __str__(self):
        state = "active" if self.ended_at is None else self.ended_reason
        return f"{self.owner} → {self.target} ({state})"


# Each recipient has independent read, archive and delete state. Notification
# creation helpers accept background calls without a request or acting user.


class NotificationType(models.TextChoices):
    """High-level category of a notification, used for filtering and the inbox icon."""

    SYSTEM = "system", "System"  # background maintenance / data migration (default)
    LIST = "list", "List"  # something changed on your list
    CAMPAIGN = "campaign", "Campaign"  # something in a campaign you arbitrate
    GENERAL = "general", "General"


class NotificationQuerySet(models.QuerySet):
    """Query helpers for the inbox buckets, badge count and banner surfaces."""

    def for_recipient(self, user):
        return self.filter(owner=user)

    def active(self):
        """The inbox bucket: not archived, not (soft-)deleted."""
        return self.filter(archived=False, deleted_at__isnull=True)

    def archived_bucket(self):
        """The archived bucket: archived but not deleted."""
        return self.filter(archived=True, deleted_at__isnull=True)

    def unread(self):
        return self.filter(is_read=False)

    def unread_count_for(self, user):
        """Cheap COUNT for the navbar badge (backed by a partial index)."""
        return self.for_recipient(user).active().unread().count()

    def banners_for(self, user, obj):
        """Active, unread, banner-flagged notifications to show on ``obj``'s page.

        Matches either relation, so a notification about a gang *within* a campaign
        (``target`` the gang, ``scope`` the campaign) banners on both pages.
        """
        content_type = ContentType.objects.get_for_model(obj)
        return (
            self.for_recipient(user)
            .active()
            .unread()
            .filter(show_as_banner=True)
            .filter(
                Q(target_content_type=content_type, target_object_id=obj.pk)
                | Q(scope_content_type=content_type, scope_object_id=obj.pk)
            )
            .select_related("sender")
        )


class NotificationManager(HistoryAwareManager):
    """Manager for :class:`Notification`. Combined with the queryset below."""

    pass


class Notification(AppBase):
    """A notification for one recipient, stored as owner.

    Deleting the recipient deletes the notification. A null sender represents
    a system notification. No history table is kept: these disposable inbox
    records change on each read or archive action, while Event and Backfill
    record the originating actions.
    """

    sender = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_notifications",
        help_text="User who caused this notification. Null for background/system jobs.",
    )
    subject = models.CharField(max_length=255)
    content = models.TextField(blank=True, default="")
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices,
        default=NotificationType.SYSTEM,
        db_index=True,
    )

    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Soft-delete timestamp. Deleted rows disappear from every inbox view.",
    )

    # Generic relations avoid platform ForeignKeys to edition models. The target
    # identifies the subject; scope identifies its container, such as a campaign.
    # Deleted objects leave their UUIDs stored, preserving inbox text without a link.
    target_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_targets",
    )
    target_object_id = models.UUIDField(null=True, blank=True)
    target = GenericForeignKey("target_content_type", "target_object_id")

    scope_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_scopes",
    )
    scope_object_id = models.UUIDField(null=True, blank=True)
    scope = GenericForeignKey("scope_content_type", "scope_object_id")

    # Banner surface. Persistent dismiss == mark read.
    show_as_banner = models.BooleanField(
        default=False,
        help_text="Also show this on the target object's page as a banner.",
    )
    banner_colour = models.CharField(
        max_length=20,
        blank=True,
        default="info",
        help_text="Bootstrap colour for the in-page banner (info/warning/success/danger).",
    )
    icon = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Bootstrap icon class, e.g. 'bi-info-circle'.",
    )

    objects = NotificationManager.from_queryset(NotificationQuerySet)()

    class Meta:
        # Pinned: the table predates the move to the platform and was not renamed.
        db_table = "core_notification"
        ordering = ["-created"]
        indexes = [
            # Hot path: unread badge count. Partial index over active-unread rows.
            models.Index(
                fields=["owner"],
                name="notif_unread_idx",
                condition=Q(is_read=False, archived=False, deleted_at__isnull=True),
            ),
            # Inbox listing (recipient, newest first).
            models.Index(fields=["owner", "-created"], name="notif_inbox_idx"),
            # Banner surfaces, one index per generic relation. banners_for() ORs
            # the two, which Postgres can satisfy as a bitmap OR over both.
            models.Index(
                fields=["target_content_type", "target_object_id", "show_as_banner"],
                name="notif_banner_target_idx",
            ),
            models.Index(
                fields=["scope_content_type", "scope_object_id", "show_as_banner"],
                name="notif_banner_scope_idx",
            ),
        ]

    # Default icon per type, used when no explicit `icon` is set.
    TYPE_ICONS = {
        NotificationType.SYSTEM: "bi-gear",
        NotificationType.LIST: "bi-people",
        NotificationType.CAMPAIGN: "bi-flag",
        NotificationType.GENERAL: "bi-bell",
    }

    def __str__(self):
        return f"{self.subject} → {self.owner}"

    @property
    def display_icon(self):
        """The explicit icon if set, otherwise a sensible default for the type."""
        return self.icon or self.TYPE_ICONS.get(self.notification_type, "bi-bell")

    @property
    def target_url(self):
        """Return the first available URL from the target or scope.

        Skip missing objects and objects without get_absolute_url. Return an
        empty string if neither can supply a URL. Prefetching UUID-backed keys
        with a different Python representation may leave either relation empty.
        """
        for obj in (self.target, self.scope):
            if obj is None:
                continue
            getter = getattr(obj, "get_absolute_url", None)
            if getter is not None:
                return getter()
        return ""

    @property
    def recipient(self):
        """Readable alias for ``owner`` (AppBase's owner IS the recipient)."""
        return self.owner

    @property
    def is_system(self):
        """True when there's no human sender — shown as a Gyrinx system notification."""
        return self.sender_id is None

    @property
    def sender_label(self):
        """Display name for the source: 'Gyrinx' for system, else the sender username."""
        if self.is_system:
            return "Gyrinx"
        return self.sender.get_username()

    def mark_read(self, *, commit=True):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            if commit:
                self.save(update_fields=["is_read", "read_at", "modified"])

    def mark_unread(self, *, commit=True):
        if self.is_read:
            self.is_read = False
            self.read_at = None
            if commit:
                self.save(update_fields=["is_read", "read_at", "modified"])


#
# Creation service — mirrors log_event: module-level, never-raises, no request needed.
#


def _generic_key(obj):
    """Return a content type and UUID for a generic relation.

    Convert UUID-compatible keys before writing them to UUID columns. Invalid
    keys leave the notification unlinked, avoiding a database error that
    could invalidate the caller's transaction.
    """
    if obj is None:
        return None, None
    key = obj.pk
    if not isinstance(key, uuid.UUID):
        becomes = getattr(key, "to_uuid", None)
        try:
            key = becomes() if callable(becomes) else uuid.UUID(str(key))
        except AttributeError, TypeError, ValueError:
            logger.warning(
                "Cannot link a notification to %r: its key is not a UUID",
                type(obj).__name__,
            )
            return None, None
    return ContentType.objects.get_for_model(obj), key


def notify(
    *,
    recipient,
    subject,
    content="",
    notification_type=NotificationType.SYSTEM,
    sender=None,
    target=None,
    scope=None,
    show_as_banner=False,
    banner_colour="info",
    icon="",
):
    """Create one notification. Safe: logs and returns ``None`` on any error.

    Args:
        recipient: the User whose inbox receives this (becomes ``owner``).
        subject: short headline.
        content: optional longer body.
        notification_type: a :class:`NotificationType` value.
        sender: the acting User, or ``None`` for a system/background notification.
        target: what the notification is about (any model instance), or ``None``.
        scope: the wider context ``target`` sits in, or ``None``.
        show_as_banner: also surface it on the target's page.
        banner_colour / icon: banner styling.

    Returns:
        The created :class:`Notification`, or ``None`` if it couldn't be created.
    """
    try:
        if recipient is None:
            logger.warning("notify() called with no recipient; skipping")
            return None
        target_type, target_key = _generic_key(target)
        scope_type, scope_key = _generic_key(scope)
        return Notification.objects.create_with_user(
            user=sender,  # history user (no-op — no history table); harmless
            owner=recipient,  # AppBase owner == recipient
            sender=sender,
            subject=subject,
            content=content,
            notification_type=notification_type,
            target_content_type=target_type,
            target_object_id=target_key,
            scope_content_type=scope_type,
            scope_object_id=scope_key,
            show_as_banner=show_as_banner,
            banner_colour=banner_colour,
            icon=icon,
        )
    except Exception:
        logger.exception(
            "Failed to create notification for recipient=%r",
            getattr(recipient, "id", None),
        )
        return None


def notify_list_owner(
    list_,
    *,
    subject,
    content="",
    sender=None,
    notification_type=NotificationType.LIST,
    show_as_banner=False,
    **kwargs,
):
    """Notify the owner of ``list_``. No-op (returns ``None``) if the list has no owner."""
    if getattr(list_, "owner_id", None) is None:
        return None
    return notify(
        recipient=list_.owner,
        subject=subject,
        content=content,
        sender=sender,
        notification_type=notification_type,
        target=list_,
        show_as_banner=show_as_banner,
        **kwargs,
    )


def notify_campaign_arbitrator(
    campaign,
    *,
    subject,
    content="",
    sender=None,
    target=None,
    notification_type=NotificationType.CAMPAIGN,
    show_as_banner=False,
    **kwargs,
):
    """Notify the arbitrator (``campaign.owner``). No-op if the campaign has no owner.

    ``target`` is the thing inside the campaign the notification is about (a gang,
    say); the campaign is then its ``scope``. With no ``target``, the campaign is
    itself the subject.
    """
    if getattr(campaign, "owner_id", None) is None:
        return None
    return notify(
        recipient=campaign.owner,
        subject=subject,
        content=content,
        sender=sender,
        notification_type=notification_type,
        target=campaign if target is None else target,
        scope=None if target is None else campaign,
        show_as_banner=show_as_banner,
        **kwargs,
    )


def notify_list_changed(
    list_, *, subject, content="", sender=None, show_as_banner=True
):
    """Tell the list owner, and the campaign arbitrator if the list is in a campaign.

    Guards against double-notifying when the arbitrator also owns the list.
    """
    notify_list_owner(
        list_,
        subject=subject,
        content=content,
        sender=sender,
        notification_type=NotificationType.LIST,
        show_as_banner=show_as_banner,
    )
    campaign_id = getattr(list_, "campaign_id", None)
    if getattr(list_, "is_campaign_mode", False) and campaign_id:
        campaign = list_.campaign
        if campaign.owner_id and campaign.owner_id != list_.owner_id:
            notify_campaign_arbitrator(
                campaign,
                subject=subject,
                content=content,
                sender=sender,
                target=list_,
                show_as_banner=show_as_banner,
            )


def notify_many(
    recipients,
    *,
    subject,
    content="",
    sender=None,
    notification_type=NotificationType.SYSTEM,
    show_as_banner=False,
    banner_colour="info",
    icon="",
    batch_size=500,
):
    """Fan out to many recipients efficiently (broadcast). Returns the count created.

    De-dupes recipients and creates rows in batches of ``batch_size`` so peak memory
    stays bounded for large audiences (there's no history table, so no per-row save
    cost). Pass a queryset's ``.iterator()`` to also stream the recipients rather than
    loading them all at once. Safe: logs and returns the count created so far on error.
    """

    def build():
        seen = set()
        for recipient in recipients:
            if recipient is None or recipient.id in seen:
                continue
            seen.add(recipient.id)
            yield Notification(
                owner=recipient,
                sender=sender,
                subject=subject,
                content=content,
                notification_type=notification_type,
                show_as_banner=show_as_banner,
                banner_colour=banner_colour,
                icon=icon,
            )

    created = 0
    try:
        objs = build()
        while batch := list(islice(objs, batch_size)):
            Notification.objects.bulk_create(batch, batch_size=batch_size)
            created += len(batch)
    except Exception:
        logger.exception("notify_many failed for subject=%r", subject)
    return created


class ChangelogEntryTag(Base):
    """An admin-managed tag shared by changelog entries.

    Tags have no owner because deleting a staff account must not delete
    shared classifications.
    """

    class Colour(models.TextChoices):
        DEFAULT = "default", "Gyrinx default"
        INK = "ink", "Ink"
        RED = "red", "Red"
        ORANGE = "orange", "Orange"
        AMBER = "amber", "Amber"
        YELLOW = "yellow", "Yellow"
        LIME = "lime", "Lime"
        GREEN = "green", "Green"
        EMERALD = "emerald", "Emerald"
        TEAL = "teal", "Teal"
        CYAN = "cyan", "Cyan"
        SKY = "sky", "Sky"
        BLUE = "blue", "Blue"
        INDIGO = "indigo", "Indigo"
        VIOLET = "violet", "Violet"
        PURPLE = "purple", "Purple"
        FUCHSIA = "fuchsia", "Fuchsia"
        PINK = "pink", "Pink"
        ROSE = "rose", "Rose"

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="The tag as shown, e.g. 'N26'.",
    )
    colour = models.CharField(
        max_length=20,
        choices=Colour,
        default=Colour.DEFAULT,
        help_text="The tag colour. Gyrinx default follows light and dark mode.",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "changelog entry tag"
        verbose_name_plural = "changelog entry tags"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ChangelogEntry(AppBase):
    """One dated entry in the site changelog.

    Platform-owned: what changed is a fact about the site, whichever
    edition's dashboard lists it. The body is rich text, written in the
    admin and sanitised at render time by whatever page shows it — the
    n26 dashboard runs it through its ``richtext`` filter.
    """

    date = models.DateField(help_text="The day the change shipped.")
    title = models.CharField(max_length=255, help_text="One line naming the change.")
    body = models.TextField(
        blank=True,
        help_text="The detail, as rich text. Keep it short — a dashboard lists many.",
    )
    tags = models.ManyToManyField(
        ChangelogEntryTag,
        blank=True,
        related_name="entries",
        help_text="Labels for filtering, e.g. the edition the change belongs to.",
    )

    # Tag membership is deliberately not history-tracked (no ``m2m_fields``):
    # entries are edited in the admin, whose LogEntry already records the
    # change, and m2m tracking would write extra full-body historical rows
    # per save for no additional audit value.
    history = HistoricalRecords()

    class Meta:
        verbose_name = "changelog entry"
        verbose_name_plural = "changelog entries"
        ordering = ["-date", "-created"]

    def __str__(self):
        return f"{self.date}: {self.title}"


class Availability(models.TextChoices):
    """Feature access levels. OFF denies access even to allowlisted users."""

    OFF = "off", "Off — nobody, whatever the group says"
    ALLOWLIST = "allowlist", "Allowlist — whoever is in the group"
    EVERYONE = "everyone", "Everyone — any signed-in reader"


class FeatureFlag(Base):
    """Admin-managed access settings for a registered feature slug.

    Availability controls access for all signed-in users or for a selected
    group. A missing record disables the feature. Editions register the
    slugs in gyrinx.site.flags; the platform stores their access settings.
    """

    slug = models.SlugField(
        unique=True,
        help_text="What the code asks for. Fixed once the row exists.",
    )
    name = models.CharField(
        max_length=100,
        help_text="What this feature is called on this page.",
    )
    availability = models.CharField(
        max_length=20,
        choices=Availability,
        default=Availability.OFF,
        help_text="Off shuts the feature for everyone, the group included.",
    )
    group = models.ForeignKey(
        "auth.Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feature_flags",
        help_text=(
            "Who gets the feature while it is on the allowlist. Add and "
            "remove people here or on the group itself. No group means an "
            "empty allowlist, not an open door."
        ),
    )
    note = models.TextField(
        blank=True,
        default="",
        help_text="What this feature is, for whoever finds this page later.",
    )

    class Meta:
        verbose_name = "feature flag"
        verbose_name_plural = "feature flags"
        ordering = ["name"]
        constraints = [
            # Enforce availability values for writes that bypass model validation.
            models.CheckConstraint(
                condition=models.Q(availability__in=Availability.values),
                name="site_feature_flag_availability_known",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.get_availability_display()})"

    def open_to(self, user):
        """Return whether a signed-in user may access the feature.

        Staff and superusers have no bypass. Unknown availability values deny
        access, including to members of the selected group.
        """
        if self.availability == Availability.OFF:
            return False
        if not user or not user.is_authenticated:
            return False
        if self.availability == Availability.EVERYONE:
            return True
        if self.availability != Availability.ALLOWLIST:
            # Reject unknown values before checking group membership.
            return False
        if self.group_id is None:
            return False
        return user.groups.filter(pk=self.group_id).exists()
