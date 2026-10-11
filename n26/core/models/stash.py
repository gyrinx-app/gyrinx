from django.db import models

from n26.core.models.abstract import Base, Rated


class Stash(Base, Rated):
    """An assignment host for a gang's stored equipment: storage, not a model.

    It has no name, XP or profile and is never drawn as a card. Its pinned
    rating is one term of the gang's wealth: stashed gear counts toward
    what the gang is worth, not toward its rating.
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
