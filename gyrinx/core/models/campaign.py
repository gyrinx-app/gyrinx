import logging

from django.core import validators
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.core.models.base import AppBase

logger = logging.getLogger(__name__)


class Campaign(AppBase):
    name = models.CharField(
        max_length=255, validators=[validators.MinLengthValidator(3)]
    )
    public = models.BooleanField(
        default=True, help_text="Public Campaigns are visible to all users."
    )
    summary = models.TextField(
        blank=True,
        validators=[validators.MaxLengthValidator(300)],
        help_text="A short summary of the campaign. This will be displayed on the campaign list page.",
    )
    narrative = models.TextField(
        blank=True,
        help_text="A longer narrative of the campaign. This will be displayed on the campaign detail page.",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Campaign"
        verbose_name_plural = "Campaigns"
        ordering = ["-created"]
