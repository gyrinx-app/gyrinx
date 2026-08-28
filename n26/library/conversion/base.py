"""The conversion discipline: plan, check, apply — the preview is the contract.

A conversion moves one hand-built choice system (an offer, its menu
collection, its chosen-kind rows) onto slots and picks without changing
what any page says. Three stages, the ingest discipline:

* ``plan()`` — each system's module reads the database and returns a
  frozen :class:`Plan`: typed steps, the gangs the system touches, and
  any problems. It never writes. ``plan.preview()`` says everything the
  apply would do, one line per step.
* ``apply(plan)`` — performs exactly the plan's steps in one
  transaction. Before writing it captures what every affected gang's
  pages say (``n26.core.capture``); after writing it captures again and
  **refuses** — unwinding the whole transaction — on any difference, and
  on any touched gang that no longer reconciles. A conversion that would
  change what a reader is told never lands.
* A plan whose system is absent (``plan.nothing_here``) applies as a
  no-op, so the migration that ships a conversion is safe on databases
  that never held the system — a fresh environment, a pack without it.

Pick rewrites touch ``Assignment`` rows outside ``operation()`` — the
one sanctioned place: a conversion moves no money. Nothing is created or
priced, columns change on existing free rows, the ledger is untouched,
and the reconcile assertion proves it gang by gang.

What the ledger *says*, though, is not untouched, and the captures do
not see it. The gang's history describes an old event by looking up what
its assignment names now, so moving an assignment from one kind to
another rewrites the wording of things that already happened. Every
conversion must check the history page against a converted assignment
and keep those words the same — see the note in ``n26/core/CLAUDE.md``.
"""

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field

from django.db import transaction

logger = logging.getLogger(__name__)


def carriers_of(modifier):
    """Everything carrying this modifier, across every library kind — a
    plan that detaches or deletes one must know it is not shared."""
    from django.apps import apps as django_apps

    found = []
    for model in django_apps.get_app_config("library").get_models():
        if not any(f.name == "modifiers" for f in model._meta.many_to_many):
            continue
        for row in model.objects.filter(modifiers=modifier):
            found.append((model.__name__, row))
    return found


def offers_of(carrier, kind):
    """The carrier's choice offers of one kind, by the kind's model name."""
    return [
        m
        for m in carrier.modifiers.all()
        if getattr(m, "offers_choice", None) is not None
        and m.offers_choice.of_kind.model == kind
    ]


def the_offer(carrier, kind, kind_word, said, problems):
    """The carrier's one offer of the kind, or a stated problem."""
    offers = offers_of(carrier, kind)
    if len(offers) != 1:
        problems.append(
            f"{said} carries {len(offers)} {kind_word} offers — expected one"
        )
        return None
    return offers[0]


def solely_carried(offer, carrier, problems):
    """Deleting an offer's modifier detaches it from every carrier at
    once, so the plan must know no third thing shares it — a sharer's
    gangs are outside the proven set and would lose their question
    unnoticed."""
    others = [
        f"{kind} “{row}”"
        for kind, row in carriers_of(offer)
        if not (kind == type(carrier).__name__ and row.pk == carrier.pk)
    ]
    if others:
        problems.append(
            f"“{offer.name}” is shared — also carried by " + ", ".join(others)
        )


def duplicate_names(rows):
    """Names two or more of the rows share. A pick is matched to its
    pickable by name, and a name is only unique within a pack and
    qualifier — so two live rows called the same thing would quietly
    become one pickable, and half the picks would land on the wrong
    one."""
    names = [row.name for row in rows]
    return sorted({name for name in names if names.count(name) > 1})


def refuse_if_granted(held, said, problems):
    """A carrier that arrives by grant has no assignment to find it by,
    so the gangs it reaches can be neither counted nor drawn into the
    spread a plan proves. The apply page would understate the change,
    and pages nothing checked would move — refuse instead, and whoever
    makes such a grant decides what a conversion ought to do.

    A kind that cannot be granted is skipped: asking the grant table
    about it is a FieldError, and there is nothing to find.
    """
    from n26.library.models import AddsAssignable, Modifier
    from n26.library.models.modifier import GRANTABLE_FIELDS

    path = f"library.{type(held).__name__}"
    field = next(
        (name for name, model in GRANTABLE_FIELDS.items() if model == path), None
    )
    if field is None:
        return
    for granter in Modifier.objects.filter(
        adds_assignable__in=AddsAssignable.objects.filter(**{field: held})
    ):
        if carriers_of(granter):
            problems.append(
                f"“{granter.name}” grants {said}, so the gangs it reaches "
                "cannot be counted or proven"
            )


def one_answer_per_question(picks):
    """One pick per question, and the spares left behind.

    The same question answered twice — a click that landed twice — shows
    on the page as the answer plus a spare line. Moving the answer keeps
    the page: the pick becomes a pick, and the spare goes on being the
    ordinary assignment it already is.
    """
    answers, spares, seen = [], [], set()
    for pick in picks:
        question = (pick.miniature_id, pick.caused_by_id)
        if question in seen:
            spares.append(pick)
        else:
            seen.add(question)
            answers.append(pick)
    return answers, spares


def spread(gang_ids, kinds, limit):
    """A sample wide enough to hold every shape, in a stable order.

    One from each kind, round and round, so no kind crowds the others
    out — a plentiful ordinary kind must not fill the sample before a
    later kind's only gang is seen. The odd shapes lead each round, and
    whatever room is left goes back around the kinds that still have
    gangs to give.
    """
    chosen, used = [], set()
    remaining = [list(wanted) for wanted in kinds]
    while len(chosen) < limit and any(remaining):
        for wanted in remaining:
            while wanted:
                gang_id = wanted.pop(0)
                if gang_id in used or gang_id not in gang_ids:
                    continue
                used.add(gang_id)
                chosen.append(gang_id)
                break
            if len(chosen) >= limit:
                break
    return chosen


class ConversionRefused(Exception):
    """The apply found the world changed by its own hand — or not shaped
    the way the plan promised — and unwound. The message says exactly
    what differed."""


@dataclass(frozen=True)
class CreateSlotType:
    name: str
    plural_name: str = ""
    allows_repeats: bool = True

    def say(self):
        refused = "" if self.allows_repeats else ", refusing repeats"
        return f"create slot type “{self.name}”{refused}"

    def perform(self, made):
        from n26.library.authoring import create_slot_type

        made.slot_types[self.name] = create_slot_type(
            self.name, plural_name=self.plural_name, allows_repeats=self.allows_repeats
        )


@dataclass(frozen=True)
class CreatePickable:
    name: str
    slot_type: str
    #: Modifier rows to move from the old kind's row onto the pickable —
    #: the same rows, so scopes, conditions and effects are untouched.
    moved_modifier_ids: tuple = ()
    #: The old row the modifiers come off, as (model label, pk).
    moved_from: tuple = ()
    #: The pickable's linked category, as (pk, name) — for a system
    #: whose whole payload is the link itself: a chosen-mode placement
    #: reads the chosen thing's ``category`` and nothing else.
    linked: tuple = ()
    #: What tells this one apart from another pickable of the same name
    #: — author-facing only, and never drawn for a player. A name is
    #: unique per pack and qualifier, so a system whose names are
    #: already spoken for by another slot type's pickables converts by
    #: qualifying its own.
    qualifier: str = ""

    def say(self):
        n = len(self.moved_modifier_ids)
        moved = f", moving {n} modifier{'' if n == 1 else 's'}" if n else ""
        linked = f", linked to category “{self.linked[1]}”" if self.linked else ""
        told = f", told apart as “{self.qualifier}”" if self.qualifier else ""
        return f"create pickable “{self.name}” ({self.slot_type}){moved}{linked}{told}"

    def perform(self, made):
        from django.apps import apps

        from n26.library.authoring import create_pickable
        from n26.library.models import Modifier

        linking = {"category_id": self.linked[0]} if self.linked else {}
        pickable = create_pickable(
            self.name,
            made.slot_types[self.slot_type],
            qualifier=self.qualifier,
            **linking,
        )
        if self.moved_modifier_ids:
            app_label, model_name = self.moved_from[0].split(".")
            old = apps.get_model(app_label, model_name).objects.get(
                pk=self.moved_from[1]
            )
            for modifier in Modifier.objects.filter(pk__in=self.moved_modifier_ids):
                old.modifiers.remove(modifier)
                pickable.modifiers.add(modifier)
        made.pickables[self.name] = pickable


@dataclass(frozen=True)
class CreatePicklist:
    name: str
    slot_type: str
    members: tuple = ()

    def say(self):
        return f"create picklist “{self.name}” offering {', '.join(self.members)}"

    def perform(self, made):
        from n26.library.authoring import create_picklist

        made.picklists[self.name] = create_picklist(
            self.name,
            made.slot_types[self.slot_type],
            members=[made.pickables[name] for name in self.members],
        )


@dataclass(frozen=True)
class CreateSlot:
    name: str
    slot_type: str
    picklist: str
    label: str = ""
    assigned_to: str = "bearer"
    min_picks: int = 1
    max_picks: int = 1
    #: Author-facing only. Two slots of one type that share a printed
    #: name (two doors, one question) need distinct qualifiers so the
    #: unique constraint holds.
    qualifier: str = ""
    #: How later steps name this slot in ``made.slots``. Empty uses
    #: ``name``. Two same-named slots need distinct keys.
    key: str = ""

    def say(self):
        told = f", told apart as “{self.qualifier}”" if self.qualifier else ""
        return (
            f"create slot “{self.name}” drawing on “{self.picklist}”, "
            f"pick landing on the {self.assigned_to}{told}"
        )

    def perform(self, made):
        from n26.library.authoring import create_slot

        made.slots[self.key or self.name] = create_slot(
            self.name,
            made.slot_types[self.slot_type],
            made.picklists[self.picklist],
            label=self.label,
            assigned_to=self.assigned_to,
            min_picks=self.min_picks,
            max_picks=self.max_picks,
            qualifier=self.qualifier,
        )


def _grant_scope(reach):
    """The scope a swapped grant reaches with.

    ``gang`` is ``targets_gang()`` (the gang and its models); ``gang_alone``
    keeps the grant on the gang's card; anything else is the bearer.
    """
    from n26.library.authoring import targets_gang, targets_gang_alone, targets_model

    if reach == "gang":
        return targets_gang()
    if reach == "gang_alone":
        return targets_gang_alone()
    return targets_model()


@dataclass(frozen=True)
class SwapCarrier:
    """The carrier stops offering and starts granting the slot."""

    carrier: tuple  # (model label, pk)
    carrier_name: str
    drop_modifier_id: object
    drop_modifier_name: str
    grant_name: str
    slot: str
    #: The scope the grant reaches with — "gang" for a question the gang
    #: asks (and whose payload may reach its models), "gang_alone" for a
    #: question that stays on the gang's card, "model" for one each
    #: bearer's card asks.
    reach: str = "gang_alone"
    #: When the offer was moved onto a pickable earlier in this plan,
    #: perform looks the pickable up here rather than the plan-time
    #: carrier — which by then no longer holds the modifier.
    made_pickable: str = ""

    def say(self):
        return (
            f"on {self.carrier_name}: replace “{self.drop_modifier_name}” "
            f"with a grant of the “{self.slot}” slot"
        )

    def perform(self, made):
        from django.apps import apps

        from n26.library.authoring import ef_adds, modifier
        from n26.library.models import Modifier

        if self.made_pickable:
            carrier = made.pickables[self.made_pickable]
            model_name = type(carrier).__name__
            expected = {(model_name, carrier.pk)}
        else:
            app_label, model_name = self.carrier[0].split(".")
            carrier = apps.get_model(app_label, model_name).objects.get(
                pk=self.carrier[1]
            )
            expected = {(model_name, self.carrier[1])}
        dropped = Modifier.objects.get(pk=self.drop_modifier_id)
        # The plan proved this modifier solely carried, but the plan was
        # read outside this transaction: a carrier attached since would
        # be detached silently by the delete below. Prove it again here,
        # where the snapshot holds.
        holders = {(kind, row.pk) for kind, row in carriers_of(dropped)}
        if holders != expected:
            raise ConversionRefused(
                f"“{self.drop_modifier_name}” is no longer carried only by "
                f"{self.carrier_name} — the world moved since the plan was made"
            )
        scope_row, effect_row = dropped.scope, dropped.effect
        carrier.modifiers.remove(dropped)
        dropped.delete()
        scope_row.delete()
        effect_row.delete()
        modifier(
            self.grant_name,
            _grant_scope(self.reach),
            ef_adds(made.slots[self.slot]),
            attach_to=carrier,
        )


@dataclass(frozen=True)
class SwapSharedCarrier:
    """One offer shared by many carriers becomes one shared grant.

    The offer modifier is a single row every carrier holds, so dropping
    it detaches all of them at once — which is why the plan proves the
    carriers are exactly the ones named here before this step exists.
    The grant is one shared modifier too, so the factoring the authors
    chose is preserved: one question's wiring, held in one place.
    """

    carriers: tuple  # ((model label, pk), ...) — every carrier, proven
    carriers_said: str
    drop_modifier_id: object
    drop_modifier_name: str
    grant_name: str
    slot: str
    #: Same reach vocabulary as :class:`SwapCarrier`.
    reach: str = "model"

    def say(self):
        return (
            f"on {self.carriers_said}: replace the shared "
            f"“{self.drop_modifier_name}” with a shared grant of the "
            f"“{self.slot}” slot"
        )

    def perform(self, made):
        from django.apps import apps

        from n26.library.authoring import attach_modifiers_to, ef_adds, modifier
        from n26.library.models import Modifier

        rows = [
            apps.get_model(*label.split(".")).objects.get(pk=pk)
            for label, pk in self.carriers
        ]
        dropped = Modifier.objects.get(pk=self.drop_modifier_id)
        # The plan proved exactly these carriers, but the plan was read
        # outside this transaction: a carrier attached since would be
        # detached silently by the delete below. Prove it again here,
        # where the snapshot holds.
        holders = {(kind, row.pk) for kind, row in carriers_of(dropped)}
        named = {(label.split(".")[1], pk) for label, pk in self.carriers}
        if holders != named:
            raise ConversionRefused(
                f"“{self.drop_modifier_name}” is no longer carried by exactly "
                f"{self.carriers_said} — the world moved since the plan was made"
            )
        scope_row, effect_row = dropped.scope, dropped.effect
        for carrier in rows:
            carrier.modifiers.remove(dropped)
        dropped.delete()
        scope_row.delete()
        effect_row.delete()
        grant = modifier(
            self.grant_name,
            _grant_scope(self.reach),
            ef_adds(made.slots[self.slot]),
            attach_to=rows[0],
        )
        for carrier in rows[1:]:
            attach_modifiers_to(carrier, [grant])


@dataclass(frozen=True)
class ArchivePick:
    """A stored pick archived in place — the declared ledger change for
    a printed “None” that an optional slot already says with nothing
    chosen. Already-archived picks stay archived; this does not revive
    them. No money, no event: the conversion exception."""

    assignment_id: object
    gang: str
    name: str = "None"

    def say(self):
        return f"archive pick {self.assignment_id} ({self.gang}) — “{self.name}”"

    def perform(self, made):
        from n26.core.models import Assignment

        pick = Assignment.objects.get(pk=self.assignment_id)
        if not pick.archived:
            pick.archive()


@dataclass(frozen=True)
class RewritePick:
    """One stored choice, re-said as a pick: the old kind's column moves
    to ``pickable``, the anchor it already hangs from (``caused_by``)
    becomes the choice it settles, and the slot is named."""

    assignment_id: object
    old_column: str
    pickable: str
    slot: str
    gang: str

    def say(self):
        return f"rewrite pick {self.assignment_id} ({self.gang}) -> “{self.pickable}”"

    def perform(self, made):
        from n26.core.models import Assignment

        pick = Assignment.objects.get(pk=self.assignment_id)
        pick.pickable = made.pickables[self.pickable]
        pick.chosen_for_id = pick.caused_by_id
        pick.chosen_for_slot = made.slots[self.slot]
        # The question it used to answer is not the one it answers now,
        # and a pick naming both a slot and an offer says two things.
        pick.chosen_for_offer = None
        setattr(pick, self.old_column, None)
        pick.save()


@dataclass(frozen=True)
class Retire:
    """An old row the system no longer needs, deleted by identity."""

    model: str  # app_label.ModelName
    pk: object
    name: str

    def say(self):
        return f"retire {self.model} “{self.name}”"

    def perform(self, made):
        from django.apps import apps

        app_label, model_name = self.model.split(".")
        apps.get_model(app_label, model_name).objects.get(pk=self.pk).delete()


@dataclass
class _Made:
    """What the apply has created so far, by the plan's own names."""

    slot_types: dict = field(default_factory=dict)
    picklists: dict = field(default_factory=dict)
    pickables: dict = field(default_factory=dict)
    slots: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Plan:
    system: str
    steps: tuple = ()
    #: The gangs the apply proves unchanged before committing — a spread
    #: chosen by the system's own plan to hold every shape it comes in,
    #: not every gang it reaches. Rendering everyone with the transaction
    #: open is the part that used to take minutes; a few hundred row
    #: updates do not.
    gang_ids: tuple = ()
    problems: tuple = ()
    #: How many gangs the change reaches in all, proven or not.
    reaches: int = 0
    #: Every gang the write reaches: locked before capture, reconciled
    #: after. Broader than ``gang_ids`` (the spread whose pages are
    #: compared). Empty means "the spread is everyone".
    holder_ids: tuple = ()
    #: Assignments the plan deliberately leaves as they are.
    left_alone: int = 0
    #: True when the system simply is not here — nothing to convert and
    #: nothing wrong: the apply is a clean no-op.
    nothing_here: bool = False
    #: Choice pairs this conversion treats as unanswered after the write.
    #: Archiving a printed “None” leaves the same question with nothing
    #: settled; capture otherwise sees the stored name become "". Each
    #: pair is ``(kind_label, chosen)``.
    unanswered_as: tuple = ()

    @property
    def ok(self):
        return not self.problems

    def preview(self):
        if self.nothing_here:
            return [f"[{self.system}] nothing to convert — the system is not here"]
        lines = [f"[{self.system}] {step.say()}" for step in self.steps]
        if self.left_alone:
            lines.append(
                f"[{self.system}] leave {self.left_alone} spare assignment"
                f"{'' if self.left_alone == 1 else 's'} exactly as they are"
            )
        reaches = self.reaches or len(self.holder_ids) or len(self.gang_ids)
        many = "gangs read" if reaches != 1 else "gang reads"
        lines.append(
            f"[{self.system}] prove {len(self.gang_ids)} of {reaches} reached "
            f"{many} the same, or refuse"
        )
        holders = self.holder_ids or self.gang_ids
        if holders:
            n = len(holders)
            lines.append(
                f"[{self.system}] reconcile all {n} reached "
                f"gang{'' if n == 1 else 's'}, or refuse"
            )
        return lines


def apply(plan):
    """Perform exactly the plan, prove the pages unchanged, or refuse.

    Returns the report lines. Raises :class:`ConversionRefused` — after
    unwinding everything — if the plan carries problems, any affected
    gang's pages change, or any touched gang stops reconciling.
    """
    if plan.problems:
        raise ConversionRefused(
            f"[{plan.system}] not applied: " + "; ".join(plan.problems)
        )
    if plan.nothing_here:
        return list(plan.preview())

    report = list(plan.preview())
    _perform(plan, report)
    report.append(f"[{plan.system}] applied; every page reads the same")
    return report


#: What Postgres may call an isolation level. The restore has to be
#: written into the statement rather than passed as a value, so what
#: goes in is checked against this rather than trusted — an answer
#: nobody expected should stop the run, not travel into SQL.
ISOLATION_LEVELS = frozenset(
    {"read uncommitted", "read committed", "repeatable read", "serializable"}
)


@contextmanager
def _one_snapshot():
    """Ask for the whole run to read one unchanging view of the database.

    The proof compares what the pages said before with what they say
    after, and takes any difference to be this conversion's doing. On a
    live database that only holds if both readings are of the same world.
    Proving hundreds of gangs takes minutes and players go on playing
    throughout, so reading whatever is committed at the time — the
    ordinary way — puts their purchases in the second reading, and the
    conversion is blamed for a hazard suit somebody bought while it
    worked, refusing for a reason nobody can act on.

    Reading from one snapshot instead, what differs is what the run did.
    Somebody changing an assignment it also writes ends it in a refusal
    rather than a guess, which is the right ending for work that cannot
    be half done. Set on the session, because a transaction's isolation can only
    be chosen before it has read anything, and put back afterwards so a
    pooled connection is handed on as it was found.
    """
    from django.db import connection

    outermost = not connection.in_atomic_block
    if not (outermost and connection.vendor == "postgresql"):
        # Nested inside a transaction somebody else opened — a test, a
        # shell. Isolation can only be chosen before a transaction reads
        # anything, so it is theirs to set and too late to ask here. That
        # is not the same as being safe: at the ordinary level each
        # statement reads afresh, so a caller nesting this while players
        # are writing would not get the one snapshot promised above.
        # Nothing does that today — a conversion from the console or the
        # command opens the transaction itself.
        yield
        return
    with connection.cursor() as cursor:
        cursor.execute("SHOW default_transaction_isolation")
        was = cursor.fetchone()[0]
        if was.lower() not in ISOLATION_LEVELS:
            raise ConversionRefused(
                f"the database calls its isolation “{was}”, which is not a "
                "level this knows how to put back"
            )
        cursor.execute(
            "SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL REPEATABLE READ"
        )
    try:
        yield
    finally:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL {was}"
                )
        except Exception:
            # Putting the setting back is courtesy to the next borrower of
            # this connection, and must never be the thing the caller hears
            # about. A run that ended badly can leave the connection unable
            # to answer at all — and one that cannot answer is also one
            # nobody will be handed again.
            logger.warning(
                "could not put the isolation level back to %s", was, exc_info=True
            )


def _canonicalize_unanswered(state, pairs):
    """Rewrite captured choices so listed ``(kind, chosen)`` pairs read
    as unanswered. A conversion that archives a printed None in favour
    of an optional slot uses this rather than weakening ``differences``
    for every caller."""
    if not pairs:
        return state
    equivalent = set(pairs)

    def choices(rows):
        return sorted(
            (kind, "") if (kind, chosen) in equivalent else (kind, chosen)
            for kind, chosen in rows
        )

    rewritten = dict(state)
    rewritten["choices"] = choices(state["choices"])
    rewritten["models"] = {
        model_id: {**model, "choices": choices(model["choices"])}
        for model_id, model in state.get("models", {}).items()
    }
    return rewritten


def _perform(plan, report):
    from n26.core.capture import differences, gang_state
    from n26.core.models import Gang
    from n26.core.reconcile import assert_reconciled

    with _one_snapshot(), transaction.atomic():
        lock_ids = plan.holder_ids or plan.gang_ids
        list(Gang.objects.filter(pk__in=lock_ids).order_by("pk").select_for_update())
        before = {
            str(gang.pk): gang_state(gang)
            for gang in Gang.objects.filter(pk__in=plan.gang_ids)
        }
        made = _Made()
        for step in plan.steps:
            try:
                step.perform(made)
            except Exception as failed:
                # A step that cannot be performed is a refusal too: the
                # command and the migration both promise words, never a
                # traceback, and the transaction unwinds either way.
                raise ConversionRefused(
                    f"[{plan.system}] failed at “{step.say()}”: {failed}"
                ) from failed
        # Fresh instances: the steps may have moved column-backed facts,
        # and a stale row would compare stale with stale.
        after = {
            str(gang.pk): gang_state(gang)
            for gang in Gang.objects.filter(pk__in=plan.gang_ids)
        }
        changed = differences(
            {
                key: _canonicalize_unanswered(state, plan.unanswered_as)
                for key, state in before.items()
            },
            {
                key: _canonicalize_unanswered(state, plan.unanswered_as)
                for key, state in after.items()
            },
        )
        if changed:
            raise ConversionRefused(
                f"[{plan.system}] refused — the pages would change:\n  "
                + "\n  ".join(changed)
            )
        for gang in Gang.objects.filter(pk__in=lock_ids):
            try:
                assert_reconciled(gang)
            except Exception as failed:
                raise ConversionRefused(
                    f"[{plan.system}] refused — {gang} no longer reconciles: {failed}"
                ) from failed
