"""The gang as a data structure of its own.

A gang gets the same treatment a miniature does (design/gang-sheet.md):
a data structure holding all its properties, so there is something to
test against, with the renderable version derived from it. So:
``GangCard`` is the
fetch, ``ComputedGang`` is the test interface, and the grown
``GangSheet`` derives from both — the same three layers a miniature
has, and the surface gang-level choices (a Venator's ranked skill
trees) live on.

The load-bearing rule here is **scope symmetry**: a gang-hosted row's
``TargetsMiniature`` modifiers reach members through the broadcast, as
ever, and never the gang's own card; a ``TargetsGang`` modifier appears
exactly once, on the gang's card, and never on any member's. Each card
says what it hosts (``host_kind``) and scopes read it.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.card import GANG, MODEL, build_card, build_gang_card, build_modifier_index
from n26.core.effects import compute, compute_gang
from n26.core.render import render_gang
from n26.core.render_text import gang_to_text
from n26.library.models import Skill
from n26.tests.sandbox.actions import (
    adds as _adds,
)
from n26.tests.sandbox.actions import (
    assign,
    buy,
    create_collection,
    create_counter,
    create_rule,
    create_skill,
    create_weapon,
    found_gang,
    hire_with_option,
    modifier,
    offers_choice,
    tally,
    targets_gang,
    targets_model,
)
from n26.tests.sandbox.actions import (
    choose as _choose,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def house_list(default_pack):
    return create_collection(
        "House List",
        entries=[
            (
                create_weapon("Lasgun", profiles=[("Standard", 0)]),
                {"price_override": 15},
            )
        ],
    )


@pytest.fixture
def escherish(gang_type, house_list):
    """A gang type with one of everything a gang card holds: a built-in
    list, a member-facing rule, and a gang-level choice."""
    from n26.tests.sandbox.actions import create_default_set

    gang_type.built_ins = create_default_set("Gang built-ins", members=[house_list])
    gang_type.save()
    modifier(
        "Nimble for everyone",
        targets_model(),
        _adds(create_rule("Nimble")),
        carried_by=gang_type,
    )
    modifier(
        "The gang names a favoured skill",
        targets_gang(),
        offers_choice(Skill),
        carried_by=gang_type,
    )
    return gang_type


@pytest.fixture
def gang(escherish):
    return found_gang("The Bad Girls", escherish, owner=User.objects.create_user("tom"))


@pytest.fixture
def yolanda(gang, make_profile):
    return hire_with_option(gang, make_profile("Gang Queen", price=135), "Yolanda")


def gang_computed(gang):
    card = build_gang_card(gang)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute_gang(card, index)


def member_computed(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


class TestTheGangCard:
    def test_each_card_says_what_it_hosts(self, gang, yolanda):
        """The contract scope symmetry hangs off."""
        assert build_gang_card(gang).host_kind == GANG
        assert build_card(yolanda).host_kind == MODEL

    def test_founding_puts_the_gangs_own_rows_on_its_card(self, gang):
        """The founding and the house list are first-class rows *here* —
        on member cards the same rows are broadcast echoes."""
        card = build_gang_card(gang)
        assert [node.name for node in card.roots] == ["Escher", "House List"]
        assert not any(node.broadcast for node in card.all_nodes())

    def test_members_come_from_the_same_fetch(self, gang, yolanda):
        card = build_gang_card(gang)
        assert set(card.members) == {yolanda.pk}
        aboard = card.members[yolanda.pk].find("House List")
        assert aboard is not None and aboard.broadcast

    def test_the_stash_is_storage_not_facts(self, gang, house_list):
        """Stash rows draw on the gang card but are not in ``all_nodes``:
        nothing in the stash is a fact about the gang, and nothing in it
        computes (design/gang-sheet.md)."""
        from n26.core.browse import browse

        buy(gang.stash, next(browse(house_list).all_lines()))

        card = build_gang_card(gang)
        assert card.stash_find("Lasgun") is not None
        assert card.stash_rating == 15
        assert card.find("Lasgun") is None

    def test_the_gang_card_costs_a_fixed_number_of_queries(self, gang, make_profile):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        profile = make_profile("Ganger", price=50)
        hire_with_option(gang, profile, "One")

        def measure():
            with CaptureQueriesContext(connection) as captured:
                assert build_gang_card(gang).members
            return len(captured.captured_queries)

        few = measure()
        for index in range(3):
            hire_with_option(gang, profile, f"More {index}")
        assert measure() == few


class TestScopeSymmetry:
    def test_a_gang_level_offer_never_reaches_a_member(self, gang, yolanda):
        computed = member_computed(yolanda)
        assert [slot.kind_label for slot in computed.choices] == []
        # Not silently absent: the plan shows the scope asked and refused.
        step = next(s for s in computed.plan if "names a favoured" in str(s.modifier))
        assert step.outcome == "skipped"

    def test_a_member_facing_rule_never_lands_on_the_gang(self, gang):
        computed = gang_computed(gang)
        assert [c.name for c in computed.rules] == []
        step = next(s for s in computed.plan if "Nimble" in str(s.modifier))
        assert step.outcome == "skipped"

    def test_the_same_rows_work_both_ways(self, gang, yolanda):
        """One carrier, two scopes, each reaching exactly its own kind of
        card — the broadcast is unchanged by the gang card existing."""
        computed = member_computed(yolanda)
        assert [c.name for c in computed.rules] == ["Nimble"]
        assert [slot.kind_label for slot in gang_computed(gang).choices] == ["Skill"]


class TestComputedGang:
    def test_a_choice_nobody_has_made_is_an_open_slot(self, gang):
        slot = gang_computed(gang).choice("Skill")
        assert slot is not None and not slot.is_resolved

    def test_choosing_settles_it_gang_hosted(self, gang):
        anchor = next(
            row for row in gang.assignments.all() if row.assignable.name == "Escher"
        )
        chosen = _choose(anchor, create_skill("Overwatch"))

        assert chosen.gang == gang and chosen.miniature is None
        slot = gang_computed(gang).choice("Skill")
        assert slot.is_resolved and slot.chosen_name == "Overwatch"

    def test_the_same_thing_chosen_twice_draws_a_note(self, gang, escherish):
        """Two slots, one thing chosen — incoherent-ish, so it is *said*, never
        blocked: the owner may do as they please (inform, not police)."""
        modifier(
            "The gang names a second skill",
            targets_gang(),
            offers_choice(Skill),
            carried_by=escherish,
        )
        anchor = next(
            row for row in gang.assignments.all() if row.assignable.name == "Escher"
        )
        overwatch = create_skill("Overwatch")
        _choose(anchor, overwatch)

        computed = gang_computed(gang)
        assert [slot.is_resolved for slot in computed.choices] == [True, True]
        assert [note.about for note in computed.notes] == [overwatch]

    def test_counters_read_with_their_values(self, gang):
        meat = create_counter("Meat")
        held = assign(meat, gang=gang)
        tally(held, +3)

        readings = gang_computed(gang).counters
        assert [(reading.name, reading.value) for reading in readings] == [("Meat", 3)]


class TestTheRosterOrder:
    """Fighters print in the gang list's own order, not the alphabet's.

    Rank first (the profile's home category, by the taxonomy's
    positions), name within a rank, and a model somebody's purchase
    brought in — a pet — directly after its owner. The first edition's
    roster is the reference order.
    """

    @pytest.fixture
    def ranks(self, default_pack):
        from n26.tests.sandbox.actions import create_category

        return {
            name: create_category("Gang List", name, position)
            for position, name in enumerate(["Leader", "Champion", "Ganger", "Pet"])
        }

    @pytest.fixture
    def ranked_crew(self, gang, ranks, make_profile):
        """Hired in no particular order, named against the alphabet —
        so only the rank ordering can put them right."""
        from n26.tests.sandbox.actions import hire_with_option

        for name, rank in [
            ("Bob", "Ganger"),
            ("Zed", "Leader"),
            ("Wilma", "Ganger"),
            ("Ann", "Champion"),
        ]:
            profile = make_profile(f"{rank} entry {name}", category=ranks[rank])
            hire_with_option(gang, profile, name)
        return gang

    def test_rank_beats_the_alphabet_and_the_hire_order(self, ranked_crew):
        sheet = render_gang(ranked_crew)
        assert [card.name for card in sheet.models] == [
            "Zed",
            "Ann",
            "Bob",
            "Wilma",
        ]

    def test_a_pet_rides_with_its_owner(self, ranked_crew, ranks, make_profile):
        """Ann's pet sorts directly after Ann — not under Pets at the
        end, and not alphabetically among the fighters."""
        from n26.core.browse import browse
        from n26.core.models import Miniature
        from n26.tests.sandbox.actions import (
            buy,
            create_collection,
            create_wargear,
            modifier,
            op_adds_model,
            targets_model,
        )

        beast = make_profile("Pet entry", category=ranks["Pet"])
        leash = create_wargear("Sumpkroc leash", price=50)
        modifier(
            "The leash brings a Sumpkroc",
            targets_model(),
            op_adds_model(beast),
            carried_by=leash,
        )
        shop = create_collection("Pet Shop", entries=[(leash, {})])

        ann = Miniature.objects.get(name="Ann")
        buy(ann, next(browse(shop).all_lines()))
        # The spawned model takes the profile's name until renamed.
        sheet = render_gang(ranked_crew)
        assert [card.name for card in sheet.models] == [
            "Zed",
            "Ann",
            "Pet entry",
            "Bob",
            "Wilma",
        ]

    def test_the_unranked_sort_after_everyone_placed(self, ranked_crew, make_profile):
        from n26.tests.sandbox.actions import hire_with_option

        profile = make_profile("Uncategorised entry")
        hire_with_option(ranked_crew, profile, "Aaron")

        sheet = render_gang(ranked_crew)
        assert [card.name for card in sheet.models] == [
            "Zed",
            "Ann",
            "Bob",
            "Wilma",
            "Aaron",
        ]

    def test_the_ladder_runs_across_sections(self, ranked_crew, make_profile):
        """A Hanger-on is filed under Supplementary Profiles, a Brute
        under Gang List — and the roster ranks by the category's own
        position whichever section holds it, so a supplementary rank can
        muster before a gang list one. Ranked by section first, every
        supplementary fighter could only ever sort after the whole gang
        list."""
        from n26.tests.sandbox.actions import create_category, hire_with_option

        brute = create_category("Gang List", "Brute", position=7)
        hanger_on = create_category("Supplementary Profiles", "Hanger-on", position=6)
        hire_with_option(
            ranked_crew, make_profile("Brute entry", category=brute), "Grond"
        )
        hire_with_option(
            ranked_crew, make_profile("Hanger-on entry", category=hanger_on), "Dok"
        )

        sheet = render_gang(ranked_crew)
        assert [card.name for card in sheet.models] == [
            "Zed",
            "Ann",
            "Bob",
            "Wilma",
            "Dok",
            "Grond",
        ]

    def test_a_rule_may_refile_a_model(self, ranked_crew, ranks, make_profile):
        """A ganger selected as the gang's Leader sorts with the Leaders,
        whatever their entry says: the re-filing is computed off the
        card like any other fact, and goes if its carrier goes."""
        from n26.core.models import Miniature
        from n26.tests.sandbox.actions import (
            assign,
            create_subtype,
            ef_changes_category,
            remove,
        )

        chosen = create_subtype("Chosen Leader")
        modifier(
            "The chosen one leads",
            targets_model(),
            ef_changes_category(ranks["Leader"]),
            carried_by=chosen,
        )
        wilma = Miniature.objects.get(name="Wilma")
        carrier = assign(chosen, miniature=wilma)

        sheet = render_gang(ranked_crew)
        assert [card.name for card in sheet.models] == ["Wilma", "Zed", "Ann", "Bob"]

        remove(carrier)
        sheet = render_gang(ranked_crew)
        assert [card.name for card in sheet.models] == ["Zed", "Ann", "Bob", "Wilma"]

    def test_vehicles_sort_after_every_fighter(
        self, ranked_crew, make_profile, vehicle_type
    ):
        """A vehicle's category numbers it within its own section, and a
        position that collides with a fighter rank's must not pull the
        machine up among the crew: the Type puts every vehicle after
        every fighter, whatever its category says."""
        from n26.tests.sandbox.actions import create_category, hire_with_option

        motor_pool = create_category("Vehicles", "Vehicle", position=0)
        hire_with_option(
            ranked_crew,
            make_profile(
                "Ridgehauler entry", category=motor_pool, profile_type=vehicle_type
            ),
            "Big Rig",
        )

        sheet = render_gang(ranked_crew)
        assert [card.name for card in sheet.models] == [
            "Zed",
            "Ann",
            "Bob",
            "Wilma",
            "Big Rig",
        ]


class TestTheSheetDerives:
    def test_rows_choices_and_stash(self, gang, yolanda, house_list):
        from n26.core.browse import browse

        buy(gang.stash, next(browse(house_list).all_lines()))
        anchor = next(
            row for row in gang.assignments.all() if row.assignable.name == "Escher"
        )
        _choose(anchor, create_skill("Overwatch"))

        sheet = render_gang(gang)
        assert [line.name for line in sheet.rows] == ["Escher", "House List"]
        assert [(c.kind_label, c.chosen) for c in sheet.choices] == [
            ("Skill", "Overwatch")
        ]
        assert [(line.name, line.rating) for line in sheet.stash] == [("Lasgun", 15)]
        assert sheet.stash_rating == 15
        # The chosen row is drawn as the choice's line, never twice.
        assert "Overwatch" not in [line.name for line in sheet.rows]

    def test_the_gangs_rules_are_their_own_list(self, gang):
        """A rule on the gang is dispatched apart from the other rows —
        the sheet prints rules under their own term, as a model card
        does. A ``targets_gang`` grant of one folds in beside the stored
        rows, told apart by provenance: the gang's card carries named
        rules and standing lists, and those two kinds alone."""
        assign(create_rule("Chem Dealers"), gang=gang)
        modifier(
            "The house trades in toxins",
            targets_gang(),
            _adds(create_rule("Toxin Trade")),
            carried_by=gang.gang_type,
        )

        sheet = render_gang(gang)
        assert [line.name for line in sheet.rules] == ["Chem Dealers", "Toxin Trade"]
        granted = next(line for line in sheet.rules if line.name == "Toxin Trade")
        assert granted.provenance.computed is True
        assert "Chem Dealers" not in [line.name for line in sheet.rows]

        computed = gang_computed(gang)
        step = next(s for s in computed.plan if "toxins" in str(s.modifier))
        assert step.outcome == "reached"

    def test_the_gang_may_be_granted_a_standing_list(self, gang):
        """A collection granted to the gang draws among its rows — an
        alliance's standing access, gone when the alliance goes."""
        from n26.tests.sandbox.actions import create_collection, remove

        bazaar = create_collection("Bazaar Access")
        charter = create_rule("Trade Charter")
        modifier(
            "The charter opens the bazaar",
            targets_gang(),
            _adds(bazaar),
            carried_by=charter,
        )
        carrier = assign(charter, gang=gang)

        sheet = render_gang(gang)
        assert "Bazaar Access" in [line.name for line in sheet.rows]

        remove(carrier)
        sheet = render_gang(gang)
        assert "Bazaar Access" not in [line.name for line in sheet.rows]

    def test_the_gangs_colour_rides_the_sheet(self, gang):
        """The mark drawn beside a gang's name comes off the sheet like
        everything else a page shows, so a heading and the row that
        opened it cannot disagree about which colour the gang is."""
        assert render_gang(gang).colour == ""

        gang.colour = "violet"
        gang.save()
        assert render_gang(gang).colour == "violet"

    def test_wealth_still_counts_everything(self, gang, yolanda, house_list):
        from n26.core.browse import browse

        buy(gang.stash, next(browse(house_list).all_lines()))
        gang.refresh_from_db()
        sheet = render_gang(gang)
        assert sheet.rating == 135  # Yolanda; never the stash
        assert sheet.wealth == 150  # rating + credits (0) + stash

    def test_the_text_renderer_draws_the_gang_block(self, gang, yolanda, house_list):
        from n26.core.browse import browse

        buy(gang.stash, next(browse(house_list).all_lines()))
        assign(create_rule("Chem Dealers"), gang=gang)
        text = gang_to_text(gang)
        print("\n" + text)

        assert "Gang: Escher, House List" in text
        assert "Rules: Chem Dealers" in text
        assert "Skill: — (not chosen)" in text
        assert "Stash — 15cr" in text
        assert "  Lasgun — 15cr" in text
