"""Print configs — what one print run of a gang includes.

A config names a selection over the gang: which models get a card, which
of each model's weapons show, and whether the gang header and the stash
print at all. It is the print screen's memory, nothing more — pure
display state, like ``AssignmentSet``, so it costs nothing, changes no
rating and never goes through ``n26.operations``.

Selections are literal: a config prints exactly what was ticked, and
nothing joins it by being acquired later. A model hired after a config
was saved is not on it until someone reopens the config and ticks them —
predictable staleness, over a config whose meaning shifts under it.

One config per gang has no name — the scratch config, rewritten by every
ad-hoc print so unnamed runs never pile up as rows. Giving it a name is
what saves it: the same row, now listed with the others.
"""

from django.db import models
from django.db.models.functions import Lower

from n26.core.models.abstract import Base


class PrintConfig(Base):
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
    miniatures = models.ManyToManyField(
        "n26.Miniature",
        blank=True,
        related_name="print_configs",
        help_text="The models that get a card on this print.",
    )
    #: Ticked weapons, across every model on the config. Weapons only:
    #: wargear, skills and the rest always ride a printed card, the same
    #: split ``AssignmentSet`` draws — this is about which guns clutter
    #: the table, not about what the model owns.
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
