"""Founding an Outcast gang: archetypes, affiliations, chosen carriers.

Follows the 2026 Outcast gang list (design/outcasts.md). The shape
inverts the Venator one: where a
Venator slot carries the meaning and the pick names a tree, an Outcast
gang picks a **carrier** — an ``Archetype``, an ``Affiliation`` —
whose whole payload rides the pick as ordinary modifiers. The mapping table lives
in this file's ``ARCHETYPES`` dict; no code knows it.

What this pins:

* **Leader → Gang → fighters**: the Leader
  carries the archetype question, the answer is *for the gang*
  (``OffersChoice.answer_host="gang"``), it radiates via the broadcast — and
  dies with the Leader through the caused_by cascade;
* the archetype tables per rank, one carrier per printed archetype,
  **including the Wyrd counts proof** (Wyrd runs one Primary short at
  every rank; Wyrd Powers supplies it);
* **how a rank row targets, as the printed sheet has it**: the Leader
  row hangs off the shared Leader *subtype*, so every Leader variant
  receives it; the Champion and Hive Scum rows name their *profiles*
  outright (``is_profile``), so a same-ranked outsider reads nothing;
* "…all models except Champions": the Champion row is **bearer only**
  (``TargetsMiniature.when_directly_assigned``) — what a Champion gets
  if *they* pick it, inert in the gang's radiated copy;
* **chained choices**: Clan House's answer offers the house pick —
  a slot caused by a slot's answer, no new machinery;
* affiliations as scoped access grants;
* Lead the Masses as a composition *note*, never a removal.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.browse import offered_by, placements_for
from n26.core.card import build_card, build_gang_card, build_modifier_index
from n26.core.effects import compute, compute_gang
from n26.core.render_text import gang_to_text
from n26.library.authoring import has_subtypes, is_profile, targets_model
from n26.library.models import Affiliation, Archetype, Skill
from n26.tests.sandbox.actions import (
    adds,
    choose,
    create_affiliation,
    create_archetype,
    create_category,
    create_collection,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_profile,
    create_rule,
    create_skill,
    create_subtype,
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
def subtypes(db):
    """The generic rank vocabulary — shared across gang lists, which is
    exactly why the Champion and Hive Scum rows cannot hang off it."""
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
def archetypes(sets, skills_collection, subtypes, profiles):
    """One carrier per printed archetype, all three rank rows aboard.

    Targeting reads off the printed sheet: the Leader row hangs off the
    Leader *subtype*, so every Leader variant receives it; the Champion
    and Hive Scum rows name their *profiles* outright — the rank
    subtypes are shared vocabulary, and naming the entry keeps a
    same-ranked outsider out of the archetype's reach.

    The Champion row is also **bearer only**: it
    says what a Champion gets *if they pick this archetype* — inert when
    it radiates from the gang, active when a Champion carries
    their own copy. Hosting decides; the content is one table."""
    _, tiers = skills_collection

    scopes = {
        "leader": lambda: targets_model(has_subtypes(subtypes["leader"])),
        "champion": lambda: targets_model(
            is_profile(profiles["champion"]), when_directly_assigned=True
        ),
        "scum": lambda: targets_model(is_profile(profiles["scum"])),
    }
    made = {}
    for name, table in ARCHETYPES.items():
        archetype = create_archetype(name)
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
def affiliation_lists(affiliations):
    """One small collection per question, so each offer narrows to
    exactly its own list."""
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
def mutations(db):
    from n26.tests.sandbox.actions import create_wargear

    return create_collection(
        "Mutations", entries=[(create_wargear("Extra Arm", price=30), {})]
    )


@pytest.fixture
def affiliations(subtypes, house_lists, mutations):
    """Four affiliations; Clan House chains a second pick whose answers
    carry their own payloads (each house token knows its own list)."""
    house_tokens = {}
    for house, house_list in house_lists.items():
        house_tokens[house] = create_affiliation(
            f"House {house}",
            effects=[
                (
                    targets_model(
                        has_subtypes(subtypes["leader"], subtypes["champion"])
                    ),
                    adds(house_list),
                ),
            ],
        )

    tokens = {
        # TP grants live in the parked budget design — the token stands.
        "clanless": create_affiliation("Clanless Outcast"),
        "clan_house": create_affiliation("Clan House Outcast"),
        "mutant": create_affiliation(
            "Mutant Outcast",
            effects=[(targets_model(), adds(mutations))],
        ),
        "aranthian": create_affiliation(
            "Aranthian Outcast",
            effects=[
                (
                    targets_model(
                        has_subtypes(subtypes["leader"], subtypes["champion"])
                    ),
                    adds(create_collection("Aranthian Equipment List")),
                ),
            ],
        ),
    }
    return tokens, house_tokens


@pytest.fixture
def outcasts(subtypes, skills_collection, affiliations, affiliation_lists):
    """The gang type: the affiliation slot, the gang rules, the ratio
    ask. The archetype slot is *not* here — it rides the Leader
    (see ``archetype_question``): Leader → Gang → fighters."""
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
    # The chained pick: carried by the Clan House *answer*, so the slot
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
        targets_model(),
        adds(create_rule("Cult of Personality")),
        carried_by=gang_type,
    )
    modifier(
        "Outcasts: Starting Skills",
        targets_model(has_subtypes(subtypes["leader"], subtypes["champion"])),
        offers_choice(Skill, from_section=tiers["primary"]),
        carried_by=gang_type,
    )
    modifier(
        "Outcasts: Lead the Masses",
        targets_gang(),
        requires_companions(subtypes["champion"], 3, subtypes["scum"]),
        carried_by=gang_type,
    )
    return gang_type


@pytest.fixture
def profiles(outcasts, subtypes, person_type):
    """The gang list: four Leader variants sharing the Leader subtype,
    and the Champion and Hive Scum entries the archetype rows name."""
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
def archetype_question(archetypes, profiles):
    """The pick list, and the offers that ask it.

    Leader → Gang → fighters: every Leader variant carries the
    archetype choice, but the answer is for the gang — it lands as a
    gang row, radiates to the members, and dies with the Leader.
    Champions may choose a different Archetype to their gang's Leader:
    the same five archetypes, answered on — and borne by — the fighter.
    """
    collection = create_collection(
        "Archetypes", entries=[(a, {}) for a in archetypes.values()]
    )
    section = section_of(collection, "Archetypes", 0, is_default=True)
    for leader in profiles["leaders"]:
        modifier(
            f"{leader.name}: chooses the gang's Archetype",
            targets_model(),
            offers_choice(
                Archetype, from_section=section, label="archetype", answer_host="gang"
            ),
            carried_by=leader,
        )
    modifier(
        "Outcast Champion: chooses an Archetype",
        targets_model(),
        offers_choice(Archetype, from_section=section, label="archetype"),
        carried_by=profiles["champion"],
    )
    return section


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


class TestFoundingOffersTheChoices:
    def test_the_gang_asks_for_its_affiliation(self, gang):
        """The affiliation question is the gang's from founding; the
        archetype question does not exist until there is a Leader —
        "when an Outcast Leader is recruited… they must choose"."""
        computed = the_gang_computed(gang)
        assert [slot.kind_label for slot in computed.choices] == ["Affiliation"]
        assert not computed.choices[0].is_resolved

    def test_the_archetype_question_arrives_with_the_leader(self, gang, crew):
        computed = fighter_computed(crew["leader"])
        slot = next(s for s in computed.choices if s.kind_label == "Archetype")
        assert not slot.is_resolved

    def test_each_offer_narrows_to_its_own_list(self, gang, crew):
        computed = fighter_computed(crew["leader"])
        slot = next(s for s in computed.choices if s.kind_label == "Archetype")
        offerable = offered_by(slot, computed)
        assert {line.name for line in offerable.all_lines()} == set(ARCHETYPES)

        gang_computed = the_gang_computed(gang)
        affiliations = offered_by(gang_computed.choice("Affiliation"), gang_computed)
        assert {line.name for line in affiliations.all_lines()} == {
            "Clanless Outcast",
            "Clan House Outcast",
            "Mutant Outcast",
            "Aranthian Outcast",
        }


def leader_anchor(crew):
    """The assignment whose assignable (the Leader profile) offers the
    archetype — the Leader's membership row."""
    return crew["leader"].assignments.get(profile__isnull=False)


def pick_archetype(crew, archetype):
    """The Leader → Gang arrow: the Leader answers; the gang carries it."""
    return choose(leader_anchor(crew), archetype)


class TestArchetypes:
    def test_the_leader_answers_and_the_gang_carries_it(self, gang, crew, archetypes):
        answer = pick_archetype(crew, archetypes["Brawler"])
        assert answer.gang == gang and answer.miniature is None
        assert answer.caused_by == leader_anchor(crew)

        slot = next(
            s
            for s in fighter_computed(crew["leader"]).choices
            if s.kind_label == "Archetype"
        )
        assert slot.is_resolved and slot.chosen_name == "Brawler"

    def test_the_archetype_dies_with_the_leader(
        self, gang, crew, archetypes, skills_collection, sets
    ):
        """ "When an Outcast Leader is recruited they must choose" falls
        out of the hosting: the answer is caused by the Leader's row, so
        removing the Leader retires it, and the scum's sections reset."""
        from n26.tests.sandbox.actions import remove

        pick_archetype(crew, archetypes["Brawler"])
        assert tiers_for(crew["scum"], skills_collection, sets) != {}

        remove(leader_anchor(crew))
        assert tiers_for(crew["scum"], skills_collection, sets) == {}

    @pytest.mark.parametrize("name", list(ARCHETYPES))
    def test_the_tables_land_per_rank(
        self, gang, crew, archetypes, skills_collection, sets, name
    ):
        """Leader and Hive Scum read their rows; the Champion reads
        *nothing* from the gang's pick — the champion row is bearer-only,
        and the gang's copy is nobody's bearer."""
        pick_archetype(crew, archetypes[name])

        want = {
            rank: {
                key: tier.capitalize() for key, tier in ARCHETYPES[name][rank].items()
            }
            for rank in ("leader", "scum")
        }
        if name == "Wyrd":
            for rank in want:
                want[rank]["wyrd powers"] = "Primary"
        assert tiers_for(crew["leader"], skills_collection, sets) == want["leader"]
        assert tiers_for(crew["scum"], skills_collection, sets) == want["scum"]
        assert tiers_for(crew["champion"], skills_collection, sets) == {}

    def test_every_leader_variant_reads_the_leader_row(
        self,
        outcasts,
        profiles,
        archetypes,
        archetype_question,
        skills_collection,
        sets,
    ):
        """The Leader row hangs off the shared subtype, so a gang led by
        any of the four Leader entries lands the same table — and every
        variant carries the archetype question."""
        other = found_gang(
            "The Unforgotten", outcasts, owner=User.objects.create_user("meg")
        )
        leader = hire_with_option(other, profiles["leaders"][3], "Last Chance")
        anchor = leader.assignments.get(profile__isnull=False)
        choose(anchor, archetypes["Brawler"])

        assert tiers_for(leader, skills_collection, sets) == {
            "combat": "Primary",
            "savant": "Primary",
            "brawn": "Secondary",
            "cunning": "Secondary",
        }

    def test_a_shared_rank_subtype_does_not_leak_the_scum_row(
        self,
        gang,
        crew,
        archetypes,
        subtypes,
        outcasts,
        person_type,
        skills_collection,
        sets,
    ):
        """The Hive Scum row names the profile outright: an outsider who
        merely carries the Hive Scum subtype reads nothing from the
        gang's pick, while the named entry lands its table."""
        outsider_entry = create_profile("Dust Rat", person_type, outcasts, price=15)
        outsider_entry.built_ins = create_default_set(
            "Dust Rat built-ins", members=[subtypes["scum"]]
        )
        outsider_entry.save()
        outsider = hire_with_option(gang, outsider_entry, "Skitter")

        pick_archetype(crew, archetypes["Brawler"])
        assert tiers_for(crew["scum"], skills_collection, sets) != {}
        assert tiers_for(outsider, skills_collection, sets) == {}

    def test_a_champion_chooses_their_own(
        self, gang, crew, archetypes, skills_collection, sets
    ):
        """Same five archetypes: the champion row wakes because the fighter
        *bears* the pick; the leader and scum rows stay asleep because
        the champion is neither."""
        pick_archetype(crew, archetypes["Brawler"])
        anchor = crew["champion"].assignments.get(profile__isnull=False)
        answer = choose(anchor, archetypes["Gunslinger"])
        assert answer.miniature == crew["champion"]

        assert tiers_for(crew["champion"], skills_collection, sets) == {
            "agility": "Primary",
            "shooting": "Primary",
            "savant": "Secondary",
        }
        # And nobody else moved: the champion's personal pick radiates
        # nowhere.
        assert tiers_for(crew["scum"], skills_collection, sets)["combat"] == "Primary"

    def test_wyrd_grants_the_subtype(self, gang, crew, archetypes):
        pick_archetype(crew, archetypes["Wyrd"])

        for rank, expected in [("leader", True), ("scum", True), ("champion", False)]:
            computed = fighter_computed(crew[rank])
            assert ("Wyrd" in [c.name for c in computed.subtypes]) is expected, rank

    def test_starting_skills_follow_the_archetype(
        self, gang, crew, archetypes, skills_collection
    ):
        """Leaders and Champions select one skill from a Primary set —
        the Escher-shaped offer, fed by whatever the archetype placed."""
        pick_archetype(crew, archetypes["Brawler"])

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

    def test_a_gang_carried_offer_is_answered_per_fighter(self, gang, crew, archetypes):
        """Starting Skills rides the gang type, so the slot appears on
        every Leader's and Champion's card — but each answer names its
        fighter, and only that fighter's slot resolves."""
        from n26.library.models import Skill

        pick_archetype(crew, archetypes["Brawler"])
        founding = gang_slot(gang, "Outcasts")
        answer = choose(
            founding, Skill.objects.get(name="Berserker"), miniature=crew["leader"]
        )
        assert answer.miniature == crew["leader"]

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

    def test_cult_of_personality_reaches_everyone(self, gang, crew):
        for member in crew.values():
            computed = fighter_computed(member)
            assert "Cult of Personality" in [c.name for c in computed.rules]


class TestAffiliationChains:
    def test_clan_house_opens_the_second_pick(self, gang, affiliations):
        """The chained-choice proof: the answer is an ordinary gang row,
        so the choice it carries computes into a new slot."""
        tokens, house_tokens = affiliations
        computed = the_gang_computed(gang)
        assert computed.choice("Clan house") is None  # not until it's chosen

        choose(gang_slot(gang, "Affiliation"), tokens["clan_house"])
        computed = the_gang_computed(gang)
        slot = computed.choice("Clan house")
        assert slot is not None and not slot.is_resolved

        anchor = next(
            row
            for row in gang.assignments.all()
            if row.assignable.name == "Clan House Outcast"
        )
        choose(anchor, house_tokens["Escher"])
        assert (
            the_gang_computed(gang).choice("Clan house").chosen_name == "House Escher"
        )

    def test_the_house_opens_its_list_to_the_right_ranks(
        self, gang, crew, affiliations
    ):
        tokens, house_tokens = affiliations
        choose(gang_slot(gang, "Affiliation"), tokens["clan_house"])
        anchor = next(
            row
            for row in gang.assignments.all()
            if row.assignable.name == "Clan House Outcast"
        )
        choose(anchor, house_tokens["Escher"])

        for rank, expected in [("leader", True), ("champion", True), ("scum", False)]:
            computed = fighter_computed(crew[rank])
            held = "House Escher Equipment List" in [
                c.name for c in computed.collections
            ]
            assert held is expected, rank

    def test_mutants_open_the_mutation_list_to_all(self, gang, crew, affiliations):
        tokens, _ = affiliations
        choose(gang_slot(gang, "Affiliation"), tokens["mutant"])

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
        choose(gang_slot(gang, "Affiliation"), tokens["clan_house"])
        anchor = next(
            row
            for row in gang.assignments.all()
            if row.assignable.name == "Clan House Outcast"
        )
        choose(anchor, house_tokens["Goliath"])
        anchor = crew["champion"].assignments.get(profile__isnull=False)
        choose(anchor, archetypes["Survivor"])

        text = gang_to_text(gang)
        print("\n" + text)
        # The Leader's choice, resolved on the Leader's card; the gang
        # carries the answer, so the gang block lists it as a row.
        assert "Archetype: Wyrd" in text
        assert "Gang: Outcasts, Wyrd" in text
        assert "Affiliation: Clan House Outcast" in text
        assert "Clan house: House Goliath" in text
        assert "Archetype: Survivor" in text  # Grix's own, on Grix's card
        assert "need 3 Hive Scum" in text
