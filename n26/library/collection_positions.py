"""Plan equipment-list ordering from the routes that grant each collection.

Trace built-ins and modifier grants through hidden carriers. Preserve
unresolved or cyclic routes in the preview so they remain visible.

A collection reached only through non-archetype pickables is a variant list
and receives ``VARIANT_POSITION``. Preserve existing authored positions and
leave other collections unchanged. Equip sorts using these positions.

The write is library-only and transactional. Lock collections and rebuild the
plan before applying to reject changes since confirmation.
"""

from dataclasses import dataclass, replace

from django.db import transaction

from n26.library.archetype_display import GANG_ARCHETYPE_IDS

#: Place variant lists after the gang list at position zero, leaving room for
#: manual ordering between them.
VARIANT_POSITION = 100

#: Follow grants through this hidden carrier kind when tracing collection access.
HIDDEN_KIND = "hidden assignable"


class Refused(Exception):
    """The confirmed collection-position plan no longer matches current content."""


@dataclass(frozen=True)
class Route:
    """One way a collection reaches a card."""

    #: "built-in" or "modifier".
    how: str
    #: The kind of thing carrying it, as its model calls itself.
    kind: str
    #: The carrier's name.
    name: str
    #: The carrier's pk, so a hidden carrier's own routes can be found.
    pk: str = ""
    #: The pickable's slot type — "Variant", "Gang Archetype" — where
    #: the carrier is one; empty otherwise.
    slot_type: str = ""
    #: Whether the carrier is one of the Outcast gang archetypes.
    gang_archetype: bool = False
    #: The hidden assignables the route passed through on its way from
    #: the carrier to the collection, nearest the carrier first.
    via: tuple = ()
    #: A hidden carrier nothing grants or builds in: the route stops at
    #: it, and the collection is reached by nobody this way.
    unresolved: bool = False

    @property
    def variant_pick(self):
        """A pickable's grant, and not a gang archetype's."""
        return (
            self.how == "modifier"
            and self.kind == "pickable"
            and not self.gang_archetype
        )

    def __str__(self):
        verb = "built into" if self.how == "built-in" else "granted by"
        detail = ""
        if self.slot_type:
            detail = f" ({self.slot_type}"
            detail += ", an Outcast gang archetype)" if self.gang_archetype else ")"
        said = f"{verb} {self.kind} {self.name}{detail}"
        if self.unresolved:
            return f"{said}, which nothing grants or builds in"
        if self.via:
            return f"{said} through {HIDDEN_KIND} {' and '.join(self.via)}"
        return said


@dataclass(frozen=True)
class Reading:
    """One collection: how it is reached, and where it will sit."""

    pk: str
    name: str
    pack: str
    position: int
    routes: tuple = ()

    @property
    def variant_list(self):
        """Reached only through picks that are not gang archetypes."""
        return bool(self.routes) and all(route.variant_pick for route in self.routes)

    @property
    def proposed(self):
        if self.variant_list and self.position == 0:
            return VARIANT_POSITION
        return self.position

    @property
    def changes(self):
        return self.proposed != self.position

    @property
    def granted(self):
        """The routes in words, or why there are none."""
        if not self.routes:
            return "not built into anything and granted by nothing"
        return "; ".join(str(route) for route in self.routes)

    @property
    def outcome(self):
        if self.changes:
            return f"set to {self.proposed}"
        if self.variant_list:
            return f"left at {self.position}, already set"
        return f"left at {self.position}"

    def line(self):
        return f"{self.name} ({self.pack}): {self.granted} — {self.outcome}"


@dataclass(frozen=True)
class Plan:
    """Every collection, read once, and what applying does to each."""

    readings: tuple = ()
    problems: tuple = ()

    @property
    def ok(self):
        return not self.problems

    @property
    def nothing_here(self):
        return not any(reading.changes for reading in self.readings)

    @property
    def to_set(self):
        return [reading for reading in self.readings if reading.changes]

    def preview(self):
        if self.nothing_here:
            return ["nothing to set: no list is at 0 and reached only by variant picks"]
        return [reading.line() for reading in self.to_set]


def _carriers():
    """Every library kind that can carry a modifier or a set of
    built-ins — the Assignable mixin gives a kind both at once."""
    from django.apps import apps as django_apps

    return [
        model
        for model in django_apps.get_app_config("library").get_models()
        if any(f.name == "modifiers" for f in model._meta.many_to_many)
    ]


def _pickable_details(rows):
    """Slot type and archetype flag per pickable pk, one query."""
    from n26.library.models import Pickable

    return {
        str(pk): (slot_type, str(pk) in GANG_ARCHETYPE_IDS)
        for pk, slot_type in Pickable.objects.filter(pk__in=rows).values_list(
            "pk", "slot_type__name"
        )
    }


def _routes_to(field):
    """Batch direct grant and built-in routes by target primary key.

    ``field`` names the content field on effects and default memberships.
    Query each carrier kind together rather than per target.
    """
    from n26.library.models import AddsAssignable, DefaultAssignment

    routes = {}

    def add(target_pk, route):
        routes.setdefault(str(target_pk), []).append(route)

    # Modifier grants: the effect names the row, the modifier holds the
    # effect, and a carrier holds the modifier.
    granting = dict(
        AddsAssignable.objects.filter(
            **{f"{field}__isnull": False}, modifier__isnull=False
        ).values_list("modifier__pk", f"{field}__pk")
    )
    # Built-ins: the member names the row, and a carrier names the set.
    built_in = {}
    for set_pk, target_pk in DefaultAssignment.objects.filter(
        **{f"{field}__isnull": False}
    ).values_list("default_set__pk", f"{field}__pk"):
        built_in.setdefault(str(set_pk), []).append(target_pk)

    for model in sorted(_carriers(), key=lambda m: m._meta.label_lower):
        kind = str(model._meta.verbose_name)
        pairs = list(
            model.modifiers.through.objects.filter(
                modifier__pk__in=granting
            ).values_list(f"{model._meta.model_name}_id", "modifier_id")
        )
        holders = list(
            model.objects.filter(built_ins__pk__in=built_in).values_list(
                "pk", "built_ins__pk"
            )
        )
        named = {
            str(pk): name
            for pk, name in model.objects.filter(
                pk__in=[*(pk for pk, _ in pairs), *(pk for pk, _ in holders)]
            ).values_list("pk", "name")
        }
        details = (
            _pickable_details([pk for pk, _ in pairs])
            if model._meta.model_name == "pickable"
            else {}
        )
        for carrier_pk, modifier_pk in sorted(pairs, key=lambda p: named[str(p[0])]):
            slot_type, archetype = details.get(str(carrier_pk), ("", False))
            add(
                granting[modifier_pk],
                Route(
                    "modifier",
                    kind,
                    named[str(carrier_pk)],
                    pk=str(carrier_pk),
                    slot_type=slot_type,
                    gang_archetype=archetype,
                ),
            )
        for carrier_pk, set_pk in sorted(holders, key=lambda p: named[str(p[0])]):
            for target_pk in built_in[str(set_pk)]:
                add(
                    target_pk,
                    Route("built-in", kind, named[str(carrier_pk)], pk=str(carrier_pk)),
                )
    return routes


def _resolved(route, hidden_routes, seen=frozenset()):
    """Follow hidden-carrier routes back to their sources.

    Retain unreferenced and cyclic routes as unresolved rather than dropping them.
    """
    if route.kind != HIDDEN_KIND:
        return [route]
    upstream = [] if route.pk in seen else hidden_routes.get(route.pk, [])
    if not upstream:
        return [replace(route, unresolved=True)]
    return [
        replace(beyond, via=(*beyond.via, route.name))
        for up in upstream
        for beyond in _resolved(up, hidden_routes, seen | {route.pk})
    ]


def _routes_by_collection():
    """Every route to every collection, keyed by collection pk, with
    the routes through hidden carriers followed back to their source."""
    hidden_routes = _routes_to("hidden")
    return {
        collection_pk: [
            resolved for route in routes for resolved in _resolved(route, hidden_routes)
        ]
        for collection_pk, routes in _routes_to("collection").items()
    }


def find():
    """Read every collection and how it is reached. Never writes."""
    from n26.library.models import Collection

    routes = _routes_by_collection()
    readings = []
    for collection in Collection.objects.with_pack().order_by("pack__name", "name"):
        found = routes.get(str(collection.pk), [])
        readings.append(
            Reading(
                pk=str(collection.pk),
                name=collection.authoring_label,
                pack=str(collection.pack),
                position=collection.position,
                # Deduplicate a carrier that grants the same list to both the gang and its members.
                routes=tuple(
                    sorted(set(found), key=lambda r: (r.how, r.kind, r.name, r.via))
                ),
            )
        )
    return Plan(readings=tuple(readings))


def apply(plan):
    """Lock collections and apply exactly the confirmed positions in one transaction.

    Reject a changed plan, including positions edited after preview.
    """
    from n26.library.models import Collection

    if plan.problems:
        raise Refused(
            "The positions cannot be set because " + "; ".join(plan.problems) + "."
        )
    if plan.nothing_here:
        return list(plan.preview())

    wanted = {reading.pk: reading for reading in plan.to_set}
    report = []
    with transaction.atomic():
        rows = list(
            Collection.objects.select_for_update().filter(pk__in=wanted).order_by("pk")
        )
        moved = [
            f"{wanted[str(row.pk)].name} is at {row.position}, "
            f"not {wanted[str(row.pk)].position} as read"
            for row in rows
            if row.position != wanted[str(row.pk)].position
        ]
        if len(rows) != len(wanted):
            moved.append(f"{len(wanted) - len(rows)} of the lists read are gone")
        if moved:
            raise Refused(
                "The positions cannot be set because the lists changed since "
                "they were read: " + "; ".join(moved) + ". Open the page again."
            )
        for row in rows:
            reading = wanted[str(row.pk)]
            row.position = reading.proposed
            row.save(update_fields=["position", "modified"])
            report.append(f"{reading.name} ({reading.pack}): set to {reading.proposed}")
    report.append(f"Set {len(rows)} list{'' if len(rows) == 1 else 's'}.")
    return report
