"""Deleting a gang type with no name — a one-shot repair.

An ingest of a profiles sheet planned a gang type from a blank ``Gang``
cell, so a ``GangType`` was founded whose name is the empty string. Being
foundable by default, it drew as an empty card on the create-gang page,
sorting before every real gang type because nothing sorts before nothing
— and one player founded a gang on it, which is a gang of nothing: no
house list to hire from, no built-ins, no name to print.

A blank Gang cell is a problem the sheet must fix
(``n26.library.ingest``), the verb refuses a blank name
(``n26.library.authoring.create_gang_type``) and the create page offers
no nameless type (``n26.core.forms``). This deletes the row that stands
in spite of all three, and the gang founded on it.

Deletion is why this is its own operation: conversions delete nothing,
and ``Gang.gang_type`` is ``PROTECT``, so the gang must go first. What
stands between this and deleting somebody's real gang is the check that
each doomed gang is **untouched** — its founding assignment and nothing
else. A gang anyone has hired into is a gang somebody meant to keep,
whatever its type is called, and this refuses in words rather than
delete it.

The plan/apply split is the conversion discipline's: :func:`find` reads
and describes, :func:`apply` performs exactly that.
"""

from dataclasses import dataclass

from django.db import transaction


class Refused(Exception):
    """The repair found more than the accident it was written for."""


@dataclass(frozen=True)
class Nameless:
    """What stands, and what deleting it would take with it."""

    gang_type_ids: tuple = ()
    gang_ids: tuple = ()
    assignment_ids: tuple = ()
    events: int = 0
    problems: tuple = ()
    nothing_here: bool = False

    @property
    def ok(self):
        return not self.problems

    def preview(self):
        if self.nothing_here:
            return ["nothing to delete — every gang type in the pack has a name"]
        types = len(self.gang_type_ids)
        gangs = len(self.gang_ids)
        lines = []
        if gangs:
            lines.append(
                f"delete {gangs} gang{'' if gangs == 1 else 's'} founded on a "
                f"nameless type — each untouched since founding — and with "
                f"{'it' if gangs == 1 else 'them'} "
                f"{len(self.assignment_ids)} founding "
                f"assignment{'' if len(self.assignment_ids) == 1 else 's'}, "
                f"{self.events} history event"
                f"{'' if self.events == 1 else 's'}, and an empty stash"
            )
        else:
            lines.append("no gang was founded on it, so nothing of a player's dies")
        lines.append(
            f"delete {types} gang type{'' if types == 1 else 's'} with no name"
        )
        return lines


def find():
    """Read the nameless types as they stand. Never writes."""
    from n26.core.models import Assignment, Gang, LedgerEvent, Miniature
    from n26.library.models import GangType, Profile
    from n26.library.models.pack import default_pack_id

    # Scoped to the default pack: a custom pack's own rows are somebody's
    # content and not this accident, and the create page no longer offers
    # a nameless one from anywhere.
    doomed_types = list(
        GangType.objects.filter(name="", pack_id=default_pack_id()).order_by("created")
    )
    if not doomed_types:
        return Nameless(nothing_here=True)

    problems = []
    for gang_type in doomed_types:
        if gang_type.built_ins_id is not None or gang_type.modifiers.exists():
            problems.append(
                f"the nameless type {gang_type.pk} carries built-ins or "
                "modifiers — something has been authored onto it, so it is "
                "not the empty row this deletes"
            )
        hired = Profile.objects.filter(gang_type=gang_type)
        if hired.exists():
            problems.append(
                f"{hired.count()} fighter entries are hired off the nameless "
                f"type {gang_type.pk} — it is being used as a gang list, so "
                "it wants a name rather than deleting"
            )

    gangs = list(Gang.objects.filter(gang_type__in=doomed_types))
    doomed_gang_ids = {gang.pk for gang in gangs}
    foundings = {gang.founding_id for gang in gangs if gang.founding_id}

    for gang in gangs:
        # Untouched means: the founding assignment and nothing else. Both
        # the hosted and the denormalised root are read, and archived rows
        # count — a sold weapon is still a gang somebody played.
        theirs = Assignment.objects.filter(gang=gang) | Assignment.objects.filter(
            gang_root=gang
        )
        strays = theirs.exclude(pk=gang.founding_id).distinct().count()
        if strays:
            problems.append(
                f"a gang founded on a nameless type has {strays} assignments "
                "beyond its founding — it has been played, so it is not this "
                "repair's to delete"
            )
        models_in = Miniature.objects.filter(membership__gang=gang).count()
        if models_in:
            problems.append(
                f"a gang founded on a nameless type holds {models_in} models "
                "— it has been hired into, so it is not this repair's to delete"
            )

    # An assignment naming a nameless type that is not one of these gangs'
    # foundings is something this has not accounted for; ``PROTECT`` would
    # stop the delete anyway, and a refusal in words beats a crash.
    strangers = (
        Assignment.objects.filter(gang_type__in=doomed_types)
        .exclude(pk__in=foundings)
        .count()
    )
    if strangers:
        problems.append(
            f"{strangers} assignments name a nameless gang type but are not "
            "one of these gangs' foundings"
        )

    events = LedgerEvent.objects.filter(gang_id__in=doomed_gang_ids).count()
    return Nameless(
        gang_type_ids=tuple(sorted((t.pk for t in doomed_types), key=str)),
        gang_ids=tuple(sorted(doomed_gang_ids, key=str)),
        assignment_ids=tuple(sorted((f for f in foundings), key=str)),
        events=events,
        problems=tuple(problems),
    )


def apply(nameless):
    """Delete exactly what the plan names — the gangs, then the types."""
    from django.db.models import ProtectedError

    from n26.core.models import Gang
    from n26.library.models import GangType

    if nameless.problems:
        raise Refused("not deleted: " + "; ".join(nameless.problems))
    if nameless.nothing_here:
        return list(nameless.preview())

    report = list(nameless.preview())
    try:
        with transaction.atomic():
            # The gangs first: ``Gang.gang_type`` is PROTECT, and their
            # assignments, stash and history events ride them down.
            Gang.objects.filter(pk__in=nameless.gang_ids).delete()
            GangType.objects.filter(pk__in=nameless.gang_type_ids).delete()
    except ProtectedError as protected:
        # The backstop behind find()'s enumerated checks: whatever this
        # names is a referent nobody listed, and the answer is the same
        # refusal in words, never a crash.
        raise Refused(
            "refused — something still names what would be deleted: "
            f"{sorted(str(obj) for obj in protected.protected_objects)[:5]}"
        ) from protected
    report.append("deleted; every gang type in the pack has a name")
    return report
