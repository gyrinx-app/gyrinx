from django.db import models
from django.db.models.functions import Lower

from n26.library.models.assignable import (
    Assignable,
    Family,
    exclusive_has_no_trade_points,
)
from n26.library.models.base import Content


class GangType(Content, Assignable):
    """A kind of gang, e.g. Escher or Ironhead Squat Prospectors.

    Assignable, for the same reason a profile is: **founding a gang is a
    gang-hosted assignment naming its type**, exactly as hiring a model is
    a gang-hosted assignment naming its profile. That gives the gang's
    built-ins something to be caused by, gives its house list a source to
    report, and — the point — gives its gang-wide ``modifiers`` a carrier
    that every member's card can find.

    What it carries is mostly *overrides and extras*, because most of what
    a gang list prints belongs elsewhere: the fighter entries are
    ``Profile`` rows, and each entry's skill access is ``PlacesCategory``
    modifiers on that profile. See design/gang-type.md.

    ``name`` comes from the mixin, as do the pricing fields — which stay
    at zero here, since nobody buys a gang type.
    """

    family = Family.GANG

    starting_credits = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Founding budget for gangs of this type. Blank uses the game "
            "default: the budget is generally the same for everyone, it may "
            "be varied per gang, and a gang list stating its own is the "
            "exception."
        ),
    )

    class Meta:
        verbose_name = "gang type"
        verbose_name_plural = "gang types"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="gang_type_unique_per_pack",
            ),
            exclusive_has_no_trade_points("gang_type"),
        ]

    def __str__(self):
        return self.name
