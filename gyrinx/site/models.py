"""Site-level platform models: the banner, the impersonation log, the
per-user notification inbox (with the small ``notify*`` creation service that
sits beside it), and the feature flags that say who may reach work still
being built.
"""

import logging
from itertools import islice

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

# Cache keys/timeout for the live banner, one per edition — each side of the
# site shows its own banner, so each caches its own answer. Defined beside the
# model rather than in the context processor that reads it, so the platform
# owns its own constants.
BANNER_CACHE_KEYS = {
    "n23": "site_banner_live:n23",
    "n26": "site_banner_live:n26",
}
BANNER_CACHE_TIMEOUT = 300  # 5 minutes


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
        """The Bootstrap Icons class for this banner, or "" for no icon.

        A property rather than a template filter because Bootstrap is the
        platform's own stack, not an edition's: platform templates can ask the
        model directly. n26 does not get an equivalent — it resolves the same
        key through its own filter, so that this model never has to know an
        edition's icon names.
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


#
# Notifications: per-recipient inbox rows plus a small creation service.
#
# The model follows the fan-out approach — one row per recipient — so read/unread,
# archive and delete state is independent per user. The ``notify*`` functions mirror
# the ergonomics of :func:`gyrinx.analytics.models.log_event`: they are module-level
# helpers that live beside the model, never raise (they log and return ``None``/``0``
# instead), and work with no request and no acting user, so background jobs and data
# migrations can call them safely.
#


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
    # Generic rather than fixed FKs because this model lives on the platform,
    # which cannot hold a ForeignKey to an edition table — see #2093. Deletion
    # leaves a dangling id rather than nulling the column, which is the same end
    # state the old SET_NULL gave us (the inbox text survives, the link stops
    # resolving); primary keys are UUIDs, so a dangling id can never be recycled
    # onto some other object.
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
        """URL of the related object, if any, for the inbox row title link.

        Asks the object where it lives rather than reversing a URL name here, so
        this works for anything an edition might point a notification at.
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
        return Notification.objects.create_with_user(
            user=sender,  # history user (no-op — no history table); harmless
            owner=recipient,  # AppBase owner == recipient
            sender=sender,
            subject=subject,
            content=content,
            notification_type=notification_type,
            target=target,
            scope=scope,
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
    """A label an entry can carry — an edition ("N23", "N26"), say.

    A lookup table rather than a choices field so tags can be added in the
    admin without a deploy. Entries wear any number of them. Plain ``Base``
    rather than ``AppBase`` — like :class:`~gyrinx.pages.models.FlatPageVisibility`,
    a site-wide lookup row has no meaningful owner, and an owner FK's CASCADE
    would delete shared tags with the staff account that created them.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="The tag as shown, e.g. 'N26'.",
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
    """How widely a feature is open.

    Three states rather than a tick box, because "nobody", "a few people"
    and "everybody" are three different answers and the middle one is the
    whole point of gating something. Off wins over the group, which is what
    makes it the control to reach for when a half-built screen starts
    writing bad rows.
    """

    OFF = "off", "Off — nobody, whatever the group says"
    ALLOWLIST = "allowlist", "Allowlist — whoever is in the group"
    EVERYONE = "everyone", "Everyone — any signed-in reader"


class FeatureFlag(Base):
    """A feature still being built, and who may reach it.

    A row per feature, edited in the admin, so opening one to another player
    is a change somebody makes on a page rather than a deploy. The two ways
    to move are deliberately different acts: change ``availability`` to open
    or shut the feature as a whole, or leave it on the allowlist and add
    people to the group one at a time.

    ``slug`` is what code asks for and never changes; ``name`` is what the
    admin reads. A slug with no row is off, so a feature reaches nobody until
    somebody opens it. Which slugs exist is an edition's knowledge, claimed
    through ``gyrinx.site.flags.register_flags``; this table holds the state,
    not the vocabulary.
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
            # Choices are model-level validation and nothing more: a raw
            # write, a data migration or a shell can store any string. What
            # this row says is who reaches a feature, so the database refuses
            # a word nothing can read rather than leaving it to be guessed.
            models.CheckConstraint(
                condition=models.Q(availability__in=Availability.values),
                name="site_feature_flag_availability_known",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.get_availability_display()})"

    def open_to(self, user):
        """Whether this account may reach the feature.

        A visitor never qualifies, even where the feature is open to
        everyone: a page nobody is supposed to know about should not
        announce itself to someone who is not signed in.

        There is no bypass for staff or superusers. An account that should
        see a gated feature goes in the group, so what a person can reach is
        one question with one answer rather than two rules that drift.
        """
        if self.availability == Availability.OFF:
            return False
        if not user or not user.is_authenticated:
            return False
        if self.availability == Availability.EVERYONE:
            return True
        if self.availability != Availability.ALLOWLIST:
            # A word nothing here recognises. Falling through to the group
            # check would let a member of any attached group in on the
            # strength of a value no code wrote — so an unreadable state is
            # shut, the same as off.
            return False
        if self.group_id is None:
            return False
        return user.groups.filter(pk=self.group_id).exists()
