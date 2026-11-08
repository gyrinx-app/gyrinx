"""Plan required built-in and selected-option assignments without writing.

A carrier's content and recorded options identify its sets. Each live set
member requires a copy with matching ``materialised_from`` and
``materialised_for`` provenance. ``Operation.reconcile_defaults`` creates
missing copies; previews can display the plan directly.

An unrelated purchase cannot satisfy a grant requirement. Archived copies
do satisfy it, preventing automatic replacement of removed equipment.
"""

from dataclasses import dataclass

from n26.core.models import Assignment, ProfileRole


def copies_of(member, carrier, include_archived=True):
    """Find assignments with matching set-member and carrier provenance.

    Do not filter the member's archival: option removal still needs to find
    copies created by archived members.
    """
    copies = Assignment.objects.filter(
        materialised_from=member, materialised_for=carrier
    )
    if not include_archived:
        copies = copies.filter(archived=False)
    return copies


def copies_of_set(default_set, carrier, include_archived=True):
    """Every copy any member of one set materialised for a carrier."""
    copies = Assignment.objects.filter(
        materialised_from__default_set=default_set,
        materialised_for=carrier,
    )
    if not include_archived:
        copies = copies.filter(archived=False)
    return copies


def is_satisfied(member, carrier, include_archived=True):
    """Whether a copy with this member and carrier provenance exists.

    Include archived copies by default so background repair cannot recreate
    removed equipment. Newly selected sets can require live copies instead.
    """
    return copies_of(member, carrier, include_archived=include_archived).exists()


def sets_for(carrier, built_ins=True):
    """Return the carrier's built-ins followed by its recorded option sets."""
    sets = []
    if built_ins:
        held = getattr(carrier.assignable, "built_ins", None)
        if held is not None:
            sets.append(held)
    for row in carrier.chosen_options.select_related("default_set"):
        sets.append(row.default_set)
    return sets


def kinds_for(carrier):
    """Return grant kinds permitted by the carrier role, or None for all.

    Legacy profiles grant collection access without duplicating equipment.
    """
    from n26.library.models import Collection

    role = getattr(carrier, "profile_role", None)
    if role is not None and role.role == ProfileRole.Role.LEGACY:
        return (Collection,)
    return None


@dataclass(frozen=True)
class MemberPlan:
    """One live set membership, and whether its copy already exists."""

    member: object
    satisfied: bool


@dataclass(frozen=True)
class DefaultsPlan:
    """What one carrier's sets say it should hold, member by member."""

    carrier: object
    entries: tuple

    @property
    def missing(self):
        return [entry.member for entry in self.entries if not entry.satisfied]


@dataclass(frozen=True)
class ReconcileOutcome:
    """A reconciliation plan, created copies and skipped members with reasons."""

    carrier: object
    plan: DefaultsPlan
    created: list
    skipped: list


def plan_defaults(carrier, kinds=None, built_ins=True, fresh=(), omit=()):
    """Identify live set members missing a materialised copy for this carrier.

    Ignore archived members without retracting their existing copies.
    ``kinds`` limits assignable kinds, defaulting to the carrier role.

    ``fresh`` names newly acquired sets, for which only live copies satisfy
    a requirement. Ordinary background reconciliation also counts archived copies
    to avoid replacing equipment the owner removed.

    ``omit`` lists member IDs the caller considers satisfied by another route.
    """
    if kinds is None:
        kinds = kinds_for(carrier)
    fresh_pks = {default_set.pk for default_set in fresh}
    omitted = set(omit)
    entries = []
    for default_set in sets_for(carrier, built_ins=built_ins):
        include_archived = default_set.pk not in fresh_pks
        for member in default_set.members.filter(archived=False):
            assignable = member.assignable
            if assignable is None:
                continue
            if kinds is not None and not isinstance(assignable, kinds):
                continue
            entries.append(
                MemberPlan(
                    member=member,
                    satisfied=member.pk in omitted
                    or is_satisfied(member, carrier, include_archived=include_archived),
                )
            )
    return DefaultsPlan(carrier=carrier, entries=tuple(entries))
