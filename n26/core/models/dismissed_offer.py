"""Store display dismissals by the key of a computed choice.

A dismissal applies to owner pages, shared sheets and printed rosters.
It changes no money or rating and uses plain saves rather than operations.
Only choices without picks that permit dismissal can be hidden; renderers ignore
stored dismissals when the choice disallows them.

Keys include the host, stored anchor and authored choice identity, optionally
scoped to a status transition. Replacing a carrier changes its anchor key,
so a previous dismissal does not hide the new choice.
"""

from django.db import models

from n26.core.models.abstract import Base

#: What a gang's own choice slots are addressed under, where a model's are
#: addressed under the model's id. A ULID is never this word, so the two
#: kinds of host cannot collide in a slot key.
GANG_SLOT_HOST = "gang"
HOLDING_SLOT_HOST = "holding"


def holding_slot_key(holding, identity_pk):
    """A holding's choice in one ownership period."""
    return (
        f"{HOLDING_SLOT_HOST}:{holding.pk}@{holding.ownership_revision}:{identity_pk}"
    )


def identity_key(identity_pk, status_revision=None):
    """An authored choice, optionally scoped to one status transition."""
    return (
        f"{identity_pk}:{status_revision}"
        if status_revision is not None
        else str(identity_pk)
    )


def slot_key(host, anchor_pk, identity_pk, status_revision=None):
    """Build a shared choice key from its host, stored anchor and authored identity.

    Include a status revision when the choice belongs to one status transition.
    """
    return f"{host}:{anchor_pk}:{identity_key(identity_pk, status_revision)}"


class DismissedOffer(Base):
    gang = models.ForeignKey(
        "n26.Gang", on_delete=models.CASCADE, related_name="dismissed_offers"
    )
    slot_key = models.CharField(
        max_length=200,
        help_text=(
            "The slot's address: the card it is drawn on, the assignment "
            "carrying the choice, and the choice itself."
        ),
    )

    class Meta:
        verbose_name = "dismissed choice"
        verbose_name_plural = "dismissed choices"
        constraints = [
            models.UniqueConstraint(
                fields=["gang", "slot_key"], name="dismissed_offer_unique_per_gang"
            ),
        ]

    def __str__(self):
        return f"{self.slot_key} ({self.gang})"

    @classmethod
    def clear(cls, gang, *, host, anchor, identity, status_revision=None):
        """Clear a choice's dismissal when selecting a pick so later removal exposes the choice again."""
        cls.objects.filter(
            gang=gang, slot_key=slot_key(host, anchor.pk, identity.pk, status_revision)
        ).delete()

    @classmethod
    def keys_for(cls, gang):
        return frozenset(
            cls.objects.filter(gang=gang).values_list("slot_key", flat=True)
        )
