from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.core.models.base import AppBase


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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # History tracking
    history = HistoricalRecords()

    class Meta:
        ordering = ["-updated_at"]
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

    def clean(self):
        super().clean()
        # Ensure CTA text is provided if CTA URL is provided
        if self.cta_url and not self.cta_text:
            raise models.ValidationError(
                {"cta_text": "CTA text is required when CTA URL is provided."}
            )
