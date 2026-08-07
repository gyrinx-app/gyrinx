from django.db import models

from n26.core.models.abstract import Base, Rated


class Stash(Base, Rated):
    """The gang's holding pen for surplus equipment.

    A fourth place an assignment can live — not a model: no name, no XP,
    no profile, never a card. Created at founding; fed by purchases and
    (later) the post-battle flows; drained by moving things onto models.
    Its pinned rating is Wealth's third term — stashed gear counts toward
    what a gang is worth, never toward its rating.

    v1 modelled this as a hidden fighter and regretted it; here the
    database itself knows the difference between a fighter and storage.
    """

    gang = models.OneToOneField(
        "n26.Gang", on_delete=models.CASCADE, related_name="stash"
    )

    class Meta:
        verbose_name = "stash"
        verbose_name_plural = "stashes"

    def __str__(self):
        return f"{self.gang.name}'s stash"

    def recompute_rating(self):
        from n26.core.reconcile import sum_rating

        return sum_rating(stash_root=self)
