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
"""

from dataclasses import dataclass, field

from django.db import transaction


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
        return f"create slot type “{self.name}”"

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

    def say(self):
        n = len(self.moved_modifier_ids)
        moved = f", moving {n} modifier{'' if n == 1 else 's'}" if n else ""
        return f"create pickable “{self.name}” ({self.slot_type}){moved}"

    def perform(self, made):
        from django.apps import apps

        from n26.library.authoring import create_pickable
        from n26.library.models import Modifier

        pickable = create_pickable(self.name, made.slot_types[self.slot_type])
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

    def say(self):
        return (
            f"create slot “{self.name}” drawing on “{self.picklist}”, "
            f"pick landing on the {self.assigned_to}"
        )

    def perform(self, made):
        from n26.library.authoring import create_slot

        made.slots[self.name] = create_slot(
            self.name,
            made.slot_types[self.slot_type],
            made.picklists[self.picklist],
            label=self.label,
            assigned_to=self.assigned_to,
            min_picks=self.min_picks,
            max_picks=self.max_picks,
        )


@dataclass(frozen=True)
class SwapCarrier:
    """The carrier stops offering and starts granting the slot."""

    carrier: tuple  # (model label, pk)
    carrier_name: str
    drop_modifier_id: object
    drop_modifier_name: str
    grant_name: str
    slot: str
    #: The scope the grant reaches with — "gang_alone" for a question the
    #: gang's card asks, "model" for one each bearer's card asks.
    reach: str = "gang_alone"

    def say(self):
        return (
            f"on {self.carrier_name}: replace “{self.drop_modifier_name}” "
            f"with a grant of the “{self.slot}” slot"
        )

    def perform(self, made):
        from django.apps import apps

        from n26.library.authoring import (
            ef_adds,
            modifier,
            targets_gang_alone,
            targets_model,
        )
        from n26.library.models import Modifier

        app_label, model_name = self.carrier[0].split(".")
        carrier = apps.get_model(app_label, model_name).objects.get(pk=self.carrier[1])
        dropped = Modifier.objects.get(pk=self.drop_modifier_id)
        scope_row, effect_row = dropped.scope, dropped.effect
        carrier.modifiers.remove(dropped)
        dropped.delete()
        scope_row.delete()
        effect_row.delete()
        scope = targets_gang_alone() if self.reach == "gang_alone" else targets_model()
        modifier(
            self.grant_name,
            scope,
            ef_adds(made.slots[self.slot]),
            attach_to=carrier,
        )


@dataclass(frozen=True)
class DropModifier:
    """A modifier retired outright — for behaviour that is ending, not
    moving. The plan must have proven the modifier does nothing on any
    page: either nothing holds its carrier, or the modifier itself is
    inert wherever the carrier appears."""

    carrier: tuple  # (model label, pk)
    carrier_name: str
    modifier_id: object
    modifier_name: str

    def say(self):
        return f"on {self.carrier_name}: retire “{self.modifier_name}”"

    def perform(self, made):
        from django.apps import apps

        from n26.library.models import Modifier

        app_label, model_name = self.carrier[0].split(".")
        carrier = apps.get_model(app_label, model_name).objects.get(pk=self.carrier[1])
        dropped = Modifier.objects.get(pk=self.modifier_id)
        scope_row, effect_row = dropped.scope, dropped.effect
        carrier.modifiers.remove(dropped)
        dropped.delete()
        scope_row.delete()
        effect_row.delete()


@dataclass(frozen=True)
class RetireModifier:
    """A modifier nothing carries, deleted with its scope and effect
    rows. A detached modifier does nothing on any page, but its effect
    row still names whatever it granted or removed — and protects that
    thing from retiring."""

    modifier_id: object
    modifier_name: str

    def say(self):
        return f"retire the carrierless modifier “{self.modifier_name}”"

    def perform(self, made):
        from n26.library.models import Modifier

        dropped = Modifier.objects.get(pk=self.modifier_id)
        scope_row, effect_row = dropped.scope, dropped.effect
        dropped.delete()
        scope_row.delete()
        effect_row.delete()


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
    #: Primary keys of every gang whose pages this system touches — the
    #: capture set the apply proves unchanged. Derived from stored rows,
    #: which every carrier so far is; a system whose carrier arrives by
    #: grant has no row to find, and its plan must widen this set the
    #: renderer's way.
    gang_ids: tuple = ()
    problems: tuple = ()
    #: True when the system simply is not here — nothing to convert and
    #: nothing wrong: the apply is a clean no-op.
    nothing_here: bool = False

    @property
    def ok(self):
        return not self.problems

    def preview(self):
        if self.nothing_here:
            return [f"[{self.system}] nothing to convert — the system is not here"]
        lines = [f"[{self.system}] {step.say()}" for step in self.steps]
        lines.append(
            f"[{self.system}] prove {len(self.gang_ids)} gang"
            f"{'' if len(self.gang_ids) == 1 else 's'} read the same, or refuse"
        )
        return lines


def apply(plan, *, keep=True):
    """Perform exactly the plan, prove the pages unchanged, or refuse.

    Returns the report lines. Raises :class:`ConversionRefused` — after
    unwinding everything — if the plan carries problems, any affected
    gang's pages change, or any touched gang stops reconciling.

    With ``keep=False`` it does the whole thing and then throws it away:
    every step performed, every page proven, and the transaction unwound
    on purpose. That is the closest a live database can be asked "would
    this work here?" without being changed by the answer, and it is worth
    asking of one holding real players' gangs, where the surprises are.
    A rehearsal that would have refused refuses, in the same words.
    """
    if plan.problems:
        raise ConversionRefused(
            f"[{plan.system}] not applied: " + "; ".join(plan.problems)
        )
    if plan.nothing_here:
        return list(plan.preview())

    report = list(plan.preview())
    try:
        _perform(plan, report, keep=keep)
    except _Rehearsed:
        report.append(
            f"[{plan.system}] rehearsed; every page reads the same; nothing kept"
        )
        return report
    report.append(f"[{plan.system}] applied; every page reads the same")
    return report


class _Rehearsed(Exception):
    """Raised at the end of a rehearsal to unwind it. Never escapes."""


def _perform(plan, report, *, keep):
    from n26.core.capture import differences, gang_state
    from n26.core.models import Gang
    from n26.core.reconcile import assert_reconciled

    with transaction.atomic():
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
        gangs = list(Gang.objects.filter(pk__in=plan.gang_ids))
        after = {str(gang.pk): gang_state(gang) for gang in gangs}
        changed = differences(before, after)
        if changed:
            raise ConversionRefused(
                f"[{plan.system}] refused — the pages would change:\n  "
                + "\n  ".join(changed)
            )
        for gang in gangs:
            try:
                assert_reconciled(gang)
            except Exception as failed:
                raise ConversionRefused(
                    f"[{plan.system}] refused — {gang} no longer reconciles: {failed}"
                ) from failed
        if not keep:
            # Everything held true. Unwind it anyway — that was the ask.
            raise _Rehearsed
