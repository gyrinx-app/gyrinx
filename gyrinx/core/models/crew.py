"""Battle crews — the virtual sub-gang assigned to a battle (#1346).

A :class:`Crew` is a read-model overlay on a gang for a single battle: which
fighters attend (with which equipment set), plus credit-consuming extras
(tactics cards, later hired guns). It is deliberately NOT a second ``List`` — it
never writes to the gang's canonical cost caches, credits, or audit stream. Its
rating and credits value are computed on the fly.

Two concepts live here:

- The **recipe**: the player's explicit ``chosen_fighters`` plus a
  ``random_spec`` describing the random draw ("D3+4"). Editable while the crew
  is a DRAFT.
- The **attendees**: the frozen :class:`CrewMember` rows created when the crew
  is LOCKED at battle start (the random draw executes then, once, no re-rolls).

See ``.claude/notes/battle-crew-design.md`` for the full design.
"""

import re
from random import Random  # nosec B311 - game dice, not crypto

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.core.models.base import AppBase

__all__ = [
    "Crew",
    "CrewMember",
    "CrewLineItem",
    "validate_selection_spec",
    "roll_selection_spec",
]


# --- Selection spec grammar: "" | N | DX | DX+N ---------------------------
#
# Necromunda scenarios choose a starting crew with one of three methods:
# Custom (X), Random (X), Hybrid (A+B). We model the *random* component as a
# small dice spec that is rolled once at battle start; the chosen component is
# the ``chosen_fighters`` M2M. Every scenario's random count fits N / DX / DX+N.

_SPEC_RE = re.compile(r"^(?:(\d+)|[dD]([1-9]\d*)(?:\+(\d+))?)$")


def validate_selection_spec(value):
    """Validate a crew random-selection spec.

    Accepts an empty value (no random draw), a flat count (``6``), a die
    (``D3``), or a die-plus-constant (``D3+4``). Raises ``ValidationError``
    otherwise.
    """
    value = (value or "").strip()
    if not value:
        return
    if not _SPEC_RE.match(value):
        raise ValidationError(
            "Enter a number (e.g. 6), a die (e.g. D3), or a die + number (e.g. D3+4)."
        )


def roll_selection_spec(value, rng=None):
    """Resolve a random-selection spec to a concrete count.

    Returns ``(count, detail)`` where ``detail`` is a short human string for the
    campaign log when a die was rolled (empty for a flat count or empty spec).
    Pass ``rng`` (anything with ``randint(a, b)``) for deterministic tests.
    """
    value = (value or "").strip()
    if not value:
        return 0, ""
    m = _SPEC_RE.match(value)
    if not m:
        raise ValidationError(f"Invalid selection spec: {value}")
    flat, sides, plus = m.groups()
    if flat is not None:
        return int(flat), ""
    sides = int(sides)
    plus = int(plus) if plus else 0
    rng = rng or Random()  # nosec B311 - game dice, not crypto
    roll = rng.randint(1, sides)
    total = roll + plus
    if plus:
        detail = f"D{sides}+{plus}: rolled {roll} → {total}"
    else:
        detail = f"D{sides}: rolled {roll}"
    return total, detail


class Crew(AppBase):
    """A gang's crew for one battle: the recipe, then the frozen attendees."""

    DRAFT = "draft"
    LOCKED = "locked"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (LOCKED, "Locked"),
    ]

    # Payment / provenance for extra credit-consuming things. Descriptive only:
    # crews never move real credits. Lives on CrewLineItem.
    PAY_CREDITS = "credits"
    PAY_FREE = "free"
    PAY_PATRONAGE = "patronage"
    PAYMENT_CHOICES = [
        (PAY_CREDITS, "Gang credits"),
        (PAY_FREE, "Free"),
        (PAY_PATRONAGE, "House patronage"),
    ]

    battle = models.ForeignKey(
        "core.Battle",
        on_delete=models.CASCADE,
        related_name="crews",
        help_text="The battle this crew fights in.",
    )
    list = models.ForeignKey(
        "core.List",
        on_delete=models.CASCADE,
        related_name="crews",
        help_text="The gang this crew is drawn from.",
    )
    name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional name for this crew.",
    )
    random_spec = models.CharField(
        max_length=20,
        blank=True,
        default="",
        validators=[validate_selection_spec],
        help_text=(
            "How many random fighters to draw at battle start, in addition to "
            "the chosen ones. A number (6), a die (D3), or die + number (D3+4)."
        ),
    )
    chosen_fighters = models.ManyToManyField(
        "core.ListFighter",
        blank=True,
        related_name="chosen_in_crews",
        help_text="Fighters the player specifically picks for the crew.",
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=DRAFT,
        help_text="Draft while being set up; locked once drawn at battle start.",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["list__name", "created"]
        verbose_name = "Crew"
        verbose_name_plural = "Crews"
        constraints = [
            models.UniqueConstraint(
                fields=["battle", "list"], name="unique_crew_per_gang_per_battle"
            )
        ]

    def __str__(self):
        return self.name or f"{self.list.name} crew"

    # --- state -----------------------------------------------------------

    @property
    def is_locked(self):
        return self.status == self.LOCKED

    def can_manage(self, user):
        """Who may create/edit/lock/delete this crew: the crew's own gang owner
        or the battle's arbitrator (battle owner or campaign owner). Blocked
        while the battle or its campaign is archived."""
        if not user or not user.is_authenticated:
            return False
        battle = self.battle
        if battle.archived or battle.campaign.archived:
            return False
        return (
            user == self.list.owner
            or user == battle.owner
            or user == battle.campaign.owner
        )

    # --- selection method label (derived from recipe) --------------------

    def method_label(self):
        """Human label mirroring the rulebook's Custom / Random / Hybrid."""
        chosen = self.chosen_fighters.count()
        has_random = bool((self.random_spec or "").strip())
        if chosen and has_random:
            return f"Hybrid ({chosen}+{self.random_spec})"
        if has_random:
            return f"Random ({self.random_spec})"
        if chosen:
            return f"Custom ({chosen})"
        return "Custom (whole gang)"

    # --- rating & credits (computed live, never persisted) ---------------

    def _member_fighters(self):
        return self.members.select_related("list_fighter", "equipment_set")

    def rating(self):
        """The crew's fighter rating, computed live (never reads/writes caches).

        Once locked, it's the sum of each frozen member's cost scoped to their
        chosen battle equipment set. While still a draft (no members yet), it's
        a provisional sum of the chosen fighters at full kit — the random
        component is unknown until the draw at lock, so it isn't counted.
        """
        if self.is_locked:
            return sum(member.rating() for member in self._member_fighters())
        return sum(fighter.cost_int_cached for fighter in self.chosen_fighters.all())

    def extras_total(self):
        """Total credits of the crew's extra line items (tactics cards, etc.)."""
        return sum(item.cost for item in self.line_items.all())

    def credits_value(self):
        """The crew's Credits value (rating + extras) — the rulebook quantity
        scenarios compare for underdog bonuses."""
        return self.rating() + self.extras_total()

    def rating_delta_vs_gang(self):
        """Crew rating minus the whole gang's current cached rating — usually
        negative, since a crew is a subset of the gang."""
        return self.rating() - self.list.rating_current


class CrewMember(AppBase):
    """A frozen attendee of a locked crew: a fighter with a battle loadout."""

    crew = models.ForeignKey(
        Crew,
        on_delete=models.CASCADE,
        related_name="members",
        help_text="The crew this member belongs to.",
    )
    list_fighter = models.ForeignKey(
        "core.ListFighter",
        on_delete=models.CASCADE,
        related_name="crew_memberships",
        help_text="The fighter attending the battle.",
    )
    equipment_set = models.ForeignKey(
        "core.ListFighterEquipmentSet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crew_memberships",
        help_text=(
            "The equipment set (loadout) this fighter brings to the battle. "
            "Blank means their full kit."
        ),
    )
    was_random = models.BooleanField(
        default=False,
        help_text="Whether this fighter was drawn randomly (audit of the draw).",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["created"]
        verbose_name = "Crew Member"
        verbose_name_plural = "Crew Members"
        constraints = [
            models.UniqueConstraint(
                fields=["crew", "list_fighter"], name="unique_fighter_per_crew"
            )
        ]

    def __str__(self):
        return f"{self.list_fighter.name} in {self.crew}"

    def rating(self):
        """This member's contribution to crew rating: the fighter's cost scoped
        to the chosen equipment set (full kit when no set is chosen)."""
        return self.list_fighter.cost_int_for_equipment_set(self.equipment_set)


class CrewLineItem(AppBase):
    """A credit-consuming extra attached to a crew (or one of its members).

    Generic on purpose: a tactics card is a crew-level item; a hired gun (later)
    is a member plus a member-linked item. ``payment`` records how it is paid
    for — descriptive only, never touching the gang's real credit books.
    """

    crew = models.ForeignKey(
        Crew,
        on_delete=models.CASCADE,
        related_name="line_items",
        help_text="The crew this line item belongs to.",
    )
    member = models.ForeignKey(
        CrewMember,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="line_items",
        help_text="The crew member this item is attached to, if any.",
    )
    label = models.CharField(
        max_length=255,
        help_text="What this is (e.g. 'Tactics card: Ambush').",
    )
    cost = models.PositiveIntegerField(
        default=0,
        help_text="Credits value of this item.",
    )
    payment = models.CharField(
        max_length=12,
        choices=Crew.PAYMENT_CHOICES,
        default=Crew.PAY_CREDITS,
        help_text="How this is paid for (descriptive; no credits are moved).",
    )
    reason = models.CharField(
        max_length=255,
        blank=True,
        help_text="Why, when free or by patronage.",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["created"]
        verbose_name = "Crew Line Item"
        verbose_name_plural = "Crew Line Items"

    def __str__(self):
        return f"{self.label} ({self.cost}¢)"
