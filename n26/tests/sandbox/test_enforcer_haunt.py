"""Verify a chosen Enforcer Haunt subtype that places its power family in the Primary
section and offers a further power choice. The selected subtype remains available to
selectors and the type line, while the chosen power appears once in the Powers row.
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
    """Subtypes that place their power category and offer a chained choice from the
    resulting Primary section.
    """
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
        asked = slot(computed, "Sanctioned wyrd type")
        assert asked is not None and not asked.is_resolved
        # The power choice is granted by the selected subtype.
        assert slot(computed, "Primary power") is None

    def test_the_pick_list_is_the_two_types(self, morrow):
        computed = computed_for(morrow)
        offerable = offered_by(slot(computed, "Sanctioned wyrd type"), computed)
        assert {line.name for line in offerable.all_lines()} == {
            "Psyrender",
            "Bonecrusher",
        }

    def test_choosing_a_type_places_its_family_and_chains_the_power_pick(
        self, morrow, wyrd_types, powers_collection, families
    ):
        anchor = morrow.assignments.get(profile__isnull=False)
        chosen = choose(anchor, wyrd_types["psyrender"])
        assert chosen.miniature == morrow

        computed = computed_for(morrow)
        collection, _ = powers_collection
        placed = placements_for(computed, collection)
        assert placed[families["psyrender"]].section.name == "Primary"
        assert families["bonecrusher"] not in placed

        chained = slot(computed, "Primary power")
        assert chained is not None and not chained.is_resolved
        # The selected subtype places only Psyrender powers in Primary.
        offerable = offered_by(chained, computed)
        assert {line.name for line in offerable.all_lines()} == {
            "Mind Flense",
            "Psychic Scream",
        }

    def test_knowing_the_power(self, morrow, wyrd_types):
        """A resolved power choice becomes a power row without duplicating the choice
        control.
        """
        anchor = morrow.assignments.get(profile__isnull=False)
        choose(anchor, wyrd_types["psyrender"])
        type_row = morrow.assignments.get(subtype__name="Psyrender")
        choose(type_row, Power.objects.get(name="Mind Flense"))

        card = build_model_card(morrow, computed=computed_for(morrow))
        assert card.power_choices == []
        assert not any(c.kind_label == "Primary power" for c in card.choices)
        assert [p.name for p in card.powers] == ["Mind Flense"]

    def test_the_type_line_stays_honest(self, morrow, wyrd_types):
        """Show the chosen subtype in both the settled choice and model type line."""
        anchor = morrow.assignments.get(profile__isnull=False)
        choose(anchor, wyrd_types["psyrender"])

        card = build_model_card(morrow, computed=computed_for(morrow))
        assert card.type_line == "Fighter (Psyrender)"
        settled = next(
            c for c in card.choices if c.kind_label == "Sanctioned wyrd type"
        )
        assert settled.chosen == "Psyrender"
