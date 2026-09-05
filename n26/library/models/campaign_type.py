"""Campaign types and their assets — what a campaign is founded on.

A **campaign type** is to a campaign what a gang type is to a gang: the
authored thing it is founded on. It holds a built-in set (what every
member gang gets), campaign-wide modifiers, and its **asset types**, each
of which lists the **assets** of that type. Shared types live in the
system pack; an arbitrator's own additions to one campaign live in that
campaign's own pack as a second campaign type layered on top. See
design/campaign-assets.md.

An **asset type** is a row on the campaign type with a label and an
ownership. The ownership is on the asset type rather than the asset
because a whole class of asset behaves one way: a Settlement is a
possession, given to every gang on joining and kept; a Territory is a
holding, kept by the campaign with one holder at a time.

An **asset** is one entry in a campaign type's list of what it hands
out, filed under one of the type's asset types — that is the whole of
how it belongs to the campaign type, and it is authored on the campaign
type's page. It is assignable so that a possession can be a built-in
member and so that either ownership can carry modifiers for what having
it does. A holding is never assigned; the campaign's own record of the
asset says who holds it.
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
    """A kind of campaign — Territory campaign, Dominion — assigned to every
    gang that joins a campaign founded on it.

    Assignable for the same reason a gang type is: joining a campaign is a
    gang-hosted assignment naming its type. That gives the built-ins every
    member gang arrives with — a Reputation counter, a Settlement —
    something to be caused by, and puts campaign-wide modifiers on every
    member's card.

    It also declares its **asset types** — Territory, Racket, Settlement —
    and under each asset type lists the **assets** a campaign of this type
    hands out. Its pricing fields stay at zero; nobody buys a campaign type.

    The **description** is the one field here written for a player: the
    arbitrator setting a campaign up reads it on the set-up screen. The
    library author help stays for content authors, as on every other kind.
    """

    family = Family.GANG

    description = models.TextField(
        blank=True,
        default="",
        help_text=(
            "What a campaign of this type is about, for the arbitrator "
            "setting one up: what the gangs fight over, what each starts "
            "with, how the campaign runs and how it ends. Shown on the "
            "set-up screen. Use your own words, not the book's."
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

    @property
    def assets(self):
        """Every asset this type hands out: the assets of its asset types.

        An asset belongs to one asset type and the asset type to one
        campaign type, so this is the whole relationship — there is no
        list on the campaign type to keep in step with it. Archived assets
        are included, as a plain read is; a surface offering new campaign
        assets narrows with ``unarchived()``.
        """
        return Asset.objects.filter(asset_type__campaign_type=self)

    def holding_assets(self):
        """The assets a campaign of this type keeps and hands between gangs:
        those of its asset types whose ownership is Holding. A possession
        is every member gang's own, and the campaign keeps none of it."""
        return self.assets.filter(asset_type__ownership=AssetType.Ownership.HOLDING)


class AssetType(Content):
    """A class of asset a campaign type has — Territory, Racket,
    Settlement — with the label a campaign page prints and the ownership
    that fixes how every asset of the type behaves.

    **Possession** means every gang has its own: a
    Settlement, a home territory. **Holding** means one gang holds it at a
    time, and it can change hands: a Territory, a Racket, a Relic.
    """

    class Ownership(models.TextChoices):
        #: Every gang has its own.
        POSSESSION = "held-one-each", "Possession"
        #: One gang holds it at a time, and it can change hands.
        HOLDING = "pooled", "Holding"

    campaign_type = models.ForeignKey(
        CampaignType, on_delete=models.CASCADE, related_name="asset_types"
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
    ownership = models.CharField(
        max_length=20,
        choices=Ownership,
        verbose_name="Ownership",
        help_text=(
            "Possession: every gang has its own. Holding: one "
            "gang holds it at a time, and it can change hands."
        ),
    )
    position = models.PositiveIntegerField(
        default=0,
        help_text="Where this asset type sits in the campaign's listing.",
    )

    class Meta:
        verbose_name = "asset type"
        verbose_name_plural = "asset types"
        # The id rather than the relation: ordering by the relation would
        # join the campaign type and sort by its own ordering on every read.
        ordering = ["campaign_type_id", "position", "label_singular"]
        constraints = [
            models.UniqueConstraint(
                "campaign_type",
                Lower("label_singular"),
                name="asset_type_unique_label_per_campaign_type",
            ),
        ]

    def __str__(self):
        return self.label_singular

    @property
    def plural(self):
        """Several of them, as a surface should say it."""
        return self.label_plural or f"{self.label_singular}s"

    @property
    def is_holding(self):
        return self.ownership == self.Ownership.HOLDING

    @property
    def authoring_label(self):
        """The label with the campaign type it belongs to, for a picker that
        offers every campaign type's asset types at once."""
        return f"{self.label_singular} ({self.campaign_type})"


class Asset(Content, Assignable):
    """One thing a campaign has — a Settlement, the Old Ruins
    territory, a Racket — of one asset type.

    An asset is one entry in the list of what its campaign type hands
    out, and is added on that campaign type's page under its asset type.
    What having it does for the gang rides it as ordinary modifiers. Its
    **income** is one of them: a contribution to the system Income counter
    (``n26.library.income``), so a gang's Income reads as the sum of what
    it holds. Nothing collects that reading yet.

    Assignable so that a possession can be built into its campaign type
    and arrive on every member gang, and so that an asset of either
    ownership can carry modifiers. A holding is never assigned: the
    campaign's own record of the asset says who holds it.
    """

    family = Family.BASE

    asset_type = models.ForeignKey(
        AssetType,
        on_delete=models.PROTECT,
        related_name="assets",
        verbose_name="Asset type",
        help_text=(
            "Which asset type this asset is one of. Settled when the asset is "
            "made on its campaign type's page, and never changed afterwards."
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
        """The campaign type whose asset type this belongs to."""
        return self.asset_type.campaign_type

    @property
    def income(self):
        """What this brings its holder each cycle, read off its Income
        contribution. A query unless the modifiers are prefetched; a page
        listing many assets reads them through ``income.income_of`` with
        the modifiers it already holds."""
        from n26.library.income import income_of

        return income_of(self)
