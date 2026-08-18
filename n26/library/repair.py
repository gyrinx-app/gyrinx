"""Gear stored twice — once as wargear, once as the weapon it already is.

A thing with a firing line is a weapon. ``WeaponProfile`` points at
``Weapon`` and at nothing else, so a grenade — which the books type as
wargear because it does not count against the weapons a fighter holds —
is kept as a weapon taking no slots, homed in its wargear category. That
is what lets it print a statline while still sitting under Grenades.

Where the same gear also survives as a wargear row, the two stand for
one thing and only one of them can carry the firing line. The wargear
row is the one to lose: everything naming it moves onto the weapon, and
it goes.

**It moves no money.** The matching rule makes the two agree on price,
and what a purchase was worth is pinned on its ledger entry, which is
never rewritten. ``apply`` proves that gang by gang and unwinds the
whole repair on any disagreement. The proof survives players acting
while it runs: reconcile compares a gang's pinned numbers against its
own ledger, and a purchase committed midway moves both.

**It writes the weapon's firing lines.** Those lines are assignments of
their own, made when a weapon is acquired, and a purchase made against
the wargear row never had any — so moving one onto the weapon without
them would leave the card as blank as before. They are free, so they
add nothing to what anyone owns, and they are written directly rather
than through an operation: the gang's history must not claim its owner
did something today.

**It does change one word.** A gang's history asks what an assignment
names *now*, so these purchases start reading "weapon" where they read
"wargear". The name, the price and the sums are untouched; the kind is
the thing that was wrong and is now right.

The matching rule is deliberately narrow, because the seam is not
symmetric. A ceiling on how many may be held, and option groups, can
name a wargear but not a weapon — and option groups cascade, so a
careless delete would empty them in silence. A wargear row carrying any
of that is reported and left alone for someone to settle.
"""

from dataclasses import dataclass, field

from django.db import transaction

__all__ = [
    "Candidate",
    "MERGE",
    "Refused",
    "Result",
    "SKIP_REASONS",
    "apply",
    "find_candidates",
    "gangs_holding",
]

#: The decision meaning "these are one thing, and the wargear row goes".
MERGE = "merge"

#: Why a same-named pair is left alone, in the words the console prints.
SKIP_REASONS = {
    "no_firing_line": (
        "the weapon has no firing line, so these are two different things"
    ),
    "different_category": "the two are homed in different categories",
    "different_price": "the two disagree on what they price at",
    "carries_options": "the wargear offers options, which a weapon cannot hold",
    "carries_rules": (
        "the wargear carries modifiers, use restrictions or built-in kit"
    ),
    "spoken_for": (
        "something names the wargear: a ceiling on how many may be held, "
        "or a default assignment"
    ),
}


class Refused(Exception):
    """The repair unwound: a number it must not move, moved."""


@dataclass
class Candidate:
    """One wargear row and the weapon sharing its pack and name."""

    wargear: object
    weapon: object
    decision: str
    entries: int = 0
    assignments: int = 0
    gangs: int = 0

    @property
    def merges(self):
        return self.decision == MERGE

    @property
    def reason(self):
        return SKIP_REASONS.get(self.decision, "")

    def as_dict(self):
        return {
            "name": self.wargear.name,
            "pack": str(self.wargear.pack),
            "wargear_category": str(self.wargear.category),
            "weapon_category": str(self.weapon.category),
            "decision": self.decision,
            "reason": self.reason,
            "entries": self.entries,
            "assignments": self.assignments,
            "gangs": self.gangs,
        }


@dataclass
class Result:
    """What a run did, for the record it is written onto."""

    merged: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    entries_moved: int = 0
    entries_dropped: int = 0
    assignments_moved: int = 0
    lines_granted: int = 0
    gangs: int = 0

    def as_dict(self):
        return {
            "merged": self.merged,
            "skipped": self.skipped,
            "entries_moved": self.entries_moved,
            "entries_dropped": self.entries_dropped,
            "assignments_moved": self.assignments_moved,
            "lines_granted": self.lines_granted,
            "gangs": self.gangs,
        }


def find_candidates():
    """Every wargear row sharing a pack, a name and a qualifier with a
    weapon, each carrying the decision made about it. Reads only."""
    from n26.library.models import Wargear, Weapon

    found = []
    for wargear in Wargear.objects.select_related("category__section", "pack").order_by(
        "name"
    ):
        weapon = (
            Weapon.objects.filter(
                pack=wargear.pack,
                name__iexact=wargear.name,
                qualifier__iexact=wargear.qualifier,
            )
            .select_related("category__section")
            .first()
        )
        if weapon is not None:
            found.append(_judge(wargear, weapon))
    return found


def gangs_holding(candidates):
    """The gangs holding any of this gear — each counted once, however
    many pieces of it they hold."""
    from n26.core.models import Assignment

    found = set(
        Assignment.objects.filter(
            wargear__in=[candidate.wargear.pk for candidate in candidates]
        ).values_list("gang_root", flat=True)
    )
    found.discard(None)
    return found


def _judge(wargear, weapon):
    from n26.core.models import Assignment
    from n26.library.models.collection import CollectionEntry

    assignments = Assignment.objects.filter(wargear=wargear)
    gangs = set(assignments.values_list("gang_root", flat=True))
    gangs.discard(None)
    return Candidate(
        wargear=wargear,
        weapon=weapon,
        decision=_decide(wargear, weapon),
        entries=CollectionEntry.objects.filter(wargear=wargear).count(),
        assignments=assignments.count(),
        gangs=len(gangs),
    )


def _decide(wargear, weapon):
    """One name in two tables is not proof they are one thing. Everything
    that could make them differ is asked, and the first answer wins."""
    from n26.library.models.assignable import USABLE_BY_LISTS
    from n26.library.models.defaults import DefaultAssignment
    from n26.library.models.modifier import AllowsAtMost

    if not weapon.profiles.exists():
        return "no_firing_line"
    if wargear.category_id != weapon.category_id:
        return "different_category"
    priced = (wargear.price, wargear.trade_point_price, wargear.is_exclusive)
    if priced != (weapon.price, weapon.trade_point_price, weapon.is_exclusive):
        return "different_price"
    if wargear.option_groups.exists() or wargear.options.exists():
        return "carries_options"
    if (
        wargear.built_ins_id
        or wargear.modifiers.exists()
        or any(getattr(wargear, listed).exists() for listed in USABLE_BY_LISTS)
    ):
        return "carries_rules"
    if (
        AllowsAtMost.objects.filter(wargear=wargear).exists()
        or DefaultAssignment.objects.filter(wargear=wargear).exists()
    ):
        return "spoken_for"
    return MERGE


def apply():
    """Merge every matched wargear row into its weapon, or write nothing.

    One transaction. The deletes go last on purpose: what still names a
    wargear row is protected, so anything the moves missed stops the
    repair whole rather than letting it half-finish.
    """
    from n26.core.models import Assignment, Gang
    from n26.core.reconcile import check_gang

    candidates = find_candidates()
    merges = [c for c in candidates if c.merges]
    result = Result(
        skipped=[c.as_dict() for c in candidates if not c.merges],
    )
    if not merges:
        return result

    gang_ids = gangs_holding(merges)

    with transaction.atomic():
        gangs = list(Gang.objects.filter(pk__in=gang_ids))
        # Only a gang whose books already balance can be held to them
        # afterwards. Drift that was there beforehand is somebody else's
        # to answer for, and refusing over it would block the repair.
        balanced = {gang.pk for gang in gangs if not check_gang(gang)}

        for candidate in merges:
            _move_entries(candidate, result)
            moved = list(
                Assignment.objects.filter(wargear=candidate.wargear).values_list(
                    "pk", flat=True
                )
            )
            # Both columns in one statement, so the constraint that
            # exactly one assignable is named holds throughout. A bulk
            # write is safe here where it usually is not: an assignment's
            # denormalised roots follow its host, and the host is not
            # what changes.
            Assignment.objects.filter(pk__in=moved).update(
                wargear=None, weapon=candidate.weapon
            )
            result.assignments_moved += len(moved)
            result.lines_granted += _grant_firing_lines(candidate, moved)
            result.merged.append(candidate.as_dict())
            candidate.wargear.delete()

        for gang in gangs:
            if gang.pk not in balanced:
                continue
            # The pinned numbers are read from the database rather than
            # from the instance the pre-check ran against, which is stale
            # by now.
            gang.refresh_from_db()
            problems = check_gang(gang)
            if problems:
                raise Refused("; ".join(problems))
        result.gangs = len(gangs)
    return result


def _grant_firing_lines(candidate, moved):
    """Give each moved purchase the weapon's free firing lines.

    A weapon's free lines are assignments of their own, written when it
    is acquired — without them its card line has no statline and no
    traits, which is the whole of what the wargear copy got wrong. A
    purchase made against the wargear row never had any.

    They are free, and they are written directly rather than through an
    operation: nothing is bought, so the gang's history must not claim
    its owner did something today. A line on a sold weapon is sold with
    it, so it arrives archived where its weapon is.
    """
    from n26.core.models import Assignment, LedgerEntry, Reason

    free = list(candidate.weapon.profiles.filter(price=0))
    granted = 0
    for assignment in Assignment.objects.filter(pk__in=moved):
        held = set(
            Assignment.objects.filter(parent=assignment).values_list(
                "weapon_profile_id", flat=True
            )
        )
        for profile in free:
            if profile.pk in held:
                continue
            line = Assignment.objects.create(
                weapon_profile=profile,
                parent=assignment,
                caused_by=assignment,
                archived=assignment.archived,
                archived_at=assignment.archived_at,
            )
            LedgerEntry.objects.create(assignment=line, reason=Reason.DEFAULT)
            granted += 1
    return granted


def _move_entries(candidate, result):
    """Point this gear's equipment-list lines at the weapon.

    A list already offering the weapon would show the same gear twice, so
    that line goes instead of moving — but the money bought through it
    keeps its provenance, which means pointing those purchases at the
    line that survives before this one does not.
    """
    from n26.core.models import LedgerEntry
    from n26.library.models.collection import CollectionEntry

    for entry in CollectionEntry.objects.filter(wargear=candidate.wargear):
        standing = CollectionEntry.objects.filter(
            collection_id=entry.collection_id, weapon=candidate.weapon
        ).first()
        if standing is None:
            CollectionEntry.objects.filter(pk=entry.pk).update(
                wargear=None, weapon=candidate.weapon
            )
            result.entries_moved += 1
        else:
            LedgerEntry.objects.filter(bought_from=entry).update(bought_from=standing)
            entry.delete()
            result.entries_dropped += 1
