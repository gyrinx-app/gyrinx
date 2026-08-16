from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.functional import cached_property
from simple_history.models import HistoricalRecords

from gyrinx.badges import (
    HIDE_BADGE,
    PATREON_BADGES,
    STAFF_BADGE,
    BadgeDef,
    badge_by_slug,
    code_badge_slugs,
    everyone_badge_ids,
    granted_badges_by_id,
    invalidate_granted_badges,
    rank_for_tier_title,
)
from gyrinx.models import Archived, Base


class PatreonStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    FORMER = "former", "Former"
    DECLINED = "declined", "Declined"


class Badge(Base, Archived):
    """A badge somebody created in the admin, for granting to people.

    The counterpart to the badges defined in ``gyrinx.badges``: those are held
    by whoever the live rules say holds them, these are held by whoever has been
    given one. Artwork is uploaded rather than committed, so it is untrusted and
    is cleaned on the way out every time it is drawn.

    Archiving retires a badge without deleting the history of who held it: it
    leaves the pickers and the pages at once, and its grants stop counting.
    """

    slug = models.SlugField(
        max_length=50,
        unique=True,
        help_text=(
            "Short name used internally and stored against anyone who picks "
            "this badge. Changing it later un-picks the badge for everybody "
            "displaying it, so choose it once."
        ),
    )
    title = models.CharField(
        max_length=100,
        help_text="What this badge is called, shown in the badge picker.",
    )
    description = models.CharField(
        max_length=200,
        help_text=(
            "The one-line explanation shown when somebody hovers the badge. "
            "Write it for a reader who has never seen it before."
        ),
    )
    artwork_url = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text=(
            "Address of the SVG drawn beside the username. Upload a drawing to "
            "fill this in, or paste the address of one already uploaded. "
            "Colours are kept as drawn. Leave blank and nothing is drawn."
        ),
    )
    rank = models.IntegerField(
        default=0,
        help_text=(
            "Breaks the tie when somebody holds several badges and has not "
            "picked one. The supporter tiers rank 1 to 3 and staff ranks 100, "
            "so the default of 0 means a supporter keeps showing their "
            "supporter badge."
        ),
    )
    auto_display = models.BooleanField(
        default=False,
        help_text=(
            "Show this badge to people who hold it without them choosing it. "
            "Leave off for anything granted widely — on, it would appear "
            "beside every holder's name the moment it is granted."
        ),
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "badge"
        verbose_name_plural = "badges"
        ordering = ["title"]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        # The two kinds of badge share one slug namespace, because a profile
        # stores its selection as a bare slug and cannot say which kind it meant.
        if self.slug in code_badge_slugs():
            raise ValidationError(
                {"slug": f'"{self.slug}" is the name of a built-in badge.'}
            )

    def as_def(self) -> BadgeDef:
        """This row as the shape the render path reads every badge as."""
        return BadgeDef(
            slug=self.slug,
            title=self.title,
            rank=self.rank,
            description=self.description,
            artwork_url=self.artwork_url,
            auto_display=self.auto_display,
            id=self.id,
        )


class BadgeGrant(Base):
    """A record that somebody — or everybody — has been given a badge.

    Deleting a grant is how one is taken back, and the history table keeps the
    record of it having existed. Nothing else needs doing on the way out: a
    profile still naming a badge it no longer holds falls through to whatever
    the person does hold, because eligibility is worked out on read.
    """

    class Audience(models.TextChoices):
        USER = "user", "A single person"
        EVERYONE = "everyone", "Everyone"

    badge = models.ForeignKey(
        Badge,
        on_delete=models.CASCADE,
        related_name="grants",
    )
    audience = models.CharField(
        max_length=20,
        choices=Audience.choices,
        default=Audience.USER,
        help_text=(
            "Who this grant covers. Granting to everyone adds the badge to "
            "every account's picker; it changes nobody's displayed badge "
            "unless the badge is set to show automatically."
        ),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="badge_grants",
        help_text="The person granted the badge. Leave blank when granting to everyone.",
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="badges_granted",
    )
    reason = models.TextField(
        blank=True,
        default="",
        help_text="Why this was granted. Internal note — never shown to anyone.",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "badge grant"
        verbose_name_plural = "badge grants"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(audience="user", user__isnull=False)
                    | models.Q(audience="everyone", user__isnull=True)
                ),
                name="badgegrant_user_matches_audience",
            ),
            models.UniqueConstraint(
                fields=["badge", "user"],
                condition=models.Q(audience="user"),
                name="badgegrant_one_per_person",
            ),
            models.UniqueConstraint(
                fields=["badge"],
                condition=models.Q(audience="everyone"),
                name="badgegrant_one_everyone",
            ),
        ]

    def __str__(self):
        if self.audience == self.Audience.EVERYONE:
            return f"{self.badge} — everyone"
        return f"{self.badge} — {self.user}"

    def clean(self):
        super().clean()
        if self.audience == self.Audience.USER and self.user_id is None:
            raise ValidationError({"user": "Say who is being granted this badge."})
        if self.audience == self.Audience.EVERYONE and self.user_id is not None:
            raise ValidationError(
                {"user": "A grant to everyone names nobody in particular."}
            )


@receiver(post_save, sender=Badge)
@receiver(post_delete, sender=Badge)
@receiver(post_save, sender=BadgeGrant)
@receiver(post_delete, sender=BadgeGrant)
def _clear_badge_cache(sender, **kwargs):
    """Keep the cached badge table honest.

    Every page that draws a username reads that cache, so a stale entry is
    visible everywhere at once — cheap to rebuild, and rebuilt on any write.
    """
    invalidate_granted_badges()


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

    # Both tables are pinned to their original names. This model moved from the
    # `core` app to `accounts`, and the whole point is that no table is renamed
    # and no row is copied — 2,803 profiles stay exactly where they are.
    history = HistoricalRecords(table_name="core_historicaluserprofile")

    class Meta:
        db_table = "core_userprofile"
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
    def granted_badges(self) -> list[BadgeDef]:
        """Badges this user holds because somebody granted them one.

        Two sources, both read from the cached badge table rather than the
        database: the grants naming this person, and the grants naming
        everybody. Grants are looked up by ``badge_id`` so this needs no join —
        call sites rendering many users must ``prefetch_related`` the grants,
        or this costs a query per user.
        """
        badges = granted_badges_by_id()
        held = {grant.badge_id for grant in self.user.badge_grants.all()}
        held.update(everyone_badge_ids())
        return [badges[badge_id] for badge_id in held if badge_id in badges]

    @property
    def available_badges(self) -> list[BadgeDef]:
        """Every badge the user may display.

        Three sources: the Patreon tiers they have unlocked, the staff badge if
        they are staff, and anything granted to them or to everybody. Staff is
        just another badge here (opt-out, shown by default like the Patreon
        ones), gated on ``User.is_staff`` so it retracts automatically when
        staff access is removed.
        """
        badges = list(self.unlocked_badges)
        if self.user.is_staff:
            badges.append(STAFF_BADGE)
        badges.extend(self.granted_badges)
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
          Patreon tier instead). A badge that does not show automatically can
          still be picked; choosing it is the whole point of it being there.
        * Otherwise (no choice, or a stale selection) → the highest-ranked
          available badge that shows automatically. Staff outranks the Patreon
          tiers, which outrank granted badges, so a supporter who is also a
          playtester keeps showing their supporter badge.
        * If nothing available shows automatically → nothing. Somebody whose
          only badge is opt-in has not opted in yet.
        """
        available = self.available_badges
        if not available:
            return None
        if self.selected_badge == HIDE_BADGE:
            return None
        if self.selected_badge in self.eligible_badge_slugs:
            return badge_by_slug(self.selected_badge)
        automatic = [badge for badge in available if badge.auto_display]
        if not automatic:
            return None
        # Select by rank rather than list position so it doesn't depend on
        # registry ordering.
        return max(automatic, key=lambda b: b.rank)
