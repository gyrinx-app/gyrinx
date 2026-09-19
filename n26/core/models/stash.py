from django.db import models

from n26.core.models.abstract import Base, Rated


class Stash(Base, Rated):
    """A fourth host an assignment can live on — storage, not a model.

    No name, no XP, no profile, never a card. Its pinned rating is
    wealth's third term: stashed gear counts toward what a gang is
    worth, never toward its rating.
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
