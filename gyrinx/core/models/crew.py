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


def default_included_categories():
    """Empty opt-in list default for ``Crew.included_categories``.

    A named function, not the ``list`` builtin: inside the ``Crew`` class body
    the name ``list`` is the gang ForeignKey, so ``default=list`` would bind to
    that field.
    """
    return []


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
    included_categories = models.JSONField(
        default=default_included_categories,
        blank=True,
        help_text=(
            "Fighter categories this crew opts into beyond the always-eligible "
            "set. Hangers-on and vehicle crew are excluded from selection by "
            "default — hangers-on don't normally fight, and crew are an Ash "
            "Wastes thing — and a player adds them here per crew. A list of "
            'FighterCategoryChoices values (e.g. ["HANGER_ON", "CREW"]). Seeds '
            "the eligibility screen's per-category defaults."
        ),
    )
    eligibility_overrides = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Per-fighter eligibility set on the eligibility screen, overriding "
            'the category default. Shape: {"<list_fighter_id>": "<state>"} where '
            "state is one of eligible / included / excluded. Only fighters the "
            "player changed from their default are stored; everyone else uses the "
            "computed default (see handlers.crew.crew_eligibility)."
        ),
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=DRAFT,
        help_text="Draft while being set up; locked once drawn at battle start.",
    )
    rating_selected = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "The crew's rating at the moment it was picked (locked). A record "
            "of intent, not what was fielded. Blank on a draft, and on crews "
            "locked before snapshotting existed."
        ),
    )
    rating_played = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "The crew's rating when the battle ended — what actually fought. "
            "Blank until then, and on battles ended before snapshotting existed."
        ),
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["list__name", "created"]
        verbose_name = "Crew"
        verbose_name_plural = "Crews"
        constraints = [
            # Conditional on archived=False so archiving a crew frees its gang to
            # get a fresh crew for the same battle. An archived crew is kept only
            # as a record; it must not block a replacement (matches the
            # CustomContentPackItem unique constraint's archived=False pattern).
            models.UniqueConstraint(
                fields=["battle", "list"],
                condition=models.Q(archived=False),
                name="unique_crew_per_gang_per_battle",
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
        """Who may create/edit/lock/archive this crew: the crew's own gang owner
        or the battle's arbitrator (battle owner or a campaign admin). Blocked
        while the battle or its campaign is archived, and once the crew itself is
        archived — an archived crew is a frozen record with no manage actions."""
        if not user or not user.is_authenticated:
            return False
        if self.archived:
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
        """``loadout_overrides`` reduced to the entries that still mean
        something for ``fighters``.

        Kept: an entry naming a set that still exists and still belongs to that
        fighter, and an explicit ``null`` (Default). Dropped: everyone not in
        ``fighters``, entries whose set has been deleted or belongs to someone
        else, and malformed leftovers. Called whenever the overrides are
        written, and again at lock, so the blob self-heals rather than
        accumulating junk.

        **Which roster you pass decides what survives.** Saving choices passes
        the whole gang (``crew_loadout_gang_fighters``), because a fighter who
        is only *temporarily* ineligible may be back by battle start and their
        choice must not be thrown away. The lock passes the eligible roster,
        because by then ineligibility is final for this battle.
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

    # --- rating & credits ------------------------------------------------
    #
    # Three values answer three different questions, and only the third is a
    # record of what happened:
    #
    #   selected (``rating_selected``, frozen at lock) — what did I pick?
    #   live     (computed)                            — what would I field now?
    #   played   (``rating_played``, frozen at end)    — what actually fought?
    #
    # A crew that is locked but hasn't fought yet reports **live**, not the
    # selection snapshot: when the battle is played the roster is printed and
    # fielded as the gang stands *then*, so a fighter who bought a weapon since
    # selection really does bring it. Underdog calculations are decided
    # pre-battle from what each side actually fields, so they need the live
    # figure too. Freezing exists to stop the record moving *after* the fight,
    # which is why ``rating_played`` is the only snapshot ``rating()`` returns.

    def _attendee_lines(self):
        """Per-member ``(cost, line)`` for the crew.

        Members are the single source of attendance at every stage: the chosen
        ones exist from selection time, the drawn ones join at lock. The
        fighters are loaded in one batch via ``with_related_data()`` so their
        costs compute from the prefetch cache rather than N+1 per fighter. Each
        member's equipment set is resolved against its fighter's own prefetched
        sets (so the set's assignments also come from the cache); a member with
        no set is costed at their whole kit.

        ``cost`` is the member's played rating once the battle has frozen one,
        falling back to the live figure; ``line["live_rating"]`` always carries
        what the fighter costs *now*, which is what the selection note is
        measured against. ``line`` is otherwise a small display dict (name,
        loadout, random flag, ids).
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
                member.rating_played if member.rating_played is not None else live_cost
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
        """The crew's fighter rating.

        Once the battle has ended, ``rating_played``: that is what fought, and
        it must never move again. Before that — draft or locked — the live sum
        of each member's cost scoped to the equipment set they bring, because
        that is what the gang would actually field right now. While the crew is
        a draft this only counts the chosen members: the random component is
        unknown until the draw at lock.

        ``rating_played`` is a **read-model snapshot on a virtual overlay
        object**, not a cost cache. The gang it was drawn from legitimately
        keeps changing after the battle (new weapons bought, equipment sets
        re-cut), which would otherwise silently move the rating of a battle
        already fought. Nothing here feeds gang rating, credits, the audit
        stream, or any cached cost: it is written once, when the battle ends,
        and never reconciled. Battles ended before this existed have no
        snapshot and go on computing live.
        """
        if self.rating_played is not None:
            return self.rating_played
        return self.live_rating()

    def live_rating(self):
        """The crew's rating recomputed from the fighters as they are *now* —
        what the gang would field if the battle were played today."""
        return sum(line["live_rating"] for _, line in self._attendee_lines())

    def live_member_ratings(self):
        """Map of member id → that member's live cost. The input to both
        snapshots (see ``handlers.crew.snapshot_crew_rating``)."""
        return {
            line["member_id"]: line["live_rating"] for _, line in self._attendee_lines()
        }

    def _note(self, live):
        """The selection note given a precomputed ``live`` rating (ignored once
        the battle has frozen a played rating). ``None`` when there is nothing
        to say."""
        if not self.is_locked or self.rating_selected is None:
            return None
        current = self.rating_played if self.rating_played is not None else live
        return {
            "selected": self.rating_selected,
            "current": current,
            "is_played": self.rating_played is not None,
            "differs": current != self.rating_selected,
        }

    def rating_note(self):
        """How the crew's headline rating relates to what was picked.

        ``None`` for a draft (nothing has been committed to yet) and for crews
        locked before selection was snapshotted. Otherwise ``{"selected",
        "current", "is_played", "differs"}``:

        - **locked, not yet played** — ``current`` is the live rating, and a
          difference means the gang has changed since selection. The live
          figure is the honest one (it is what would be fielded), so the note
          records the selection rather than correcting it.
        - **played** — ``current`` is what fought, and a difference preserves
          the fact that the crew changed between being picked and playing. The
          gang moving on *after* the battle is irrelevant here and deliberately
          not reported: it is not a discrepancy.
        """
        # Both early exits are checked before touching live_rating(), which
        # batch-loads every attendee: a draft has nothing to compare against,
        # and a played crew compares against its own snapshot. The battle page
        # asks every crew for its note, so computing live first would pay that
        # load per crew and then discard it.
        if not self.is_locked or self.rating_selected is None:
            return None
        if self.rating_played is not None:
            return self._note(None)
        return self._note(self.live_rating())

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
        """The crew's fighter rating plus its extra line items.

        NOT the rulebook's underdog-comparison quantity, despite the tempting
        name: scenarios compare the credits value of the *fighters* in each
        starting crew (Core Rulebook p238), and extras — tactics cards, hired
        help — never enter that comparison. The quantity to compare is
        :meth:`rating`; this sum (rating + extras) is only a headline total.
        """
        return self.rating() + self.extras_total()

    def receipt(self):
        """Columnar receipt for the crew page, grouped into a Fighters section
        and an Extras section. Each fighter contributes to the Rating column;
        each extra falls in the Credits, Allowance, or Free column by how it is
        paid for. Returns the grouped rows, the per-column totals (for the
        annotated subtotal rows), the grand total (the crew's credits value),
        and the selection note. One batch load; the extras are computed live and
        only the two rating snapshots are ever persisted."""
        lines = self._attendee_lines()
        attendees = [{"rating": cost, **line} for cost, line in lines]
        # The played snapshot is the crew's rating once the battle has frozen
        # one; before that the per-member figures are live and sum to the same
        # thing.
        fighters_total = (
            self.rating_played
            if self.rating_played is not None
            else sum(cost for cost, _ in lines)
        )
        # The lines are already loaded, so the live figure is free here — no
        # need for rating_note()'s guard against computing it.
        note = self._note(sum(line["live_rating"] for _, line in lines))

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
            # None when there's nothing to say; otherwise what was picked, what
            # the headline number is now, and whether they differ.
            "note": note,
            # Draft crew with a draw still to roll: the random attendees aren't
            # known, so rating/total render as "?" and a "+spec from the roll"
            # row stands in for them.
            "pending_roll": self.pending_roll,
            "random_spec": self.random_spec,
        }


class CrewMember(AppBase):
    """An attendee of a crew: a fighter with a battle loadout.

    Chosen members exist from selection time (a draft crew already has them);
    drawn members are added by the random draw when the crew is locked; linked
    members are the vehicles and exotic beasts that ride in with their owner —
    never selected in their own right, enrolled by
    ``handlers.crew.sync_linked_crew_members`` whenever their owner is a member.
    Included members are hired guns / bounty hunters / house agents / dramatis
    personae / hive scum — they join the crew regardless of the selection method
    ("You Get What You Pay For": not counted during the choose step, added on
    top), enrolled by ``handlers.crew.sync_included_crew_members``.
    """

    CHOSEN = "chosen"
    DRAWN = "random"
    LINKED = "linked"
    INCLUDED = "included"
    SOURCE_CHOICES = [
        (CHOSEN, "Chosen"),
        (DRAWN, "Drawn at random"),
        (LINKED, "Linked to owner"),
        (INCLUDED, "Always included"),
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
    rating_selected = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "This member's contribution to the crew's rating at the moment the "
            "crew was picked (locked). Blank until then."
        ),
    )
    rating_played = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "This member's contribution to what actually fought, frozen when "
            "the battle ended. Blank until then."
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
        battle ended, or, before that, the fighter's cost scoped to the
        equipment set they bring (their whole kit when no set is chosen) — what
        they would field right now.

        Mirrors :meth:`Crew.rating`, including why the selection snapshot isn't
        what's returned. Like it, ``rating_played`` is a read-model record of
        what was fielded: it never feeds gang rating, credits, or any cost
        cache.
        """
        if self.rating_played is not None:
            return self.rating_played
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


class CrewStashItem(AppBase):
    """A stash item this crew brings to its battle.

    The gang's stash holds equipment as assignments on the stash fighter; a row
    here marks one of those assignments as coming along. Only *optional* items
    are stored — equipment whose content is flagged ``crew_always_brought``
    (e.g. the Iron Automaton) joins every crew automatically and is computed,
    never stored, so it can't be left behind.

    Deliberately not lock-gated: gang terrain and the like are picked after the
    crew is drawn, so the stash selection stays editable on a locked crew. Its
    value therefore counts in the live totals but never in the frozen rating
    snapshots (which cover members only).
    """

    crew = models.ForeignKey(
        Crew,
        on_delete=models.CASCADE,
        related_name="stash_items",
        help_text="The crew bringing this stash item.",
    )
    assignment = models.ForeignKey(
        "core.ListFighterEquipmentAssignment",
        on_delete=models.CASCADE,
        related_name="crew_stash_items",
        help_text="The stash equipment assignment being brought.",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["created"]
        verbose_name = "Crew Stash Item"
        verbose_name_plural = "Crew Stash Items"
        constraints = [
            models.UniqueConstraint(
                fields=["crew", "assignment"],
                name="unique_stash_item_per_crew",
            )
        ]

    def __str__(self):
        return f"{self.assignment} for {self.crew}"
