"""What attaching a thing asks for, and what a create page offers — as data.

Two declarations live on the models, and everything a form shows is
computed from them here; no form ever knows a kind by name.

**Attachment asks.** When a row is named by a through row — built into
a profile (``DefaultAssignment``), listed in a collection
(``CollectionEntry``) — the through row sometimes carries values that
only make sense for some kinds: a counter's opening value, an entry's
price override. Which of those apply is the *kind's* knowledge, declared
in ``ATTACHMENT_ASKS`` on the assignable class, keyed by the through
row's ``attachment_context``. :func:`attachment_asks` resolves one
kind + one through row to the extra inputs attaching it wants.

**Suggested built-ins.** A kind can declare what a new one of it
usually comes with (``SUGGESTED_BUILT_INS`` — a profile wants Starting
XP and an equipment list), and :func:`built_in_offer` resolves that
against the library: the named row found, candidates pre-queried, and
each suggestion's attachment asks attached. The create page renders the
offer; blank means skipped.

Both functions return frozen structures, and the structures are the
interface tests assert against — forms are derivations (the
miniature-card rule).
"""

from dataclasses import dataclass

from django.db import models


@dataclass(frozen=True)
class Ask:
    """One extra value attaching a kind asks for, beyond the pick
    itself. ``input`` says what control a renderer draws — "number" or
    "text" — and ``help`` is the through row field's own words."""

    name: str
    input: str
    help: str


def attachment_contexts():
    """Every through row that attaches assignables, by its context key —
    what the declarations on the kinds are checked against."""
    from n26.library.models import CollectionEntry, DefaultAssignment

    return {
        through.attachment_context: through
        for through in (DefaultAssignment, CollectionEntry)
    }


def attachment_asks(kind_model, through):
    """What attaching a ``kind_model`` row via ``through`` asks for.

    Read off the kind's own declaration — the form shows what the kind
    says it needs, never what some form decided a kind is like.
    """
    declared = getattr(kind_model, "ATTACHMENT_ASKS", {})
    return tuple(
        Ask(
            name=name,
            input=_input_for(through._meta.get_field(name)),
            help=str(through._meta.get_field(name).help_text),
        )
        for name in declared.get(through.attachment_context, ())
    )


def _input_for(model_field):
    return "number" if isinstance(model_field, models.IntegerField) else "text"


@dataclass(frozen=True)
class Suggest:
    """One line of a kind's ``SUGGESTED_BUILT_INS`` declaration.

    ``kind`` is the suggested class itself — a kind that does not exist
    is unwritable, and one built-ins cannot name fails the guard.
    ``named`` fixes the suggestion to a specific row ("Starting XP" is
    *the* XP counter); ``many`` offers several picks of the kind (a
    profile's subtypes). Named and many contradict — a specific row is
    one row — and many with asks is unsupported until something needs
    per-pick values.
    """

    label: str
    kind: type
    named: str = None
    many: bool = False


@dataclass(frozen=True)
class Suggestion:
    """One built-in a kind's create page offers up front.

    ``fixed`` is the specific row when the declaration named one and it
    exists ("Starting XP" is *the* XP counter); otherwise ``candidates``
    are the pre-queried rows to pick from — including when a named row
    is missing, so the page keeps working before foundations are
    seeded. ``asks`` are the extra values attaching this kind wants,
    and ``many`` says the pick is a multi-select.
    """

    label: str
    kind: str
    model: type
    fixed: object = None
    candidates: tuple = ()
    asks: tuple = ()
    many: bool = False

    @property
    def slug(self):
        """The label as a form-field stem — "Starting XP" → "starting_xp"."""
        import re

        return re.sub(r"[^a-z0-9]+", "_", self.label.lower()).strip("_")


def built_in_offer(kind_model):
    """The quick build-out for creating one of ``kind_model``: its
    declared suggestions, resolved against the library right now."""
    from n26.library.models import DefaultAssignment

    offer = []
    for suggest in getattr(kind_model, "SUGGESTED_BUILT_INS", ()):
        fixed = (
            suggest.kind.objects.filter(name=suggest.named).first()
            if suggest.named
            else None
        )
        asks = attachment_asks(suggest.kind, DefaultAssignment)
        if suggest.many and (suggest.named or asks):
            raise ValueError(
                f"{kind_model.__name__} suggests many {suggest.label!r}: a "
                f"many suggestion cannot fix a named row, and per-pick "
                f"values are unsupported."
            )
        offer.append(
            Suggestion(
                label=suggest.label,
                kind=_built_in_key(suggest.kind),
                model=suggest.kind,
                fixed=fixed,
                candidates=() if fixed else tuple(suggest.kind.objects.all()),
                asks=asks,
                many=suggest.many,
            )
        )
    return tuple(offer)


def _built_in_key(kind_model):
    """The DefaultAssignment column this kind rides — and the loud
    refusal when a declaration suggests something built-ins cannot name."""
    from n26.library.models import DefaultAssignment

    for name in DefaultAssignment.ASSIGNABLE_FIELDS:
        if DefaultAssignment._meta.get_field(name).related_model is kind_model:
            return name
    raise ValueError(f"A {kind_model.__name__} cannot be a built-in")
