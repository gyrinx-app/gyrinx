"""Print configs — what one print run of a gang includes.

A config names a selection over the gang: which models get a card, which
of each model's weapons show, and whether the gang header, the stash,
and the notes strip (notes, picture, space to write) print at all. It is
display state only, like ``AssignmentSet``: it moves no money, changes no
rating and does not go through ``n26.operations``.

Selections are literal: a config prints exactly what was ticked, and
nothing acquired later joins it. A model hired after a config was saved
is not on it until someone reopens the config and ticks the model. This
is deliberate, so a saved config never changes as the gang changes.

Each gang has at most one unnamed config: the scratch config, rewritten
by every ad-hoc print so unsaved prints do not accumulate. Naming it saves
it; the same row then appears in the saved list.
"""

from django.db import models
from django.db.models.functions import Lower

from n26.core.models.abstract import Base


class PrintConfig(Base):
    class Orientation(models.TextChoices):
        PORTRAIT = "portrait", "Portrait"
        LANDSCAPE = "landscape", "Landscape"

    gang = models.ForeignKey(
        "n26.Gang", on_delete=models.CASCADE, related_name="print_configs"
    )
    name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            "Blank is the gang's scratch config — the one ad-hoc prints "
            "rewrite. Named configs are the saved list."
        ),
    )
    include_header = models.BooleanField(
        default=True, help_text="Print the gang's own header block."
    )
    include_stash = models.BooleanField(
        default=True, help_text="Print the stash listing."
    )
    include_notes = models.BooleanField(
        default=True,
        help_text=(
            "Print the gang's notes, and on each model card its notes, "
            "picture, and space to write during a game."
        ),
    )
    #: Phones lay print out at their screen width and ignore the
    #: orientation picked in the print dialog, so the sheet is sized for
    #: this one before the dialog opens.
    orientation = models.CharField(
        max_length=20,
        choices=Orientation,
        default=Orientation.PORTRAIT,
        help_text="Which way round the paper goes. Landscape prints three cards across.",
    )
    miniatures = models.ManyToManyField(
        "n26.Miniature",
        blank=True,
        related_name="print_configs",
        help_text="The models that get a card on this print.",
    )
    #: Ticked weapon assignments across every model on the config. Only
    #: weapons are selectable; wargear, skills and everything else always
    #: print.
    assignments = models.ManyToManyField(
        "n26.Assignment",
        blank=True,
        related_name="print_configs",
        help_text="The weapons shown on this print's cards.",
    )

    class Meta:
        verbose_name = "print config"
        verbose_name_plural = "print configs"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "gang", Lower("name"), name="print_config_unique_per_gang"
            ),
        ]

    def __str__(self):
        return f"{self.name or '(unsaved)'} ({self.gang})"

    @property
    def is_scratch(self):
        return self.name == ""
