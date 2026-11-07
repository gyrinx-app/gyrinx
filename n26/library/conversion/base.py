"""Convert stored choice systems to slots and picks with transactional checks.

Planners read content and return frozen steps, affected gangs and problems.
``apply`` executes those steps in one transaction. It compares captured pages
for the plan's sample and reconciles every touched gang before committing.
An absent system is a no-op.

Conversions may rewrite free assignments outside ``operation()``. They create
no purchase and change no recorded prices or ledger entries. History text
still needs separate verification because it resolves the assignment's
current content kind. See n26/core/AGENTS.md.

``unanswered_as`` allows a stored "None" choice to compare as an unanswered
optional slot. Check the planned archives separately by assignment identity
because page comparison cannot distinguish a successful archive from a no-op.

Reconciliation queries run for every affected gang while locks remain held.
Count gangs and time the complete apply on a realistic database before a
production run. Local timings omit production database network latency.
"""

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field

from django.db import transaction

logger = logging.getLogger(__name__)


def carriers_of(modifier):
    """Find all library carriers of a modifier before detaching or deleting it."""
    from django.apps import apps as django_apps

    found = []
    for model in django_apps.get_app_config("library").get_models():
        if not any(f.name == "modifiers" for f in model._meta.many_to_many):
            continue
        for row in model.objects.filter(modifiers=modifier):
            found.append((model.__name__, row))
    return found


def offers_of(carrier, kind):
    """Find a carrier's offers for the named model kind."""
    return [
        m
        for m in carrier.modifiers.all()
        if getattr(m, "offers_choice", None) is not None
        and m.offers_choice.of_kind.model == kind
    ]


def the_offer(carrier, kind, kind_word, said, problems):
    """Return a unique matching offer or append a planning problem."""
    offers = offers_of(carrier, kind)
    if len(offers) != 1:
        problems.append(
            f"{said} carries {len(offers)} {kind_word} offers — expected one"
        )
        return None
    return offers[0]


def solely_carried(offer, carrier, problems):
    """Reject an offer shared with carriers outside this conversion's checked set."""
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
    """Find duplicate names that make name-based pickable matching ambiguous."""
    names = [row.name for row in rows]
    return sorted({name for name in names if names.count(name) > 1})


def refuse_if_granted(held, said, problems):
    """Reject granted carriers whose affected gangs cannot be found through assignments.

    Skip ungrantable kinds rather than querying a nonexistent grant field.
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
    """Partition picks into the first per miniature and cause, and the remaining duplicates.

    Convert only the first; retain duplicate assignments to preserve existing display.
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
    """Choose a stable sample round-robin across gang groups up to ``limit``.

    Earlier groups receive priority within each round without filling the whole
    sample before later groups are considered.
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
    """A conversion failed validation and rolled back; the message identifies the difference."""


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
    #: An author-only qualifier distinguishes same-named pickables across slot types.
    #: Names and qualifiers are unique together within a pack.
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
    #: Author-only qualifier distinguishing same-named slots of one type.
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
    """Resolve gang, gang-alone or bearer scope for the replacement grant."""
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
    #: Replacement scope: gang broadcasts to members; gang_alone stays on the gang;
    #: model affects the carrier's model.
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
        # Recheck exclusive carriage inside the snapshot before deleting the offer;
        # the plan was built outside this transaction.
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
    """Replace one shared offer with one shared grant for the same carriers.

    Validate the exact carrier set before deleting the offer, preserving shared
    modifier structure.
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
        # Recheck the complete shared carrier set inside the snapshot before deletion.
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
    """Archive a stored "None" choice without a ledger entry or event.

    Existing archives remain archived. The plan declares this optional-choice
    normalisation so page comparison can treat it as unanswered.
    """

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
    """Replace a stored choice's content kind with a pickable and slot.

    Use the existing ``caused_by`` anchor as the choice being answered.
    """

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
        # Clear the old offer reference so the pick identifies only its new slot.
        pick.chosen_for_offer = None
        setattr(pick, self.old_column, None)
        pick.save()


@dataclass(frozen=True)
class Retire:
    """Delete an obsolete conversion source by model label and primary key."""

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
    """Library records created so far, keyed by the names used in plan steps."""

    slot_types: dict = field(default_factory=dict)
    picklists: dict = field(default_factory=dict)
    pickables: dict = field(default_factory=dict)
    slots: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Plan:
    system: str
    steps: tuple = ()
    #: Sample gang identifiers whose captured pages are compared before commit.
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
    """Perform the plan, verify captured pages and reconciliation, then return report lines.

    Raise ``ConversionRefused`` after rollback for plan problems, changed sampled
    pages, unapplied archives or an unreconciled touched gang.
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


#: Allowlisted PostgreSQL isolation names for restoring the session setting.
#: SQL cannot bind an isolation level as a value.
ISOLATION_LEVELS = frozenset(
    {"read uncommitted", "read committed", "repeatable read", "serializable"}
)


@contextmanager
def _one_snapshot():
    """Use one database snapshot for before-and-after conversion checks.

    Read-committed isolation could include concurrent purchases only in the
    second capture and falsely attribute them to the conversion. A concurrent
    change to an assignment this conversion also writes must fail the transaction.

    Set isolation on the session before opening a transaction and restore it
    afterwards so pooled connections retain their previous setting.
    """
    from django.db import connection

    outermost = not connection.in_atomic_block
    if not (outermost and connection.vendor == "postgresql"):
        # A caller-owned transaction must set isolation before its first read.
        # This helper cannot change it; read-committed nesting would not provide the
        # snapshot required for concurrent production use.
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
            # Restore the connection setting without masking the original failure.
            # A broken connection cannot be reused by the pool.
            logger.warning(
                "could not put the isolation level back to %s", was, exc_info=True
            )


def _assert_archives_landed(plan):
    """Verify every planned archive by assignment identity.

    Optional-choice normalisation makes page comparison insufficient for this check.
    """
    from n26.core.models import Assignment

    wanted = [
        step.assignment_id for step in plan.steps if isinstance(step, ArchivePick)
    ]
    if not wanted:
        return
    landed = set(
        Assignment.objects.filter(pk__in=wanted, archived=True).values_list(
            "pk", flat=True
        )
    )
    missing = [pk for pk in wanted if pk not in landed]
    if missing:
        n = len(missing)
        raise ConversionRefused(
            f"[{plan.system}] refused — {n} planned archive"
            f"{'' if n == 1 else 's'} did not land"
        )


def _canonicalize_unanswered(state, pairs):
    """Normalise only the plan's declared ``(kind, chosen)`` pairs to unanswered choices."""
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
                # Wrap step failures as ConversionRefused after the transaction rolls back.
                raise ConversionRefused(
                    f"[{plan.system}] failed at “{step.say()}”: {failed}"
                ) from failed
        # unanswered_as makes a printed None compare equal to an unanswered
        # optional slot, so the proof cannot tell a landed archive from a
        # no-op. The planned rows are checked by identity instead.
        _assert_archives_landed(plan)
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
