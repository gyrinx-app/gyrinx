"""One committed hire and the input needed to recognise its retries."""

from django.db import models

from n26.core.models.abstract import Base


class HireReceipt(Base):
    gang = models.ForeignKey(
        "n26.Gang", on_delete=models.CASCADE, related_name="hire_receipts"
    )
    actor = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    request_key = models.UUIDField(editable=False)
    payload = models.JSONField()
    # Preserve the result after removal of the model or its library profile.
    miniature_key = models.CharField(max_length=26, editable=False)
    model_name = models.CharField(max_length=200)
    profile_name = models.CharField(max_length=200)
    paid = models.IntegerField(null=True)
    written = models.JSONField(default=list)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["gang", "request_key"], name="hire_receipt_request_once"
            )
        ]
