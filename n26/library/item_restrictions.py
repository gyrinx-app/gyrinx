"""The fighter-entry restrictions an upload wrote onto listed items, and
clearing them.

A restriction can live in two places. On an item, ``usable_by_*`` means
"true wherever this item appears" (``UsableBy`` in
``n26/library/models/assignable.py``). On a collection entry, the same
three lists mean "only on this list's line" — the "(Forge-born only)"
one gang's book prints beside a saw that every other gang lists
plainly.

The equipment-lists upload read the sheet's Restrictions column as a
fact about the item rather than about the line, so every "<Fighter>
only" it met was written onto the item, and an item one gang's list
narrowed was narrowed for every gang. The upload is add-only, so every
re-upload wrote the same links again, and the collection page — where
an author working a list looks — showed only the entry's own narrowing,
so the restriction seemed to come from nowhere.

This is the repair: strip the item-level restriction to fighter entries
from every item that appears in at least one collection entry. The
upload now writes the column onto the entry, so uploading the lists
again afterwards restores each list's own brackets where the sheet
prints them.

What it leaves alone, and why:

* An item's restriction to types or subtypes. The upload only ever
  resolved profiles, so those were written by hand and are meant.
* An item no collection lists. Nothing wrote that link on the way past
  a list, so it was authored on purpose.
* Every entry's own lists. Those are the right place, and the upload's
  fixed reading writes there.

It is one transaction, and it strips exactly what the preview showed.
The plan is written onto the record when the run is asked for; the run
locks the items it names and the listings that make them eligible,
reads them again, and refuses if what stands differs from what was
approved. One difference is not a refusal: every
approved item carrying nothing at all is the plan carried out — the
clearing committed but its ending was never written, or an author took
the same links off by hand — and that run ends done, writing nothing.
"""

from dataclasses import dataclass

from django.conf import settings
from django.db import transaction


class Refused(Exception):
    """The world is not the one the reading found."""


@dataclass(frozen=True)
class Restricted:
    """One listed item and the restriction to strip from it."""

    #: ``app_label.model_name``, so the row can be found again.
    model: str
    pk: str
    #: How the item reads: its label and kind.
    label: str
    #: The pack's name where it is not the default pack, else empty.
    pack: str
    profile_ids: tuple
    profiles: tuple
    #: The collections whose entries list the item.
    lists: tuple

    @property
    def identity(self):
        return (self.model, self.pk, frozenset(self.profile_ids))

    def recorded(self):
        """This item as the record holds it: enough to find the row
        again and to tell whether its restriction has moved."""
        return {
            "model": self.model,
            "pk": self.pk,
            "profile_ids": list(self.profile_ids),
        }


@dataclass(frozen=True)
class Restrictions:
    """Everything the run would strip, item by item."""

    items: tuple = ()
    problems: tuple = ()
    nothing_here: bool = False

    @property
    def ok(self):
        return not self.problems

    def preview(self):
        if self.nothing_here:
            return [
                "nothing to clear: no listed item carries a restriction to fighter entries"
            ]
        lines = [_line(item) for item in self.items]
        count = len(self.items)
        lines.append(
            f"clear the restriction to fighter entries from {count} listed "
            f"item{'' if count == 1 else 's'}; every restriction to a type or a "
            "subtype, every unlisted item and every entry's own lists stay as "
            "they are"
        )
        return lines

    def recorded(self):
        """What the record keeps beyond the preview's lines: the plan
        itself, so the run can hold its own reading against what was
        approved rather than against a second live scan."""
        return {"plan": [item.recorded() for item in self.items]}


def _line(item):
    where = f" [{item.pack}]" if item.pack else ""
    return (
        f"clear {item.label}{where}: usable by {', '.join(item.profiles)} only — "
        f"listed in {', '.join(item.lists)}"
    )


def listable_kinds():
    """The kinds a collection entry can name that carry the use lists,
    as ``(entry column, model)`` pairs. Read off the entry's own columns
    rather than listed, so a kind that gains the mixin is covered."""
    from n26.library.models import CollectionEntry
    from n26.library.models.assignable import UsableBy
    from n26.library.models.collection import ENTRY_ASSIGNABLE_FIELDS

    found = []
    for column in ENTRY_ASSIGNABLE_FIELDS:
        model = CollectionEntry._meta.get_field(column).related_model
        if issubclass(model, UsableBy):
            found.append((column, model))
    return found


def _restricted_and_listed(column, model):
    """The rows of one kind that some entry lists and that name at least
    one fighter entry, with their packs and profiles read alongside."""
    from n26.library.models import CollectionEntry

    listed = CollectionEntry.objects.filter(**{f"{column}__isnull": False}).values(
        column
    )
    return (
        model.objects.filter(pk__in=listed, usable_by_profiles__isnull=False)
        .distinct()
        .select_related("pack")
        .prefetch_related("usable_by_profiles")
        .order_by("name", "pk")
    )


def _pack_words(slug, name):
    """The pack's name where it is not the default pack, else empty."""
    return "" if slug is None or slug == settings.DEFAULT_CONTENT_PACK_SLUG else name


def _collection_words(name, qualifier, pack_slug, pack_name):
    """How a collection reads in the plan. A collection is unique by
    pack, name and qualifier together, so two lists printing one name
    are told apart the way the authoring pages tell them apart: by the
    qualifier, and by the pack where it is not the default."""
    said = f"{name} — {qualifier}" if qualifier else name
    pack = _pack_words(pack_slug, pack_name)
    return f"{said} [{pack}]" if pack else said


def _lists_naming(column, rows):
    """The collections listing each of these rows, one query for the
    kind: ``{pk: (collection words, ...)}``."""
    from n26.library.models import CollectionEntry

    naming = {}
    for pk, *collection in (
        CollectionEntry.objects.filter(**{f"{column}__in": rows})
        .values_list(
            column,
            "collection__name",
            "collection__qualifier",
            "collection__pack__slug",
            "collection__pack__name",
        )
        .distinct()
    ):
        naming.setdefault(str(pk), set()).add(_collection_words(*collection))
    return {pk: tuple(sorted(names)) for pk, names in naming.items()}


def _label(row):
    label = getattr(row, "authoring_label", None) or str(row)
    return f"{label} ({row._meta.verbose_name})"


def find():
    """Read every listed item that names a fighter entry. Never writes."""
    items = []
    for column, model in listable_kinds():
        rows = list(_restricted_and_listed(column, model))
        lists = _lists_naming(column, rows)
        for row in rows:
            profiles = sorted(row.usable_by_profiles.all(), key=str)
            pack = row.pack
            items.append(
                Restricted(
                    model=model._meta.label_lower,
                    pk=str(row.pk),
                    label=_label(row),
                    pack="" if pack is None else _pack_words(pack.slug, pack.name),
                    profile_ids=tuple(str(profile.pk) for profile in profiles),
                    profiles=tuple(str(profile) for profile in profiles),
                    lists=lists.get(str(row.pk), ()),
                )
            )
    return Restrictions(items=tuple(items), nothing_here=not items)


def _approved_identities(approved):
    """The plan as the record holds it, as identities."""
    return {
        (item["model"], item["pk"], frozenset(item["profile_ids"])) for item in approved
    }


def _by_model(approved):
    """The approved plan's item ids, grouped by model label."""
    by_model = {}
    for item in approved:
        by_model.setdefault(item["model"], []).append(item["pk"])
    return by_model


def _lock(approved):
    """Every item the approved plan names, locked for the rest of the
    transaction.

    An insert into an item's use list checks its key against the item,
    which the row lock blocks, so nothing can be added to a locked
    item's lists between the reading and the clearing.
    """
    from django.apps import apps

    by_model = _by_model(approved)
    locked = {}
    for label in sorted(by_model):
        model = apps.get_model(label)
        rows = list(
            model.objects.select_for_update()
            .filter(pk__in=by_model[label])
            .order_by("pk")
        )
        for row in rows:
            locked[(label, str(row.pk))] = row
    return locked


def _lock_entries(approved):
    """The listings that make each approved item eligible, locked for
    the rest of the transaction — one query per kind.

    A listing taken off between the reading and the clearing would
    have the run strip an item no list carries any more. Held, the
    removal waits for the run to end, and the reading holds.
    """
    from n26.library.models import CollectionEntry

    columns = {model._meta.label_lower: column for column, model in listable_kinds()}
    for label, pks in _by_model(approved).items():
        list(
            CollectionEntry.objects.select_for_update()
            .filter(**{f"{columns[label]}__in": pks})
            .values_list("pk", flat=True)
        )


def _any_still_restricted(approved):
    """Whether any item the plan names still carries a restriction to
    fighter entries — one query per kind, asked after the rows are
    locked so the answer holds for the rest of the transaction."""
    from django.apps import apps

    return any(
        apps.get_model(label)
        .objects.filter(pk__in=pks, usable_by_profiles__isnull=False)
        .exists()
        for label, pks in _by_model(approved).items()
    )


UPLOAD_AGAIN = (
    "Upload the equipment lists again to write each list's own "
    "restrictions onto its entries."
)


def _nothing_left(approved):
    count = len(approved)
    return [
        f"Nothing left to clear: none of the {count} listed "
        f"item{'' if count == 1 else 's'} the preview named carries a "
        "restriction to fighter entries now, so they were cleared already. "
        "Nothing was written.",
        UPLOAD_AGAIN,
    ]


def apply(approved):
    """Strip exactly what was approved, or refuse and strip nothing.

    ``approved`` is the plan the record holds — what the preview showed
    when the run was asked for. The reading the run makes for itself is
    held against that, not against another live scan: a restriction
    added, or an item newly listed, after the preview was read was never
    approved, and a run that met one would sweep it up without anybody
    having seen it.
    """
    if approved is None:
        raise Refused(
            "This record holds no plan, so there is nothing to check the "
            "run's own reading against. Ask for the removal again from its "
            "page."
        )
    if not approved:
        return list(Restrictions(nothing_here=True).preview())

    planned = _approved_identities(approved)
    with transaction.atomic():
        locked = _lock(approved)
        _lock_entries(approved)
        # The clearing commits, then the record is written. A worker cut
        # off between the two leaves the record running, and the queue
        # delivers the task again to a world where the approved items
        # carry nothing — the plan carried out, not the plan changed.
        if len(locked) == len(planned) and not _any_still_restricted(approved):
            return _nothing_left(approved)
        standing = find()
        if planned != {item.identity for item in standing.items} or len(locked) != len(
            planned
        ):
            raise Refused(
                "The restrictions have changed since the preview was read: "
                f"the preview named {len(planned)} item"
                f"{'' if len(planned) == 1 else 's'} and there are now "
                f"{len(standing.items)}, or one of them names different "
                "fighter entries. Nothing was cleared. Open the page again "
                "to read the current plan."
            )
        for item in standing.items:
            locked[(item.model, item.pk)].usable_by_profiles.clear()

    count = len(standing.items)
    report = [
        f"Cleared the restriction to fighter entries from {count} listed "
        f"item{'' if count == 1 else 's'}."
    ]
    for item in standing.items:
        where = f" [{item.pack}]" if item.pack else ""
        report.append(
            f"cleared {item.label}{where}: was usable by "
            f"{', '.join(item.profiles)} only"
        )
    report.append(UPLOAD_AGAIN)
    return report
