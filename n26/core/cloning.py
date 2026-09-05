"""Read the standing state that a gang or model clone will copy.

The plan contains objects from the source and no destination assignments.
Writing it is an operation's job; keeping selection here makes the boundary
between a snapshot and a replay explicit.
"""

from dataclasses import dataclass

from n26.core.models import Assignment, Gang, Miniature, PrintConfig, Reason
from n26.library.models.modifier import OFFERABLE_KINDS

_CLONE_EVENT_NOTE_VERSION = "v1"


@dataclass(frozen=True)
class ClonePlan:
    """The source assignments that make one independent snapshot."""

    source_gang: Gang
    miniatures: tuple[Miniature, ...]
    assignments: tuple[Assignment, ...]
    guards: frozenset = frozenset()
    neutral: frozenset = frozenset()
    print_configs: tuple[PrintConfig, ...] = ()
    primary: Miniature | None = None

    @property
    def copied_spend(self):
        """Credits represented by the entries in this snapshot."""
        return sum(entry.paid for entry in self._standing_entries())

    @property
    def copied_rating(self):
        """Rating represented by the entries in this snapshot."""
        return sum(entry.rating_contribution for entry in self._standing_entries())

    def _standing_entries(self):
        for assignment in self.assignments:
            if assignment.archived or assignment.pk in self.neutral:
                continue
            if entry := getattr(assignment, "ledger_entry", None):
                yield entry


def clone_name(name, max_length=200):
    """Append the clone suffix without overrunning the destination field."""
    suffix = " (Clone)"
    return f"{name[: max_length - len(suffix)]}{suffix}"


def clone_event_note(source_name, *, credits=0, rating=0):
    """Store one clone act's display totals without making them ledger deltas.

    ``note`` is already machinery for a clone event. Keeping its source name
    last means names may contain the separator without escaping, while the
    small version prefix leaves old plain-name notes readable.
    """
    return f"{_CLONE_EVENT_NOTE_VERSION}|{credits}|{rating}|{source_name}"[:255]


def clone_event_details(note):
    """Return ``(source name, credits, rating)`` from a clone event note.

    Plain notes predate the summary format. Their totals are ``None`` so a
    full history can recover them from the assignment openings it loaded.
    """
    try:
        version, credits, rating, source_name = note.split("|", 3)
        if version != _CLONE_EVENT_NOTE_VERSION:
            raise ValueError
        return source_name, int(credits), int(rating)
    except AttributeError, TypeError, ValueError:
        return note, None, None


def plan_gang_clone(source):
    """Plan a new gang from the source's current, reachable state."""
    assignments = _gang_assignments(source)
    miniature_by_membership = _miniatures_by_membership(source)
    copied_miniatures = {
        miniature.pk: miniature
        for miniature in miniature_by_membership.values()
        if not miniature.membership.archived
    }

    included = {assignment.pk for assignment in assignments if not assignment.archived}
    miniature_by_pk = {
        miniature.pk: miniature for miniature in miniature_by_membership.values()
    }
    for assignment in assignments:
        if assignment.pk not in included:
            continue
        if miniature := miniature_by_pk.get(assignment.miniature_root_id):
            copied_miniatures.setdefault(miniature.pk, miniature)

    # Independently bought kit can remain live on a departed model. Such a
    # model stays off the cloned roster, but its archived membership is the
    # structural host that keeps the live assignment's roots and any models it
    # later brought intact.
    structural = {
        miniature.membership_id
        for miniature in copied_miniatures.values()
        if miniature.membership.archived
    }
    included.update(structural)
    guards = _include_materialisation_guards(included, assignments)
    neutral = guards | structural

    return ClonePlan(
        source_gang=source,
        miniatures=tuple(
            sorted(copied_miniatures.values(), key=lambda miniature: str(miniature.pk))
        ),
        assignments=_ordered(assignments, included),
        guards=frozenset(guards),
        neutral=frozenset(neutral),
        print_configs=tuple(
            PrintConfig.objects.filter(gang=source)
            .prefetch_related("miniatures", "assignments")
            .order_by("created", "pk")
        ),
    )


def plan_miniature_clone(source):
    """Plan one model and the live models its assignment graph brought."""
    gang = source.gang
    assignments = _gang_assignments(gang)
    assignment_by_id = {assignment.pk: assignment for assignment in assignments}
    miniature_by_membership = _miniatures_by_membership(gang)
    source = miniature_by_membership.get(source.membership_id, source)
    membership_by_miniature = {
        miniature.pk: membership_id
        for membership_id, miniature in miniature_by_membership.items()
    }
    miniatures = {source.pk: source}
    included = set()

    changed = True
    while changed:
        before = (len(included), len(miniatures))
        membership_ids = {
            membership_by_miniature[pk]
            for pk in miniatures
            if pk in membership_by_miniature
        }
        for assignment in assignments:
            if assignment.archived:
                continue
            if (
                assignment.pk in membership_ids
                or assignment.miniature_root_id in miniatures
                or _is_gang_wide_choice(assignment, included)
                or _is_live_gang_wide_materialisation(
                    assignment,
                    included,
                    assignment_by_id,
                )
                or (
                    assignment.pk in miniature_by_membership
                    and assignment.caused_by_id in included
                )
            ):
                included.add(assignment.pk)

        for membership_id in tuple(included):
            miniature = miniature_by_membership.get(membership_id)
            if miniature is not None and not miniature.membership.archived:
                miniatures.setdefault(miniature.pk, miniature)
        changed = before != (len(included), len(miniatures))

    guards = _include_materialisation_guards(included, assignments)

    return ClonePlan(
        source_gang=gang,
        miniatures=tuple(
            sorted(miniatures.values(), key=lambda miniature: str(miniature.pk))
        ),
        assignments=_ordered(assignments, included),
        guards=frozenset(guards),
        neutral=frozenset(guards),
        primary=source,
    )


def _gang_assignments(gang):
    """All assignments once, with everything the writer copies resolved."""
    queryset = Assignment.objects.filter(gang_root=gang).select_related(
        "ledger_entry",
        "profile_role",
        "counter_value",
        "parent",
        "caused_by",
        "chosen_for",
        "materialised_for",
        "miniature",
        "stash",
    )
    return tuple(
        Assignment.with_assignables(queryset)
        .prefetch_related("chosen_options__default_set")
        .order_by("created", "pk")
    )


def _miniatures_by_membership(gang):
    miniatures = (
        Miniature.objects.filter(membership__gang=gang)
        .select_related(
            "membership__caused_by__miniature_root__membership",
        )
        .prefetch_related(
            "stat_overrides",
            "assignment_sets__assignments",
        )
    )
    return {miniature.membership_id: miniature for miniature in miniatures}


def _include_materialisation_guards(included, assignments):
    """Keep tombstones for defaults no longer standing on the copied host.

    A live default moved elsewhere still satisfies its original carrier. The
    copy must not take the item from its new host, so it carries an archived
    provenance-only copy instead. An already archived default is the same
    guard directly. The writer re-homes both beside the cloned carrier rather
    than bringing an obsolete parent along merely to hold a tombstone.
    """
    guards = {
        assignment.pk
        for assignment in assignments
        if assignment.pk in included
        and assignment.archived
        and assignment.materialised_from_id is not None
    }
    changed = True
    while changed:
        before = len(included)
        for assignment in assignments:
            if (
                assignment.materialised_from_id is None
                or assignment.materialised_for_id not in included
            ):
                continue
            if assignment.archived or assignment.pk not in included:
                included.add(assignment.pk)
                guards.add(assignment.pk)
        changed = len(included) != before
    return guards


def _is_gang_wide(assignment):
    """Whether an assignment lives at gang scope rather than on one holder."""
    return assignment.miniature_root_id is None and assignment.stash_root_id is None


def _is_gang_wide_choice(assignment, included):
    """Whether a selected model's choice deliberately lives on the gang."""
    if not _is_gang_wide(assignment):
        return False
    if assignment.chosen_for_id in included:
        return True
    entry = getattr(assignment, "ledger_entry", None)
    return (
        assignment.caused_by_id in included
        and entry is not None
        and entry.reason == Reason.GRANTED
        and (
            assignment.chosen_for_offer_id is not None
            or any(
                getattr(assignment, f"{field}_id") is not None
                for field in OFFERABLE_KINDS
            )
        )
    )


def _is_live_gang_wide_materialisation(assignment, included, assignment_by_id):
    """Whether copied gang-scoped content brought this live payload.

    A model's answer may deliberately live on the gang. Defaults that answer
    materialises there are part of the answer's standing state, and each can
    itself bring another assignment or model. Include them in the main fixed
    point so that whole live graph follows. A default moved to another scope
    is left for the guard pass: it satisfies the source carrier, but is not
    payload the clone should take from its current holder.
    """
    if (
        assignment.materialised_from_id is None
        or assignment.materialised_for_id not in included
        or not _is_gang_wide(assignment)
    ):
        return False
    carrier = assignment_by_id.get(assignment.materialised_for_id)
    return carrier is not None and _is_gang_wide(carrier)


def _ordered(assignments, included):
    return tuple(assignment for assignment in assignments if assignment.pk in included)
