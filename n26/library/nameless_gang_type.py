"""Retiring a gang type with no name — a one-shot repair.

An ingest of a profiles sheet planned a gang type from a blank ``Gang``
cell, so a ``GangType`` was founded whose name is the empty string. Being
foundable by default, it draws as an empty card on the create-gang page,
sorting before every real gang type because nothing sorts before nothing.
A gang founded on it is a gang of nothing: no house list to hire from, no
built-ins, no name to print.

A blank Gang cell is a problem the sheet must fix
(``n26.library.ingest``), the verb refuses a blank name
(``n26.library.authoring.create_gang_type``) and the create page offers
no nameless type (``n26.core.forms``). This retires the row that stands
in spite of all three, and settles whatever was founded on it.

Two endings, per gang, because the gangs are not alike:

* **Untouched** — its founding assignment and nothing else. Nobody has
  played it, so it goes with the type.
* **Played** — models hired, gear bought. Deleting one of these would
  destroy somebody's gang, so instead it is **repointed** to the type it
  has really been played as: the one every model it holds was hired
  from. A gang whose models all come from the Outcast list is an Outcast
  gang naming the wrong type, and saying so takes nothing away.

Repointing is not a change of column, and it is not a second founding
either. What a gang type brings — its built-ins and its gang-wide
modifiers — arrives *caused by the founding assignment*, so the repoint
goes through ``operation.refound``: the founding the owner made is kept
and made to name the new type, and that type's built-ins arrive caused
by it. Keeping it is the point. The founding carries the gang's opening
ledger entry and the history event that says its owner created it, and
both cascade with the assignment — a gang founded afresh would open its
history with a stranger creating it, dated the day of the repair. The
operation rewrites the pinned numbers as it closes; built-ins arrive
free, so the gang's rating cannot move.

A gang that cannot be read this way — models from several lists, or from
none — is left exactly as it stands, and the type it names is left with
it. Half a repair on somebody's gang is worse than none, and a type
nothing stands on can be retired whenever it is.

``Gang.gang_type`` is ``PROTECT``, which fixes the order: every gang
settles before the type it names can go.

The plan/apply split is the conversion discipline's: :func:`find` reads
and describes, :func:`apply` performs exactly that.
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

    #: Types nothing stands on once the plan has run — these go.
    gang_type_ids: tuple = ()
    #: Types left standing, because a gang nobody can read names them.
    kept_type_ids: tuple = ()
    #: Untouched gangs, deleted with the type.
    doomed_gang_ids: tuple = ()
    #: ``(gang id, target type id)`` for each gang played as something.
    repoint: tuple = ()
    #: The foundings of the doomed gangs, which ride them down.
    assignment_ids: tuple = ()
    events: int = 0
    print_configs: int = 0
    #: What the nameless type materialised onto the gangs being
    #: repointed, which the new type's built-ins replace.
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
        if self.replaced:
            lines.append(
                f"remove {self.replaced} assignment"
                f"{'' if self.replaced == 1 else 's'} the nameless type gave "
                "those gangs, replaced by what the new type gives"
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
    """The gang type this gang's models were really hired from.

    One answer or none: a gang whose living models all come from one
    list is that list's gang under another name, and one whose models
    come from several is a gang nobody can read on its owner's behalf.
    Archived rows are left out — a model long since dead says less about
    what the gang is than the ones standing in it now.

    The one answer must also be a list a player could found a gang on,
    or the repair would move somebody's gang somewhere they could never
    have put it themselves.
    """
    from n26.core.models import Assignment
    from n26.library.models import GangType

    hired = Assignment.objects.filter(
        gang_root=gang, profile__isnull=False, archived=False
    ).values_list("profile__gang_type_id", flat=True)
    types = set(hired) - {None} - set(doomed_type_ids)
    # Only onto a type somebody could have founded. A pet or a hired gun
    # carries a profile off a list nobody plays as — Dramatis Personae,
    # Allies — and a gang moved onto one of those would be a gang no
    # player could have made.
    foundable = set(
        GangType.objects.filter(pk__in=types, foundable=True).values_list(
            "pk", flat=True
        )
    )
    return next(iter(foundable)) if len(foundable) == 1 and len(types) == 1 else None


def _why_unreadable(gang, doomed_type_ids):
    """Which of the two shapes a gang nobody can read is in."""
    from n26.core.models import Assignment

    found = (
        set(
            Assignment.objects.filter(
                gang_root=gang, profile__isnull=False, archived=False
            ).values_list("profile__gang_type_id", flat=True)
        )
        - {None}
        - set(doomed_type_ids)
    )
    if not found:
        return "no gang list at all"
    if len(found) > 1:
        return f"{len(found)} different gang lists"
    return "a list nobody can found a gang on"


def find():
    """Read the nameless types as they stand. Never writes."""
    from n26.core.models import Assignment, Gang, LedgerEvent, Miniature, PrintConfig
    from n26.library.models import GangType, Profile
    from n26.library.models.pack import default_pack_id

    # Scoped to the default pack: a custom pack's own rows are somebody's
    # content and not this accident, and the create page offers no
    # nameless type from any pack.
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
        # Not covered by the strays count, and not belt and braces:
        # ``Miniature.membership`` is SET_NULL, so deleting a gang with
        # models on it would leave the models behind, belonging to nothing.
        models_in = Miniature.objects.filter(membership__gang=gang).count()

        if not strays and not models_in:
            doomed_gangs.append(gang)
            continue

        target = _played_as(gang, doomed_type_ids)
        if target is None:
            stranded.append(
                f"a gang holding {models_in} models and {strays} assignments "
                f"beyond its founding, whose models come from "
                f"{_why_unreadable(gang, doomed_type_ids)} — nobody can say "
                "what it was played as, so it keeps the type it has"
            )
            standing_on.add(gang.gang_type_id)
            continue
        repoint.append((gang.pk, target))
        said[target] = str(GangType.objects.get(pk=target))
        # What the old type gave the gang goes when the new type's
        # built-ins arrive. A nameless type carrying built-ins is refused
        # above, so this is normally nothing — counted rather than
        # assumed, because the preview promises the gang keeps what it
        # owns and that promise should be checked.
        replaced += Assignment.objects.filter(caused_by_id=gang.founding_id).count()

    doomed_gang_ids = {gang.pk for gang in doomed_gangs}
    foundings = {gang.founding_id for gang in doomed_gangs if gang.founding_id}
    repointing = {pk for pk, _ in repoint}

    # Only the types actually going are at issue: a gang left standing
    # goes on naming the type it names, which is why that type stays.
    # Every assignment naming a type that *is* going has to be one this
    # plan takes away — the founding of a gang being deleted, or of one
    # being repointed, whose founding is reissued. Anything else still
    # names the type when the delete comes, and ``PROTECT`` would fail
    # the run whole: a refusal in words beats a rollback nobody can read.
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
    # Saved print layouts cascade with the gang. They are not a reason to
    # refuse — a layout is a view of a gang, not something played — but
    # the preview enumerates everything that dies, so it says these too.
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
    """Say what a gang really is, and give it what that brings.

    The founding assignment is repointed rather than replaced, because
    it carries the gang's opening ledger entry and the history event
    that says its owner created it. Deleting it would take that act out
    of the gang's history — entry and event cascade with the assignment
    — and write a new one, dated today, in the name of whoever ran the
    repair. What changes is the type the gang names, the built-ins that
    arrive with it, and the pinned numbers the operation rewrites as it
    closes.
    """
    from n26.core.operations import operation

    gang.gang_type = target
    gang.save(update_fields=["gang_type", "modified"])
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
            # The plan was read before this transaction opened, and a
            # gang's assignments cascade rather than protect — so a gang
            # played in between would ride a delete down instead of
            # refusing. Two things close that window. The gangs are
            # locked first: assigning anything to a gang takes a
            # key-share lock on its row, which this conflicts with, so
            # no hire can land from here on. Then the plan is read
            # again, and anything that moved before the lock refuses.
            list(
                Gang.objects.select_for_update()
                .filter(pk__in=[*nameless.doomed_gang_ids, *repointed])
                .order_by("pk")
            )
            # The types as well as the gangs: a gang founded on one after
            # the re-read would fail the delete as a database error
            # rather than as a refusal anybody can read.
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
                # The counts too, not only the rows named: the preview
                # promises everything that dies, and a history event or a
                # saved layout written since it was read would die
                # unannounced.
                or now.events != nameless.events
                or now.print_configs != nameless.print_configs
            ):
                raise Refused(
                    "not retired: what stands has changed since the plan was "
                    "read — read it again"
                )

            # Played gangs first: each stops naming a nameless type, which
            # is what lets the type go at the end.
            for gang_id, target_id in nameless.repoint:
                try:
                    _repoint(
                        Gang.objects.get(pk=gang_id),
                        GangType.objects.get(pk=target_id),
                        actor=actor,
                    )
                except Refusal as refused:
                    # An operation that turns something away says why in
                    # words; that is an ending the record can carry,
                    # never a traceback.
                    raise Refused(
                        f"refused — a repoint was turned away: {refused}"
                    ) from refused

            Gang.objects.filter(pk__in=nameless.doomed_gang_ids).delete()
            GangType.objects.filter(pk__in=nameless.gang_type_ids).delete()

            # A repoint must leave the books exactly as it found them:
            # built-ins arrive free, so the rating cannot move, and the
            # pinned numbers must still describe the ledger they came
            # from.
            for gang_id in repointed:
                gang = Gang.objects.get(pk=gang_id)
                try:
                    assert_reconciled(gang)
                except Discrepancy as failed:
                    raise Refused(
                        f"refused — a repointed gang no longer reconciles: {failed}"
                    ) from failed
    except ProtectedError as protected:
        # The backstop behind find()'s enumerated checks: whatever this
        # names is a referent nobody listed, and the answer is the same
        # refusal in words, never a crash.
        raise Refused(
            "refused — something still names what would be retired: "
            f"{sorted(str(obj) for obj in protected.protected_objects)[:5]}"
        ) from protected

    if nameless.repoint:
        report.append(
            "repointed gangs "
            + ", ".join(f"{pk} → {target}" for pk, target in nameless.repoint)
        )
    # A gang can be deleted while the type it stood on stays, and a
    # destructive outcome the record does not name is a deletion nobody
    # can trace.
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
