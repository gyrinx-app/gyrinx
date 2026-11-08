"""An equipment command's settled write or confirmation decision."""

from django.db import models

from n26.core.models.abstract import Base


class EquipReceipt(Base):
    gang = models.ForeignKey(
        "n26.Gang", on_delete=models.CASCADE, related_name="equip_receipts"
    )
    actor = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    request_key = models.UUIDField(editable=False)
    payload = models.JSONField()
    result = models.JSONField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["gang", "request_key"], name="equip_receipt_request_once"
            )
        ]
