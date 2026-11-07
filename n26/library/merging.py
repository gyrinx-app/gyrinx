"""Merge duplicate library content into a selected surviving record.

Repoint assignments and library references, then delete the duplicate.
Preserve purchase ledger entries and verify each gang reconciles around its
own transaction; merging changes no recorded prices or ratings.

Weapon profiles require same-named counterparts on the survivor. Deduplicate
free copies and grant missing free survivor profiles. Reject unmatched lines
and duplicate-side modifiers, restrictions or built-ins that need an author's
decision before merging.

``plan_merge`` produces the preview. ``merge_gang`` locks and processes each
gang; the last gang finishes references and deletion through ``merge_library``.
"""

from dataclasses import dataclass, replace

from django.db import transaction

from n26.library.references import named, references_to


class Refused(Exception):
    """The merge cannot run, and the reason is already in words."""


@dataclass(frozen=True)
class GangPart:
    """One gang's share of a merge: the assignments naming the duplicate."""

    pk: str
    name: str
    owner: str
    archived: bool
    #: How many assignments — the weapon itself and its lines — move.
    assignments: int = 0

    def as_dict(self):
        return {
            "pk": self.pk,
            "name": self.name,
            "owner": self.owner,
            "archived": self.archived,
            "assignments": self.assignments,
        }

    @classmethod
    def from_dict(cls, held):
        return cls(
            pk=held["pk"],
            name=held["name"],
            owner=held["owner"],
            archived=bool(held.get("archived")),
            assignments=int(held.get("assignments", 0)),
        )


@dataclass(frozen=True)
class MergePlan:
    """What merging one row into another would do, and what stops it."""

    duplicate: tuple = ()
    survivor: tuple = ()
    duplicate_said: str = ""
    survivor_said: str = ""
    #: ``(duplicate line pk, its name, survivor line pk)`` for each line.
    lines: tuple = ()
    gangs: tuple = ()
    #: How many list lines move to the survivor, and how many go because
    #: the list already offers it.
    entries_moved: int = 0
    entries_dropped: int = 0
    #: How many built-in memberships and modifier parts move.
    members_moved: int = 0
    parts_moved: int = 0
    refusals: tuple = ()

    @property
    def ok(self):
        return not self.refusals

    @property
    def touches_players(self):
        return bool(self.gangs)

    def preview(self):
        lines = []
        if self.gangs:
            assignments = sum(part.assignments for part in self.gangs)
            lines.append(
                f"point {assignments} assignment{'' if assignments == 1 else 's'} "
                f"on {len(self.gangs)} gang{'' if len(self.gangs) == 1 else 's'} "
                f"at {self.survivor_said}, gang by gang, each proved to reconcile"
            )
        for _, name, _ in self.lines:
            lines.append(
                f"the line “{name or 'its own line'}” becomes {self.survivor_said}'s"
            )
        if self.entries_moved:
            lines.append(
                f"move {self.entries_moved} list line{'' if self.entries_moved == 1 else 's'} "
                f"to {self.survivor_said}"
            )
        if self.entries_dropped:
            lines.append(
                f"drop {self.entries_dropped} list line{'' if self.entries_dropped == 1 else 's'} "
                f"on lists that already offer {self.survivor_said}"
            )
        if self.members_moved:
            lines.append(
                f"move {self.members_moved} built-in "
                f"membership{'' if self.members_moved == 1 else 's'}"
            )
        if self.parts_moved:
            lines.append(
                f"point {self.parts_moved} modifier "
                f"part{'' if self.parts_moved == 1 else 's'} at {self.survivor_said}"
            )
        lines.append(f"delete {self.duplicate_said}")
        for refusal in self.refusals:
            lines.append(f"refused: {refusal}")
        return lines

    def as_record(self):
        return {
            "merge": True,
            "duplicate": list(self.duplicate),
            "survivor": list(self.survivor),
            "duplicate_said": self.duplicate_said,
            "survivor_said": self.survivor_said,
            "lines": [list(line) for line in self.lines],
            "gangs": [part.as_dict() for part in self.gangs],
            "entries_moved": self.entries_moved,
            "entries_dropped": self.entries_dropped,
            "members_moved": self.members_moved,
            "parts_moved": self.parts_moved,
            "refusals": list(self.refusals),
            "preview": list(self.preview()),
        }

    @classmethod
    def from_record(cls, summary):
        return cls(
            duplicate=tuple(summary.get("duplicate", ())),
            survivor=tuple(summary.get("survivor", ())),
            duplicate_said=summary.get("duplicate_said", ""),
            survivor_said=summary.get("survivor_said", ""),
            lines=tuple(tuple(line) for line in summary.get("lines", [])),
            gangs=tuple(GangPart.from_dict(g) for g in summary.get("gangs", [])),
            entries_moved=int(summary.get("entries_moved", 0)),
            entries_dropped=int(summary.get("entries_dropped", 0)),
            members_moved=int(summary.get("members_moved", 0)),
            parts_moved=int(summary.get("parts_moved", 0)),
            refusals=tuple(summary.get("refusals", [])),
        )

    def same_as(self, other):
        return (
            self.duplicate == other.duplicate
            and self.survivor == other.survivor
            and set(self.lines) == set(other.lines)
            and {part.pk for part in self.gangs} == {part.pk for part in other.gangs}
            and self.refusals == other.refusals
        )


def _key(row):
    return (type(row)._meta.label_lower, str(row.pk))


def _said(row):
    return getattr(row, "authoring_label", None) or named(row)


def _lines_of(row):
    """A weapon's firing lines; nothing for a kind without them."""
    profiles = getattr(row, "profiles", None)
    return list(profiles.all()) if profiles is not None else []


def _map_lines(duplicate, survivor):
    """Each of the duplicate's lines to the survivor's line of the same
    name, and the names that have none."""
    theirs = {line.name.strip().lower(): line for line in _lines_of(survivor)}
    mapping, missing = [], []
    for line in _lines_of(duplicate):
        match = theirs.get(line.name.strip().lower())
        if match is None:
            missing.append(line)
        else:
            mapping.append((str(line.pk), line.name, str(match.pk)))
    return mapping, missing


def _carries_own_decisions(row):
    """What on the row itself would have to be guessed at to move."""
    from n26.library.models.assignable import USABLE_BY_LISTS

    found = []
    if getattr(row, "built_ins_id", None):
        found.append("built-ins")
    if hasattr(row, "modifiers") and row.modifiers.exists():
        found.append("modifiers")
    if any(
        hasattr(row, listed) and getattr(row, listed).exists()
        for listed in USABLE_BY_LISTS
    ):
        found.append("use restrictions")
    if hasattr(row, "options") and row.options.exists():
        found.append("options")
    if hasattr(row, "option_groups") and row.option_groups.exists():
        found.append("option groups")
    return found


def plan_merge(duplicate, survivor):
    """Read what merging ``duplicate`` into ``survivor`` would do. Never writes."""
    from n26.core.models import Assignment, Gang
    from n26.library.models import CollectionEntry, DefaultAssignment

    refusals = []
    if type(duplicate) is not type(survivor):
        refusals.append(
            f"{_said(survivor)} is a {type(survivor)._meta.verbose_name}, not a "
            f"{type(duplicate)._meta.verbose_name}"
        )
    if duplicate.pk == survivor.pk:
        refusals.append("a row cannot be merged into itself")
    if getattr(duplicate, "pack_id", None) != getattr(survivor, "pack_id", None):
        refusals.append("the two are in different packs")
    carried = _carries_own_decisions(duplicate)
    if carried:
        refusals.append(
            f"{_said(duplicate)} carries {', '.join(carried)} of its own; move "
            "or detach them first"
        )

    mapping, missing = _map_lines(duplicate, survivor) if not refusals else ([], [])
    for line in missing:
        refusals.append(
            f"the line “{line.name or 'its own line'}” has no line of that name "
            f"on {_said(survivor)}; add one there, or delete the line first"
        )

    # Every reference to the duplicate and to its lines, sorted.
    things = [duplicate, *_lines_of(duplicate)]
    gangs = {}
    entries_moved = entries_dropped = members_moved = parts_moved = 0
    by_model = {}
    for thing in things:
        by_model.setdefault(type(thing), []).append(thing)
    for rows in by_model.values():
        for reference in references_to(*rows):
            row = reference.row
            label = reference.label
            if label == "n26.assignment":
                gang_id = row.gang_root_id
                if gang_id is None:
                    refusals.append(
                        f"an assignment on no gang names {_said(duplicate)}"
                    )
                    continue
                gangs[str(gang_id)] = gangs.get(str(gang_id), 0) + 1
            elif label == "library.collectionentry":
                if reference.field == "weapon_profile":
                    entries_moved += 1
                    continue
                standing = CollectionEntry.objects.filter(
                    collection_id=row.collection_id,
                    **{reference.field: survivor},
                ).exists()
                if standing:
                    entries_dropped += 1
                else:
                    entries_moved += 1
            elif label == "library.defaultassignment":
                if reference.field == "weapon_profile":
                    members_moved += 1
                    continue
                already = DefaultAssignment.objects.filter(
                    default_set_id=row.default_set_id, **{reference.field: survivor}
                ).exists()
                if already:
                    refusals.append(
                        f"the built-in set “{row.default_set}” already brings "
                        f"{_said(survivor)}; take {_said(duplicate)} out of it first"
                    )
                else:
                    members_moved += 1
            elif reference.cascades:
                # A part of the duplicate: its lines, their characteristics.
                continue
            elif not reference.protects and not reference.empties:
                # A many-to-many: a modifier condition listing it. Swapped.
                parts_moved += 1
            elif label.startswith("library.") and _modifier_part(row):
                parts_moved += 1
            else:
                refusals.append(
                    f"the {type(row)._meta.verbose_name} “{named(row)}” names "
                    f"{_said(duplicate)}"
                )

    parts = []
    for gang in Gang.objects.filter(pk__in=list(gangs)).select_related("owner"):
        parts.append(
            GangPart(
                pk=str(gang.pk),
                name=gang.name,
                owner=gang.owner.username if gang.owner_id else "",
                archived=gang.archived,
                assignments=gangs[str(gang.pk)],
            )
        )
    del Assignment
    return MergePlan(
        duplicate=_key(duplicate),
        survivor=_key(survivor),
        duplicate_said=_said(duplicate),
        survivor_said=_said(survivor),
        lines=tuple(mapping),
        gangs=tuple(sorted(parts, key=lambda part: (part.owner, part.name))),
        entries_moved=entries_moved,
        entries_dropped=entries_dropped,
        members_moved=members_moved,
        parts_moved=parts_moved,
        refusals=tuple(dict.fromkeys(refusals)),
    )


def _modifier_part(row):
    from n26.library.models import Modifier
    from n26.library.models.modifier import EFFECT_FIELDS, SCOPE_FIELDS

    parts = {
        Modifier._meta.get_field(name).related_model
        for name in (*SCOPE_FIELDS, *EFFECT_FIELDS)
    }
    return type(row) in parts or hasattr(row, "scope_id")


def _rows(plan):
    """The duplicate and the survivor as they stand, or a refusal."""
    from django.apps import apps

    found = []
    for label, pk in (plan.duplicate, plan.survivor):
        row = apps.get_model(label).objects.filter(pk=pk).first()
        if row is None:
            raise Refused(f"nothing was merged: {label} {pk} is already gone")
        found.append(row)
    return found


def plan_again(plan):
    duplicate, survivor = _rows(plan)
    return plan_merge(duplicate, survivor)


class MergeRun:
    """A merge plan as the gang-by-gang runner reads one."""

    def __init__(self, plan):
        self.plan = plan

    @property
    def gangs(self):
        return [(part.pk,) for part in self.plan.gangs]

    @property
    def problems(self):
        return list(self.plan.refusals)

    @property
    def nothing_here(self):
        return False

    def preview(self):
        return list(self.plan.preview())


def merge_run(plan):
    """Rebuild the plan under the runner lock and reject changes since confirmation.

    Return a ``MergeRun`` for the refreshed plan.
    """
    now = plan_again(plan)
    if not now.same_as(plan):
        return MergeRun(
            replace(
                now,
                refusals=(
                    *now.refusals,
                    "what names this row has changed since the page was read "
                    "— read it again",
                ),
            )
        )
    return MergeRun(now)


def merge_gang(gang_id, plan):
    """Repoint one gang in its own transaction, then finish library cleanup if last.

    Lock and reload the gang. Include newer purchases, but reject profiles
    without survivor counterparts. Preserve ledger entries and reconcile before
    and after. An already deleted duplicate makes a replay a no-op.
    """
    from django.apps import apps

    from n26.core.models import Assignment, Gang, LedgerEntry, Reason
    from n26.core.reconcile import check_gang

    label, pk = plan.duplicate
    if not apps.get_model(label).objects.filter(pk=pk).exists():
        # A delivery replayed after the last gang finished the merge.
        return "nothing left to move: the duplicate is already gone"
    with transaction.atomic():
        gang = Gang.objects.select_for_update().get(pk=gang_id)
        duplicate, survivor = _rows(plan)
        mapping, missing = _map_lines(duplicate, survivor)
        if missing:
            return f"gang {gang.name}: skipped — " + "; ".join(
                f"the line “{line.name or 'its own line'}” has no counterpart"
                for line in missing
            )
        to_line = {dup: survivor_pk for dup, _, survivor_pk in mapping}
        column = _column_for(type(duplicate))
        held = list(
            Assignment.objects.select_for_update()
            .filter(gang_root=gang, **{column: duplicate})
            .order_by("pk")
        )
        lines = list(
            Assignment.objects.select_for_update()
            .filter(gang_root=gang, weapon_profile__in=list(to_line))
            .order_by("pk")
        )
        if not held and not lines:
            return f"gang {gang.name}: nothing left to move"
        problems = check_gang(gang)
        if problems:
            raise Refused(
                f"gang {gang.name} did not reconcile before the merge: "
                + "; ".join(problems)
            )

        moved = 0
        # Replace the duplicate in its existing assignable column.
        # Bulk updates are safe because assignment hosts and roots do not change.
        Assignment.objects.filter(pk__in=[a.pk for a in held]).update(
            **{column: survivor}
        )
        moved += len(held)
        # Merge profiles by name, removing a later duplicate when it is free.
        seen = {}
        for line in lines:
            target = to_line[str(line.weapon_profile_id)]
            keep = seen.get((line.parent_id, target))
            if keep is not None:
                if _paid_for(line):
                    raise Refused(
                        f"gang {gang.name}: a fighter paid twice for the line "
                        f"“{line.weapon_profile.name}”; refund one first"
                    )
                line.delete()
                continue
            Assignment.objects.filter(pk=line.pk).update(weapon_profile_id=target)
            seen[(line.parent_id, target)] = line.pk
            moved += 1
        # Add missing free profiles directly, without attributing a purchase to the owner.
        granted = 0
        # Add every free profile of the survivor. Collection-specific profile prices
        # are unavailable here because the original purchase collection is not read.
        free = [line for line in _lines_of(survivor) if line.price == 0]
        for weapon in Assignment.objects.filter(pk__in=[a.pk for a in held]):
            has = set(
                Assignment.objects.filter(parent=weapon).values_list(
                    "weapon_profile_id", flat=True
                )
            )
            for profile in free:
                if profile.pk in has:
                    continue
                line = Assignment.objects.create(
                    weapon_profile=profile,
                    parent=weapon,
                    caused_by=weapon,
                    archived=weapon.archived,
                    archived_at=weapon.archived_at,
                )
                LedgerEntry.objects.create(assignment=line, reason=Reason.DEFAULT)
                granted += 1
        problems = check_gang(gang)
        if problems:
            raise Refused(
                f"gang {gang.name} did not reconcile after the merge: "
                + "; ".join(problems)
            )
        said = f"gang {gang.name}: pointed {moved} assignment{'' if moved == 1 else 's'} at {_said(survivor)}"
        if granted:
            said += f", granting {granted} free line{'' if granted == 1 else 's'}"
        # After the last gang is processed, remove library references to the duplicate.
        if not _any_gang_names(duplicate):
            said += "; " + merge_library(plan)
        return said


def _paid_for(assignment):
    try:
        entry = assignment.ledger_entry
    except Exception:  # noqa: BLE001 — no entry is not a payment
        return False
    return (entry.paid, entry.trade_points, entry.rating_contribution) != (0, 0, 0)


def _column_for(model):
    from django.apps import apps

    from n26.core.models.assignment import ASSIGNABLE_FIELDS

    for column, label in ASSIGNABLE_FIELDS.items():
        if apps.get_model(label) is model:
            return column
    raise Refused(f"a {model._meta.verbose_name} is never assigned")


def _any_gang_names(duplicate):
    from n26.core.models import Assignment

    column = _column_for(type(duplicate))
    if Assignment.objects.filter(**{column: duplicate}).exists():
        return True
    lines = _lines_of(duplicate)
    return bool(lines) and Assignment.objects.filter(weapon_profile__in=lines).exists()


def merge_library(plan):
    """Point the library's own references at the survivor and delete
    the duplicate, in one transaction. Returns the line for the report."""
    from n26.core.models import LedgerEntry
    from n26.library import authoring
    from n26.library.models import CollectionEntry, DefaultAssignment

    with transaction.atomic():
        duplicate, survivor = _rows(plan)
        mapping, missing = _map_lines(duplicate, survivor)
        if missing:
            raise Refused(
                "the library's part was not done: "
                + "; ".join(
                    f"the line “{line.name or 'its own line'}” has no counterpart"
                    for line in missing
                )
            )
        to_line = {dup: survivor_pk for dup, _, survivor_pk in mapping}
        things = [duplicate, *_lines_of(duplicate)]
        survivor_lines = {str(line.pk): line for line in _lines_of(survivor)}
        by_model = {}
        for thing in things:
            by_model.setdefault(type(thing), []).append(thing)
        moved = dropped = 0
        for model, rows in by_model.items():
            for reference in references_to(*rows):
                row = reference.row
                label = reference.label
                if reference.field == "weapon_profile":
                    current = str(getattr(row, "weapon_profile_id", ""))
                    target = survivor_lines.get(to_line.get(current, ""))
                else:
                    target = survivor
                if label == "n26.assignment":
                    raise Refused(
                        f"a fighter still has {_said(duplicate)}; run the merge again"
                    )
                if (
                    label == "library.collectionentry"
                    and reference.field != "weapon_profile"
                ):
                    standing = CollectionEntry.objects.filter(
                        collection_id=row.collection_id, **{reference.field: survivor}
                    ).first()
                    if standing is not None:
                        LedgerEntry.objects.filter(bought_from=row).update(
                            bought_from=standing
                        )
                        row.delete()
                        dropped += 1
                        continue
                if reference.cascades:
                    continue
                if not reference.protects and not reference.empties:
                    # A many-to-many listing the duplicate: swapped, each
                    # member for its own counterpart.
                    manager = getattr(row, reference.field)
                    listed = [t for t in things if isinstance(t, model)]
                    manager.remove(*listed)
                    for member in listed:
                        manager.add(
                            survivor_lines[to_line[str(member.pk)]]
                            if str(member.pk) in to_line
                            else survivor
                        )
                    moved += 1
                    continue
                if (
                    isinstance(row, DefaultAssignment)
                    and reference.field != "weapon_profile"
                ):
                    if DefaultAssignment.objects.filter(
                        default_set_id=row.default_set_id, **{reference.field: survivor}
                    ).exists():
                        raise Refused(
                            f"the built-in set “{row.default_set}” already brings "
                            f"{_said(survivor)}"
                        )
                setattr(row, reference.field, target)
                row.save(update_fields=[reference.field])
                moved += 1
        authoring.delete_content(duplicate)
        said = f"moved {moved} library reference{'' if moved == 1 else 's'}"
        if dropped:
            said += f", dropped {dropped} list line{'' if dropped == 1 else 's'} already offered"
        return said + f"; deleted {plan.duplicate_said}"
