"""What a profile comes with, and what may be chosen instead.

v1 modelled default equipment as an *inherited* assignment living on the
profile-equivalent and overridden per fighter, which got messy: the default
had to exist and then be suppressed. Here nothing is ever replaced —
a choice decides which set **materialises at hire**, and the option not
taken simply never comes into being.

Anything acquirable is ``(built_ins, [options])``, and the shape is the
documentation:

``built_ins``   always granted, no choice offered
``options``     ordered alternatives; the head of the list is what is
                taken unasked, and a UI puts the choice in front of the
                player whenever the list is non-empty

A profile offers its options at hire; a mount in an equipment list offers
them when bought. Same grammar, so the same two models — which is why
they name a *carrier* rather than a profile.

Options come in **groups**, and each group is one axis of the choice:

* Ungrouped options form the carrier's *default group* — no row to create
  first, an author just adds options. It is **one-of**: a hire takes
  exactly one, the head of the list unasked.
* An ``OptionGroup`` is a further axis. ``choose`` says how it
  works: ``ONE`` is another one-of (exactly one, head is the default);
  ``ANY`` is the rulebook's "may select any of the below options" —
  take any number, none by default.

Pricing is a sum: a hire costs ``profile.price`` plus the built-ins'
price plus every chosen set's price. Usually only one of those carries
the base number, and which one is the content manager's choice — put it
all on ``built_ins`` and leave the profile's own ``price`` at zero, or
the other way round.

Axes that are genuinely entangled (the Sanctioner replaces its claw
and/or baton with *one* pick) stay one-of, enumerated as combinations
within their group — the content manager decides how to carve it up.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from n26.core.constraints import NamesAnAssignable, exactly_one_of
from n26.library.models.base import Content

#: What a default assignment may name. Not profiles (a fighter cannot come
#: with a fighter — that is what OpAddsMiniature is for) and not injuries.
#: Collections are here because a profile's equipment list arrives the way
#: its kit does: in the built-ins, materialised at hire. A weapon profile
#: member is an extra ammo type for a weapon arriving in the same hire —
#: it materialises stacked on that weapon's assignment, mirroring
#: ``buy_weapon_profile``.
DEFAULT_ASSIGNABLE_FIELDS = (
    "weapon",
    "weapon_profile",
    "wargear",
    "subtype",
    "skill",
    "rule",
    "hidden",
    "collection",
    "counter",
)


class DefaultAssignmentSet(Content):
    """A named set of things an assignable can come with."""

    name = models.CharField(max_length=200)
    price = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Credits this set adds to a hire. Options are priced "
            "absolutely, not as a delta: plain talons 0, razor-sharp 25."
        ),
    )

    class Meta:
        verbose_name = "default assignment set"
        verbose_name_plural = "default assignment sets"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack", Lower("name"), name="default_assignment_set_unique_per_pack"
            ),
        ]

    def __str__(self):
        return f"{self.name} (+{self.price}cr)" if self.price else self.name


class DefaultAssignment(NamesAnAssignable, Content):
    """One thing something always comes with when it is acquired.

    Anything assignable can carry these rows, and they read differently
    on each. A fighter entry comes with the weapons in its hands at
    hire, a skill it always knows, a counter's opening value, and access
    to a collection — which is how it names the equipment list it uses.
    A piece of wargear comes with whatever arrives with it: a beast with
    its claws. No choice is offered; a thing that may be swapped for
    something else is an option, not a built-in.

    Deliberately parallel to ``n26.Assignment`` — same mixin, same
    ``assignable=`` constructor, same ``assignable`` property — because that
    is exactly what it becomes at hire: one of these makes one of those,
    free, caused by the membership.

    The permitted kinds differ, and should: a player can be assigned a
    fighter profile, but a profile cannot *come with* one. That is what
    ``OpAddsMiniature`` is for.
    """

    ASSIGNABLE_FIELDS = DEFAULT_ASSIGNABLE_FIELDS

    #: The key assignable kinds use in their ``ATTACHMENT_ASKS`` to say
    #: which of this row's columns matter when they are the thing named
    #: (library/offers.py).
    attachment_context = "built-in"

    default_set = models.ForeignKey(
        DefaultAssignmentSet, on_delete=models.CASCADE, related_name="members"
    )
    weapon = models.ForeignKey(
        "library.Weapon",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    weapon_profile = models.ForeignKey(
        "library.WeaponProfile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "An extra ammo type for a weapon in the same hire — the "
            "Sanctioner's choke gas grenades for its launcher array."
        ),
    )
    wargear = models.ForeignKey(
        "library.Wargear",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    subtype = models.ForeignKey(
        "library.Subtype",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    skill = models.ForeignKey(
        "library.Skill",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    rule = models.ForeignKey(
        "library.Rule",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    hidden = models.ForeignKey(
        "library.Hidden",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    collection = models.ForeignKey(
        "library.Collection",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    counter = models.ForeignKey(
        "library.Counter",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    amount = models.PositiveIntegerField(
        default=0,
        help_text=("The initial value for a counter"),
    )
    position = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "default assignment"
        verbose_name_plural = "default assignments"
        ordering = ["default_set", "position"]
        constraints = [
            models.CheckConstraint(
                condition=exactly_one_of(DEFAULT_ASSIGNABLE_FIELDS),
                name="default_assignment_exactly_one",
            ),
        ]

    def __str__(self):
        return str(self.assignable) if self.assignable else "nothing"

    @property
    def dependent_members(self):
        """The set's other members that stop making sense without this one.

        Ammo lines ride their gun: a weapon profile materialises stacked
        on the assignment of a weapon arriving in the same acquisition,
        so with the weapon gone it names a gun nothing brings, and
        acquiring the carrier refuses.
        """
        if self.weapon_id is None:
            return DefaultAssignment.objects.none()
        return self.default_set.members.filter(weapon_profile__weapon_id=self.weapon_id)


#: Which kinds may offer options. Narrow on purpose: a profile offers
#: them at hire, a wargear offers them when bought. Widening is one line
#: plus a migration, as with DEFAULT_ASSIGNABLE_FIELDS.
OPTION_CARRIER_FIELDS = ("profile", "wargear")


class OptionGroup(NamesAnAssignable, Content):
    """One axis of choice a thing offers when it is acquired.

    A Sanctioner picks its melee loadout *and* whether it takes choke gas
    *and* whether it takes stun grenades — three groups, prices summing,
    instead of every combination spelt out as its own set.

    Only extra axes need a row: options with no group form the carrier's
    default group, so the first option an author creates needs nothing
    made first.

    The carrier is a union of one nullable key per kind — the same shape
    ``Assignment`` and ``DefaultAssignment`` use, because assignables are
    a mixin with no shared table. Both keys share a related name, so
    ``thing.option_groups`` reads the same on a profile and a wargear.
    """

    ASSIGNABLE_FIELDS = OPTION_CARRIER_FIELDS

    class Choose(models.TextChoices):
        #: Exactly one of the group's sets; the head of the list unasked.
        ONE = "one", "Exactly one"
        #: "May select any of the below options" — any number, none unasked.
        ANY = "any", "Any number"

    profile = models.ForeignKey(
        "library.Profile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="option_groups",
    )
    wargear = models.ForeignKey(
        "library.Wargear",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="option_groups",
    )
    name = models.CharField(
        max_length=200,
        verbose_name="Name (authoring only)",
        help_text=(
            "What this axis is called while you are writing it, e.g. "
            '"Melee weapons" or "Additional grenades". Never shown to a '
            "player: a hire screen puts the answers in front of them and "
            "the question is what the answers are. Name it for yourself."
        ),
    )
    choose = models.CharField(
        max_length=10,
        choices=Choose,
        default=Choose.ONE,
        help_text=(
            "Exactly one takes the first option unasked, and picking "
            "another replaces it. Any number starts with none taken."
        ),
    )
    position = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "option group"
        verbose_name_plural = "option groups"
        ordering = ["position"]
        constraints = [
            models.CheckConstraint(
                condition=exactly_one_of(OPTION_CARRIER_FIELDS),
                name="option_group_exactly_one_carrier",
            ),
        ]

    def __str__(self):
        return f"{self.carrier}: {self.name}"

    @property
    def carrier(self):
        """The thing offering this axis. Reads better than ``assignable``
        for a row that *belongs to* one rather than *names* one."""
        return self.assignable


class Option(NamesAnAssignable, Content):
    """One alternative a thing offers when it is acquired.

    The name is the player's: it is what a hire screen writes beside the
    tick box, so it says what taking this gets you. The set of things it
    brings is named separately and only for authors — set names must be
    unique across a pack, so two profiles both offering "As standard"
    would fight over one name, and whichever lost would show a player
    the name of a bag rather than the name of a choice.
    """

    ASSIGNABLE_FIELDS = OPTION_CARRIER_FIELDS

    profile = models.ForeignKey(
        "library.Profile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="options",
    )
    wargear = models.ForeignKey(
        "library.Wargear",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="options",
    )
    name = models.CharField(
        max_length=200,
        help_text=(
            'What a player is offered, e.g. "As standard" or "with '
            'razor-sharp talons". This is the wording on the hire screen.'
        ),
    )
    group = models.ForeignKey(
        OptionGroup,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="options",
        verbose_name="Axis",
        help_text=(
            "The axis this option belongs to. Blank puts it in the basic "
            "choice — exactly one of those is taken, the first unasked."
        ),
    )
    default_set = models.ForeignKey(
        DefaultAssignmentSet, on_delete=models.PROTECT, related_name="offered_by"
    )
    position = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "option"
        verbose_name_plural = "options"
        ordering = ["position"]
        constraints = [
            models.CheckConstraint(
                condition=exactly_one_of(OPTION_CARRIER_FIELDS),
                name="option_exactly_one_carrier",
            ),
        ]

    def __str__(self):
        return f"{self.carrier}: {self.name}"

    @property
    def carrier(self):
        return self.assignable

    @property
    def price(self):
        """What taking this adds to the acquisition. Stored on the set,
        because a price is a property of the kit, and the same kit
        offered twice is priced the same both times."""
        return self.default_set.price

    def clean(self):
        if self.group_id and self.group.assignable != self.assignable:
            raise ValidationError({"group": "This group belongs to something else."})
