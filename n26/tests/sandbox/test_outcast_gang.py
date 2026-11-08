"""Outcast choices assign archetypes and affiliations with scoped modifiers.

A Leader chooses a gang-assigned archetype that broadcasts to models and is
removed with the Leader's membership. Champions can choose a bearer-only
archetype. Leader effects match the shared rank subtype; Champion and Hive
Scum effects match their specific profiles.

The content table supplies rank-specific placements, including Wyrd Powers.
Affiliations can grant collections and follow-up choices. Composition ratios
produce notes without removing models. See design/outcasts.md.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.browse import offered_by, placements_for
from n26.core.card import build_card, build_gang_card, build_modifier_index
from n26.core.effects import compute, compute_gang
from n26.core.reconcile import assert_reconciled
from n26.core.render_text import gang_to_text
from n26.library.authoring import (
    has_subtypes,
    is_profile,
    targets_every_model,
    targets_model,
)
from n26.library.models import Affiliation, Skill
from n26.tests.fixtures import library_setup
from n26.tests.sandbox.actions import (
    adds,
    choose,
    create_affiliation,
    create_category,
    create_collection,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_pickable,
    create_picklist,
    create_profile,
    create_rule,
    create_skill,
    create_slot,
    create_slot_type,
    create_subtype,
    ef_adds,
    found_gang,
    hire_with_option,
    modifier,
    offers_choice,
    places,
    requires_companions,
    section_of,
    targets_gang,
)

pytestmark = pytest.mark.django_db


# --- The skills taxonomy (as the Venator suite, plus Wyrd Powers) ----------


@pytest.fixture
@library_setup
def sets(db):
    made = {
        name.lower(): create_category("Skills", name, position)
        for position, name in enumerate(
            ["Agility", "Brawn", "Combat", "Cunning", "Savant", "Shooting"]
        )
    }
    made["wyrd powers"] = create_category("Powers", "Wyrd Powers", 6)
    return made


@pytest.fixture
@library_setup
def skills_collection(sets):
    library = [
        create_skill(name, category=sets[key])
        for key, name in [
            ("agility", "Dodge"),
            ("brawn", "Bull Charge"),
            ("combat", "Berserker"),
            ("cunning", "Backstab"),
            ("savant", "Medicate"),
            ("shooting", "Marksman"),
        ]
    ]
    collection = create_collection(
        "Skills & Powers", entries=[(skill, {}) for skill in library]
    )
    tiers = {
        "primary": section_of(collection, "Primary", 0),
        "secondary": section_of(collection, "Secondary", 1),
        "other": section_of(collection, "Other", 2, is_default=True),
    }
    return collection, tiers


@pytest.fixture
@library_setup
def subtypes(db):
    """Create shared rank subtypes; profile-specific effects must target profiles separately."""
    return {
        "leader": create_subtype("Leader"),
        "champion": create_subtype("Champion"),
        "scum": create_subtype("Hive Scum"),
        "wyrd": create_subtype("Wyrd"),
    }


# --- The archetype tables, read per rank ----------------------------------

ARCHETYPES = {
    "Brawler": {
        "leader": {
            "combat": "primary",
            "savant": "primary",
            "brawn": "secondary",
            "cunning": "secondary",
        },
        "champion": {"brawn": "primary", "combat": "primary", "savant": "secondary"},
        "scum": {"combat": "primary", "brawn": "secondary", "cunning": "secondary"},
    },
    "Gunslinger": {
        "leader": {
            "savant": "primary",
            "shooting": "primary",
            "agility": "secondary",
            "cunning": "secondary",
        },
        "champion": {
            "agility": "primary",
            "shooting": "primary",
            "savant": "secondary",
        },
        "scum": {"shooting": "primary", "agility": "secondary", "cunning": "secondary"},
    },
    "Mastermind": {
        "leader": {
            "agility": "primary",
            "savant": "primary",
            "combat": "secondary",
            "cunning": "secondary",
        },
        "champion": {"agility": "primary", "combat": "primary", "savant": "secondary"},
        "scum": {"agility": "primary", "brawn": "secondary", "combat": "secondary"},
    },
    "Survivor": {
        "leader": {
            "cunning": "primary",
            "savant": "primary",
            "agility": "secondary",
            "shooting": "secondary",
        },
        "champion": {"agility": "primary", "cunning": "primary", "savant": "secondary"},
        "scum": {"cunning": "primary", "agility": "secondary", "shooting": "secondary"},
    },
    # One Primary short at every rank — Wyrd Powers supplies it below.
    "Wyrd": {
        "leader": {"savant": "primary", "agility": "secondary", "cunning": "secondary"},
        "champion": {"cunning": "primary", "savant": "secondary"},
        "scum": {"agility": "secondary", "cunning": "secondary"},
    },
}


@pytest.fixture
@library_setup
def archetype_type(default_pack):
    """Use one non-repeating slot type for gang and Champion archetype choices."""
    return create_slot_type("Archetype", allows_repeats=False)


@pytest.fixture
@library_setup
def archetypes(sets, skills_collection, subtypes, profiles, archetype_type):
    """Create each archetype with rank-specific placement modifiers.

    Leader modifiers match the shared subtype; Champion and Hive Scum modifiers
    match their profiles. Champion modifiers use bearer reach so gang broadcasts
    do not apply the Champion's personal archetype row.
    """
    _, tiers = skills_collection

    scopes = {
        "leader": lambda: targets_every_model(has_subtypes(subtypes["leader"])),
        "champion": lambda: targets_model(is_profile(profiles["champion"])),
        "scum": lambda: targets_every_model(is_profile(profiles["scum"])),
    }
    made = {}
    for name, table in ARCHETYPES.items():
        archetype = create_pickable(name, archetype_type)
        for rank, row in table.items():
            for set_key, tier in row.items():
                modifier(
                    f"{name} {rank}: {set_key} {tier}",
                    scopes[rank](),
                    places(sets[set_key], tiers[tier]),
                    carried_by=archetype,
                )
        made[name] = archetype

    # Wyrds treat Wyrd Powers as Primary and gain the Wyrd Subtype —
    # at every rank, per the counts (design/outcasts.md): radiated for
    # Leader and Hive Scum, bearer-only for a Champion's own pick.
    for rank in scopes:
        modifier(
            f"Wyrd {rank}: powers are Primary",
            scopes[rank](),
            places(sets["wyrd powers"], tiers["primary"]),
            carried_by=made["Wyrd"],
        )
        modifier(
            f"Wyrd {rank}: gains the Wyrd subtype",
            scopes[rank](),
            adds(subtypes["wyrd"]),
            carried_by=made["Wyrd"],
        )
    return made


@pytest.fixture
@library_setup
def affiliation_lists(affiliations):
    """Create separate offer sections for the affiliation and Clan House choices."""
    affiliation_tokens, house_tokens = affiliations
    made = {}
    for key, name, things in [
        ("affiliations", "Affiliations", affiliation_tokens.values()),
        ("houses", "Clan Houses", house_tokens.values()),
    ]:
        collection = create_collection(name, entries=[(t, {}) for t in things])
        made[key] = section_of(collection, name, 0, is_default=True)
    return made


@pytest.fixture
@library_setup
def house_lists(db):
    from n26.tests.sandbox.actions import create_weapon

    return {
        "Escher": create_collection(
            "House Escher Equipment List",
            entries=[
                (
                    create_weapon("Lasgun", profiles=[("Standard", 0)]),
                    {"price_override": 15},
                )
            ],
        ),
        "Goliath": create_collection("House Goliath Equipment List"),
    }


@pytest.fixture
@library_setup
def mutations(db):
    from n26.tests.sandbox.actions import create_wargear

    return create_collection(
        "Mutations", entries=[(create_wargear("Extra Arm", price=30), {})]
    )


@pytest.fixture
@library_setup
def affiliations(subtypes, house_lists, mutations):
    """Create affiliation carriers and House carriers with their own collection grants."""
    house_tokens = {}
    for house, house_list in house_lists.items():
        house_tokens[house] = create_affiliation(
            f"House {house}",
            effects=[
                (
                    targets_every_model(
                        has_subtypes(subtypes["leader"], subtypes["champion"])
                    ),
                    adds(house_list),
                ),
            ],
        )

    tokens = {
        "clanless": create_affiliation("Clanless Outcast"),
        "clan_house": create_affiliation("Clan House Outcast"),
        "mutant": create_affiliation(
            "Mutant Outcast",
            effects=[(targets_every_model(), adds(mutations))],
        ),
        "aranthian": create_affiliation(
            "Aranthian Outcast",
            effects=[
                (
                    targets_every_model(
                        has_subtypes(subtypes["leader"], subtypes["champion"])
                    ),
                    adds(create_collection("Aranthian Equipment List")),
                ),
            ],
        ),
    }
    return tokens, house_tokens


@pytest.fixture
@library_setup
def outcasts(subtypes, skills_collection, affiliations, affiliation_lists):
    """Build in the affiliation anchor and add gang rules and composition notes.

    Leader profiles grant the separate gang archetype choice.
    """
    _, tiers = skills_collection
    _, house_tokens = affiliations
    gang_type = create_gang_type("Outcasts")

    affiliation_slot = create_hidden("Affiliation")
    modifier(
        "Outcasts: the Leader chooses an Affiliation",
        targets_gang(),
        offers_choice(
            Affiliation,
            from_section=affiliation_lists["affiliations"],
            label="affiliation",
        ),
        carried_by=affiliation_slot,
    )
    # The chained pick: carried by the chosen *Clan House*, so the slot
    # exists exactly while that affiliation is the chosen one.
    tokens, _ = affiliations
    modifier(
        "Clan House: choose one of the six Houses",
        targets_gang(),
        offers_choice(
            Affiliation, from_section=affiliation_lists["houses"], label="clan house"
        ),
        carried_by=tokens["clan_house"],
    )

    gang_type.built_ins = create_default_set(
        "Outcast gang built-ins", members=[affiliation_slot]
    )
    gang_type.save()

    modifier(
        "Outcasts: Cult of Personality",
        targets_every_model(),
        adds(create_rule("Cult of Personality")),
        carried_by=gang_type,
    )
    modifier(
        "Outcasts: Starting Skills",
        targets_every_model(has_subtypes(subtypes["leader"], subtypes["champion"])),
        offers_choice(Skill, from_section=tiers["primary"]),
        carried_by=gang_type,
    )
    modifier(
        "Outcasts: Lead the Masses",
        targets_gang(),
        requires_companions(subtypes["champion"], 3, subtypes["scum"]),
        carried_by=gang_type,
    )
    from n26.library.conversion import apply, plan_outcast_affiliation

    apply(plan_outcast_affiliation())
    return gang_type


@pytest.fixture
@library_setup
def profiles(outcasts, subtypes, person_type):
    """Create four Leader variants with one shared subtype and specific Champion and Hive Scum profiles."""
    made = {"leaders": []}
    for number in (1, 2, 3, 4):
        leader = create_profile(f"Leader {number}", person_type, outcasts, price=100)
        leader.built_ins = create_default_set(
            f"Leader {number} built-ins", members=[subtypes["leader"]]
        )
        leader.save()
        made["leaders"].append(leader)
    made["leader"] = made["leaders"][0]
    for key, name, price in [
        ("champion", "Outcast Champion", 80),
        ("scum", "Outcast Hive Scum", 20),
    ]:
        profile = create_profile(name, person_type, outcasts, price=price)
        profile.built_ins = create_default_set(
            f"{name} built-ins", members=[subtypes[key]]
        )
        profile.save()
        made[key] = profile
    return made


@pytest.fixture
@library_setup
def archetype_question(archetypes, profiles, archetype_type):
    """Offer one archetype picklist through gang-assigned Leader choices and a bearer-assigned Champion choice."""
    offered = create_picklist(
        "Outcast Archetypes", archetype_type, members=list(archetypes.values())
    )
    asked = {
        "gang": create_slot(
            "Gang archetype",
            archetype_type,
            offered,
            label="Archetype",
            assigned_to="gang",
        ),
        "champion": create_slot(
            "Champion archetype",
            archetype_type,
            offered,
            label="Archetype",
            assigned_to="bearer",
        ),
    }
    for leader in profiles["leaders"]:
        modifier(
            f"{leader.name}: chooses the gang's Archetype",
            targets_model(),
            ef_adds(asked["gang"]),
            carried_by=leader,
        )
    modifier(
        "Outcast Champion: chooses an Archetype",
        targets_model(),
        ef_adds(asked["champion"]),
        carried_by=profiles["champion"],
    )
    return asked


@pytest.fixture
def gang(outcasts):
    return found_gang("The Forgotten", outcasts, owner=User.objects.create_user("tom"))


@pytest.fixture
def crew(gang, profiles, archetype_question):
    return {
        "leader": hire_with_option(gang, profiles["leader"], "Sorrow"),
        "champion": hire_with_option(gang, profiles["champion"], "Grix"),
        "scum": hire_with_option(gang, profiles["scum"], "Rat"),
    }


def gang_slot(gang, assignable_name):
    return next(
        row for row in gang.assignments.all() if row.assignable.name == assignable_name
    )


def the_gang_computed(gang):
    card = build_gang_card(gang)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute_gang(card, index)


def fighter_computed(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


def tiers_for(miniature, skills_collection, sets):
    collection, _ = skills_collection
    placed = placements_for(fighter_computed(miniature), collection)
    return {
        key: placed[category].section.name
        for key, category in sets.items()
        if category in placed
    }


class TestTheLeadersChoiceLifecycle:
    def test_the_leaders_choice_radiates_and_leaves_with_the_leader(
        self,
        gang,
        profiles,
        archetype_question,
        archetypes,
        skills_collection,
        sets,
        subtypes,
        outcasts,
        person_type,
    ):
        from n26.tests.sandbox.actions import remove

        computed = the_gang_computed(gang)
        assert [slot.kind_label for slot in computed.choices] == ["Affiliation"]
        assert not computed.choices[0].is_resolved

        crew = {
            "leader": hire_with_option(gang, profiles["leader"], "Sorrow"),
            "champion": hire_with_option(gang, profiles["champion"], "Grix"),
            "scum": hire_with_option(gang, profiles["scum"], "Rat"),
        }

        computed = fighter_computed(crew["leader"])
        slot = next(s for s in computed.choices if s.kind_label == "Archetype")
        assert not slot.is_resolved
        offerable = offered_by(slot, computed)
        assert {pickable.name for pickable in offerable} == set(ARCHETYPES)

        gang_computed = the_gang_computed(gang)
        affiliations = offered_by(gang_computed.choice("Affiliation"), gang_computed)
        assert {line.name for line in affiliations} == {
            "Clanless Outcast",
            "Clan House Outcast",
            "Mutant Outcast",
            "Aranthian Outcast",
        }

        for member in crew.values():
            computed = fighter_computed(member)
            assert "Cult of Personality" in [c.name for c in computed.rules]

        chosen = pick_archetype(crew, archetypes["Brawler"])
        assert chosen.gang == gang and chosen.miniature is None
        assert chosen.caused_by == leader_anchor(crew)

        slot = next(
            s
            for s in fighter_computed(crew["leader"]).choices
            if s.kind_label == "Archetype"
        )
        assert slot.is_resolved and slot.chosen_name == "Brawler"

        computed = fighter_computed(crew["leader"])
        offer = next(
            slot for slot in computed.choices if slot.kind_label == "Primary skill"
        )
        picklist = offered_by(offer, computed)
        # Brawler Leader Primary = Combat + Savant.
        assert {line.name for line in picklist.all_lines()} == {
            "Berserker",
            "Medicate",
        }

        from n26.library.models import Skill

        founding = gang_slot(gang, "Outcasts")
        chosen = choose(
            founding, Skill.objects.get(name="Berserker"), miniature=crew["leader"]
        )
        assert chosen.miniature == crew["leader"]

        leader_slot = next(
            slot
            for slot in fighter_computed(crew["leader"]).choices
            if slot.kind_label == "Primary skill"
        )
        assert leader_slot.is_resolved and leader_slot.chosen_name == "Berserker"
        champion_slot = next(
            slot
            for slot in fighter_computed(crew["champion"]).choices
            if slot.kind_label == "Primary skill"
        )
        assert not champion_slot.is_resolved

        outsider_entry = create_profile("Dust Rat", person_type, outcasts, price=15)
        outsider_entry.built_ins = create_default_set(
            "Dust Rat built-ins", members=[subtypes["scum"]]
        )
        outsider_entry.save()
        outsider = hire_with_option(gang, outsider_entry, "Skitter")

        assert tiers_for(crew["scum"], skills_collection, sets) != {}
        assert tiers_for(outsider, skills_collection, sets) == {}

        anchor = crew["champion"].assignments.get(profile__isnull=False)
        chosen = choose(
            anchor, archetypes["Gunslinger"], slot=_slot_named("Champion archetype")
        )
        assert chosen.miniature == crew["champion"]

        assert tiers_for(crew["champion"], skills_collection, sets) == {
            "agility": "Primary",
            "shooting": "Primary",
            "savant": "Secondary",
        }
        # The Champion's personal archetype does not broadcast to other models.
        assert tiers_for(crew["scum"], skills_collection, sets)["combat"] == "Primary"

        assert tiers_for(crew["scum"], skills_collection, sets) != {}

        remove(leader_anchor(crew))
        assert tiers_for(crew["scum"], skills_collection, sets) == {}

        gang.refresh_from_db()
        assert_reconciled(gang)


def _slot_named(name):
    from n26.library.models import Slot

    return Slot.objects.get(name=name)


def _pickable_named(name, slot_type):
    from n26.library.models import Pickable

    return Pickable.objects.get(name=name, slot_type__name=slot_type)


def pick_affiliation(gang, token):
    return choose(
        gang_slot(gang, "Affiliation"),
        _pickable_named(token.name, "Affiliation"),
        slot=_slot_named("Affiliation"),
    )


def pick_house(gang, token):
    anchor = next(
        row
        for row in gang.assignments.filter(archived=False)
        if row.assignable.name == "Clan House Outcast"
    )
    return choose(
        anchor,
        _pickable_named(token.name, "Clan House"),
        slot=_slot_named("Clan House"),
    )


def leader_anchor(crew):
    """Return the Leader membership that anchors the archetype choice."""
    return crew["leader"].assignments.get(profile__isnull=False)


def pick_archetype(crew, archetype, asked=None):
    """Choose the gang-assigned archetype using the Leader membership and explicit granted slot."""
    return choose(leader_anchor(crew), archetype, slot=_slot_named("Gang archetype"))


class TestArchetypes:
    def test_the_tables_land_per_rank(
        self,
        outcasts,
        profiles,
        archetype_question,
        archetypes,
        skills_collection,
        sets,
    ):
        owner = User.objects.create_user("tom")
        for name in ARCHETYPES:
            gang = found_gang("The Forgotten", outcasts, owner=owner)
            crew = {
                "leader": hire_with_option(gang, profiles["leader"], "Sorrow"),
                "champion": hire_with_option(gang, profiles["champion"], "Grix"),
                "scum": hire_with_option(gang, profiles["scum"], "Rat"),
            }
            pick_archetype(crew, archetypes[name])

            want = {
                rank: {
                    key: tier.capitalize()
                    for key, tier in ARCHETYPES[name][rank].items()
                }
                for rank in ("leader", "scum")
            }
            if name == "Wyrd":
                for rank in want:
                    want[rank]["wyrd powers"] = "Primary"
            assert tiers_for(crew["leader"], skills_collection, sets) == want["leader"]
            assert tiers_for(crew["scum"], skills_collection, sets) == want["scum"]
            assert tiers_for(crew["champion"], skills_collection, sets) == {}

            gang.refresh_from_db()
            assert_reconciled(gang)

    def test_every_leader_variant_reads_the_leader_row(
        self,
        outcasts,
        profiles,
        archetypes,
        archetype_question,
        skills_collection,
        sets,
    ):
        """Match Leader archetype effects through the shared subtype across profile variants."""
        other = found_gang(
            "The Unforgotten", outcasts, owner=User.objects.create_user("meg")
        )
        leader = hire_with_option(other, profiles["leaders"][3], "Last Chance")
        anchor = leader.assignments.get(profile__isnull=False)
        choose(anchor, archetypes["Brawler"], slot=_slot_named("Gang archetype"))

        assert tiers_for(leader, skills_collection, sets) == {
            "combat": "Primary",
            "savant": "Primary",
            "brawn": "Secondary",
            "cunning": "Secondary",
        }


class TestAffiliationChains:
    def test_clan_house_opens_the_second_pick_and_its_list_to_the_right_ranks(
        self, gang, affiliations, profiles, archetype_question
    ):
        crew = {
            "leader": hire_with_option(gang, profiles["leader"], "Sorrow"),
            "champion": hire_with_option(gang, profiles["champion"], "Grix"),
            "scum": hire_with_option(gang, profiles["scum"], "Rat"),
        }
        tokens, house_tokens = affiliations
        computed = the_gang_computed(gang)
        assert computed.choice("Clan house") is None  # not until it's chosen

        pick_affiliation(gang, tokens["clan_house"])
        computed = the_gang_computed(gang)
        slot = computed.choice("Clan house")
        assert slot is not None and not slot.is_resolved

        pick_house(gang, house_tokens["Escher"])
        assert (
            the_gang_computed(gang).choice("Clan house").chosen_name == "House Escher"
        )

        for rank, expected in [("leader", True), ("champion", True), ("scum", False)]:
            computed = fighter_computed(crew[rank])
            held = "House Escher Equipment List" in [
                c.name for c in computed.collections
            ]
            assert held is expected, rank

        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_mutants_open_the_mutation_list_to_all(self, gang, crew, affiliations):
        tokens, _ = affiliations
        pick_affiliation(gang, tokens["mutant"])

        for member in crew.values():
            computed = fighter_computed(member)
            assert "Mutations" in [c.name for c in computed.collections]


class TestLeadTheMasses:
    def test_a_short_roster_is_said_never_fixed(self, gang, profiles):
        hire_with_option(gang, profiles["leader"], "Sorrow")
        hire_with_option(gang, profiles["champion"], "Grix")
        hire_with_option(gang, profiles["scum"], "Rat")

        (note,) = the_gang_computed(gang).notes
        assert "1 Champion need 3 Hive Scum" in note.text
        assert "the gang has 1" in note.text

        hire_with_option(gang, profiles["scum"], "Skab")
        hire_with_option(gang, profiles["scum"], "Twitch")
        assert the_gang_computed(gang).notes == []


class TestTheSheet:
    def test_the_gang_block_reads_like_the_roster(
        self, gang, crew, archetypes, affiliations
    ):
        tokens, house_tokens = affiliations
        pick_archetype(crew, archetypes["Wyrd"])

        for rank, expected in [("leader", True), ("scum", True), ("champion", False)]:
            computed = fighter_computed(crew[rank])
            assert ("Wyrd" in [c.name for c in computed.subtypes]) is expected, rank

        pick_affiliation(gang, tokens["clan_house"])
        pick_house(gang, house_tokens["Goliath"])
        choose(
            crew["champion"].assignments.get(profile__isnull=False),
            archetypes["Survivor"],
            slot=_slot_named("Champion archetype"),
        )

        text = gang_to_text(gang)
        print("\n" + text)
        # The Leader chooses the gang-assigned archetype, which appears in the gang summary.
        assert "Archetype: Wyrd" in text
        assert "Gang: Outcasts, Wyrd" in text
        assert "Affiliation: Clan House Outcast" in text
        assert "Clan house: House Goliath" in text
        assert "Archetype: Survivor" in text  # Grix's own, on Grix's card
        assert "need 3 Hive Scum" in text

        gang.refresh_from_db()
        assert_reconciled(gang)
