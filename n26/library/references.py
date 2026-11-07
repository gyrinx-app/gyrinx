"""Read references to library content for deletion checks and reach descriptions.

Inspect reverse model relations, including hidden ``related_name="+"``
relations. Batch records of one content kind by relation so the query
count depends on the model graph rather than the number of references.
"""

from dataclasses import dataclass

from django.db import models

#: Relations needed to describe each referenced record without extra queries.
#: Kinds whose labels use only local fields need no entry.
READ_WITH = {
    # The description of a default pick also names its slot.
    "library.defaultassignment": ("default_set", "slot"),
    "library.picklistmember": ("picklist", "pickable"),
    "library.interstitialslot": ("interstitial", "slot"),
    "library.assettableentry": ("table", "asset"),
    "library.option": ("default_set", "profile", "wargear"),
    # The description of a granted starting pick also names its slot.
    "library.addsassignable": ("modifier", "slot", "with_pick"),
    "library.removesassignable": ("modifier",),
    "library.offerschoice": ("modifier", "from_section__collection"),
    "library.randomisesskilladvancements": ("modifier", "from_section__collection"),
    "library.placescategory": ("modifier", "section__collection", "category"),
    "library.changesstat": ("modifier", "stat"),
    "library.changescategory": ("modifier", "category"),
    "library.allowsatmost": ("modifier",),
    "library.requirescompanions": ("modifier", "for_each", "of"),
    "library.opaddsminiature": ("modifier", "profile"),
    "library.opchangescounter": ("modifier", "counter"),
    "library.collectionentry": ("collection",),
    "library.collectionselector": ("collection", "category"),
}


#: Describe a reference through the object an author must edit.
#: For example, a built-in member should identify its set rather than repeat the
#: content being deleted. READ_WITH loads these relations.
NAMED_BY = {
    "library.defaultassignment": "default_set",
    "library.assettableentry": "table",
    "library.interstitialslot": "interstitial",
}


def named(row):
    """One stored row, as a page naming it should say it."""
    through = NAMED_BY.get(type(row)._meta.label_lower)
    return str(getattr(row, through)) if through else str(row)


@dataclass(frozen=True)
class Reference:
    """A referencing record and its field, including deletion semantics.

    The field distinguishes references with different roles even when they point
    to the same content kind.
    """

    row: object
    field: str
    #: Whether the database would refuse to delete the thing while this
    #: row stands. False for a part of the thing (a weapon's own firing
    #: lines) and for a list membership, which is simply forgotten.
    protects: bool
    #: Whether this row goes with the thing — a part of it, deleted by
    #: the database along with it. False for a list membership, which is
    #: forgotten rather than deleted, and for a column that is emptied.
    cascades: bool = False
    #: Whether this row keeps standing with the column emptied: a
    #: ledger line that bought from an entry no longer there.
    empties: bool = False

    @property
    def label(self):
        """The model label of the row's kind — ``"library.addsassignable"``."""
        return type(self.row)._meta.label_lower


def carrying_models():
    """Discover every concrete content model with a modifiers relation."""
    from django.apps import apps

    return [
        model
        for model in apps.get_app_config("library").get_models()
        if hasattr(model, "modifiers")
    ]


def forward_relations(model):
    """The foreign keys a row reads through — what a page loads with the
    row so that saying it costs no further queries."""
    return [
        field.name
        for field in model._meta.get_fields()
        if field.concrete and (field.many_to_one or field.one_to_one)
    ]


def _edges(model):
    """Enumerate reverse relations, including hidden relations.

    Exclude automatic many-to-many through models because their relation is
    already represented by the many-to-many field.
    """
    seen = []
    for rel in model._meta.get_fields(include_hidden=True):
        if not rel.is_relation or not rel.auto_created or rel.concrete:
            continue
        if rel.related_model._meta.auto_created:
            continue
        seen.append(rel)
    return seen


def references_to(thing, *more):
    """Read references to records of one kind with one query per relation."""
    things = [thing, *more]
    model = type(thing)
    found = []
    for rel in _edges(model):
        rows = rel.related_model.objects.filter(**{f"{rel.field.name}__in": things})
        with_them = READ_WITH.get(rel.related_model._meta.label_lower)
        if with_them:
            rows = rows.select_related(*with_them)
        on_delete = getattr(rel, "on_delete", None)
        found.extend(
            Reference(
                row=row,
                field=rel.field.name,
                protects=on_delete is models.PROTECT,
                cascades=on_delete is models.CASCADE,
                empties=on_delete is models.SET_NULL,
            )
            for row in rows
        )
    return tuple(found)


def of_kind(references, label, field=None):
    """The references from one kind, optionally through one of its columns."""
    return tuple(
        reference
        for reference in references
        if reference.label == label and (field is None or reference.field == field)
    )


def reading_sentences(modifiers):
    """Prefetch relations used by modifier descriptions.

    Derive paths from scope, effect and condition fields. Separate prefetches
    avoid a wide joined query with expensive PostgreSQL planning; unused paths
    issue no query.
    """
    from n26.library.models import Modifier
    from n26.library.models.modifier import EFFECT_FIELDS, SCOPE_FIELDS

    # Section labels include their collection, so these descriptions need two joins.
    # The automatic relation loader below follows only one hop.
    paths = [
        "hides_categories__categories",
        "places_category__section__collection",
        "offers_choice__from_section__collection",
        "randomises_skill_advancements__from_section__collection",
    ]
    for half in (*SCOPE_FIELDS, *EFFECT_FIELDS):
        paths.append(half)
        related = Modifier._meta.get_field(half).related_model
        paths.extend(f"{half}__{name}" for name in forward_relations(related))
        for condition in getattr(related, "CONDITIONS", ()):
            model = related._meta.get_field(condition).related_model
            paths.append(f"{half}__{condition}")
            # Prefetch many-to-many condition values; they are absent from concrete fields
            # and would otherwise add a query for each description.
            paths.extend(
                f"{half}__{condition}__{field.name}"
                for field in model._meta.get_fields()
                if field.many_to_many or (field.concrete and field.many_to_one)
            )

    return modifiers.prefetch_related(*paths)
