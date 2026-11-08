"""Save a gang's selected models, weapons and optional print sections.

Print configs are display state: they change no money or rating and use
plain saves rather than operations. Stored selections do not automatically
include later acquisitions or hires.

Each gang has at most one unnamed scratch config, reused by ad-hoc prints.
Naming it preserves the same row as a saved config.
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
