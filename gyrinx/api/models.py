from django.db import models

from gyrinx.models import Base


class WebhookRequest(Base):
    """
    Webhook is a URL that will receive POST requests when certain events occur.
    """

    source = models.CharField(max_length=150, blank=False, null=False)
    event = models.CharField(max_length=150, blank=True, null=False)
    payload = models.JSONField()
    signature = models.CharField(max_length=150, blank=True)

    class Meta:
        verbose_name = "webhook request"
        verbose_name_plural = "webhook requests"

    def __str__(self):
        return f"{self.source} - {self.event}"
