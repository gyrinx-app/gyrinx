from django.db import models

from n26.core.models.abstract import Base, Owned, Rated
from n26.core.status import Status


class Miniature(Base, Owned, Rated):
    """A single model in a gang.

    Called "Model" throughout the UI; ``Miniature`` in code only to keep
    clear of ``django.db.models.Model``.

    Being in a gang is itself an assignment — ``membership`` points at the
    gang-hosted assignment whose assignable is the model's primary profile.
    """

    name = models.CharField(max_length=200)
    #: The model's status between battles. Written only by
    #: ``Operation.set_status``, which journals every change. A dead model
    #: keeps its row and card and adds nothing to rating; removing a model
    #: from the roster archives its membership instead.
    status = models.CharField(max_length=12, choices=Status, default=Status.ACTIVE)
    status_revision = models.PositiveIntegerField(default=0)
    #: Shown on the card only when the model has no XP counter. Otherwise
    #: the counter's value is shown and ``tally`` changes it.
    xp = models.PositiveIntegerField(default=0)
    xp_target = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "XP needed for the next advancement. Should come from the Model "
            "Ranks table once ranks are modelled."
        ),
    )
    #: Store editor HTML unchanged and sanitise through the richtext filter
    #: when rendering, so allowlist updates also apply to saved content.
    notes = models.TextField(blank=True, default="")
    #: The model's story. Same treatment as notes.
    lore = models.TextField(blank=True, default="")
    #: Read the uploaded model image through its URL.
    image = models.ImageField(upload_to="model-images/", blank=True, default="")
    #: The gang-hosted membership assignment links the model to its gang. Deleting that
    #: assignment cascades to the model; roster removal archives it instead.
    #: A nullable membership also permits unhosted models. Hire and clone create
    #: the membership first, then create the model pointing to it.
    membership = models.OneToOneField(
        "n26.Assignment",
        on_delete=models.CASCADE,
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
        """Return the owning model from the membership's cause, or None.

        Derive this relationship so moving the granting purchase changes the owner
        without updating a second stored relationship.
        """
        cause = self.membership.caused_by if self.membership else None
        return cause.miniature_root if cause else None

    def recompute_rating(self):
        """What this model is worth: the hire, plus everything on it."""
        from n26.core.reconcile import sum_rating

        return sum_rating(miniature_root=self)
