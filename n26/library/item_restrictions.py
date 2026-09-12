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

It is one transaction, and it strips exactly what the preview showed:
the items are locked, read a second time, and the run refuses if the
second reading differs from the plan somebody approved.
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
    said: str
    #: The pack's name where it is not the default pack, else empty.
    pack: str
    profile_ids: tuple
    profiles: tuple
    #: The collections whose entries list the item.
    lists: tuple

    @property
    def identity(self):
        return (self.model, self.pk, frozenset(self.profile_ids))


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


def _line(item):
    where = f" [{item.pack}]" if item.pack else ""
    return (
        f"clear {item.said}{where}: usable by {', '.join(item.profiles)} only — "
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
    one fighter entry, with their lists and profiles read alongside."""
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


def _lists_naming(column, row):
    from n26.library.models import CollectionEntry

    return tuple(
        sorted(
            {
                entry.collection.name
                for entry in CollectionEntry.objects.filter(
                    **{column: row}
                ).select_related("collection")
            }
        )
    )


def _said(row):
    label = getattr(row, "authoring_label", None) or str(row)
    return f"{label} ({row._meta.verbose_name})"


def find():
    """Read every listed item that names a fighter entry. Never writes."""
    items = []
    for column, model in listable_kinds():
        for row in _restricted_and_listed(column, model):
            profiles = sorted(row.usable_by_profiles.all(), key=str)
            pack = row.pack
            items.append(
                Restricted(
                    model=model._meta.label_lower,
                    pk=str(row.pk),
                    said=_said(row),
                    pack=(
                        ""
                        if pack is None
                        or pack.slug == settings.DEFAULT_CONTENT_PACK_SLUG
                        else pack.name
                    ),
                    profile_ids=tuple(str(profile.pk) for profile in profiles),
                    profiles=tuple(str(profile) for profile in profiles),
                    lists=_lists_naming(column, row),
                )
            )
    return Restrictions(items=tuple(items), nothing_here=not items)


def _lock(found):
    """Every item the plan names, locked for the rest of the transaction.

    An insert into an item's use list checks its key against the item,
    which the row lock blocks, so nothing can be added to a locked
    item's lists between the second reading and the clearing.
    """
    from django.apps import apps

    by_model = {}
    for item in found.items:
        by_model.setdefault(item.model, []).append(item.pk)
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


def apply(found):
    """Strip exactly what was read, or refuse and strip nothing."""
    if found.problems:
        raise Refused(
            "The removal cannot run because " + "; ".join(found.problems) + "."
        )
    if found.nothing_here:
        return list(found.preview())

    with transaction.atomic():
        locked = _lock(found)
        again = find()
        planned = {item.identity for item in found.items}
        standing = {item.identity for item in again.items}
        if planned != standing or len(locked) != len(found.items):
            raise Refused(
                "The restrictions have changed since the preview was read: "
                f"the preview named {len(planned)} item"
                f"{'' if len(planned) == 1 else 's'} and there are now "
                f"{len(standing)}. Nothing was cleared. Open the page again "
                "to read the current plan."
            )
        for item in found.items:
            locked[(item.model, item.pk)].usable_by_profiles.clear()

    count = len(found.items)
    report = [
        f"Cleared the restriction to fighter entries from {count} listed "
        f"item{'' if count == 1 else 's'}."
    ]
    for item in found.items:
        where = f" [{item.pack}]" if item.pack else ""
        report.append(
            f"cleared {item.said}{where}: was usable by {', '.join(item.profiles)} only"
        )
    report.append(
        "Upload the equipment lists again to write each list's own "
        "restrictions onto its entries."
    )
    return report
