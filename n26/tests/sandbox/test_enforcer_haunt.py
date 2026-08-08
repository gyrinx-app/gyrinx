"""The Enforcer Haunt: a chosen *type*, as a Subtype.

Tom's modelling (2026-08-06): Psyrender and Bonecrusher are Subtypes —
the book says the Haunt "selects one of the following **types**", and
Subtype is the system's word for exactly that. The pick is then a
matchable fact ("all Psyrender models…" is expressible), it reads in
the type line, and the payload rides the subtype as ordinary modifiers:

* "may gain additional Psyrender Wyrd Powers as if they were Primary
  skills" — ``places(psyrender family, Primary)``, the Psy-Gheist
  pattern verbatim;
* "knows one Psyrender Wyrd Power of the player's choice" — a chained
  ``OffersChoice(Power, from_section=Primary)`` **whose pick list falls
  out of the placement just made**: the fighter's Primary tier *is*
  that family.

The only code this took was ``OFFERABLE_KINDS += ("subtype",)`` and a
render decision: an answered subtype still joins the type line — the
slot shows the resolution, the type line stays honest.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.browse import offered_by, placements_for
from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.render import build_model_card
from n26.library.models import Power, Subtype
from n26.tests.sandbox.actions import (
    choose,
    create_category,
    create_collection,
    create_default_set,
    create_power,
    create_profile,
    create_rule,
    create_subtype,
    found_gang,
    hire_with_option,
    modifier,
    offers_choice,
    places,
    section_of,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def families(db):
    return {
        "psyrender": create_category("Powers", "Psyrender", 0),
        "bonecrusher": create_category("Powers", "Bonecrusher", 1),
    }


@pytest.fixture
def powers_collection(families):
    library = [
        create_power(name, category=families[key])
        for key, name in [
            ("psyrender", "Mind Flense"),
            ("psyrender", "Psychic Scream"),
            ("bonecrusher", "Shatter Limb"),
        ]
    ]
    collection = create_collection(
        "Skills & Powers", entries=[(power, {}) for power in library]
    )
    tiers = {
        "primary": section_of(collection, "Primary", 0),
        "other": section_of(collection, "Other", 1, is_default=True),
    }
    return collection, tiers


@pytest.fixture
def wyrd_types(families, powers_collection):
    """Psyrender and Bonecrusher: each a Subtype carrying its placement
    and its chained power pick — Tom's sketch, verbatim."""
    _, tiers = powers_collection
    made = {}
    for key, name in [("psyrender", "Psyrender"), ("bonecrusher", "Bonecrusher")]:
        subtype = create_subtype(name)
        modifier(
            f"{name}: powers are Primary",
            targets_model(),
            places(families[key], tiers["primary"]),
            carried_by=subtype,
        )
        modifier(
            f"{name}: knows one power",
            targets_model(),
            offers_choice(Power, from_section=tiers["primary"]),
            carried_by=subtype,
        )
        made[key] = subtype
    return made


@pytest.fixture
def haunt(wyrd_types, person_type, gang_type):
    types_list = create_collection(
        "Sanctioned Wyrd Types", entries=[(t, {}) for t in wyrd_types.values()]
    )
    pick = section_of(types_list, "Types", 0, is_default=True)

    profile = create_profile("Enforcer Haunt", person_type, gang_type, price=110)
    profile.built_ins = create_default_set(
        "Enforcer Haunt built-ins", members=[create_rule("Sanctioned Wyrd")]
    )
    profile.save()
    modifier(
        "Enforcer Haunt: selects a type",
        targets_model(),
        offers_choice(Subtype, from_section=pick, label="sanctioned wyrd type"),
        carried_by=profile,
    )
    return profile


@pytest.fixture
def gang(gang_type):
    return found_gang("The Watch", gang_type, owner=User.objects.create_user("tom"))


@pytest.fixture
def morrow(gang, haunt):
    return hire_with_option(gang, haunt, "Morrow")


def computed_for(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


def slot(computed, label):
    return next((s for s in computed.choices if s.kind_label == label), None)


class TestTheHaunt:
    def test_the_type_question_arrives_with_the_hire(self, morrow):
        computed = computed_for(morrow)
        asked = slot(computed, "sanctioned wyrd type")
        assert asked is not None and not asked.is_resolved
        # And no power question yet: it belongs to the unanswered type.
        assert slot(computed, "Primary power") is None

    def test_the_pick_list_is_the_two_types(self, morrow):
        computed = computed_for(morrow)
        offerable = offered_by(slot(computed, "sanctioned wyrd type"), computed)
        assert {line.name for line in offerable.all_lines()} == {
            "Psyrender",
            "Bonecrusher",
        }

    def test_choosing_a_type_places_its_family_and_chains_the_power_pick(
        self, morrow, wyrd_types, powers_collection, families
    ):
        anchor = morrow.assignments.get(profile__isnull=False)
        answer = choose(anchor, wyrd_types["psyrender"])
        assert answer.miniature == morrow  # the type is the fighter's own

        computed = computed_for(morrow)
        collection, _ = powers_collection
        placed = placements_for(computed, collection)
        assert placed[families["psyrender"]].section.name == "Primary"
        assert families["bonecrusher"] not in placed

        chained = slot(computed, "Primary power")
        assert chained is not None and not chained.is_resolved
        # The pick list fell out of the placement: Primary IS Psyrender.
        offerable = offered_by(chained, computed)
        assert {line.name for line in offerable.all_lines()} == {
            "Mind Flense",
            "Psychic Scream",
        }

    def test_knowing_the_power(self, morrow, wyrd_types):
        """The answer draws as its choice's line, never twice — the
        standing render rule for every chosen thing."""
        anchor = morrow.assignments.get(profile__isnull=False)
        choose(anchor, wyrd_types["psyrender"])
        type_row = morrow.assignments.get(subtype__name="Psyrender")
        choose(type_row, Power.objects.get(name="Mind Flense"))

        card = build_model_card(morrow, computed=computed_for(morrow))
        known = next(c for c in card.choices if c.kind_label == "Primary power")
        assert known.chosen == "Mind Flense"
        assert [p.name for p in card.powers] == []  # not drawn twice

    def test_the_type_line_stays_honest(self, morrow, wyrd_types):
        """The answered subtype is drawn as its choice's line AND joins
        the type line — it is still a subtype, and rules match on it."""
        anchor = morrow.assignments.get(profile__isnull=False)
        choose(anchor, wyrd_types["psyrender"])

        card = build_model_card(morrow, computed=computed_for(morrow))
        assert card.type_line == "Fighter (Psyrender)"
        answered = next(
            c for c in card.choices if c.kind_label == "sanctioned wyrd type"
        )
        assert answered.chosen == "Psyrender"
