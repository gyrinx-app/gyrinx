"""Presentation settings for actions whose execution is built into Gyrinx."""

from django.db import models

from n26.core.models import Base


class BuiltInAction(Base):
    """An action with a dedicated screen and configurable default visibility.

    Excluded gang types can still find the action under Other actions.
    An open action remains manageable when its gang type is excluded.
    """

    class Key(models.TextChoices):
        TRADING_POST_VISIT = "trading_post_visit", "Visit Trading Post"

    key = models.CharField(max_length=40, choices=Key, unique=True, editable=False)
    excluded_gang_types = models.ManyToManyField(
        "library.GangType",
        blank=True,
        related_name="excluded_built_in_actions",
        verbose_name="gang types excluded by default",
        help_text=(
            "Hide the usual setup links for these gang types. Owners can still "
            "use Other actions. Open visits remain manageable. Unselected and "
            "new gang types show the action normally."
        ),
    )

    def __str__(self):
        return self.get_key_display()
