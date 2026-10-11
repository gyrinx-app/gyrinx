"""Dismissed offers: open choices a gang's owner has hidden.

An offer is not stored. It is a slot computed from a modifier or a
profile while its carrier exists (``n26.core.effects``); only the pick is
written. A ``DismissedOffer`` stores the slot's key, and every renderer of
the gang skips slots with a stored key.

A dismissal applies across the gang: the owner's pages, the shared sheet
and the printed roster. It is display state, like ``PrintConfig``: it moves
no money, changes no rating and does not go through ``n26.operations``.
Only an offer with no pick can be dismissed. An offer with a pick shows the
pick and has no hide control.

The key comes from ``slot_key`` below: the card, the assignment carrying
the offer, and the offer itself. It matches only while those rows exist,
so re-buying the carrier or re-authoring the offer shows the choice again.
Selling the carrier leaves a dismissal that matches no slot and has no effect.
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
    """One slot's key: the card it is drawn on (a model's id, or
    ``GANG_SLOT_HOST``), the assignment carrying the offer, and the offer or
    slot itself. The renderer and the operations both build keys here, so
    the keys they write always match."""
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
        """Delete any dismissal of one slot when a pick fills it, so that
        removing the pick later shows the offer again instead of hiding it."""
        cls.objects.filter(
            gang=gang, slot_key=slot_key(host, anchor.pk, identity.pk, status_revision)
        ).delete()

    @classmethod
    def keys_for(cls, gang):
        return frozenset(
            cls.objects.filter(gang=gang).values_list("slot_key", flat=True)
        )
