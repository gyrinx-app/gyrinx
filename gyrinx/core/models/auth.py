from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from simple_history.models import HistoricalRecords

from gyrinx.core.badges import (
    HIDE_BADGE,
    PATREON_BADGES,
    STAFF_BADGE,
    BadgeDef,
    badge_by_slug,
    rank_for_tier_title,
)
from gyrinx.models import Base


class PatreonStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    FORMER = "former", "Former"
    DECLINED = "declined", "Declined"


class UserProfile(Base):
    """
    UserProfile stores additional information about users.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    tos_agreed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user agreed to the Terms of Service",
    )
    patreon_status = models.CharField(
        max_length=20,
        choices=PatreonStatus.choices,
        blank=True,
        default="",
        help_text="Current Patreon membership status",
    )
    patreon_tier = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Patreon tier title (e.g. Scummer)",
    )
    patreon_member_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Patreon member UUID for deduplication",
    )
    patreon_email = models.EmailField(
        blank=True,
        default="",
        help_text="Email address from Patreon webhook",
    )
    selected_badge = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Slug of the supporter badge the user has chosen to display "
        "(blank = no badge).",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "user profile"
        verbose_name_plural = "user profiles"

    def __str__(self):
        return f"{self.user.username} profile"

    def record_tos_agreement(self):
        """Record that the user has agreed to the ToS."""
        self.tos_agreed_at = timezone.now()
        self.save()

    # --- Supporter badges ---
    #
    # Eligibility is derived live from the user's state, never stored as a grant,
    # so former/declined supporters (and ex-staff) automatically lose their
    # badges. Patreon badges gate on ``patreon_status == ACTIVE``: a lapsed
    # supporter can carry a stale ``patreon_tier`` (the webhook doesn't always
    # clear it), so we never trust the stored tier on its own. The staff badge
    # gates on ``User.is_staff``.

    @property
    def current_tier_rank(self) -> int:
        """Rank of the user's current badge-eligible tier (0 if none).

        Returns 0 unless the user is an active Patreon supporter at a paid tier.
        """
        if self.patreon_status != PatreonStatus.ACTIVE:
            return 0
        return rank_for_tier_title(self.patreon_tier)

    @property
    def unlocked_badges(self) -> list[BadgeDef]:
        """Patreon badges the user is allowed to display (tiers up to theirs)."""
        rank = self.current_tier_rank
        if rank <= 0:
            return []
        return [b for b in PATREON_BADGES if b.rank <= rank]

    @property
    def available_badges(self) -> list[BadgeDef]:
        """Every badge the user may display — Patreon tiers plus staff.

        Staff is just another badge here (opt-out, shown by default like the
        Patreon ones), gated on ``User.is_staff`` so it retracts automatically
        when staff access is removed.
        """
        badges = list(self.unlocked_badges)
        if self.user.is_staff:
            badges.append(STAFF_BADGE)
        return badges

    @property
    def eligible_badge_slugs(self) -> set[str]:
        """Slugs of every badge currently available to the user."""
        return {b.slug for b in self.available_badges}

    @cached_property
    def display_badge(self) -> BadgeDef | None:
        """The badge to render, or ``None``.

        Eligible users display a badge by default — the highest-ranked one they
        have — without having to choose. The rules, in order:

        * No available badges → nothing (lapsed supporters / ex-staff).
        * Explicit ``HIDE_BADGE`` opt-out → nothing.
        * An explicit, still-available selection → that badge (e.g. an Uphiver
          who prefers to show the Scummer badge, or a staff member showing a
          Patreon tier instead).
        * Otherwise (no choice, or a stale selection) → the highest-ranked
          available badge. Staff outranks the Patreon tiers, so staff members
          show the staff badge by default.
        """
        available = self.available_badges
        if not available:
            return None
        if self.selected_badge == HIDE_BADGE:
            return None
        if self.selected_badge in self.eligible_badge_slugs:
            return badge_by_slug(self.selected_badge)
        # Select by rank rather than list position so it doesn't depend on
        # registry ordering.
        return max(available, key=lambda b: b.rank)
