"""Battle crews — the virtual sub-gang assigned to a battle (#1346).

A :class:`Crew` is a read-model overlay on a gang for a single battle: which
fighters attend (with which equipment set), plus credit-consuming extras
(tactics cards, later hired guns). It is deliberately NOT a second ``List`` — it
never writes to the gang's canonical cost caches, credits, or audit stream. Its
rating and credits value are computed on the fly.

Two concepts live here:

- The **recipe**: the scenario's ``selection_method`` (the rulebook's Custom /
  Random / Hybrid) plus the numbers it needs — ``custom_count`` for the
  fighters the player chooses, ``random_spec`` for the ones drawn at random.
  Editable while the crew is a DRAFT.
- The **attendees**: :class:`CrewMember` rows. Chosen members exist from
  selection time; the random ones are drawn when the crew is LOCKED at battle
  start (once, no re-rolls).

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
    "split_selection_spec",
    "build_selection_spec",
]


# --- Selection spec grammar: "" | N | DX | DX+N ---------------------------
#
# Necromunda scenarios choose a starting crew with one of three methods:
# Custom Selection (X), Random Selection (X), Hybrid Selection (X+Y). We model
# the *random* component as a small dice spec that is rolled once at battle
# start; the chosen component is a count plus the player's picks. Every
# scenario's random count fits N / DX / DX+N.

# Counts must be positive: a flat "0" (or a redundant "+0") would be a no-op
# draw that still reads as a pending roll, so reject it — blank means "no draw".
_SPEC_RE = re.compile(r"^(?:([1-9]\d*)|[dD]([1-9]\d*)(?:\+([1-9]\d*))?)$")


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


def split_selection_spec(value):
    """Split a spec (``N`` | ``DX`` | ``DX+N``) into ``(dice, number)`` for the
    structured form widgets. ``dice`` is ``""`` or ``"DX"``; ``number`` is the
    flat count or the ``+N`` addend (``None`` when absent). ``("", None)`` for
    an empty or unparseable spec."""
    value = (value or "").strip()
    m = _SPEC_RE.match(value)
    if not m:
        return "", None
    flat, sides, plus = m.groups()
    if flat is not None:
        return "", int(flat)
    return f"D{int(sides)}", (int(plus) if plus else None)


def build_selection_spec(dice, number):
    """Combine a ``dice`` choice (``""`` | ``"DX"``) and a ``number`` (or
    ``None``) from the structured form widgets back into a spec string —
    inverse of :func:`split_selection_spec`."""
    dice = (dice or "").strip()
    number = number or 0
    if dice and number:
        return f"{dice}+{number}"
    if dice:
        return dice
    if number:
        return str(number)
    return ""


class Crew(AppBase):
    """A gang's crew for one battle: the recipe, then the frozen attendees."""

    DRAFT = "draft"
    LOCKED = "locked"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (LOCKED, "Locked"),
    ]

    # The rulebook's three crew selection methods. "Whole gang" is deliberately
    # not a fourth: it is Custom Selection with no number in brackets, i.e.
    # CUSTOM with a blank ``custom_count``.
    CUSTOM = "custom"
    RANDOM = "random"
    HYBRID = "hybrid"
    SELECTION_METHOD_CHOICES = [
        (CUSTOM, "Custom Selection"),
        (RANDOM, "Random Selection"),
        (HYBRID, "Hybrid Selection"),
    ]

    # Payment / provenance for extra credit-consuming things. Descriptive only:
    # crews never move real credits. Lives on CrewLineItem.
    # "Allowance" is the underdog's pre-battle balancing allowance — House
    # Patronage is only one source of it (see #1346 discussion), so the name
    # stays source-neutral.
    PAY_CREDITS = "credits"
    PAY_FREE = "free"
    PAY_ALLOWANCE = "allowance"
    PAYMENT_CHOICES = [
        (PAY_CREDITS, "Gang credits"),
        (PAY_FREE, "Free"),
        (PAY_ALLOWANCE, "Allowance"),
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
    selection_method = models.CharField(
        max_length=10,
        choices=SELECTION_METHOD_CHOICES,
        default=CUSTOM,
        help_text="The scenario's crew selection method.",
    )
    custom_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "How many fighters the player chooses — the number in brackets. "
            "Blank on Custom Selection means no number is shown: the whole gang "
            "may take part."
        ),
    )
    random_spec = models.CharField(
        max_length=20,
        blank=True,
        default="",
        validators=[validate_selection_spec],
        help_text=(
            "How many fighters are drawn at random at battle start — the Y of "
            "Random and Hybrid Selection. A number (6), a die (D3), or die + "
            "number (D3+4)."
        ),
    )
    # Superseded by CrewMember rows tagged ``source=CHOSEN``, which now exist
    # from selection time rather than only after the lock. Neither read nor
    # written any more, and deliberately NOT kept in sync: it holds the picks as
    # they were before this change, so reversing 0172 recovers those but loses
    # any editing done since. Dropped in a later migration once that no longer
    # matters.
    chosen_fighters = models.ManyToManyField(
        "core.ListFighter",
        blank=True,
        related_name="chosen_in_crews",
        help_text="Deprecated: superseded by CrewMember rows.",
    )
    loadout_overrides = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Advisory pre-lock intent: which equipment set each fighter should "
            "bring when a whole-gang crew is enrolled at lock. Shape: "
            '{"<list_fighter_id>": {"equipment_set": "<set_id>"}}, where a '
            "stored null means the Default card. Never authoritative — see "
            "Crew.resolve_loadout."
        ),
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=DRAFT,
        help_text="Draft while being set up; locked once drawn at battle start.",
    )
    rating_locked = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "The crew's rating at the moment it was locked. Blank on a draft, "
            "and on crews locked before snapshotting existed."
        ),
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

    @property
    def pending_roll(self):
        """A draft crew whose random draw hasn't happened yet. Until it's rolled,
        the random attendees — and therefore the crew's rating — are unknown.

        The spec has to actually draw someone: the method alone isn't enough,
        because a Random or Hybrid crew saved with a blank spec would otherwise
        advertise an unknown rating for a draw that enrols nobody. The form
        requires a spec for those methods, but the column allows a blank.
        """
        return (
            self.status == self.DRAFT
            and self.selection_method in (self.RANDOM, self.HYBRID)
            and bool((self.random_spec or "").strip())
        )

    @property
    def is_whole_gang(self):
        """Custom Selection with no number in brackets: the whole gang may take
        part, so a crew with no picks means everyone attends."""
        return self.selection_method == self.CUSTOM and self.custom_count is None

    def can_manage(self, user):
        """Who may create/edit/lock/delete this crew: the crew's own gang owner
        or the battle's arbitrator (battle owner or a campaign admin). Blocked
        while the battle or its campaign is archived."""
        if not user or not user.is_authenticated:
            return False
        battle = self.battle
        if battle.archived or battle.campaign.archived:
            return False
        # owner_id is a column, so the owner checks avoid loading the owner
        # objects; is_admin covers the campaign owner and any shared admins.
        return (
            user.id == self.list.owner_id
            or user.id == battle.owner_id
            or battle.campaign.is_admin(user)
        )

    @staticmethod
    def can_manage_new(user, battle, gang):
        """Whether ``user`` may create a crew for ``gang`` on ``battle``.

        The no-crew-yet counterpart to :meth:`can_manage` (there's no Crew
        instance to ask): the gang's owner or the battle's arbitrator (battle
        owner or a campaign admin), and not while archived.
        """
        if not user or not user.is_authenticated:
            return False
        if battle.archived or battle.campaign.archived:
            return False
        return (
            user.id == gang.owner_id
            or user.id == battle.owner_id
            or battle.campaign.is_admin(user)
        )

    # --- pre-lock loadout intent -----------------------------------------
    #
    # A whole-gang crew has no members until it is locked (the roster is
    # whoever is eligible at battle start), so there is nowhere to record which
    # card each model will bring. ``loadout_overrides`` records that intent
    # ahead of time. It is deliberately **advisory**: every read goes through
    # :meth:`resolve_loadout`, which falls back to the fighter's own active set
    # whenever the stored entry no longer makes sense. Nothing downstream may
    # treat the blob as authoritative — it can be stale, partial, or (having
    # been a JSON column touched by past code) malformed, and none of those may
    # break a lock.

    LOADOUT_SET_KEY = "equipment_set"

    def _override_entry(self, fighter_id):
        """The stored entry for ``fighter_id``, or ``None`` when there isn't a
        usable one. Tolerates anything the column might hold."""
        overrides = self.loadout_overrides
        if not isinstance(overrides, dict):
            return None
        entry = overrides.get(str(fighter_id))
        if not isinstance(entry, dict) or self.LOADOUT_SET_KEY not in entry:
            return None
        return entry

    def resolve_loadout(self, fighter):
        """The equipment set ``fighter`` brings to this battle (``None`` = the
        Default card). The single source of truth for both the pre-lock forecast
        and the enrolment at lock, so the two cannot disagree.

        An override applies only when it still resolves: the referenced set must
        still exist *and* still belong to this fighter, which also rejects a
        stale or forged id pointing at someone else's card. A stored ``null`` is
        an explicit choice of the Default card and is honoured even when the
        fighter's own active set is something else — that is the point of a
        per-battle override. Anything else falls back to the set the fighter is
        already using.

        Reads the fighter's sets from the prefetch cache
        (``with_related_data()``), so this costs no query per fighter.
        """
        entry = self._override_entry(fighter.pk)
        if entry is not None:
            raw = entry[self.LOADOUT_SET_KEY]
            if raw is None:
                return None
            for candidate in fighter.equipment_sets.all():
                if str(candidate.pk) == str(raw):
                    return candidate
            # The set has been deleted, or never belonged to this fighter: the
            # intent can't be honoured, so fall through to the fighter's own kit.

        if fighter.active_equipment_set_id is None:
            return None
        for candidate in fighter.equipment_sets.all():
            if candidate.pk == fighter.active_equipment_set_id:
                return candidate
        return None

    def pruned_loadout_overrides(self, fighters):
        """``loadout_overrides`` with the entries that no longer mean anything
        removed, given the fighters currently eligible for this crew.

        Dropped: entries for fighters who are no longer eligible (left the gang,
        archived, killed, in recovery), entries whose set has been deleted or
        belongs to someone else, and malformed leftovers. Explicit ``null``
        (Default) entries are kept. Called opportunistically whenever the
        overrides are written and again at lock, so the blob self-heals instead
        of accumulating junk.
        """
        pruned = {}
        for fighter in fighters:
            entry = self._override_entry(fighter.pk)
            if entry is None:
                continue
            raw = entry[self.LOADOUT_SET_KEY]
            if raw is None:
                pruned[str(fighter.pk)] = {self.LOADOUT_SET_KEY: None}
                continue
            match = next(
                (s for s in fighter.equipment_sets.all() if str(s.pk) == str(raw)),
                None,
            )
            if match is not None:
                pruned[str(fighter.pk)] = {self.LOADOUT_SET_KEY: str(match.pk)}
        return pruned

    # --- selection method label ------------------------------------------

    def method_label(self):
        """The scenario's selection method in the rulebook's own notation, e.g.
        "Random Selection (D6+2)", "Hybrid Selection (2+D6+2)", "Custom
        Selection (4)". Custom Selection with no number in brackets is shown
        bare — that is the rulebook's way of saying the whole gang may take
        part."""
        label = self.get_selection_method_display()
        spec = (self.random_spec or "").strip()
        if self.selection_method == self.RANDOM:
            return f"{label} ({spec})" if spec else label
        if self.selection_method == self.HYBRID:
            parts = [str(p) for p in (self.custom_count, spec) if p]
            return f"{label} ({'+'.join(parts)})" if parts else label
        if self.custom_count is not None:
            return f"{label} ({self.custom_count})"
        return label

    # --- rating & credits (computed live until the lock freezes them) ----

    def _attendee_lines(self):
        """Per-member ``(cost, line)`` for the crew.

        Members are the single source of attendance at every stage: the chosen
        ones exist from selection time, the drawn ones join at lock. The
        fighters are loaded in one batch via ``with_related_data()`` so their
        costs compute from the prefetch cache rather than N+1 per fighter. Each
        member's equipment set is resolved against its fighter's own prefetched
        sets (so the set's assignments also come from the cache); a member with
        no set is costed at their whole kit.

        ``cost`` is the member's locked rating once they have one, falling back
        to the live figure; ``line["live_rating"]`` always carries what the
        fighter costs *now*, which is what drift is measured against. ``line``
        is otherwise a small display dict (name, loadout, random flag, ids).
        """
        from gyrinx.core.models.list import ListFighter

        # self.members.all() (no select_related) so a caller's
        # prefetch_related("members") cache is honoured; the fighter and its
        # name come from the batched with_related_data() load below.
        members = list(self.members.all())
        loaded = ListFighter.objects.with_related_data().in_bulk(
            [m.list_fighter_id for m in members]
        )

        lines = []
        for member in members:
            fighter = loaded.get(member.list_fighter_id)
            equipment_set = None
            if fighter is not None and member.equipment_set_id is not None:
                equipment_set = next(
                    (
                        s
                        for s in fighter.equipment_sets.all()
                        if s.id == member.equipment_set_id
                    ),
                    None,
                )
            live_cost = (
                fighter.cost_int_for_equipment_set(equipment_set)
                if fighter is not None
                else 0
            )
            cost = (
                member.rating_locked if member.rating_locked is not None else live_cost
            )
            lines.append(
                (
                    cost,
                    {
                        "live_rating": live_cost,
                        "name": fighter.name if fighter is not None else "",
                        "category": (
                            fighter.content_fighter.get_category_display()
                            if fighter is not None
                            else ""
                        ),
                        "fighter_id": member.list_fighter_id,
                        "loadout": equipment_set.name if equipment_set else None,
                        "is_random": member.source == CrewMember.DRAWN,
                        "member_id": member.id,
                    },
                )
            )
        return lines

    def rating(self):
        """The crew's fighter rating: the snapshot taken at lock, or, before
        there is one, the sum of each member's cost scoped to the equipment set
        they bring. While the crew is a draft that only means the chosen members
        — the random component is unknown until the draw at lock, so it isn't
        counted.

        ``rating_locked`` is a **read-model snapshot on a virtual overlay
        object**, not a cost cache. A crew is a historical record of who fought
        with what, and the gang it was drawn from legitimately keeps changing
        afterwards (new weapons bought, equipment sets re-cut), which would
        otherwise silently move the rating of a battle already fought. Nothing
        here feeds gang rating, credits, the audit stream, or any cached cost:
        it is written once, by the lock, and never reconciled — where the live
        figure has since moved, that is reported as drift
        (:meth:`rating_drift`), not absorbed. Crews locked before this existed
        have no snapshot and compute live.
        """
        if self.rating_locked is not None:
            return self.rating_locked
        return self.live_rating()

    def live_rating(self):
        """The crew's rating recomputed from the fighters as they are *now* —
        what :meth:`rating` would have said had the crew been locked today."""
        return sum(line["live_rating"] for _, line in self._attendee_lines())

    def live_member_ratings(self):
        """Map of member id → that member's live cost. The input to the lock
        snapshot (see ``handlers.crew.snapshot_crew_rating``)."""
        return {
            line["member_id"]: line["live_rating"] for _, line in self._attendee_lines()
        }

    def _drift(self, live):
        """Snapshot vs ``live``, or ``None`` when there is no snapshot to
        compare against (a draft, or a crew locked before snapshotting)."""
        if self.rating_locked is None:
            return None
        return {
            "locked": self.rating_locked,
            "live": live,
            "has_drifted": live != self.rating_locked,
        }

    def rating_drift(self):
        """How far the crew's rating has moved since it was locked.

        ``None`` when there is no snapshot to compare against; otherwise
        ``{"locked", "live", "has_drifted"}``. Drift is expected and allowed —
        the gang carries on changing after the battle — so it is surfaced rather
        than corrected.
        """
        # Checked before computing the live rating, not inside _drift(): there is
        # nothing to compare a draft against, and live_rating() batch-loads every
        # attendee. The battle page asks each crew for its drift, so evaluating it
        # first would cost that load per draft crew and then discard it.
        if self.rating_locked is None:
            return None
        return self._drift(self.live_rating())

    def print_fighter_ids(self):
        """ListFighter ids to print for this crew, or ``None`` for the whole gang.

        A locked crew prints its frozen attendees; a draft prints the fighters
        chosen so far. A draft with no members (a whole-gang crew, or one whose
        attendees are all still to be drawn) has nothing specific to narrow to,
        so returns ``None`` and the print falls back to the whole gang.
        """
        ids = list(self.members.values_list("list_fighter_id", flat=True))
        if self.is_locked:
            return ids
        return ids or None

    def extras_total(self):
        """Total credits of the crew's extra line items (tactics cards, etc.)."""
        return sum(item.cost for item in self.line_items.all())

    def credits_value(self):
        """The crew's Credits value (rating + extras) — the rulebook quantity
        scenarios compare for underdog bonuses."""
        return self.rating() + self.extras_total()

    def receipt(self):
        """Columnar receipt for the crew page, grouped into a Fighters section
        and an Extras section. Each fighter contributes to the Rating column;
        each extra falls in the Credits, Allowance, or Free column by how it is
        paid for. Returns the grouped rows, the per-column totals (for the
        annotated subtotal rows), the grand total (the crew's credits value),
        and any rating drift since the lock. One batch load; the extras are
        computed live and only the locked rating is ever persisted."""
        lines = self._attendee_lines()
        attendees = [{"rating": cost, **line} for cost, line in lines]
        # The locked snapshot is the crew's rating once it has one; before that
        # the per-member figures are live and sum to the same thing.
        fighters_total = (
            self.rating_locked
            if self.rating_locked is not None
            else sum(cost for cost, _ in lines)
        )
        drift = self._drift(sum(line["live_rating"] for _, line in lines))

        extras = []
        credits_total = allowance_total = free_total = 0
        has_free = False
        for item in self.line_items.all():
            credits = allowance = free = None
            if item.payment == self.PAY_ALLOWANCE:
                allowance = item.cost
                allowance_total += item.cost
            elif item.payment == self.PAY_FREE:
                free = item.cost
                free_total += item.cost
                has_free = True
            else:
                credits = item.cost
                credits_total += item.cost
            extras.append(
                {
                    "item": item,
                    "credits": credits,
                    "allowance": allowance,
                    "free": free,
                }
            )

        total = fighters_total + credits_total + allowance_total + free_total
        return {
            "attendees": attendees,
            "extras": extras,
            "has_extras": bool(extras),
            "fighters_total": fighters_total,
            "credits_total": credits_total,
            "allowance_total": allowance_total,
            "free_total": free_total,
            "has_free": has_free,
            "total": total,
            # None when there's no snapshot to compare against; otherwise the
            # locked and live ratings plus whether they differ.
            "drift": drift,
            # Draft crew with a draw still to roll: the random attendees aren't
            # known, so rating/total render as "?" and a "+spec from the roll"
            # row stands in for them.
            "pending_roll": self.pending_roll,
            "random_spec": self.random_spec,
        }


class CrewMember(AppBase):
    """An attendee of a crew: a fighter with a battle loadout.

    Chosen members exist from selection time (a draft crew already has them);
    drawn members are added by the random draw when the crew is locked.
    """

    CHOSEN = "chosen"
    DRAWN = "random"
    SOURCE_CHOICES = [
        (CHOSEN, "Chosen"),
        (DRAWN, "Drawn at random"),
    ]

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
    source = models.CharField(
        max_length=10,
        choices=SOURCE_CHOICES,
        default=CHOSEN,
        help_text="How this fighter joined the crew (audit of the draw).",
    )
    rating_locked = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "This member's contribution to the crew's rating at the moment the "
            "crew was locked. Blank until then."
        ),
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
        """This member's contribution to crew rating: the figure frozen when the
        crew was locked, or, before that, the fighter's cost scoped to the
        equipment set they bring (their whole kit when no set is chosen).

        Like :attr:`Crew.rating_locked`, the snapshot is a read-model record of
        what was fielded — it never feeds gang rating, credits, or any cost
        cache.
        """
        if self.rating_locked is not None:
            return self.rating_locked
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
        help_text="Why, when free or from an allowance.",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["created"]
        verbose_name = "Crew Line Item"
        verbose_name_plural = "Crew Line Items"

    def __str__(self):
        return f"{self.label} ({self.cost}¢)"
