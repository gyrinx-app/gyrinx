"""The scratch card — what pending authoring would do, without doing it.

Step 3 of design/authoring-build-plan.md, and the test of whether the
fancy scratch-card UI is earnable: *an endpoint that takes the
form state and gives back card state*. ``preview(state)`` applies the
pending payloads through the authoring verbs, founds a throwaway gang,
hires exemplar fighters, computes their cards, serialises what they
say — and then **rolls the whole transaction back**. The caller's
database is untouched; the preview is pure reading in effect, bought
with writes that never commit.

The ``state`` dict is form state, one step from a POST body:

* ``create`` — name-only leaves the payloads need but the library
  doesn't have yet: subtypes, categories, a collection with its
  sections, the archetype being authored. Created first, each
  registered under its name.
* ``modifiers`` — composer submits (``ModifierComposerForm`` data,
  ``who-``/``what-``/``conditions-`` prefixes and all), plus an
  ``attach_to`` naming a created carrier. Anywhere a form field would
  hold a pk, ``"@Name"`` references a created thing instead — the pk
  does not exist until the preview runs.
* ``gang`` / ``fighters`` — the scratch roster: what the gang carries,
  and each exemplar model's name and subtypes.

``PreviewState`` is the answer, all plain strings and numbers
(JSON-able): the gang block, one dict per card, every plan step as its
sentence, and the gang's notes. Invalid payloads raise
:class:`PreviewError` carrying the form's words, which the endpoint
returns as a 400 — never a half-applied state either way.
"""

import dataclasses
from dataclasses import dataclass, field

from django.db import transaction


class PreviewError(Exception):
    """A payload the composer refuses — carries the errors, in words."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


@dataclass
class PreviewState:
    """What the scratch gang's cards say. Plain data, JSON-able."""

    gang: dict = field(default_factory=dict)
    #: One dict per exemplar fighter, each carrying its own ``plan`` —
    #: every step as its sentence, so the scratch card can say not just
    #: what it shows but why. The debugging surface, as text.
    cards: list = field(default_factory=list)
    #: The gang card's own plan steps.
    plan: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def as_dict(self):
        return dataclasses.asdict(self)


def preview(state):
    """Apply ``state``, read the cards, roll everything back."""
    with transaction.atomic():
        result = _apply_and_read(state)
        transaction.set_rollback(True)
    return result


#: What ``create`` entries may make: name-only leaves and the carriers
#: being authored. Each is a thin call into the authoring verbs.
def _creators():
    from n26.library import authoring

    return {
        "subtype": lambda entry: authoring.create_subtype(entry["name"]),
        "skill": lambda entry: authoring.create_skill(entry["name"]),
        "rule": lambda entry: authoring.create_rule(entry["name"]),
        "counter": lambda entry: authoring.create_counter(entry["name"]),
        "archetype": lambda entry: authoring.create_archetype(entry["name"]),
        "affiliation": lambda entry: authoring.create_affiliation(entry["name"]),
        "skilltree": lambda entry: authoring.create_skill_tree(
            entry["name"], entry["category"]
        ),
        "category": lambda entry: authoring.create_category(
            entry.get("section", "Skills"), entry["name"]
        ),
    }


def _apply_creates(state):
    """Build the named leaves, registering each under its name.

    A collection registers its sections too, by their own names — a
    payload says ``"@Primary"`` exactly as the admin would say
    "Primary".
    """
    from n26.library import authoring

    created = {}
    creators = _creators()
    for entry in state.get("create", ()):
        kind = entry["kind"]
        if kind == "collection":
            collection = authoring.create_collection(entry["name"])
            created[entry["name"]] = collection
            for position, section_name in enumerate(entry.get("sections", ())):
                created[section_name] = authoring.section_of(
                    collection, section_name, position
                )
            continue
        if kind == "category":
            created[entry["name"]] = creators[kind](entry)
            continue
        if kind == "skilltree":
            entry = {**entry, "category": _resolve(entry["category"], created)}
        created[entry["name"]] = creators[kind](entry)
    return created


def _resolve(value, created):
    """``"@Name"`` → the created row; anything else passes through."""
    if isinstance(value, str) and value.startswith("@"):
        name = value[1:]
        if name not in created:
            raise PreviewError({"create": [f"Nothing named {name!r} was created."]})
        return created[name]
    return value


def _resolve_form_value(value, created):
    """As :func:`_resolve`, but to the pk string a form field wants."""
    resolved = _resolve(value, created)
    return str(resolved.pk) if resolved is not value else value


def _apply_modifiers(state, created):
    from n26.library.forms import ModifierComposerForm

    for payload in state.get("modifiers", ()):
        payload = dict(payload)
        attach_to = _resolve(payload.pop("attach_to", None), created)
        data = {
            key: (
                [_resolve_form_value(item, created) for item in value]
                if isinstance(value, list)
                else _resolve_form_value(value, created)
            )
            for key, value in payload.items()
        }
        form = ModifierComposerForm(data, attach_to=attach_to)
        if not form.is_valid():
            raise PreviewError(dict(form.errors))
        form.save()


def _scratch_roster(state, created):
    """Found the throwaway gang and hire the exemplar fighters."""
    from django.contrib.auth.models import User

    from n26.library import authoring
    from n26.core.models import Gang
    from n26.core.operations import operation

    gang_type = authoring.create_gang_type("Scratch")
    profile = authoring.create_profile(
        "Scratch fighter",
        authoring.create_profile_type(
            "Fighter",
            authoring.create_statline_type(
                "Scratch statline", [authoring.create_stat("M", "Movement")]
            ),
        ),
        gang_type,
        price=0,
    )
    authoring.set_statline(profile, movement=5)

    owner = User.objects.create_user("scratch-preview")
    gang = Gang.objects.create(
        name="Scratch gang", gang_type=gang_type, owner=owner, credits=0
    )
    fighters = {}
    with operation(gang, actor=owner) as op:
        op.found(gang_type)
        for thing in state.get("gang", {}).get("carries", ()):
            op.assign(_resolve(thing, created), gang=gang)
        for spec in state.get("fighters", ()):
            miniature = op.hire(profile, spec["name"], paid=0)
            for subtype in spec.get("subtypes", ()):
                op.assign(_resolve(subtype, created), miniature=miniature)
            fighters[spec["name"]] = miniature
    return gang, fighters


def _read(gang, fighters):
    """Compute every card and say what it says, in plain data."""
    from n26.core.card import build_gang_card, build_modifier_index
    from n26.core.effects import compute, compute_gang

    gang_card = build_gang_card(gang)
    member_cards = {
        name: gang_card.members[miniature.pk] for name, miniature in fighters.items()
    }
    index = build_modifier_index(
        [
            node.assignable
            for card in (gang_card, *member_cards.values())
            for node in card.all_nodes()
        ]
    )
    computed_gang = compute_gang(gang_card, index)

    cards = []
    for name, card in member_cards.items():
        computed = compute(card, index)
        cards.append(
            {
                "name": name,
                "subtypes": sorted(str(row.thing) for row in computed.subtypes),
                "skills": sorted(str(row.thing) for row in computed.skills),
                "rules": sorted(str(row.thing) for row in computed.rules),
                "placements": [
                    f"{placement.category.name} under {placement.section.name}"
                    for placement in computed.placements
                ],
                "choices": [
                    {"label": slot.kind_label, "resolved": slot.is_resolved}
                    for slot in computed.choices
                ],
                "plan": [str(step) for step in computed.plan],
            }
        )

    return PreviewState(
        gang={
            "name": gang.name,
            "rating": gang.rating,
            "credits": gang.credits,
            "choices": [
                {"label": slot.kind_label, "resolved": slot.is_resolved}
                for slot in computed_gang.choices
            ],
        },
        cards=cards,
        plan=[str(step) for step in computed_gang.plan],
        notes=[note.text for note in computed_gang.notes],
    )


def _apply_and_read(state):
    created = _apply_creates(state)
    _apply_modifiers(state, created)
    gang, fighters = _scratch_roster(state, created)
    return _read(gang, fighters)
