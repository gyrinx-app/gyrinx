"""What points at a piece of content — read once, for everyone who asks.

Two surfaces ask the same question of a library row and must never get
two answers: the delete page, which says what is standing in the way,
and the reach column, which turns the same edges into sentences. So the
edges are read here and nowhere else.

They are found by **reflection over the model graph** rather than from a
list: every reverse relation of the row's own kind, including the ones
declared ``related_name="+"``, which is most of them. A new column
naming content is therefore seen the day it exists, with nothing to
remember and nothing to keep in step.

The reading is **batched by edge, never by row**: one query per relation
whatever the answer's size, so a thing nothing references and a thing a
hundred things reference are read at the same price. Several things of
one kind are read together for the same reason — a caller following a
chain (thing → the sets holding it → the profiles holding those) asks
once per level rather than once per link.
"""

from dataclasses import dataclass

from django.db import models

#: What a reference's row is read with, so that saying it costs no
#: further queries: the column a sentence about that row has to name.
#: A kind absent from here is read plain, which is right for a row whose
#: own columns say everything — and where it is not, the miss shows up
#: as a query per row, which the pinned counts catch.
READ_WITH = {
    "library.defaultassignment": ("default_set",),
    "library.option": ("default_set", "profile", "wargear"),
    "library.addsassignable": ("modifier",),
    "library.removesassignable": ("modifier",),
    "library.offerschoice": ("modifier", "from_section__collection"),
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


@dataclass(frozen=True)
class Reference:
    """One stored row naming the thing, and the column it names it in.

    The column matters: two of a model's columns can name the same kind
    and mean opposite things — a composition rule's ``for_each`` and
    ``of`` are both subtypes, one the rank being propped up and one the
    companions doing the propping.
    """

    row: object
    field: str
    #: Whether the database would refuse to delete the thing while this
    #: row stands. False for a part of the thing (a weapon's own firing
    #: lines) and for a list membership, which is simply forgotten.
    protects: bool

    @property
    def label(self):
        """The model label of the row's kind — ``"library.addsassignable"``."""
        return type(self.row)._meta.label_lower


def carrying_models():
    """Every concrete kind that can carry modifiers.

    Discovered rather than listed: a kind that gains the mixin is swept
    up the day it does, and a page counting carriers can never quietly
    stop counting one of them.
    """
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
    """Every relation pointing at this kind, as ``(related model, field)``.

    ``related_objects`` alone would miss most of them: a relation
    declared ``related_name="+"`` is hidden, and the grants, the
    built-ins and the list entries all declare theirs that way. Asking
    for the hidden ones brings in the through tables of every
    many-to-many as well, which are the same edge counted twice — so
    those are dropped and the many-to-many itself kept.
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
    """Every stored row naming these things, in a fixed number of queries.

    All of them must be of one kind — the edges are a property of the
    kind, and reading two kinds together would mean walking two graphs
    and calling the result one answer.
    """
    things = [thing, *more]
    model = type(thing)
    found = []
    for rel in _edges(model):
        rows = rel.related_model.objects.filter(**{f"{rel.field.name}__in": things})
        with_them = READ_WITH.get(rel.related_model._meta.label_lower)
        if with_them:
            rows = rows.select_related(*with_them)
        protects = getattr(rel, "on_delete", None) is models.PROTECT
        found.extend(
            Reference(row=row, field=rel.field.name, protects=protects) for row in rows
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
    """A modifier queryset with everything its sentences read loaded.

    A modifier says itself by walking its scope and its effect, and
    each of those walks further — the stat a change names, the subtypes
    a condition lists. Unhinted that is several queries per row. The
    paths are derived from the fields rather than listed, so a new
    scope, effect or condition kind is covered the day it is added.

    Everything loads as prefetch paths, not joins: joined together the
    paths make a select wide enough that Postgres spends longer
    planning it than running it, while each path alone is a small
    query — and a path no row uses never reaches the database.
    """
    from n26.library.models import Modifier
    from n26.library.models.modifier import EFFECT_FIELDS, SCOPE_FIELDS

    # Two hops where a sentence reads through an intermediate row: a
    # placement or a choice names a section, and a section says itself
    # as "name (collection)". Derivation below stops at one hop, so
    # these are listed the way card.py lists its deep paths — without
    # them a page of placements fetches one collection per row.
    paths = [
        "places_category__section__collection",
        "offers_choice__from_section__collection",
    ]
    for half in (*SCOPE_FIELDS, *EFFECT_FIELDS):
        paths.append(half)
        related = Modifier._meta.get_field(half).related_model
        paths.extend(f"{half}__{name}" for name in forward_relations(related))
        for condition in getattr(related, "CONDITIONS", ()):
            model = related._meta.get_field(condition).related_model
            paths.append(f"{half}__{condition}")
            paths.extend(
                f"{half}__{condition}__{field.name}"
                for field in model._meta.get_fields()
                if field.concrete and (field.many_to_one or field.many_to_many)
            )

    return modifiers.prefetch_related(*paths)
