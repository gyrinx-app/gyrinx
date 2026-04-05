from django.conf import settings
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

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
