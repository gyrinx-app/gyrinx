"""Notifications: per-recipient inbox rows plus a small creation service.

The model follows the fan-out approach — one row per recipient — so read/unread,
archive and delete state is independent per user. The ``notify*`` functions mirror
the ergonomics of :func:`gyrinx.analytics.models.log_event`: they are module-level
helpers that live beside the model, never raise (they log and return ``None``/``0``
instead), and work with no request and no acting user, so background jobs and data
migrations can call them safely.
"""

import logging
from itertools import islice

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.utils import timezone

from gyrinx.base_models import AppBase
from gyrinx.history_aware_manager import HistoryAwareManager

logger = logging.getLogger(__name__)

__all__ = [
    "NotificationType",
    "Notification",
    "notify",
    "notify_list_owner",
    "notify_campaign_arbitrator",
    "notify_list_changed",
    "notify_many",
]


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
        (``target`` the gang, ``scope`` the campaign) banners on both pages — which
        is what the two fixed FKs used to give us.
        """
        return (
            self.for_recipient(user)
            .active()
            .unread()
            .filter(show_as_banner=True)
            .filter(
                Q(
                    target_content_type=ContentType.objects.get_for_model(obj),
                    target_object_id=obj.pk,
                )
                | Q(
                    scope_content_type=ContentType.objects.get_for_model(obj),
                    scope_object_id=obj.pk,
                )
            )
            .select_related("sender")
        )


class NotificationManager(HistoryAwareManager):
    """Manager for :class:`Notification`. Combined with the queryset below."""

    pass


class Notification(AppBase):
    """A single notification in one recipient's inbox.

    ``owner`` (from :class:`gyrinx.models.Owned`) **is** the recipient — the person
    whose inbox this row lives in, and the row it should cascade-delete with on
    account deletion. ``sender`` is the actor who caused it, and is null for
    background/system notifications (surfaced as a Gyrinx "system" indicator in the UI).

    Note: this model deliberately does **not** declare ``history = HistoricalRecords()``.
    These are high-volume, per-recipient, disposable fan-out rows and every
    read/archive toggle is a ``save()``; recording history would double write volume
    and bloat the historical table for no audit value (the *cause* of a notification
    is already audited via ``Event``/``Backfill``). ``HistoryMixin`` helpers all guard
    on ``hasattr(self, "history")``, so omitting it is safe.
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

    # What the notification is about, and the wider context it belongs to, as
    # generic relations: `target` is the subject (a gang, say) and `scope` is the
    # container it sits in (that gang's campaign). Either may be null.
    #
    # Generic rather than fixed FKs because this model is on its way to the
    # platform, which cannot hold a ForeignKey to an edition table — see #2093.
    # Deletion leaves a dangling id rather than nulling the column, which is the
    # same end state the old SET_NULL gave us (the inbox text survives, the link
    # stops resolving); primary keys are UUIDs, so a dangling id can never be
    # recycled onto some other object.
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

    # Superseded by target/scope above; retained so a deploy can roll back and so
    # instances still running the previous revision keep working. Dropped in the
    # follow-up that moves this model to the platform.
    related_list = models.ForeignKey(
        "core.List",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    related_campaign = models.ForeignKey(
        "core.Campaign",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )

    # Banner surface. Persistent dismiss == mark read.
    show_as_banner = models.BooleanField(
        default=False,
        help_text="Also show this on the related List/Campaign page as a banner.",
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
        """URL of the related object, if any, for the inbox row title link.

        Asks the object where it lives rather than reversing a URL name here, so
        this works for anything a future edition might point a notification at.
        Returns "" when there is no target, when the target has been deleted, or
        when its model does not define ``get_absolute_url``.
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


def notify(
    *,
    recipient,
    subject,
    content="",
    notification_type=NotificationType.SYSTEM,
    sender=None,
    related_list=None,
    related_campaign=None,
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
        related_list / related_campaign: optional linked objects.
        show_as_banner: also surface it on the related object's page.
        banner_colour / icon: banner styling.

    Returns:
        The created :class:`Notification`, or ``None`` if it couldn't be created.
    """
    try:
        if recipient is None:
            logger.warning("notify() called with no recipient; skipping")
            return None
        # The gang is the subject when there is one, and its campaign is then the
        # surrounding scope; a campaign-only notification is its own subject.
        # These kwargs become `target=` / `scope=` once the FK columns are dropped.
        target = related_list if related_list is not None else related_campaign
        scope = related_campaign if related_list is not None else None
        return Notification.objects.create_with_user(
            user=sender,  # history user (no-op — no history table); harmless
            owner=recipient,  # AppBase owner == recipient
            sender=sender,
            subject=subject,
            content=content,
            notification_type=notification_type,
            target=target,
            scope=scope,
            # Written alongside the generic relations so the previous revision
            # keeps reading them during a rollout or rollback.
            related_list=related_list,
            related_campaign=related_campaign,
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
        related_list=list_,
        show_as_banner=show_as_banner,
        **kwargs,
    )


def notify_campaign_arbitrator(
    campaign,
    *,
    subject,
    content="",
    sender=None,
    related_list=None,
    notification_type=NotificationType.CAMPAIGN,
    show_as_banner=False,
    **kwargs,
):
    """Notify the arbitrator (``campaign.owner``). No-op if the campaign has no owner."""
    if getattr(campaign, "owner_id", None) is None:
        return None
    return notify(
        recipient=campaign.owner,
        subject=subject,
        content=content,
        sender=sender,
        notification_type=notification_type,
        related_campaign=campaign,
        related_list=related_list,
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
                related_list=list_,
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
