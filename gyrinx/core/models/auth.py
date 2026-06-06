from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from simple_history.models import HistoricalRecords

from gyrinx.core.badges import (
    PATREON_BADGES,
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
    # Eligibility is derived live from Patreon status, never stored as a grant,
    # so former/declined supporters automatically lose their badges. The single
    # load-bearing gate is ``patreon_status == ACTIVE``: a lapsed supporter can
    # carry a stale ``patreon_tier`` (the webhook doesn't always clear it), so we
    # never trust the stored tier on its own.

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
        """Badges the user is currently allowed to display (tiers up to theirs)."""
        rank = self.current_tier_rank
        if rank <= 0:
            return []
        return [b for b in PATREON_BADGES if b.rank <= rank]

    @property
    def eligible_badge_slugs(self) -> set[str]:
        """Slugs of currently-unlocked badges."""
        return {b.slug for b in self.unlocked_badges}

    @cached_property
    def display_badge(self) -> BadgeDef | None:
        """The badge to render, or ``None``.

        Returns the selected badge only if it's still unlocked, so a selection
        that's no longer eligible (e.g. the user lapsed) renders nothing.
        """
        if not self.selected_badge:
            return None
        if self.selected_badge not in self.eligible_badge_slugs:
            return None
        return badge_by_slug(self.selected_badge)
