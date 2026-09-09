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
it does. A possession is built into its campaign type the moment it is
created, and taken out again when it is deleted or archived, with no
step for the author (``n26.library.possessions``). A holding is never
assigned; the campaign's own record of the asset says who holds it.

An **asset table** is a table of one Holding asset type's assets — the
core rulebook's Territory Selection Table — with, on a rolled table, the
band of rolls that lands on each entry. A gang may roll on any table it
holds, so a table is assignable: built into its campaign type as it is
created (``n26.library.tables``), given by a modifier, or built into a
campaign's additions. It draws no line anywhere.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from n26.library.models.assignable import (
    Assignable,
    Family,
    exclusive_has_no_trade_points,
)
from n26.library.models.base import Content
from n26.library.models.slots import Dice, band_coverage, band_problem


class CampaignType(Content, Assignable):
    """A kind of campaign — Territory campaign, Dominion — assigned to every
    gang that joins a campaign founded on it.

    Assignable for the same reason a gang type is: joining a campaign is a
    gang-hosted assignment naming its type. That gives everything a member
    gang receives on joining — a Reputation counter, a Settlement —
    something to be caused by, and puts campaign-wide modifiers on every
    member's card. A counter or a rule is added to that list by hand; an
    asset of a Possession asset type is added to it when the asset is
    created.

    It also declares its **asset types** — Territory, Settlement — and
    under each asset type lists the **assets** a campaign of this type
    hands out. Its pricing fields stay at zero; nobody buys a campaign type.

    The **description** is the one field here written for a player: the
    arbitrator setting a campaign up reads it on the set-up screen. The
    library author help stays for content authors, as on every other kind.
    """

    family = Family.GANG

    #: What every gang that joins can be given by hand: a counter with
    #: its opening value, a rule, a slot to pick in. Kit is a model's,
    #: not a campaign's, and an asset is built in by its asset type.
    built_in_kinds = ("counter", "rule", "slot")

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
    """A class of asset a campaign type has — Territory, Settlement —
    with the label a campaign page prints and the ownership that fixes
    how every asset of the type behaves.

    **Possession** means every gang has its own: a
    Settlement, a home territory. **Holding** means one gang holds it at a
    time, and it can change hands: a Territory.
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
    territory — of one asset type.

    An asset is one entry in the list of what its campaign type hands
    out, and is added on that campaign type's page under its asset type.
    What having it does for the gang rides it as ordinary modifiers. Its
    **income** is one of them: a contribution to the system Income counter
    (``n26.library.income``), so a gang's Income reads as the sum of what
    it holds. Nothing collects that reading yet.

    Assignable so that a possession can be built into its campaign type
    and arrive on every member gang, and so that an asset of either
    ownership can carry modifiers. A possession is built in when it is
    created and taken out when it is deleted or archived; nobody adds it
    by hand. A holding is never assigned: the campaign's own record of
    the asset says who holds it.
    """

    family = Family.BASE

    #: The built-in picker never offers an asset. A possession is built in
    #: by being created under a Possession asset type, and a holding is
    #: never built in, so a hand-picked asset member could only be a
    #: mistake.
    offered_as_built_in = False

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
    def is_possession(self):
        """Whether every gang has its own of this — read off the asset
        type, where the ownership lives."""
        return not self.asset_type.is_holding

    def archive(self):
        """An archived possession stops being given: its built-in
        memberships go with it, the way deleting the asset takes them.
        Gangs already holding one keep it, as with every built-in."""
        from n26.library.authoring import take_out_of_built_ins

        take_out_of_built_ins(self)
        super().archive()

    def unarchive(self):
        """Bringing a possession back starts it being given again: the
        memberships archiving took out come back, and the gangs that
        joined meanwhile catch up. The mirror of ``archive``."""
        from n26.library.possessions import give_back

        super().unarchive()
        give_back(self)

    @property
    def income(self):
        """What this brings its holder each cycle, read off its Income
        contribution. A query unless the modifiers are prefetched; a page
        listing many assets reads them through ``income.income_of`` with
        the modifiers it already holds."""
        from n26.library.income import income_of

        return income_of(self)


class AssetTable(Content, Assignable):
    """A table of one asset type's assets — the Territory Selection
    Table — that a gang holds and may roll on.

    A gang may roll on any table it holds. The core rulebook's table is
    built into its campaign type the moment it is created, so every gang
    that joins holds it, with no step for the author. A journal's table
    is given by a modifier on the gang's House pick, so every gang of
    that House holds it. An arbitrator opens a table to every gang in
    one campaign by building it into that campaign's additions. A table
    draws no line on the gang sheet or the campaign page: the roll
    controls read which tables a gang holds.

    Fields of its own: its **asset type**, which fixes the campaign type
    it belongs to and what its entries may be, and **dice**. A table
    with dice is rolled on, and its entries claim bands of rolls: every
    roll the die can make lands on exactly one entry. A table without
    dice is an ordered list, chosen from rather than rolled. Only a
    Holding asset type has tables: every gang has its own of a
    Possession, so there is nothing to roll for.
    """

    family = Family.CHOICE

    #: A table arrives by being built in or given, never by being
    #: acquired, so items built into one would sit in the library unread.
    takes_built_ins = False

    #: The built-in picker never offers a table. A table is built into its
    #: campaign type by being created, and an arbitrator opens one to a
    #: campaign from the campaign's own page, so a hand-picked table member
    #: could only be a mistake.
    offered_as_built_in = False

    asset_type = models.ForeignKey(
        AssetType,
        on_delete=models.PROTECT,
        related_name="tables",
        verbose_name="Asset type",
        help_text=(
            "Which asset type this table lists. Settled when the table is "
            "made on its campaign type's page, and never changed afterwards."
        ),
    )
    dice = models.CharField(
        max_length=8,
        blank=True,
        default="",
        choices=Dice,
        help_text=(
            "The die this table is rolled on. Blank is an ordered list, "
            "chosen from rather than rolled."
        ),
    )

    class Meta:
        verbose_name = "asset table"
        verbose_name_plural = "asset tables"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="asset_table_unique_per_pack",
            ),
            exclusive_has_no_trade_points("asset_table"),
        ]

    @property
    def campaign_type(self):
        """The campaign type whose asset type this table lists."""
        return self.asset_type.campaign_type

    @property
    def may_list(self):
        """The assets this table's entries may name: its asset type's, and
        no others. The picker on the page that adds an entry reads this,
        so what an author is offered and what the table accepts are one
        statement. Archived assets are left out, as at every other surface
        where something is newly chosen."""
        return self.asset_type.assets.unarchived()

    def clean(self):
        super().clean()
        if self.asset_type_id and not self.asset_type.is_holding:
            raise ValidationError(
                {
                    "asset_type": (
                        f"{self.asset_type} is a Possession asset type: every "
                        "gang has its own, so there is nothing to roll for. A "
                        "table lists a Holding asset type."
                    )
                }
            )

    def coverage(self, entries=None):
        """Whether this table's bands claim its die (``band_coverage``).
        A caller that has already fetched the entries hands them over
        rather than paying for the same rows twice."""
        if entries is None:
            entries = list(self.entries.select_related("asset"))
        return band_coverage(self.dice, entries)

    def landing(self, roll, entries=None):
        """The entry a roll lands on, or None where no band claims it —
        and None for every roll on a table that is not rolled."""
        if not self.dice:
            return None
        if entries is None:
            entries = self.entries.all()
        return next(
            (
                entry
                for entry in entries
                if entry.roll_low is not None
                and entry.roll_low <= roll <= entry.roll_high
            ),
            None,
        )

    def archive(self):
        """An archived table stops being given: its built-in memberships
        go with it, the way deleting the table takes them. Gangs already
        holding it keep it, as with every built-in."""
        from n26.library.authoring import take_out_of_built_ins

        take_out_of_built_ins(self)
        super().archive()

    def unarchive(self):
        """Bringing a table back starts it being given again: the
        memberships archiving took out come back, and the gangs that
        joined meanwhile catch up. The mirror of ``archive``."""
        from n26.library.tables import give_back

        super().unarchive()
        give_back(self)


class AssetTableEntry(Content):
    """One asset on one table, in its place — and, on a rolled table, the
    band of rolls that lands on it.

    An entry names an asset of the table's own asset type. The same
    asset may be on several tables, and a roll that lands on an entry
    adds one more copy of its asset to the campaign, so a table may list
    an asset the campaign already has.
    """

    table = models.ForeignKey(
        AssetTable, on_delete=models.CASCADE, related_name="entries"
    )
    asset = models.ForeignKey(
        Asset,
        on_delete=models.PROTECT,
        related_name="tabled",
        help_text="The asset a roll landing here adds to the campaign.",
    )
    position = models.PositiveIntegerField(
        default=0,
        help_text="Where it sits in the table. Ties fall back to the asset's name.",
    )
    #: The band of rolls that lands on this entry, both ends inclusive —
    #: "21-26" as readily as "11", which is the band with one roll in it.
    #: Plain integers even on a D66, where a band may span rolls that
    #: cannot come up: a lookup only ever asks about a roll that did.
    roll_low = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="The lowest roll that lands here, on a rolled table.",
    )
    roll_high = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="The highest roll that lands here. The same as the lowest for one roll.",
    )

    class Meta:
        verbose_name = "asset table entry"
        verbose_name_plural = "asset table entries"
        ordering = ["table", "position", "asset__name"]
        constraints = [
            # A band is both ends or neither, and runs upwards.
            models.CheckConstraint(
                condition=models.Q(roll_low__isnull=True, roll_high__isnull=True)
                | models.Q(
                    roll_low__isnull=False,
                    roll_high__isnull=False,
                    roll_low__lte=models.F("roll_high"),
                ),
                name="asset_table_entry_band_is_whole",
            ),
        ]

    def __str__(self):
        return self.label

    @property
    def label(self):
        """What the table calls the entry: the asset's name."""
        return str(self.asset)

    @property
    def band(self):
        """The band as a table prints it: "51", "21-26", or nothing."""
        if self.roll_low is None:
            return ""
        if self.roll_low == self.roll_high:
            return str(self.roll_low)
        return f"{self.roll_low}-{self.roll_high}"

    def clean(self):
        super().clean()
        if problem := band_problem(self.roll_low, self.roll_high):
            raise ValidationError({"roll_low": problem})
        if self.roll_low is not None and self.table_id and not self.table.dice:
            raise ValidationError(
                {
                    "roll_low": (
                        f"{self.table} names no dice, so a band here would "
                        "never be rolled. Give the table its dice first."
                    )
                }
            )
        if self.table_id and self.asset_id:
            if self.asset.asset_type_id != self.table.asset_type_id:
                raise ValidationError(
                    {
                        "asset": (
                            f"{self.asset} is a {self.asset.asset_type}, and "
                            f"{self.table} lists {self.table.asset_type.plural}."
                        )
                    }
                )
