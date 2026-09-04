"""Campaign types and their assets — what a campaign is founded on.

A **campaign type** is to a campaign what a gang type is to a gang: the
authored thing it is founded on. It holds a built-in set (what every
member gang gets), campaign-wide modifiers, its **asset kinds**, and the
**assets** it offers (the catalogue). Shared types live in the system
pack; an arbitrator's additions to one campaign live in that campaign's
own pack as a second type layered on top. See design/campaign-assets.md.

An **asset kind** is a row on the type with a label and a mode. The mode
is on the kind rather than the asset because it is a whole class of
asset that behaves one way: a Settlement is given to every gang on
joining and never staked; a Territory is a token in the campaign's pool
with one holder at a time.

An **asset** is one thing of one kind. It is assignable so that a
held-one-each asset can be a built-in member and so that either mode
can carry modifiers for what holding it does. A pooled asset is never
assigned; the campaign's token records who holds it.
"""

from django.db import models
from django.db.models.functions import Lower

from n26.library.models.assignable import (
    Assignable,
    Family,
    exclusive_has_no_trade_points,
)
from n26.library.models.base import Content


class CampaignType(Content, Assignable):
    """A kind of campaign — Dominion, Law & Misrule — assigned to every
    gang that joins a campaign founded on it.

    Assignable for the same reason a gang type is: joining a campaign is a
    gang-hosted assignment naming its type. That gives the built-ins every
    member gang arrives with — a Reputation counter, a Settlement —
    something to be caused by, and gives campaign-wide modifiers a carrier
    every member's card can find.

    It also declares its **asset kinds** — Territory, Racket, Settlement —
    and lists the **assets** it offers. Its pricing fields stay at zero;
    nobody buys a campaign type.
    """

    family = Family.GANG

    assets = models.ManyToManyField(
        "library.Asset",
        blank=True,
        related_name="offered_by",
        help_text=(
            "The assets a campaign of this type can hand out. An asset can "
            "be offered by several campaign types."
        ),
    )

    class Meta:
        verbose_name = "campaign type"
        verbose_name_plural = "campaign types"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="campaign_type_unique_per_pack",
            ),
            exclusive_has_no_trade_points("campaign_type"),
        ]

    def __str__(self):
        return self.name


class AssetKind(Content):
    """A class of asset a campaign type deals in — Territory, Racket,
    Settlement — with the label a campaign page prints and the mode that
    fixes how every asset of the kind behaves.

    **Held one each** means every gang is given one when it joins and it
    is never staked: a Settlement, a home territory. **Pooled** means the
    campaign holds a pool of them and each one has one holder at a time:
    a Territory, a Racket, a Relic.
    """

    class Mode(models.TextChoices):
        #: Given to every gang on joining, never staked.
        HELD_ONE_EACH = "held-one-each", "Held one each"
        #: A token in the campaign's pool, one holder at a time.
        POOLED = "pooled", "Pooled"

    campaign_type = models.ForeignKey(
        CampaignType, on_delete=models.CASCADE, related_name="asset_kinds"
    )
    label_singular = models.CharField(
        max_length=200,
        verbose_name="Label",
        help_text='What one of these is called, e.g. "Territory".',
    )
    label_plural = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Plural label",
        help_text=(
            'What several of them are called, e.g. "Territories". Leave blank '
            "and an s is added."
        ),
    )
    mode = models.CharField(
        max_length=20,
        choices=Mode,
        help_text=(
            "Held one each: every gang is given one when it joins, and it is "
            "never staked. Pooled: the campaign holds a pool of them, and "
            "each has one holder at a time."
        ),
    )
    position = models.PositiveIntegerField(
        default=0,
        help_text="Where this kind sits in the campaign's listing.",
    )

    class Meta:
        verbose_name = "asset kind"
        verbose_name_plural = "asset kinds"
        # The id rather than the relation: ordering by the relation would
        # join the type and sort by its own ordering on every read.
        ordering = ["campaign_type_id", "position", "label_singular"]
        constraints = [
            models.UniqueConstraint(
                "campaign_type",
                Lower("label_singular"),
                name="asset_kind_unique_label_per_type",
            ),
        ]

    def __str__(self):
        return self.label_singular

    @property
    def plural(self):
        """Several of them, as a surface should say it."""
        return self.label_plural or f"{self.label_singular}s"

    @property
    def is_pooled(self):
        return self.mode == self.Mode.POOLED

    @property
    def authoring_label(self):
        """The label with the type it belongs to, for a picker that offers
        every campaign type's kinds at once."""
        return f"{self.label_singular} ({self.campaign_type})"


class Asset(Content, Assignable):
    """One thing a campaign deals in — a Settlement, the Old Ruins
    territory, a Racket — of one asset kind.

    Its **income** is a figure drawn on the card; nothing collects it.
    What holding it does for the holder rides it as ordinary modifiers.

    Assignable so that an asset of a held-one-each kind can be built into
    its campaign type and arrive on every member gang, and so that an
    asset of either kind can carry modifiers. A pooled asset is never
    assigned: the campaign's token records who holds it.
    """

    family = Family.BASE

    kind = models.ForeignKey(
        AssetKind,
        on_delete=models.PROTECT,
        related_name="assets",
        help_text="Which asset kind this is. A kind belongs to one campaign type.",
    )
    income = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Credits this asset brings its holder each cycle, as printed on "
            "the card. Shown, never collected."
        ),
    )

    class Meta:
        verbose_name = "asset"
        verbose_name_plural = "assets"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="asset_unique_per_pack",
            ),
            exclusive_has_no_trade_points("asset"),
        ]

    @property
    def campaign_type(self):
        """The type whose asset kind this belongs to."""
        return self.kind.campaign_type
