from django.db import models

from n26.core.models.abstract import Base, Owned, Rated


class Miniature(Base, Owned, Rated):
    """A single model in a gang.

    Called "Model" throughout the UI; ``Miniature`` in code only to keep clear
    of ``django.db.models.Model``.

    Being in a gang is itself an assignment — ``membership`` points at the
    gang-hosted assignment whose assignable is the model's primary profile.
    """

    name = models.CharField(max_length=200)
    #: What a card shows only when the model keeps no XP counter. Where
    #: there is one, its value is the number and ``tally`` is what moves it.
    xp = models.PositiveIntegerField(default=0)
    xp_target = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "XP needed for the next advancement. Should come from the Model "
            "Ranks table once ranks are modelled."
        ),
    )
    #: The owner's own words about this model — kit reminders, table
    #: agreements, standing injuries. Editor HTML, stored as written and
    #: sanitised on the way out (n26.core.templatetags.richtext), so a
    #: tightened allowlist reaches what was already saved.
    notes = models.TextField(blank=True, default="")
    #: The model's story, in the owner's words. Editor HTML handled as
    #: ``notes`` is: stored as written, sanitised on the way out.
    lore = models.TextField(blank=True, default="")
    #: A picture of the painted model, in the site's media storage.
    #: Surfaces read its URL and never the bytes.
    image = models.ImageField(upload_to="model-images/", blank=True, default="")
    membership = models.OneToOneField(
        "n26.Assignment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="member",
        help_text="The gang-hosted assignment that brought this model in.",
    )

    class Meta:
        verbose_name = "model"
        verbose_name_plural = "models"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def gang(self):
        return self.membership.gang if self.membership else None

    @property
    def owned_by(self):
        """The model whose purchase brought this one in — a pet's owner.

        Derived, not stored: the fact already exists in the graph, so there
        is no second copy to drift.
        """
        cause = self.membership.caused_by if self.membership else None
        return cause.miniature_root if cause else None

    def recompute_rating(self):
        """What this model is worth: the hire, plus everything on it."""
        from n26.core.reconcile import sum_rating

        return sum_rating(miniature_root=self)
