"""Slots and picks — a choice made from a curated list, authored not coded.

A new domain of choice is four rows and no code. A **slot type** names the
domain (Gang Legacy, Affiliation, Archetype). **Pickables** are its
options, each an ordinary assignable carrying ordinary modifiers. A
**picklist** is the flat, ordered list of them a choice draws from. A
**slot** is one named use of the type — a picklist, a label, how many
picks, and where the pick lands — and it is an assignable, so putting the
choice on a card is an ordinary assignment.

What is chosen is an ordinary assignment too: the pickable, hosted per the
slot's ``assigned_to``, caused by the slot's assignment and pointing back at
it through ``Assignment.chosen_for``. Resolution reads that link, so two
slots of one type on one holder stay independent and nothing is inferred
from kinds.

Two of the rules here are shaped by the rest of the app rather than by the
game. A pickable draws no row of its own and does nothing at all until its
slot is present — so a pickable built into something, with no slot to
answer, would sit in the library unread, and the authoring pages refuse
one. And a hidden slot draws no choice row while its pick still does
everything it does: that is how a bundle of behaviour arrives under one
name.
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
    """A domain of choice: Gang Legacy, Affiliation, Archetype.

    Ties a slot, its picklist and its options together — all three name
    one of these, and authoring refuses a mismatch. Whether the same
    option may be picked twice over is a fact about the domain, so it is
    stated here once rather than on every slot.
    """

    family = Family.CHOICE

    name = models.CharField(
        max_length=200,
        help_text='The domain of the choice, e.g. "Gang Legacy".',
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
            "Whether one holder may pick the same option for two slots of "
            "this type. Turned off, the card says when they have — it never "
            "stops them."
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
    """One option a choice offers: Cawdor, Aranthian, Outcast Leader.

    A named value of its slot type that carries whatever it means as
    ordinary modifiers — an equipment list opened, a subtype granted, a
    further choice offered.

    It never draws a row of its own: it appears under its slot's choice
    row as the answer. **Without its slot it shows nothing and does
    nothing** — an option nobody was offered is not a thing the holder
    has. So it arrives chosen, given, or as a slot's starting value, and
    never as a bare built-in.
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
        help_text="The domain this is an option in.",
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


class Picklist(Content):
    """The options behind a choice: a flat, ordered list of pickables.

    One slot type throughout, no headings and no prices — where a
    collection is a catalogue, this is a menu. Two slots may draw from one
    picklist, and one slot type may have several: the Outcast archetypes
    a leader chooses from and the ones a champion does are two lists over
    the same type.
    """

    family = Family.CHOICE

    slot_type = models.ForeignKey(
        SlotType,
        on_delete=models.PROTECT,
        related_name="picklists",
        help_text="The domain these options belong to.",
    )
    name = models.CharField(
        max_length=200,
        help_text='What this list of options is called, e.g. "Gang Legacies".',
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
        """The options this list may hold: its domain's, and no others.

        The picker on the page that adds a member reads this, so what an
        author is offered and what the list will accept are one
        statement rather than two that can drift apart. Archived options
        are left out, as at every other surface where something is newly
        chosen — a list already naming one goes on naming it.
        """
        return self.slot_type.pickables.unarchived()


class PicklistMember(Content):
    """One option on one list, in its place.

    The pickable says what it is and what it does; this says that this
    list offers it, where in the order, and — where one list calls it
    something else — under what wording.
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
            "What this list calls the option, where that differs from its "
            "own name. Blank uses the name."
        ),
    )
    position = models.PositiveIntegerField(
        default=0,
        help_text="Where it sits in the list. Ties fall back to name.",
    )

    class Meta:
        verbose_name = "picklist member"
        verbose_name_plural = "picklist members"
        ordering = ["picklist", "position", "pickable__name"]
        constraints = [
            models.UniqueConstraint(
                "picklist", "pickable", name="picklist_member_listed_once"
            ),
        ]

    def __str__(self):
        return self.label

    @property
    def label(self):
        """What this list calls the option."""
        return self.label_override or str(self.pickable)

    def clean(self):
        super().clean()
        if self.picklist_id and self.pickable_id:
            if self.pickable.slot_type_id != self.picklist.slot_type_id:
                raise ValidationError(
                    {
                        "pickable": (
                            f"{self.pickable} belongs to "
                            f"{self.pickable.slot_type}, and {self.picklist} "
                            f"lists {self.picklist.slot_type} options."
                        )
                    }
                )


class Slot(Content, Assignable):
    """A choice put on a card: a picklist, a label, and how many picks.

    Assigning one is what asks the question. The card draws the label
    with what has been picked, or a control to pick — on the holder's own
    card and nowhere else, so a slot the gang holds is asked once rather
    than on every fighter.

    How many picks sit between the minimum and the maximum. Under the
    minimum is a note on the card, never a refusal, and the picker stops
    offering at the maximum.

    **Hidden** draws no choice row at all: the pick still arrives and
    still does everything it does, which is how a bundle of behaviour is
    given one name.
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
        help_text="The domain this choice is in.",
    )
    picklist = models.ForeignKey(
        Picklist,
        on_delete=models.PROTECT,
        related_name="slots",
        help_text="The list of options this choice offers.",
    )
    label = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            'What the card calls this choice, e.g. "Gang Legacy". Blank '
            "uses this slot's own name."
        ),
    )
    min_picks = models.PositiveIntegerField(
        default=1,
        help_text=(
            "How many picks the card expects. Fewer is a note on the card, "
            "never a refusal. Nought asks for nothing."
        ),
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
            "Where the pick lands. Almost always the bearer; a Leader's "
            "archetype pick is carried by the gang, not the Leader."
        ),
    )
    hidden = models.BooleanField(
        default=False,
        help_text=(
            "Draw no choice row at all. What is picked still applies — this "
            "is how several things arrive together under one name."
        ),
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
                            f"{self.picklist.slot_type} options, and this is "
                            f"a {self.slot_type} choice."
                        )
                    }
                )
