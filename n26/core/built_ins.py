"""Read-only plans for bringing built-ins up to date.

The plan is the shared answer for three later writers: the authoring preview,
near-real-time propagation, and the historical backfill.  It reads current
player data and says what one default member would mean for every existing use;
it never creates or changes an assignment.
"""

from dataclasses import dataclass
from enum import StrEnum

from django.db import models

from n26.core.models import Assignment, ChosenProfileOption, ProfileRole, Reason
from n26.core.models.assignment import ASSIGNABLE_FIELDS
from n26.library.models import Collection, Counter, Rule, Subtype, WeaponProfile


class BuiltInAction(StrEnum):
    """What reconciling one use would do."""

    CREATE = "create"
    MATERIALISED = "materialised"
    SATISFIED = "satisfied"
    PARTED_WITH = "parted-with"
    OUT_OF_SCOPE = "out-of-scope"


@dataclass(frozen=True)
class PlannedBuiltInUse:
    """One existing acquisition and the answer for one built-in member."""

    carrier: Assignment
    action: BuiltInAction
    existing: Assignment | None = None
    removal: Assignment | None = None

    @property
    def writes(self):
        return self.action == BuiltInAction.CREATE

    @property
    def changes_card(self):
        return self.writes and self.removal is None


@dataclass(frozen=True)
class BuiltInPlan:
    """The impact of one actual or hypothetical member of a default set."""

    default_set: object | None
    thing: object
    member: object | None
    uses: tuple[PlannedBuiltInUse, ...]

    def count(self, action):
        return sum(use.action == action for use in self.uses)

    @property
    def writes(self):
        return sum(use.writes for use in self.uses)

    @property
    def visible_changes(self):
        return sum(use.changes_card for use in self.uses)


def plan_built_in_add(carrier, thing):
    """Plan adding ``thing`` to ``carrier`` without writing either side.

    A carrier whose set is shared reaches every holder of that set, exactly as
    the real add would.  Before its first built-in it has no set yet, so only
    existing assignments of that carrier are in scope.
    """

    default_set = getattr(carrier, "built_ins", None)
    carriers = (
        _carriers_of(default_set)
        if default_set is not None
        else _assignments_of(carrier)
    )
    return _plan(default_set, thing, member=None, carriers=carriers)


def plan_default_member(member):
    """Plan reconciling one stored ``DefaultAssignment`` member."""

    return _plan(
        member.default_set,
        member.assignable,
        member=member,
        carriers=_carriers_of(member.default_set),
    )


def _plan(default_set, thing, *, member, carriers):
    uses = tuple(
        _plan_use(carrier, thing, member)
        for carrier in sorted(carriers, key=lambda row: str(row.pk))
    )
    return BuiltInPlan(
        default_set=default_set,
        thing=thing,
        member=member,
        uses=uses,
    )


def _assignments_of(carrier):
    field = Assignment.field_for(carrier)
    rows = Assignment.objects.filter(
        archived=False,
        **{field: carrier},
    ).select_related("profile_role")
    return _hydrate(rows)


def _carriers_of(default_set):
    """Every live acquisition that took ``default_set``.

    A set can be the built-ins of several kinds and the payload of an option.
    The assignment union has one column per kind, so narrow per kind rather
    than making Postgres plan one join across the whole union.
    """

    ids = set()
    for field in ASSIGNABLE_FIELDS:
        model = Assignment._meta.get_field(field).related_model
        if not hasattr(model, "built_ins"):
            continue
        ids.update(
            Assignment.objects.filter(
                archived=False,
                **{f"{field}__built_ins": default_set},
            ).values_list("pk", flat=True)
        )
    ids.update(
        ChosenProfileOption.objects.filter(
            assignment__archived=False,
            default_set=default_set,
        ).values_list("assignment_id", flat=True)
    )
    rows = Assignment.objects.filter(pk__in=ids).select_related("profile_role")
    return _hydrate(rows)


def _hydrate(rows):
    """Resolve each carrier's assignable without a query per result."""

    return list(Assignment.with_assignables(rows))


def _plan_use(carrier, thing, member):
    if not _applies_to(carrier, thing):
        return PlannedBuiltInUse(carrier, BuiltInAction.OUT_OF_SCOPE)

    source = _source_match(carrier, thing, member, archived=False)
    if source is not None:
        return PlannedBuiltInUse(carrier, BuiltInAction.MATERIALISED, source)

    departed = _source_match(carrier, thing, member, archived=True)
    if departed is not None:
        return PlannedBuiltInUse(carrier, BuiltInAction.PARTED_WITH, departed)

    positive = _hosted_match(carrier, thing, removes=False, archived=False)
    removal = _hosted_match(carrier, thing, removes=True, archived=False)
    if isinstance(thing, (Rule, Subtype, Counter)) and positive is not None:
        return PlannedBuiltInUse(
            carrier,
            BuiltInAction.SATISFIED,
            existing=positive,
            removal=removal,
        )
    return PlannedBuiltInUse(
        carrier,
        BuiltInAction.CREATE,
        removal=removal,
    )


def _applies_to(carrier, thing):
    role = getattr(carrier, "profile_role", None)
    return (
        role is None
        or role.role != ProfileRole.Role.LEGACY
        or isinstance(thing, Collection)
    )


def _source_match(carrier, thing, member, *, archived):
    """The assignment this exact member made, including legacy rows.

    Before provenance columns existed, the cause and ``Reason.DEFAULT`` were
    the only evidence.  That fallback applies only to a stored member: a
    hypothetical add cannot already have materialised.
    """

    if member is None:
        return None
    exact = Assignment.objects.filter(
        materialised_from=member,
        materialised_for=carrier,
        archived=archived,
    ).first()
    if exact is not None:
        return exact

    field = Assignment.field_for(thing)
    roots = {
        "gang_root_id": carrier.gang_root_id,
        "miniature_root_id": carrier.miniature_root_id,
        "stash_root_id": carrier.stash_root_id,
    }
    legacy = Assignment.objects.filter(
        archived=archived,
        ledger_entry__reason=Reason.DEFAULT,
        **roots,
        **{field: thing},
    )
    if isinstance(thing, WeaponProfile):
        legacy = legacy.filter(
            parent__weapon=thing.weapon,
            parent__caused_by=carrier,
            caused_by=models.F("parent"),
        )
    else:
        legacy = legacy.filter(caused_by=carrier, **_host(carrier))
    return legacy.first()


def _hosted_match(carrier, thing, *, removes, archived):
    field = Assignment.field_for(thing)
    return Assignment.objects.filter(
        archived=archived,
        removes=removes,
        **_host(carrier),
        **{field: thing},
    ).first()


def _host(carrier):
    """Where this carrier's defaults land, mirroring ``Operation``."""

    if carrier.miniature_root_id is not None:
        return {"miniature_id": carrier.miniature_root_id}
    if carrier.gang_id is not None:
        return {"gang_id": carrier.gang_id}
    if carrier.stash_root_id is not None:
        return {"stash_id": carrier.stash_root_id}
    raise ValueError(f"{carrier} has nowhere for built-ins to materialise.")
