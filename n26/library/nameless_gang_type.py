"""Plan and repair default-pack gang types with empty or whitespace-only names.

Delete gangs with only their founding assignment. For played gangs, infer a
replacement foundable type only when every active model uses the same gang
list. Leave ambiguous gangs and their types unchanged.

Refounding preserves the original assignment, opening ledger entry and
creation history while applying the replacement type's free built-ins.
Ratings and cached ledger totals must remain unchanged.

Delete a type only after resolving every gang reference. ``find`` builds the
preview; ``apply`` locks affected records, rebuilds the plan and rejects
changes before performing it.
"""

from dataclasses import dataclass, field

from django.db import transaction

#: A name that draws as nothing: empty, or only whitespace.
BLANK = r"^\s*$"


class Refused(Exception):
    """The repair found more than the accident it was written for."""


@dataclass(frozen=True)
class Nameless:
    """What stands, and what retiring it does to each part."""

    #: Unused types to delete after processing the plan.
    gang_type_ids: tuple = ()
    #: Types retained because an unreadable gang still references them.
    kept_type_ids: tuple = ()
    #: Untouched gangs, deleted with the type.
    doomed_gang_ids: tuple = ()
    #: ``(gang id, target type id)`` for each gang played as something.
    repoint: tuple = ()
    #: Founding records deleted with their gangs.
    assignment_ids: tuple = ()
    events: int = 0
    print_configs: int = 0
    #: Assignments and options granted by types being replaced.
    #: Reject types with grants because this repair does not issue refunds.
    replaced: int = 0
    #: Gangs left alone, each with the reason in words. Not a refusal —
    #: the rest of the plan still runs.
    stranded: tuple = ()
    problems: tuple = ()
    nothing_here: bool = False
    #: What a target type is called, by id, so the preview reads in names.
    said: dict = field(default_factory=dict, compare=False)

    @property
    def ok(self):
        return not self.problems

    def preview(self):
        if self.nothing_here:
            return ["nothing to retire — every gang type in the pack has a name"]
        lines = []
        for _, target_id in self.repoint:
            lines.append(
                f"repoint a played gang onto {self.said.get(target_id, target_id)}, "
                "the list its models were hired from — the act that founded it "
                "is kept and made to name that type, so its history still opens "
                "with its owner creating it, and that type's built-ins and "
                "gang-wide rules arrive. Its models, its gear and its budget "
                "are untouched"
            )

        if self.doomed_gang_ids:
            gangs = len(self.doomed_gang_ids)
            rides = [
                f"{len(self.assignment_ids)} founding "
                f"assignment{'' if len(self.assignment_ids) == 1 else 's'}",
                f"{self.events} history event{'' if self.events == 1 else 's'}",
                "an empty stash",
            ]
            if self.print_configs:
                rides.append(
                    f"{self.print_configs} saved print "
                    f"layout{'' if self.print_configs == 1 else 's'}"
                )
            lines.append(
                f"delete {gangs} untouched gang{'' if gangs == 1 else 's'} "
                f"founded on a nameless type, and with "
                f"{'it' if gangs == 1 else 'them'} " + ", ".join(rides)
            )
        for reason in self.stranded:
            lines.append(f"leave standing: {reason}")
        if self.gang_type_ids:
            types = len(self.gang_type_ids)
            lines.append(
                f"delete {types} gang type{'' if types == 1 else 's'} with no "
                f"name, once nothing stands on {'it' if types == 1 else 'them'}"
            )
        if self.kept_type_ids:
            kept = len(self.kept_type_ids)
            lines.append(
                f"keep {kept} nameless gang type{'' if kept == 1 else 's'}, still "
                f"named by a gang nobody can read"
            )
        return lines


def _played_as(gang, doomed_type_ids):
    """Infer a replacement type from active models, or explain why it is ambiguous.

    Return ``(target, reason)`` with one value set. Ignore archived models.
    A single matching type must also be available for founding.
    """
    from n26.core.models import Assignment
    from n26.library.models import GangType

    hired = Assignment.objects.filter(
        gang_root=gang, profile__isnull=False, archived=False
    ).values_list("profile__gang_type_id", flat=True)
    types = set(hired) - {None} - set(doomed_type_ids)
    if not types:
        return None, "no gang list at all"
    if len(types) > 1:
        return None, f"{len(types)} different gang lists"
    foundable = set(
        GangType.objects.filter(pk__in=types, foundable=True).values_list(
            "pk", flat=True
        )
    )
    if not foundable:
        return None, "a list nobody can found a gang on"
    return next(iter(foundable)), ""


def find():
    """Read the nameless types as they stand. Never writes."""
    from n26.core.models import (
        Assignment,
        ChosenProfileOption,
        Gang,
        LedgerEvent,
        Miniature,
        PrintConfig,
    )
    from n26.library.models import GangType, Profile
    from n26.library.models.pack import default_pack_id

    # Limit this repair to the default pack; custom content is outside its scope.
    doomed_types = list(
        GangType.objects.filter(
            # Whitespace draws the same empty card as nothing at all.
            name__regex=BLANK,
            pack_id=default_pack_id(),
        ).order_by("created")
    )
    if not doomed_types:
        return Nameless(nothing_here=True)

    doomed_type_ids = [row.pk for row in doomed_types]
    problems = []
    for gang_type in doomed_types:
        if gang_type.built_ins_id is not None or gang_type.modifiers.exists():
            problems.append(
                f"the nameless type {gang_type.pk} carries built-ins or "
                "modifiers — something has been authored onto it, so it is "
                "not the empty row this retires"
            )
        hired = Profile.objects.filter(gang_type=gang_type).count()
        if hired:
            problems.append(
                f"{hired} fighter entries are hired off the nameless "
                f"type {gang_type.pk} — it is being used as a gang list, so "
                "it wants a name rather than retiring"
            )

    gangs = list(Gang.objects.filter(gang_type__in=doomed_types))
    doomed_gangs, repoint, stranded, said = [], [], [], {}
    standing_on = set()
    replaced = 0

    for gang in gangs:
        # Untouched means: the founding assignment and nothing else. Both
        # the hosted and the denormalised root are read, and archived rows
        # count — a sold weapon is still a gang somebody played.
        theirs = Assignment.objects.filter(gang=gang) | Assignment.objects.filter(
            gang_root=gang
        )
        strays = theirs.exclude(pk=gang.founding_id).distinct().count()
        # Miniature.membership uses SET_NULL, so explicitly reject gangs with models
        # to avoid leaving unowned models after deletion.
        models_in = Miniature.objects.filter(membership__gang=gang).count()

        if not strays and not models_in:
            doomed_gangs.append(gang)
            continue

        target, why = _played_as(gang, doomed_type_ids)
        if target is None:
            stranded.append(
                f"a gang holding {models_in} models and {strays} assignments "
                f"beyond its founding, whose models come from {why} — nobody "
                "can say what it was played as, so it keeps the type it has"
            )
            standing_on.add(gang.gang_type_id)
            continue
        repoint.append((gang.pk, target))
        if target not in said:
            said[target] = str(GangType.objects.get(pk=target))
        # Count grants caused by the existing founding before replacing its built-ins.
        # A missing founding must not become a caused_by=None filter, which would
        # match unrelated assignments.
        if gang.founding_id:
            replaced += (
                Assignment.objects.filter(caused_by_id=gang.founding_id).count()
                + ChosenProfileOption.objects.filter(
                    assignment_id=gang.founding_id
                ).count()
            )

    if replaced:
        problems.append(
            f"a founding being repointed granted its gang {replaced} things — "
            "giving those back is a refund's work, not this repair's, so it "
            "is left alone"
        )

    doomed_gang_ids = {gang.pk for gang in doomed_gangs}
    foundings = {gang.founding_id for gang in doomed_gangs if gang.founding_id}
    repointing = {pk for pk, _ in repoint}

    # Every assignment referencing a deleted type must be removed or reissued
    # by this plan. Reject other references before PROTECT fails the transaction.
    going = [row for row in doomed_types if row.pk not in standing_on]
    settled = {
        *foundings,
        *(
            gang.founding_id
            for gang in gangs
            if gang.pk in repointing and gang.founding_id
        ),
    }
    strangers = (
        Assignment.objects.filter(gang_type__in=going).exclude(pk__in=settled).count()
    )
    if strangers:
        problems.append(
            f"{strangers} assignments name a nameless gang type that would be "
            "deleted and are not a founding this takes away"
        )

    events = LedgerEvent.objects.filter(gang_id__in=doomed_gang_ids).count()
    # Saved print layouts cascade with their gang; include them in the preview.
    layouts = PrintConfig.objects.filter(gang_id__in=doomed_gang_ids).count()
    return Nameless(
        gang_type_ids=tuple(
            sorted((pk for pk in doomed_type_ids if pk not in standing_on), key=str)
        ),
        kept_type_ids=tuple(sorted(standing_on, key=str)),
        doomed_gang_ids=tuple(sorted(doomed_gang_ids, key=str)),
        repoint=tuple(sorted(repoint, key=lambda pair: str(pair[0]))),
        assignment_ids=tuple(sorted(foundings, key=str)),
        events=events,
        print_configs=layouts,
        replaced=replaced,
        stranded=tuple(stranded),
        problems=tuple(problems),
        said=said,
    )


def _repoint(gang, target, actor=None):
    """Refound a gang while preserving its founding assignment and history.

    Apply the replacement type's built-ins through the operation, which refreshes
    cached totals. Replacing the assignment would cascade the original opening
    ledger entry and creation event.
    """
    from n26.core.operations import operation

    with operation(gang, actor=actor) as op:
        op.refound(target)


def apply(nameless, actor=None):
    """Perform exactly what the plan names, and prove the gangs whole."""
    from django.db.models import ProtectedError

    from n26.core.models import Gang
    from n26.core.operations import Refusal
    from n26.core.reconcile import Discrepancy, assert_reconciled
    from n26.library.models import GangType

    if nameless.problems:
        raise Refused("not retired: " + "; ".join(nameless.problems))
    if nameless.nothing_here:
        return list(nameless.preview())

    report = list(nameless.preview())
    repointed = [pk for pk, _ in nameless.repoint]
    try:
        with transaction.atomic():
            # Lock gangs before rebuilding the plan to prevent new assignments during
            # deletion. Foreign-key checks take conflicting key-share locks; rebuilding
            # then rejects changes made before the locks were acquired.
            list(
                Gang.objects.select_for_update()
                .filter(pk__in=[*nameless.doomed_gang_ids, *repointed])
                .order_by("pk")
            )
            # Also lock types to prevent new foundings after the plan is rebuilt.
            list(
                GangType.objects.select_for_update()
                .filter(pk__in=nameless.gang_type_ids)
                .order_by("pk")
            )
            now = find()
            if (
                now.problems
                or set(now.doomed_gang_ids) != set(nameless.doomed_gang_ids)
                or set(now.repoint) != set(nameless.repoint)
                or set(now.gang_type_ids) != set(nameless.gang_type_ids)
                or set(now.assignment_ids) != set(nameless.assignment_ids)
                # Recheck counts as well as identities so new history or saved layouts cannot
                # be deleted without appearing in the confirmed preview.
                or now.events != nameless.events
                or now.print_configs != nameless.print_configs
                or now.replaced != nameless.replaced
            ):
                raise Refused(
                    "not retired: what stands has changed since the plan was "
                    "read — read it again"
                )

            # Repoint played gangs before deleting the types they reference.
            for gang_id, target_id in nameless.repoint:
                try:
                    _repoint(
                        Gang.objects.get(pk=gang_id),
                        GangType.objects.get(pk=target_id),
                        actor=actor,
                    )
                except Refusal as refused:
                    # Record operation refusals as readable task failures.
                    raise Refused(
                        f"refused — a repoint was turned away: {refused}"
                    ) from refused

            Gang.objects.filter(pk__in=nameless.doomed_gang_ids).delete()
            GangType.objects.filter(pk__in=nameless.gang_type_ids).delete()

            # Replacing a founding adds built-ins for free, so rating and cached ledger
            # totals must remain unchanged.
            for gang_id in repointed:
                gang = Gang.objects.get(pk=gang_id)
                try:
                    assert_reconciled(gang)
                except Discrepancy as failed:
                    raise Refused(
                        f"refused — a repointed gang no longer reconciles: {failed}"
                    ) from failed
    except ProtectedError as protected:
        # Convert any unenumerated protected reference into a recorded refusal.
        raise Refused(
            "refused — something still names what would be retired: "
            f"{sorted(str(obj) for obj in protected.protected_objects)[:5]}"
        ) from protected

    if nameless.repoint:
        report.append(
            "repointed gangs "
            + ", ".join(f"{pk} → {target}" for pk, target in nameless.repoint)
        )
    # Record deleted gangs separately because their former type may remain.
    if nameless.doomed_gang_ids:
        report.append(
            "deleted gangs " + ", ".join(str(pk) for pk in nameless.doomed_gang_ids)
        )
    if nameless.gang_type_ids:
        report.append(
            "deleted gang types " + ", ".join(str(pk) for pk in nameless.gang_type_ids)
        )
    report.append(
        "done; a nameless type stands where a gang could not be read"
        if nameless.kept_type_ids
        else "retired; every gang type in the pack has a name"
    )
    return report
