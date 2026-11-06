"""Plan and clear item-level fighter-profile restrictions on listed equipment.

Item ``usable_by_*`` restrictions apply everywhere; collection-entry
restrictions apply only to that catalogue listing. This repair removes
fighter-profile links from items listed by at least one collection, allowing
re-import to restore the listing-specific restrictions.

Preserve type and subtype restrictions, unlisted items and every entry's own
restrictions. Lock approved items and their qualifying listings, rebuild the
plan and reject unapproved changes before clearing in one transaction.
If all approved restrictions are already absent, record completion without
writing them again.
"""

from dataclasses import dataclass

from django.conf import settings
from django.db import transaction


class Refused(Exception):
    """The confirmed restriction-clearing plan differs from the current database."""


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
        """Serialise the approved plan so execution can reject changes since preview."""
        return {"plan": [item.recorded() for item in self.items]}


def _line(item):
    where = f" [{item.pack}]" if item.pack else ""
    return (
        f"clear {item.label}{where}: usable by {', '.join(item.profiles)} only — "
        f"listed in {', '.join(item.lists)}"
    )


def listable_kinds():
    """Discover collection-entry kinds with use restrictions as ``(field, model)`` pairs."""
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
    """Format a collection with its qualifier and non-default pack to distinguish names."""
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
    """Lock approved items against changes to use restrictions for this transaction.

    New many-to-many links require conflicting foreign-key key-share locks.
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
    """Lock qualifying collection entries, one query per item kind.

    Prevent their removal from making an item ineligible between validation and
    restriction clearing.
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
    """Check locked approved items for remaining fighter-profile restrictions."""
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
    """Clear exactly the approved restriction plan or refuse without changes.

    Compare the locked current state with the recorded preview. A fresh live
    scan alone could include restrictions or listings the author never approved.
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
        # If a worker stops after clearing but before recording completion, retrying
        # finds the approved items already empty and can finish the record.
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
