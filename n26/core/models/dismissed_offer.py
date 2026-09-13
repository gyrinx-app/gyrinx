"""Dismissed offers — the open choices a gang's owner has put out of sight.

An offer is not a stored row. It is a slot computed from a modifier or a
profile while its carrier stands (``n26.core.effects``), and only what
was chosen for it is ever written. A player who knows they will never
choose for one — a Choose they scroll past on every visit — has nothing
to delete, so this row is what stands in: the slot's address, which
every renderer of the gang then leaves out.

Per gang, everywhere. A dismissed offer is gone from the owner's screens,
the sheet anyone reads and the printed roster alike, because the sheet
is one document and a Choose the owner has waved away is not a fact
about the gang. It is display state, like ``PrintConfig``: it moves no
money, changes no rating and never goes through ``n26.operations``. Only
an offer with nothing chosen for it can be dismissed; one holding a pick
draws that pick and offers no way to hide it.

The key is the slot's address as ``n26.core.render._slot_key`` writes
it — the card it sits on, the assignment carrying the offer, the offer
itself — and is only as durable as those rows. Re-buying the carrier or
re-authoring the offer brings the Choose back, which is the right way
round: the row hides one offer, never a kind of offer. A carrier that is
sold leaves its row behind, keyed to nothing; a stale row hides nothing.
"""

from django.db import models

from n26.core.models.abstract import Base

#: What a gang's own choice slots are addressed under, where a model's are
#: addressed under the model's id. A ULID is never this word, so the two
#: kinds of host cannot collide in a slot key.
GANG_SLOT_HOST = "gang"


def slot_key(host, anchor_pk, identity_pk):
    """One slot's address: the card it is drawn on (a model's id, or the
    gang's own word), the assignment carrying the offer, and the offer or
    slot itself. The one place the shape is written, so the renderer that
    draws a slot and the operation that settles one cannot disagree."""
    return f"{host}:{anchor_pk}:{identity_pk}"


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
    def clear(cls, gang, *, host, anchor, identity):
        """Take off any dismissal of one slot, because a pick has landed
        on it: the owner has changed their mind, and taking that pick back
        later should leave the offer open rather than hide it again."""
        cls.objects.filter(
            gang=gang, slot_key=slot_key(host, anchor.pk, identity.pk)
        ).delete()

    @classmethod
    def keys_for(cls, gang):
        """Every slot address this gang's owner has dismissed — one query,
        whatever the roster's size."""
        return frozenset(
            cls.objects.filter(gang=gang).values_list("slot_key", flat=True)
        )
