"""What the conversions left standing, and deleting it.

Moving the hand-built choice systems onto slots and picks left their old
machinery behind on purpose: a conversion proves that nothing a reader
sees moves, and deleting rows is a different job with a different risk.
This is that job.

What stands is a library of things nothing uses. The kind rows the
conversions emptied — their modifiers moved onto pickables, so each is a
name and nothing else. The menus those kinds were chosen from, which no
question now offers. The offers themselves, detached from every carrier
or carried by a marker nothing holds. Read from the authoring pages it
looks like content; read from a player's page it is not there at all.

**Nothing here may change a page.** That is the whole test, and it is
what makes deleting safe to do in bulk: if these rows really are unused,
removing them is invisible, and if any of them is doing something the
proof says so and the run unwinds.

Three rules keep the reading honest:

* A kind row that still carries a modifier is doing something, whatever
  its column says. It is left where it is and named on the page, rather
  than deleted or made into a refusal — the run should not fail over
  content somebody is in the middle of moving.
* A kind row anything still names cannot be deleted at all. Those are
  the answers the sweep and the clearing deal with, so this refuses and
  says which, rather than running before its turn.
* A menu is deleted only when everything in it names a retired kind and
  nothing outside what is going asks for it. A menu holding one live
  entry keeps its shape and loses only the entries.

An effect and its modifier travel together. A modifier here is one
scope and one effect, so removing the effect would leave a scope
addressing nobody about nothing; the carrier it hangs on is kept unless
it too exists solely for what is going.
"""

from dataclasses import dataclass, field

from django.db import transaction


class Refused(Exception):
    """The world is not the one the reading found."""


@dataclass(frozen=True)
class Fossils:
    """Everything that would go, by kind of row."""

    kind_rows: tuple = ()
    entries: tuple = ()
    collections: tuple = ()
    sections: tuple = ()
    modifiers: tuple = ()
    hiddens: tuple = ()
    said: tuple = ()
    left_alone: tuple = ()
    gang_ids: tuple = ()
    problems: tuple = ()
    nothing_here: bool = False
    counts: dict = field(default_factory=dict)

    @property
    def ok(self):
        return not self.problems

    def preview(self):
        if self.nothing_here:
            return ["nothing to delete — the retired kinds have gone already"]
        lines = list(self.said)
        for note in self.left_alone:
            lines.append(f"leave {note}")
        lines.append(
            f"prove {len(self.gang_ids)} gang"
            f"{'' if len(self.gang_ids) == 1 else 's'} read exactly the same, "
            "or refuse"
        )
        return lines


def _kinds():
    """The retired kinds, each with the column an assignment names it by.

    Read from the assignment's own registry rather than guessed from the
    class name: a skill tree is ``skill_tree`` there, and a rule that
    lowercased class names would quietly find nothing.
    """
    from django.apps import apps

    from n26.core.models.assignment import ASSIGNABLE_FIELDS
    from n26.library.conversion.archived import OLD_COLUMNS

    return [
        (column, apps.get_model(ASSIGNABLE_FIELDS[column])) for column in OLD_COLUMNS
    ]


def _named_by(model, rows):
    """The menu entries naming these, where a menu can name them at all.

    Found by what a field points at rather than by what it is called:
    a menu holds only some of the kinds, so asking for a column it does
    not have would be an error rather than an empty answer.
    """
    from n26.library.models import CollectionEntry

    for entry_field in CollectionEntry._meta.get_fields():
        if not getattr(entry_field, "concrete", False):
            continue
        if getattr(entry_field, "related_model", None) is model:
            return CollectionEntry.objects.filter(**{f"{entry_field.name}__in": rows})
    return CollectionEntry.objects.none()


def _held_carriers(effect):
    """What carries this effect and is itself held by somebody, in words.

    An effect reaches a page through its carrier, so a carrier nobody
    holds means the effect is drawn nowhere. Empty when nothing carries
    it, or when what does is held by no one.
    """
    from n26.core.models import Assignment
    from n26.library.conversion.base import carriers_of
    from n26.library.models import Modifier

    modifier = Modifier.objects.filter(**{f"{_part_name(effect)}": effect}).first()
    if modifier is None:
        return ""
    said = []
    for _, carrier in carriers_of(modifier):
        column = _column_for(type(carrier))
        if column and Assignment.objects.filter(**{column: carrier}).exists():
            said.append(str(carrier))
    return ", ".join(sorted(said))


def _part_name(effect):
    """The field a modifier holds this sort of effect in."""
    from n26.library.models import Modifier

    for one_to_one in Modifier._meta.get_fields():
        if not getattr(one_to_one, "concrete", False):
            continue
        if getattr(one_to_one, "related_model", None) is type(effect):
            return one_to_one.name
    raise ValueError(f"no modifier holds a {type(effect).__name__}")


def _anything_naming(row, doomed):
    """What still names this row once everything going has gone.

    Asked of every model and every field that points here rather than of
    a list somebody remembered to write: a marker is named by the
    assignments holding it, by the grants that hand it over, and by the
    built-in kit of every profile it comes with, and only the first of
    those is obvious. What is itself being deleted does not count.
    """
    from django.apps import apps

    found = []
    for model in apps.get_models():
        if model._meta.auto_created:
            continue
        for pointing in model._meta.get_fields():
            if not getattr(pointing, "is_relation", False):
                continue
            if not (
                getattr(pointing, "concrete", False)
                or getattr(pointing, "many_to_many", False)
            ):
                continue
            if getattr(pointing, "related_model", None) is not type(row):
                continue
            here = model.objects.filter(**{pointing.name: row})
            spared = doomed.get(model, set())
            if spared:
                here = here.exclude(pk__in=spared)
            count = here.count()
            if count:
                found.append(f"{count} {model._meta.verbose_name_plural}")
    return ", ".join(sorted(found))


def _column_for(model):
    """The assignment column naming this kind of thing, if there is one."""
    from django.apps import apps

    from n26.core.models.assignment import ASSIGNABLE_FIELDS

    for column, label in ASSIGNABLE_FIELDS.items():
        if apps.get_model(label) is model:
            return column
    return ""


def find():
    """Read what is left of the retired kinds. Never writes."""
    from django.contrib.contenttypes.models import ContentType

    from n26.core.models import Assignment
    from n26.library.models import (
        AddsAssignable,
        Collection,
        CollectionEntry,
        CollectionSection,
        Hidden,
        Modifier,
        OffersChoice,
        PlacesCategory,
        RemovesAssignable,
    )

    problems = []
    left_alone = []
    said = []

    doomed_kinds = []
    for column, model in _kinds():
        for row in model.objects.all().order_by("name"):
            held = Assignment.objects.filter(**{column: row}).count()
            if held:
                problems.append(
                    f"{held} assignment{'' if held == 1 else 's'} still name "
                    f"“{row}”, so it cannot be deleted yet"
                )
                continue
            carried = row.modifiers.count()
            if carried:
                left_alone.append(
                    f"“{row}” where it is: it still carries "
                    f"{carried} modifier{'' if carried == 1 else 's'}, so it "
                    "is doing something whatever its column says"
                )
                continue
            doomed_kinds.append(row)

    if problems:
        return Fossils(problems=tuple(problems))

    # The entries of a menu that name one of those, and the menus that
    # are nothing but such entries.
    entries = []
    for _, model in _kinds():
        here = [row for row in doomed_kinds if isinstance(row, model)]
        if here:
            entries += list(_named_by(model, here).select_related("collection"))
    doomed_entries = {entry.pk for entry in entries}

    # An offer of a retired kind that somebody is carrying is still a
    # question on their card, unanswerable but drawn. Deleting it would
    # take a line off a page, which is not this to do.
    kinds = ContentType.objects.filter(
        app_label="library",
        model__in=[model._meta.model_name for _, model in _kinds()],
    )
    offers = []
    standing = []
    for offer in OffersChoice.objects.filter(of_kind__in=kinds).select_related(
        "from_section"
    ):
        carried_by = _held_carriers(offer)
        if carried_by:
            standing.append(offer)
            left_alone.append(
                f"the offer on “{carried_by}”: somebody holds it, so it is a "
                "question on a card rather than a fossil"
            )
            continue
        offers.append(offer)

    kept_sections = {
        offer.from_section_id for offer in standing if offer.from_section_id
    }
    collections = []
    for collection in Collection.objects.filter(
        pk__in={entry.collection_id for entry in entries}
    ).order_by("name"):
        held = set(
            CollectionEntry.objects.filter(collection=collection).values_list(
                "pk", flat=True
            )
        )
        if held - doomed_entries:
            left_alone.append(
                f"the menu “{collection}”: not everything in it names a "
                "retired kind, so it loses those entries and keeps its shape"
            )
            continue
        asked_of = set(
            CollectionSection.objects.filter(collection=collection).values_list(
                "pk", flat=True
            )
        )
        if asked_of & kept_sections:
            left_alone.append(
                f"the menu “{collection}”: an offer somebody holds still asks "
                "from it, so it keeps its shape"
            )
            continue
        collections.append(collection)
    sections = list(CollectionSection.objects.filter(collection__in=collections))

    for offer in OffersChoice.objects.filter(from_section__in=sections):
        if offer not in offers:
            problems.append(
                f"“{offer.modifier}” asks for a menu that would go but is "
                "not an offer of a retired kind, so the menu is not dead"
            )
    places = list(PlacesCategory.objects.filter(section__in=sections))

    if problems:
        return Fossils(problems=tuple(problems))

    modifiers = {
        row.pk: row
        for row in Modifier.objects.filter(offers_choice__in=offers)
        | Modifier.objects.filter(places_category__in=places)
    }

    # A marker carrying nothing but what is going, and held by nobody, is
    # part of what is going. Whatever grants or takes it away then names
    # something that will not exist, so those go with it.
    hiddens = []
    for hidden in Hidden.objects.filter(modifiers__in=modifiers.values()).distinct():
        others = hidden.modifiers.exclude(pk__in=modifiers).count()
        if others:
            left_alone.append(
                f"the marker “{hidden}”: it carries {others} other "
                f"modifier{'' if others == 1 else 's'}"
            )
            continue
        # Whatever hands this marker over or takes it away exists for it
        # alone and goes with it, so neither counts as a reason to keep
        # it. Everything else naming it does, and the one that matters
        # most is the built-in kit of a profile it comes with.
        handers = {
            naming: set(
                naming.objects.filter(hidden=hidden).values_list("pk", flat=True)
            )
            for naming in (AddsAssignable, RemovesAssignable)
        }
        named_by = _anything_naming(hidden, {**handers, Modifier: set(modifiers)})
        if named_by:
            left_alone.append(f"the marker “{hidden}”: {named_by} still name it")
            continue
        hiddens.append(hidden)

    for row in Modifier.objects.filter(
        adds_assignable__in=AddsAssignable.objects.filter(hidden__in=hiddens)
    ) | Modifier.objects.filter(
        removes_assignable__in=RemovesAssignable.objects.filter(hidden__in=hiddens)
    ):
        modifiers[row.pk] = row

    # Every gang that could possibly notice: one holding a marker whose
    # modifier is going, or a model of a profile carrying one.
    gang_ids = _gangs_touched(modifiers.values())

    for row in doomed_kinds:
        said.append(f"delete the emptied {type(row).__name__.lower()} “{row}”")
    if entries:
        said.append(
            f"delete {len(entries)} menu entr{'y' if len(entries) == 1 else 'ies'} "
            "naming them"
        )
    for collection in collections:
        said.append(f"delete the menu “{collection}” and its sections")
    for modifier in sorted(modifiers.values(), key=str):
        said.append(f"delete the modifier “{modifier}”, which nothing needs")
    for hidden in hiddens:
        said.append(f"delete the marker “{hidden}”, which nothing holds")

    if not (doomed_kinds or entries or collections or modifiers or hiddens):
        return Fossils(nothing_here=True, left_alone=tuple(left_alone))

    return Fossils(
        kind_rows=tuple((type(row), row.pk) for row in doomed_kinds),
        entries=tuple(entry.pk for entry in entries),
        collections=tuple(collection.pk for collection in collections),
        sections=tuple(section.pk for section in sections),
        modifiers=tuple(modifiers),
        hiddens=tuple(hidden.pk for hidden in hiddens),
        said=tuple(said),
        left_alone=tuple(left_alone),
        gang_ids=tuple(gang_ids),
        counts={
            "kind rows": len(doomed_kinds),
            "menu entries": len(entries),
            "menus": len(collections),
            "modifiers": len(modifiers),
            "markers": len(hiddens),
        },
    )


def _gangs_touched(modifiers):
    """Every gang a modifier being deleted could reach.

    A modifier hangs on a carrier and reaches a page through whoever
    holds that carrier — a marker, a subtype, a profile alike, since
    being hired as one is holding it. Asked of every kind of carrier
    rather than a chosen few: a carrier nobody thought of is a gang the
    proof would not have looked at.
    """
    from n26.core.models import Assignment
    from n26.library.conversion.base import carriers_of

    gangs = set()
    for modifier in modifiers:
        for _, carrier in carriers_of(modifier):
            column = _column_for(type(carrier))
            if not column:
                continue
            gangs |= set(
                Assignment.objects.filter(**{column: carrier})
                .values_list("gang_root_id", flat=True)
                .distinct()
            )
    gangs.discard(None)
    return sorted(gangs, key=str)


def _delete_parts_of(modifiers):
    """Delete each modifier's scope and effect, taking it with them."""
    from n26.library.models import Modifier

    parts = [
        one_to_one.name
        for one_to_one in Modifier._meta.get_fields()
        if getattr(one_to_one, "one_to_one", False)
        and getattr(one_to_one, "concrete", False)
    ]
    for modifier in list(modifiers):
        for part in parts:
            held = getattr(modifier, part, None)
            if held is not None:
                held.delete()


def apply(fossils):
    """Delete exactly what was read, and prove every page unmoved."""
    from django.db.models import ProtectedError

    from n26.core.capture import differences, gang_state
    from n26.core.models import Gang
    from n26.core.reconcile import assert_reconciled
    from n26.library.conversion.base import _one_snapshot
    from n26.library.models import (
        Collection,
        CollectionEntry,
        CollectionSection,
        Hidden,
        Modifier,
    )

    if fossils.problems:
        raise Refused("not deleted: " + "; ".join(fossils.problems))
    if fossils.nothing_here:
        return list(fossils.preview())

    report = list(fossils.preview())
    try:
        with _one_snapshot(), transaction.atomic():
            gangs = list(Gang.objects.filter(pk__in=fossils.gang_ids))
            before = {str(gang.pk): gang_state(gang) for gang in gangs}

            # The order is what protects what. An offer names the menu
            # section it asks from, and a grant names the marker it
            # hands over, so both have to go before the things they
            # name — and a modifier owns its scope and its effect, each
            # of which takes the modifier with it, so what is deleted is
            # the parts rather than the modifier that would leave them
            # behind.
            _delete_parts_of(Modifier.objects.filter(pk__in=fossils.modifiers))
            CollectionEntry.objects.filter(pk__in=fossils.entries).delete()
            CollectionSection.objects.filter(pk__in=fossils.sections).delete()
            Collection.objects.filter(pk__in=fossils.collections).delete()
            Hidden.objects.filter(pk__in=fossils.hiddens).delete()
            for model, pk in fossils.kind_rows:
                model.objects.filter(pk=pk).delete()

            gangs = list(Gang.objects.filter(pk__in=fossils.gang_ids))
            after = {str(gang.pk): gang_state(gang) for gang in gangs}
            changed = differences(before, after)
            if changed:
                raise Refused(
                    "refused — what a reader is told would change:\n  "
                    + "\n  ".join(changed[:10])
                )
            for gang in gangs:
                try:
                    assert_reconciled(gang)
                except Exception as failed:
                    raise Refused(
                        f"refused — {gang} no longer reconciles: {failed}"
                    ) from failed
    except ProtectedError as protected:
        # The backstop behind the enumerated checks: whatever this names
        # is a referent nobody listed, and the answer is a refusal in
        # words rather than a traceback.
        raise Refused(
            "refused — something still names what would be deleted: "
            f"{sorted(str(obj) for obj in protected.protected_objects)[:5]}"
        ) from protected
    report.append("deleted; every page reads the same")
    return report
