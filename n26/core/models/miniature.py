from django.db import models

from n26.core.models.abstract import Base, Owned, Rated
from n26.core.status import Status


class Miniature(Base, Owned, Rated):
    """A single model in a gang.

    Called "Model" throughout the UI; ``Miniature`` in code only to keep clear
    of ``django.db.models.Model``.

    Being in a gang is itself an assignment — ``membership`` points at the
    gang-hosted assignment whose assignable is the model's primary profile.
    """

    name = models.CharField(max_length=200)
    #: Where the model stands between battles — the roster's In Recovery
    #: box and the states a lasting effect leaves a model in. Stored, as
    #: the roster stores it, and written only by ``Operation.set_status``,
    #: which journals every change: a result's effect sets it when the
    #: pick lands, Clean House clears Recovery, and the owner may set it by
    #: hand. A dead model keeps its row and its card and counts nothing
    #: towards rating; leaving the roster is still the membership's
    #: archive.
    status = models.CharField(max_length=12, choices=Status, default=Status.ACTIVE)
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
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="member",
        help_text="The gang-hosted assignment that brought this model in.",
    )
    """The gang-hosted assignment that brought this model in.

    ``CASCADE`` because a model with no gang is unreachable: every route
    to one goes through its gang, so a model outliving its membership is
    a row nothing can show, edit or delete. A model standing on its own,
    independent of any gang, is a feature ``design/assignables.md``
    considered and dropped, so there is no state for such a row to be
    in.

    This is not how a model leaves a gang — that archives the membership
    (the roster reads ``membership__archived=False``) — so the cascade
    fires only when the assignment is genuinely deleted, which in
    practice means the gang was.

    Nullable because ``Operation.hire`` writes the model before
    attaching its membership; a null cascades from nothing.
    """

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
