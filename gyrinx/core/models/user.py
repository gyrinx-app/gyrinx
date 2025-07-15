from django.contrib.auth.models import User
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.content.models import ContentBadge

from .base import AppBase


class CoreUserBadgeAssignment(AppBase):
    """Assignment of badges to users."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="badge_assignments"
    )
    badge = models.ForeignKey(ContentBadge, on_delete=models.CASCADE)
    is_active = models.BooleanField(
        default=False,
        help_text="Only one badge can be active at a time for inline display.",
    )

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.user.username} - {self.badge.name}"

    def save(self, *args, **kwargs):
        # If this badge is being set as active, deactivate all others for this user
        if self.is_active:
            self.__class__.objects.filter(user=self.user, is_active=True).exclude(
                pk=self.pk
            ).update(is_active=False)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "User Badge Assignment"
        verbose_name_plural = "User Badge Assignments"
        unique_together = ["user", "badge"]
        ordering = ["created"]
