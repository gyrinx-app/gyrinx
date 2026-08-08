from django.db import models

from n26.core.models.abstract import Archived, Base, Owned, Rated


class Gang(Base, Owned, Archived, Rated):
    """A player's gang."""

    name = models.CharField(max_length=200)
    gang_type = models.ForeignKey(
        "library.GangType", on_delete=models.PROTECT, related_name="gangs"
    )
    founding = models.OneToOneField(
        "n26.Assignment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="founded",
        help_text=(
            "The gang-hosted assignment naming this gang's type — what a "
            "membership is to a model. Carries the gang's built-ins and "
            "its gang-wide modifiers."
        ),
    )
    starting_credits = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "The budget, where one applies. Null means unlimited — the "
            "founding default: players buy what they own and the gang "
            "shows its rating. A ceiling is a campaign's choice, and only "
            "then is overspend refused."
        ),
    )
    credits = models.PositiveIntegerField(
        default=0,
        help_text="Cash in hand. Pinned: starting budget less everything spent.",
    )
    colour = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Shown against the gang wherever it is listed.",
    )

    class Meta:
        verbose_name = "gang"
        verbose_name_plural = "gangs"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def recompute_rating(self):
        """Everything the gang owns, at any depth.

        Excludes archived assignments — a sold weapon stops counting, while
        its ledger entry stays a true statement of what it was worth.
        """
        from n26.core.reconcile import sum_rating

        # The stash is excluded: rating is what the models are worth;
        # stashed gear counts in wealth instead.
        return sum_rating(gang_root=self, stash_root__isnull=True)

    def recompute_credits(self):
        """The budget less everything spent — or None where no budget is.

        With no budget there is nothing to count down from: purchases are
        honest ledger lines and the gang's number is its rating.
        """
        from n26.core.reconcile import total_spent

        if self.starting_credits is None:
            return None
        return self.starting_credits - total_spent(self)

    def repin_credits(self):
        remaining = self.recompute_credits()
        self.credits = remaining if remaining is not None else 0
        self.save(update_fields=["credits", "modified"])
        return self.credits

    @property
    def stash_rating(self):
        """What the stash holds, or 0 before one exists. Column reads."""
        stash = getattr(self, "stash", None)
        return stash.rating if stash else 0

    @property
    def wealth(self):
        """Rating, plus cash, plus what the stash holds. Column reads."""
        return self.rating + self.credits + self.stash_rating
