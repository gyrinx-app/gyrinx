from django.core.cache import cache
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.base_models import AppBase


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
        help_text="Bootstrap icon class (e.g., 'bi-info-circle')",
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
    is_live = models.BooleanField(
        default=False,
        help_text="Whether this banner is currently live. Only one banner can be live at a time.",
    )

    # History tracking
    history = HistoricalRecords(table_name="core_historicalbanner")

    class Meta:
        db_table = "core_banner"
        ordering = ["-modified"]
        verbose_name = "Banner"
        verbose_name_plural = "Banners"

    def __str__(self):
        status = "LIVE" if self.is_live else "Draft"
        return f"[{status}] {self.text[:50]}..."

    def save(self, *args, **kwargs):
        # If this banner is being set to live, turn off all other live banners
        if self.is_live:
            Banner.objects.filter(is_live=True).exclude(pk=self.pk).update(
                is_live=False
            )
        super().save(*args, **kwargs)
        # Clear the banner cache when any banner is saved
        from n23.core.context_processors import BANNER_CACHE_KEY

        cache.delete(BANNER_CACHE_KEY)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        # Clear the banner cache when any banner is deleted
        from n23.core.context_processors import BANNER_CACHE_KEY

        cache.delete(BANNER_CACHE_KEY)

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
