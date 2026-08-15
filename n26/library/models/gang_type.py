from django.db import models
from django.db.models.functions import Lower

from n26.library.artwork import read as read_artwork
from n26.library.models.assignable import (
    Assignable,
    Family,
    exclusive_has_no_trade_points,
)
from n26.library.models.base import Content


class GangType(Content, Assignable):
    """A kind of gang — Escher, Ironhead Squats — assigned to the gang at
    founding.

    Assignable, for the same reason a profile is: **founding a gang is a
    gang-hosted assignment naming its type**, exactly as hiring a model is
    a gang-hosted assignment naming its profile. That gives the gang's
    built-ins something to be caused by, gives its house list a source to
    report, and — the point — gives its gang-wide ``modifiers`` a carrier
    that every member's card can find.

    What it carries is mostly *overrides and extras*, because most of what
    a gang list prints belongs elsewhere: the fighter entries are
    profiles, and each entry's skill access rides that profile as
    ``PlacesCategory`` modifiers. See design/gang-type.md.

    ``name`` comes from the mixin, as do the pricing fields — which stay
    at zero here, since nobody buys a gang type.
    """

    family = Family.GANG

    # The drawing is a file in the site's own storage and the row keeps its
    # address, so a badge can be uploaded here or pointed at where it already
    # sits. Drawn inline rather than as an image, which is what lets it take
    # the colour of the text beside it — and that means the server reads the
    # bytes, so an address is only ever resolved against this site's storage
    # and never fetched from wherever it points (library/artwork.py).
    icon_url = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text=(
            "Address of the SVG drawn beside this gang type's name wherever "
            "the gang is listed. Upload a drawing to fill this in, or paste "
            "the address of one already uploaded. Draw it in one colour and "
            "it will follow the surrounding text. Leave blank and nothing is "
            "drawn."
        ),
    )

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

    # Turning this off narrows one screen and nothing else. A gang founded
    # before the switch was thrown keeps its type, keeps its house list, and
    # goes on being drawn everywhere it was drawn before.
    foundable = models.BooleanField(
        default=True,
        help_text=(
            "Whether a player may create a gang of this type. Turn it off for "
            "a type that exists to be hired from or fought against rather "
            "than played, and it stops being offered when someone creates a "
            "gang. Gangs that are already this type are unaffected."
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

    @property
    def artwork(self):
        """The badge's SVG source, for a surface to clean and draw inline.

        The one accessor every surface reads, so none of them has to know
        that an address is involved. Empty for a type with no badge and for
        one whose address no longer names anything — both draw as nothing at
        all rather than as a gap in a column of names.
        """
        return read_artwork(self.icon_url)
