"""Built-ins as desired state — the read side of materialisation.

A carrier — a model's membership, the gang's founding, a bought mount's
own assignment — draws default assignments from its thing's built-ins
and from the option sets recorded as taken (``ChosenProfileOption``).
Each live member of those sets should have a stored copy: an assignment
whose provenance names the member and the carrier
(``materialised_from`` / ``materialised_for``).

This module answers, without writing anything, which members already
have their copy and which are missing. ``Operation.reconcile_defaults``
creates what a plan says is missing; a preview renders a plan directly.

Satisfaction is judged by provenance alone. An owner's own purchase of
the same thing never satisfies a member — a visible duplicate is
accepted rather than one acquisition silently standing in for another —
and an archived copy still satisfies: the owner parted with the thing,
and it is never re-granted behind their back.
"""

from dataclasses import dataclass

from n26.core.models import Assignment, ProfileRole


def copies_of(member, carrier, include_archived=True):
    """The stored assignments one set membership materialised for one
    carrier — the pair that says whether the member is satisfied there.

    This is the one lookup that follows provenance; the member's own
    archival never enters into it, because an archived member's copies
    still resolve through the foreign key and unwinds rely on finding
    them.
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
    """Whether this member already has its copy for this carrier.

    Archived copies count by default: a grant the owner removed or
    sold is settled, not something to hand back. A set being taken
    right now is the one place they do not (``plan_defaults``).
    """
    return copies_of(member, carrier, include_archived=include_archived).exists()


def sets_for(carrier, built_ins=True):
    """The sets a carrier draws default assignments from.

    Its thing's built-ins, then every option set recorded as taken —
    the same sets whether the carrier is being acquired, re-optioned,
    or reconciled long after, so a member added to any of them later
    still counts as owed.
    """
    sets = []
    if built_ins:
        held = getattr(carrier.assignable, "built_ins", None)
        if held is not None:
            sets.append(held)
    for row in carrier.chosen_options.select_related("default_set"):
        sets.append(row.default_set)
    return sets


def kinds_for(carrier):
    """What kinds of member materialise for this carrier, or None for all.

    A Legacy profile is an association, not a second hire: it brings
    the other profile's equipment lists and nothing else — no second
    helping of free kit however its sets grow.
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
    """What one reconcile pass did: the plan it worked from, the copies
    it created, and the members it had to leave unmet — each paired
    with a sentence saying why."""

    carrier: object
    plan: DefaultsPlan
    created: list
    skipped: list


def plan_defaults(carrier, kinds=None, built_ins=True, fresh=(), omit=()):
    """Walk a carrier's sets and say which members lack their copy.

    Only live members count — an archived member is a built-in an
    author has taken off, so future acquisitions come without it while
    every copy it already materialised stands untouched. ``kinds``
    narrows what is owed; passed as None it is derived from the
    carrier's role (``kinds_for``).

    ``fresh`` names sets the carrier is taking right now, whose members
    are judged by live copies alone. The archived-copy rule guards
    against *unattended* re-grants — background reconciling must never
    re-gift what an owner parted with — while taking a set is an
    acquisition, and what is bought arrives: the copies a set's earlier
    tenure left archived are history, not a settled grant.

    ``omit`` names members, by primary key, to treat as satisfied
    whatever provenance says — for a caller that has judged the carrier
    already holds the thing another way and must not be handed a second.
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
