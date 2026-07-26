"""Battle crews — the virtual sub-gang assigned to a battle (#1346).

A :class:`Crew` is a read-model overlay on a gang for a single battle: which
fighters attend (with which equipment set), plus credit-consuming extras
(tactics cards, hired guns). It is deliberately NOT a second ``List``: its
rating and credits value are computed on the fly, and it never writes to the
gang's cost caches.

ONE EXCEPTION, and it is deliberate: when the battle starts, each crew's
**Spending** is taken from its gang's credits and logged as a campaign action
(``handlers.battle.charge_crew_spending``). That is the only write a crew makes
to canonical gang data. Everything else — the ratings, the balancing allowance,
free extras — stays descriptive. If you are adding a crew field that moves real
money, it belongs in that one handler, at that one moment, and nowhere else.

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

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.core.models.base import AppBase

__all__ = [
    "Crew",
    "CrewMember",
    "CrewLineItem",
    "CrewStashItem",
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


def crew_fighter_cost(fighter, equipment_set=None):
    """What a fighter is worth to a crew.

    Normally the fighter's own cost. A card that comes from stash equipment
    flagged *treated as a fighter* (the Iron Automaton) is costed at zero as a
    fighter — the gang books its value against the equipment sitting in the
    stash — so the equipment's cost is added back here, otherwise fielding it
    would look free.

    Stash-held only, matching what the flag describes: the same equipment
    carried by a regular fighter is already priced into *that* fighter's cost,
    so adding it again for their linked child would count it twice. Callers load
    the fighters via ``handlers.crew.with_crew_cost_data`` to keep this off the
    N+1 path.
    """
    cost = fighter.cost_int_for_equipment_set(equipment_set)
    if fighter.is_captured or fighter.is_sold_to_guilders:
        # Worth nothing to its old gang; adding the equipment back would
        # contradict the zero its own cost already reports.
        return cost
    for assignment in fighter.source_assignment.all():
        if (
            assignment.content_equipment.crew_treated_as_fighter
            and assignment.list_fighter.content_fighter.is_stash
        ):
            cost += assignment.cost_int_cached
    return cost


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
        # "Membership locked", not "Locked": what freezes is *who is in the
        # crew*. The loadouts they bring, the stash they carry and the extras
        # they are credited with all stay editable afterwards, and a bare
        # "Locked" was read as though the whole crew were finished.
        (LOCKED, "Membership locked"),
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

    # Where an extra's credits come from. Lives on CrewLineItem, and decides
    # which column it lands in on the crew sheet. Only PAY_CREDITS moves real
    # money, and only at battle start (see the module docstring).
    #
    # The stored value stays "allowance" while the label reads "Balancing":
    # balancing is what the column is called, and the underdog allowance is only
    # one source of it — House Patronage is another (see #1346 discussion).
    PAY_CREDITS = "credits"
    PAY_FREE = "free"
    PAY_ALLOWANCE = "allowance"
    PAYMENT_CHOICES = [
        (PAY_CREDITS, "Gang credits"),
        (PAY_FREE, "Free"),
        (PAY_ALLOWANCE, "Balancing"),
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
    ready_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "When the gang declared this crew ready. Blank until they say so, "
            "and cleared again if they withdraw it. Deliberately separate from "
            "status: locking freezes who is in the crew and cannot be undone, "
            "while readiness just says the player has finished setting up."
        ),
    )
    ready_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crews_marked_ready",
        help_text="Who declared the crew ready.",
    )
    credits_charged = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Credits actually taken from the gang when the battle started. May "
            "be less than the crew's spending if the gang could not cover it — "
            "the balance is floored at zero rather than going negative, so the "
            "difference is a real debt the arbitrator has to settle."
        ),
    )
    credits_owed = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "What the crew's spending came to when the battle charged it. "
            "Snapshotted because the extras stay editable afterwards: the "
            "shortfall is a fact about that moment, and recomputing it live "
            "would invent a debt when an extra is added later, or hide a real "
            "one when an extra is removed."
        ),
    )
    credits_charged_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "When the battle charged this crew's spending. Also the idempotency "
            "guard: a crew that has been charged is never charged again."
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
    def is_ready(self):
        """Whether the gang has declared this crew ready for the battle."""
        return self.ready_at is not None

    @property
    def is_charged(self):
        """Whether the battle has already taken this crew's spending."""
        return self.credits_charged_at is not None

    def credits_shortfall(self):
        """Spending the gang could not cover when the battle charged it.

        Zero until the crew is charged, and zero when it paid in full. The
        charge floors the gang's balance at zero rather than taking it negative,
        so anything left over is a real debt: the crew sheet says the gang spent
        this much, and the ledger says it only paid part of it. Surfaced rather
        than left to a campaign action nobody reads.

        Both halves are snapshots taken at charge time. Measuring against a live
        ``spending_total()`` would move with edits made afterwards — adding an
        extra would conjure a debt that was never owed, and deleting one would
        erase a debt that was.
        """
        if self.credits_charged is None or self.credits_owed is None:
            return 0
        return max(0, self.credits_owed - self.credits_charged)

    def ready_blocker(self, owed=None):
        """Why this crew can't be marked ready, or ``None`` if it can.

        Only one rule today: the gang has to be able to cover what the crew
        spends. Returns the numbers rather than a sentence so the template can
        phrase it and the handler can reuse the same check.

        ``owed`` lets a caller that has already totalled the spending pass it in
        — the crew sheet builds a receipt first, and recomputing here would walk
        the line items a second time for a number it already has.
        """
        if owed is None:
            owed = self.spending_total()
        # Floored like the charge floors it: a gang already in the red can put
        # nothing towards this, and a negative "available" would report a
        # shortfall larger than the crew is actually spending.
        available = max(0, self.list.credits_current)
        if owed <= available:
            return None
        return {"owed": owed, "available": available, "short": owed - available}

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
    def over_picked(self):
        """More chosen fighters than the scenario's count. Indicative only — the
        count is a guideline, so this drives warnings, never blocking."""
        return self.custom_count is not None and (
            self.members.filter(source=CrewMember.CHOSEN).count() > self.custom_count
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
        loaded = (
            ListFighter.objects.with_related_data()
            .prefetch_related(
                "source_assignment__content_equipment",
                "source_assignment__list_fighter__content_fighter",
            )
            .in_bulk([m.list_fighter_id for m in members])
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
                crew_fighter_cost(fighter, equipment_set) if fighter is not None else 0
            )
            # Whether this fighter actually has a choice of equipment sets —
            # the sheet only names the card when there were options.
            has_sets = (
                bool(fighter.equipment_sets.all()) if fighter is not None else False
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
                        "has_sets": has_sets,
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
        chosen so far. Either way the linked fighter cards of the stash items the
        crew brings (a gun emplacement) print alongside the crew's own cards. A
        draft with no members (a whole-gang crew, or one whose attendees are all
        still to be drawn) has nothing specific to narrow to, so returns ``None``
        and the print falls back to the whole gang.
        """
        ids = list(self.members.values_list("list_fighter_id", flat=True))
        if not self.is_locked and not ids:
            return None
        return ids + self._stash_child_fighter_ids()

    def stash_rows(self):
        """The gang's stash equipment as crew-stash rows, for the Stash tab and
        the crew sheet.

        One row per (non-archived) assignment on the gang's stash fighter:
        ``{assignment, name, cost, child_fighter, brought}``, ``brought`` when
        the crew has a :class:`CrewStashItem` for it. ``child_fighter`` is the
        linked fighter card some equipment spawns (a gun emplacement) —
        displayed like a fighter, rated at the equipment's cost.

        Equipment flagged *treated as a fighter* (the Iron Automaton) is not a
        stash item at all: its card is picked on the crew's eligibility and
        selection screens like any other fighter, so it is left out here.
        """
        from gyrinx.core.models.list import ListFighterEquipmentAssignment

        stash = self.list.stash_fighter
        if stash is None:
            return []
        brought_ids = set(self.stash_items.values_list("assignment_id", flat=True))
        rows = []
        assignments = (
            ListFighterEquipmentAssignment.objects.filter(
                list_fighter=stash,
                archived=False,
            )
            # Only a flagged assignment that actually brings a card leaves the
            # stash — flagged equipment with no linked fighter has nowhere else
            # to appear, so it stays a normal stash item.
            .exclude(
                content_equipment__crew_treated_as_fighter=True,
                child_fighter__isnull=False,
            )
            .with_related_data()
            .select_related("child_fighter__content_fighter")
            .order_by("content_equipment__name")
        )
        for assignment in assignments:
            rows.append(
                {
                    "assignment": assignment,
                    "name": assignment.content_equipment.name,
                    "cost": assignment.cost_int_cached,
                    "child_fighter": assignment.child_fighter,
                    "brought": assignment.id in brought_ids,
                }
            )
        return rows

    def stash_lines(self):
        """Just the *brought* stash rows plus their total — the crew sheet's
        Stash section. Computed live (the selection is editable even on a locked
        crew), so it counts in the live totals but never in the frozen rating
        snapshots."""
        rows = [row for row in self.stash_rows() if row["brought"]]
        return {"rows": rows, "total": sum(row["cost"] for row in rows)}

    def _stash_child_fighter_ids(self):
        """Ids of the fighter cards linked to the stash items this crew brings."""
        return [
            row["child_fighter"].id
            for row in self.stash_lines()["rows"]
            if row["child_fighter"] is not None
        ]

    def extras_total(self):
        """Total the crew's extras cost the gang, whatever the source."""
        return sum(item.cost for item in self.line_items.all())

    def extras_rating(self, *, exclude_balancing=False):
        """What the crew's extras add to its rating.

        Rating and cost are separate facts: a free hired gun adds its full value
        here while costing nothing, and a tactics card costs credits while
        adding nothing. ``exclude_balancing`` drops the entries the allowance
        paid for, which is what makes the pre-balancing figure pre-balancing.
        """
        return sum(
            item.rating_value
            for item in self.line_items.all()
            if not (exclude_balancing and item.payment == self.PAY_ALLOWANCE)
        )

    def spending_total(self):
        """What the gang paid out of its own pocket for this crew's extras — the
        Spending column.

        Only ``PAY_CREDITS`` items. Anything drawn from the balancing allowance
        or handed over free is not the gang's own outlay and belongs in its own
        column.
        """
        return sum(
            item.cost
            for item in self.line_items.all()
            if item.payment == self.PAY_CREDITS
        )

    def balancing_total(self):
        """The pre-battle balancing allowance this crew spent — the Balancing
        column. Only ``PAY_ALLOWANCE`` items."""
        return sum(
            item.cost
            for item in self.line_items.all()
            if item.payment == self.PAY_ALLOWANCE
        )

    def rating_before_balancing(self, stash_total=None):
        """The crew's fundamental rating: its fighters, the stash gear it
        brings, and what its extras are worth — before any allowance.

        This is the quantity dealt against the other crews in the battle to
        decide who is the underdog and what balancing they are owed, so it is
        the figure the battle page compares. Entries the allowance paid for are
        deliberately *not* in it: the allowance is compensation for the gap, so
        counting what it bought would shrink the very gap that earned it — a
        crew would be penalised for having been behind.

        Free entries ARE in it. They cost nothing, but what they add to the
        table is real: "a Hired Gun increases the gang's Rating in the same way
        as any other fighter", and the scenario comparison is on the credits
        value of the fighters in the starting crew, not on what was paid for
        them.

        ``stash_total`` lets a caller rating several crews at once pass in the
        figure from :func:`handlers.crew.crew_stash_totals`, which loads them in
        a single batch; omitted, the crew works out its own.
        """
        if stash_total is None:
            stash_total = self.stash_lines()["total"]
        return self.rating() + stash_total + self.extras_rating(exclude_balancing=True)

    def rating_after_balancing(self, stash_total=None):
        """What the crew fields once its balancing allowance is counted.

        Compared against the other crews' post-balancing ratings, this shows
        whether the balancing actually closed the gap it was granted for. Adds
        what the allowance bought — its rating value, not the price paid, which
        can differ.
        """
        if stash_total is None:
            stash_total = self.stash_lines()["total"]
        return self.rating() + stash_total + self.extras_rating()

    def receipt(self):
        """Columnar receipt for the crew sheet, grouped into Fighters, Stash and
        Spending & balancing sections.

        Fighters and brought stash items land in the Fighters & Stash column;
        each extra lands in Spending or Balancing by how it is paid for, with a
        free extra shown in Spending at 0¢ rather than in a column of its own.
        The grand total is what the sheet calls "Total (after balancing)" —
        exactly :meth:`rating_after_balancing`. Both count what every extra is
        *worth*, including the free ones, and neither counts what was paid.

        One batch load. The extras and stash are computed live (the stash
        selection stays editable after the lock); only the two rating snapshots
        are ever persisted.
        """
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
        credits_total = allowance_total = 0
        extras_rating_total = extras_rating_before = 0
        for item in self.line_items.all():
            # Every entry shows what it adds to rating. What it *cost* goes in
            # whichever payment column applies — a free entry shows an explicit
            # 0¢ under Spending, which is the visible proof it was a gift.
            credits = allowance = None
            if item.payment == self.PAY_ALLOWANCE:
                allowance = item.cost
                allowance_total += item.cost
            elif item.payment == self.PAY_FREE:
                credits = 0
            else:
                credits = item.cost
                credits_total += item.cost
            extras.append(
                {
                    "item": item,
                    "rating": item.rating_value,
                    "credits": credits,
                    "allowance": allowance,
                }
            )
            extras_rating_total += item.rating_value
            if item.payment != self.PAY_ALLOWANCE:
                extras_rating_before += item.rating_value

        stash = self.stash_lines()
        # The Rating column: fighters, the stash they bring, and what every
        # extra is worth. The payment columns are not added in — the entry's
        # value is already here, and counting the price too would double it.
        rating_total = fighters_total + stash["total"] + extras_rating_total
        total = rating_total
        return {
            "attendees": attendees,
            "extras": extras,
            "has_extras": bool(extras),
            # The stash items this crew brings — live, like the extras: the
            # selection can change even after the lock, so it never enters the
            # frozen rating snapshots.
            "stash": stash["rows"],
            "has_stash": bool(stash["rows"]),
            "stash_total": stash["total"],
            "fighters_total": fighters_total,
            "credits_total": credits_total,
            "allowance_total": allowance_total,
            # What the extras add to rating, and the same excluding whatever the
            # allowance paid for — the sheet's two rating figures.
            "extras_rating_total": extras_rating_total,
            "rating_total": rating_total,
            "rating_before_balancing": fighters_total
            + stash["total"]
            + extras_rating_before,
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
        return crew_fighter_cost(self.list_fighter, self.equipment_set)


class CrewLineItem(AppBase):
    """A credit-consuming extra attached to a crew (or one of its members).

    Generic on purpose: a tactics card is a crew-level item; a hired gun is a
    member plus a member-linked item.

    TWO INDEPENDENT AMOUNTS, and conflating them is the bug this model exists to
    avoid. ``rating_value`` is what the thing adds to the crew's rating;
    ``cost`` is what the gang pays for it. A hired gun taken for free is worth
    its full value on the table but costs nothing (Feigned Nobility, The Hand
    That Feeds You, A Mysterious Stranger, Heroes of High Anchor all work this
    way — "a Hired Gun increases the gang's Rating in the same way as any other
    fighter"). A tactics card is the mirror image: it costs credits and adds
    nothing, because rating counts fighters and their gear, not cards.

    ``payment`` says where the cost comes from, and whether it is real: gang
    credits are taken when the battle starts, while balancing and free entries
    are only ever recorded.
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
        help_text="What this is (e.g. 'Tactics Card').",
    )
    rating_value = models.PositiveIntegerField(
        default=0,
        help_text=(
            "What this adds to the crew's rating. Independent of what it cost: "
            "a hired gun taken for free still fights, so it still counts."
        ),
    )
    cost = models.PositiveIntegerField(
        default=0,
        help_text=(
            "What the gang pays for it, from whichever source ``payment`` "
            "names. Zero for a free entry."
        ),
    )
    payment = models.CharField(
        max_length=12,
        choices=Crew.PAYMENT_CHOICES,
        default=Crew.PAY_CREDITS,
        help_text=(
            "Where the credits come from. Gang credits are charged at battle "
            "start; balancing and free entries are recorded only."
        ),
    )
    reason = models.CharField(
        max_length=255,
        blank=True,
        help_text="Why, when free or from balancing.",
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
    here marks one of those assignments as coming along. Equipment flagged
    ``crew_treated_as_fighter`` (e.g. the Iron Automaton) is not a stash item —
    its fighter card is picked on the eligibility and selection screens instead.

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
