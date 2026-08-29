"""Slots and picks — user-pickable values from a list.

A slot is used to define new labels and values for gangs and models, and
attach behaviour to them, without a code change.

A **slot type** puts a name on one or more slots, and groups pickables.
**Pickables** are what may be picked/chosen from the available options in
the slot. Each is an ordinary assignable carrying ordinary modifiers.

A **picklist** is a flat, ordered list of pickables that the player
chooses from.

Finally, a **slot** is one specific, named use of the type — a picklist,
a label, and other configuration like how many picks and where the pick
lands — and it too is an assignable, so putting the choice on a card is
an ordinary assignment (e.g. from a modifier).

The eventual pick is an ordinary assignment too: the pickable, hosted per
the slot's ``assigned_to``, caused by the slot's assignment and pointing
back at it through ``Assignment.chosen_for``. Resolution reads that link,
so two slots of one type on one holder stay independent and nothing is
inferred from kinds.

A starting pick can be set, so a slot comes pre-filled.

A "hidden" slot is not made visible to the user, but its pick still does
everything it does. The use-case for this is the same as hidden
assignables.
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


class SlotType(Content):
    """What is chosen: Gang Legacy is the first, and new ones are authored.

    Puts a name on one or more slots, and groups pickables. Ties a slot,
    its picklist and its pickables together — all three name one of
    these, and authoring refuses a mismatch. Whether the same pickable
    may be picked twice over is a fact about the slot type, so it is
    stated here once rather than on every slot.
    """

    family = Family.CHOICE

    name = models.CharField(
        max_length=200,
        help_text='What is chosen, e.g. "Gang Legacy".',
    )
    plural_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            'What several of them are called, e.g. "Gang Legacies". Blank adds an s.'
        ),
    )
    allows_repeats = models.BooleanField(
        default=True,
        help_text=(
            "Whether one holder may pick the same pickable for two slots of this type."
        ),
    )

    class Meta:
        verbose_name = "slot type"
        verbose_name_plural = "slot types"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack", Lower("name"), name="slot_type_unique_per_pack"
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def plural(self):
        """Several of them, as a surface should say it."""
        return self.plural_name or f"{self.name}s"


class Pickable(Content, Assignable):
    """A value that goes into a Slot.

    One thing offered in a slot: a specific value, of a particular slot
    type, that carries behaviour as ordinary modifiers.

    It never draws a row of its own: it appears under its slot's choice
    row when chosen. **Without its slot it shows nothing and does
    nothing**. So it arrives chosen, given, or as a slot's starting
    value, and never as a bare built-in.

    A pickable may also link a category. The link is consulted for
    categorisation decisions — a rule that places "the chosen set" asks
    the pick which category it means, which is how a Skill Tree pick
    stands for the set it names. Most pickables link nothing.
    """

    # Filed with the rest of the choice machinery, which is where an
    # author looks for it. The family is read by more than the authoring
    # menu — the Trading Post stocks itself by sweeping every GEAR kind —
    # so a pickable filed as gear would go on sale, and one filed under
    # the gang would claim to be a gang's own.
    family = Family.CHOICE

    # Chosen, given or a slot's starting value: nothing acquires one, so
    # nothing would ever hand over items built into it.
    takes_built_ins = False

    slot_type = models.ForeignKey(
        SlotType,
        on_delete=models.PROTECT,
        related_name="pickables",
        help_text="The slot type this pickable belongs to.",
    )
    # The inherited home-category column, re-presented: a pickable never
    # stands in a collection, so on this kind the field is the link a
    # pick can be asked about, not a filing address.
    category = models.ForeignKey(
        "library.Category",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="%(class)ss",
        verbose_name="linked category",
        help_text=(
            "Consulted for categorisation decisions: a rule that places "
            '"the chosen set" reads this to learn which category the pick '
            "means — a Skill Tree pick links the set it names. Leave blank "
            "for pickables that work by their own modifiers."
        ),
    )

    class Meta:
        verbose_name = "pickable"
        verbose_name_plural = "pickables"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="pickable_unique_per_pack",
            ),
            exclusive_has_no_trade_points("pickable"),
        ]


class Dice(models.TextChoices):
    """The dice a roll table is rolled on. A closed set, because the
    authoring page has to enumerate every roll to say whether a table
    covers them."""

    D3 = "d3", "D3"
    D6 = "d6", "D6"
    D66 = "d66", "D66"
    TWO_D6 = "2d6", "2D6"

    @classmethod
    def rolls(cls, dice):
        """Every roll this die can produce, in order — the rolls a table
        has to claim. D66 is two D6 read as tens and units, so 37 through
        40 are not rolls at all and a band spanning them claims only what
        can come up."""
        match dice:
            case cls.D3:
                return (1, 2, 3)
            case cls.D6:
                return tuple(range(1, 7))
            case cls.D66:
                return tuple(
                    10 * tens + units for tens in range(1, 7) for units in range(1, 7)
                )
            case cls.TWO_D6:
                return tuple(range(2, 13))
        return ()


class RollSelects(models.TextChoices):
    """How a roll finds its result on a table. A band table gives the
    one row whose band holds the roll; a threshold table gives every row
    whose band starts at or below it."""

    BAND = "band", "The one row the roll lands in"
    THRESHOLD = "threshold", "Every row at or below the roll"


class Picklist(Content):
    """A flat, ordered list of Pickables.

    A set of pickables available in a slot. One slot type throughout,
    no headings and no prices — where a collection is a catalogue, this
    is a menu. Two slots may draw from one picklist, and one slot type
    may have several different picklists.

    This allows a limited selection of the pickables to be made
    available in certain situations, but under the same slot type. This
    is meant to be a simpler alternative to the "places" system of
    Collections.

    A list that names dice is a roll table: its members claim bands of
    rolls, and the authoring page says whether those bands cover the die.
    """

    family = Family.CHOICE

    slot_type = models.ForeignKey(
        SlotType,
        on_delete=models.PROTECT,
        related_name="picklists",
        help_text="The slot type these pickables belong to.",
    )
    name = models.CharField(
        max_length=200,
        help_text='What this picklist is called, e.g. "Gang Legacies".',
    )
    dice = models.CharField(
        max_length=8,
        blank=True,
        default="",
        choices=Dice,
        help_text=(
            "The die this table is rolled on, where it is one. Blank is an "
            "ordinary list, chosen from rather than rolled."
        ),
    )
    roll_selects = models.CharField(
        max_length=16,
        blank=True,
        default="",
        choices=RollSelects,
        help_text="How a roll finds its result on this table.",
    )

    class Meta:
        verbose_name = "picklist"
        verbose_name_plural = "picklists"
        ordering = ["name"]
        constraints = [
            # One slot type's lists are told apart by name; two types may
            # each have a "Houses" without either having to rename.
            models.UniqueConstraint(
                "pack",
                "slot_type",
                Lower("name"),
                name="picklist_unique_per_pack",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def may_offer(self):
        """The pickables this list may hold: its slot type's, and no others.

        The picker on the page that adds a member reads this, so what an
        author is offered and what the list will accept are one
        statement rather than two that can drift apart. Archived
        pickables are left out, as at every other surface where something
        is newly chosen — a list already naming one goes on naming it.
        """
        return self.slot_type.pickables.unarchived()


class PicklistMember(Content):
    """One pickable on one list, in its place.

    Links a Pickable to a Picklist: where in the order, and — where one
    picklist calls it something else — under what wording.
    """

    picklist = models.ForeignKey(
        Picklist,
        on_delete=models.CASCADE,
        related_name="members",
    )
    pickable = models.ForeignKey(
        Pickable,
        on_delete=models.PROTECT,
        related_name="listed_on",
    )
    label_override = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            "What this list calls the pickable, where that differs from its "
            "own name. Blank uses the name."
        ),
    )
    position = models.PositiveIntegerField(
        default=0,
        help_text="Where it sits in the list. Ties fall back to name.",
    )
    #: The band of rolls that lands on this row, both ends inclusive —
    #: "21-26" as readily as "11", which is the band with one roll in it.
    #: Plain integers even on a D66, where a band may span rolls that
    #: cannot come up: a lookup only ever asks about a roll that did.
    roll_low = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="The lowest roll that lands here, on a roll table.",
    )
    roll_high = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="The highest roll that lands here. The same as the lowest for one roll.",
    )

    class Meta:
        verbose_name = "picklist member"
        verbose_name_plural = "picklist members"
        ordering = ["picklist", "position", "pickable__name"]
        constraints = [
            models.UniqueConstraint(
                "picklist", "pickable", name="picklist_member_listed_once"
            ),
            # A band is both ends or neither, and runs upwards.
            models.CheckConstraint(
                condition=models.Q(roll_low__isnull=True, roll_high__isnull=True)
                | models.Q(
                    roll_low__isnull=False,
                    roll_high__isnull=False,
                    roll_low__lte=models.F("roll_high"),
                ),
                name="picklist_member_band_is_whole",
            ),
        ]

    def __str__(self):
        return self.label

    @property
    def label(self):
        """What this list calls the pickable."""
        return self.label_override or str(self.pickable)

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
        if self.roll_low is not None and self.picklist_id and not self.picklist.dice:
            raise ValidationError(
                {
                    "roll_low": (
                        f"{self.picklist} names no dice, so a band here would "
                        "never be rolled. Give the list its dice first."
                    )
                }
            )
        if self.picklist_id and self.pickable_id:
            if self.pickable.slot_type_id != self.picklist.slot_type_id:
                raise ValidationError(
                    {
                        "pickable": (
                            f"{self.pickable} belongs to "
                            f"{self.pickable.slot_type}, and {self.picklist} "
                            f"lists {self.picklist.slot_type} pickables."
                        )
                    }
                )


class Slot(Content, Assignable):
    """A fully configured slot containing pickables: a picklist, a
    label, and how many picks.

    One specific use of the pickables: a type, a picklist, a label, and
    config. Assigning one to a model or gang will cause the slot to show
    up. The gang or model card draws the label with what has been picked
    by the player, or what's set by default, or a control to pick.

    How many picks sit between the minimum and the maximum. Picking
    under the minimum adds a note on the card, never a refusal, and the
    picker stops offering at the maximum.

    **Hidden** makes the slot invisible: the pick still arrives and
    still does everything it does. This is basically "grouped hidden
    assignables".
    """

    family = Family.CHOICE

    # Chosen for, never acquired in its own right: what a slot brings is
    # the pick, and the pick arrives through choosing.
    takes_built_ins = False

    #: Building a slot in is what carries its starting pick — the
    #: Ironhead Squats profile arriving with the Squats legacy already
    #: chosen — so that is what attaching one asks for. Restated with the
    #: inherited entry ask, because declaring these replaces rather than
    #: merges (library/offers.py).
    ATTACHMENT_ASKS = {
        "built-in": ("default_pickable",),
        "entry": ("price_override", "trade_point_override"),
    }

    class WillBeAssignedTo(models.TextChoices):
        #: The model or gang whose card carries the slot — the ordinary
        #: case: a fighter's Gang Legacy rides that fighter.
        BEARER = "bearer", "the bearer"
        #: The Leader → Gang arrow: the Outcast Leader is asked, and what
        #: he picks belongs to the gang, reaching every member.
        GANG = "gang", "the gang"

    slot_type = models.ForeignKey(
        SlotType,
        on_delete=models.PROTECT,
        related_name="slots",
        help_text="The type of slot being configured.",
    )
    picklist = models.ForeignKey(
        Picklist,
        on_delete=models.PROTECT,
        related_name="slots",
        help_text="The picklist this slot draws from.",
    )
    label = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            "What the card calls this choice — the heading on its row, and "
            'what the Choose control asks for, e.g. "Lasting Injuries". '
            "Blank uses this slot's own name."
        ),
    )
    min_picks = models.PositiveIntegerField(
        default=1,
        help_text="How many picks expected. Nought asks for nothing.",
    )
    max_picks = models.PositiveIntegerField(
        default=1,
        help_text="How many picks the choice holds. The picker stops offering here.",
    )
    assigned_to = models.CharField(
        max_length=20,
        choices=WillBeAssignedTo,
        default=WillBeAssignedTo.BEARER,
        help_text=(
            "Where the pick lands. Almost always the bearer; assigned to "
            "the gang, the pick is the gang's and is broadcast (but not "
            "displayed) to every member, whoever was asked."
        ),
    )
    hidden = models.BooleanField(
        default=False,
        help_text="Display no choice at all. What is picked still applies.",
    )
    position = models.PositiveIntegerField(
        default=0,
        help_text="Order among the slots on one card. Ties fall back to name.",
    )

    class Meta:
        verbose_name = "slot"
        verbose_name_plural = "slots"
        ordering = ["position", "name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="slot_unique_per_pack",
            ),
            exclusive_has_no_trade_points("slot"),
            models.CheckConstraint(
                condition=models.Q(min_picks__lte=models.F("max_picks")),
                name="slot_min_picks_within_max",
            ),
        ]

    @property
    def choice_label(self):
        """What the card calls this choice."""
        return self.label or self.name

    def clean(self):
        super().clean()
        if self.slot_type_id and self.picklist_id:
            if self.picklist.slot_type_id != self.slot_type_id:
                raise ValidationError(
                    {
                        "picklist": (
                            f"{self.picklist} lists "
                            f"{self.picklist.slot_type} pickables, and this "
                            f"is a {self.slot_type} choice."
                        )
                    }
                )
