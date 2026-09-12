"""Which of a fighter's equipment lists comes first, and the repair that
sinks the variant lists.

A fighter holds several lists at once: the one the house brings and the
one a variant pick adds arrive by the same route — a grant a pick or a
gang type carries — so nothing about how a list was come by says which
is the gang's own. ``Collection.position`` does. Every list read off a
card is sorted by it once, in ``n26.core.access``, so the Equip screen,
the hire screen and the edit page agree on which list comes first; the
standard Trading Post is last whatever it carries.

The repair (``n26.library.collection_positions``) reads every collection
and how it reaches a card, and gives 100 to the lists reached only
through picks that are not gang archetypes.

Issue #2538.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.access import collections_for, gang_collections
from n26.core.card import build_gang_card, build_modifier_index
from n26.core.effects import compute_gang
from n26.core.views.equip import buyable_lists
from n26.library.archetype_display import GANG_ARCHETYPE_IDS
from n26.library.collection_positions import (
    VARIANT_POSITION,
    Refused,
    apply,
    find,
)
from n26.library.models import Collection
from n26.tests.sandbox.actions import (
    add_built_in,
    add_entry,
    choose,
    create_collection,
    create_gang_type,
    create_hidden,
    create_pickable,
    create_picklist,
    create_profile,
    create_slot,
    create_slot_type,
    create_wargear,
    ef_adds,
    found_gang,
    hire,
    modifier,
    targets_every_model,
    targets_gang,
    targets_gang_alone,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def lists(db):
    """Two equipment lists, each holding a piece of gear so a buying
    screen offers it."""
    made = {}
    for key, name, gear in [
        ("house", "Escher Equipment List", "Mesh armour"),
        ("variant", "Chaos Corrupted Equipment List", "Chaos icon"),
    ]:
        collection = create_collection(name)
        add_entry(collection, create_wargear(gear, price=20))
        made[key] = collection
    return made


@pytest.fixture
def escher(lists):
    """The house: a gang type that grants its list to the gang and to
    every member — the route a house list takes in the shipped content,
    and the same route a variant's list takes."""
    gang_type = create_gang_type("Escher", starting_credits=1000)
    modifier(
        "Escher: the gang buys from the Escher list",
        targets_gang_alone(),
        ef_adds(lists["house"]),
        carried_by=gang_type,
    )
    modifier(
        "Escher: its fighters buy from the Escher list",
        targets_every_model(),
        ef_adds(lists["house"]),
        carried_by=gang_type,
    )
    return gang_type


@pytest.fixture
def sister(escher, person_type, make_statline):
    profile = create_profile("Gang Sister", person_type, escher, price=55)
    make_statline(profile, movement=5, weapon_skill=3, toughness=3)
    return profile


@pytest.fixture
def variant(escher, lists):
    """The question the house asks — which variant, or none — and the
    one pick on offer, carrying the variant's list to the gang and to
    every member."""
    slot_type = create_slot_type("Variant", allows_repeats=False)
    corrupted = create_pickable("Chaos Corrupted", slot_type)
    picklist = create_picklist("Variants", slot_type, members=[corrupted])
    slot = create_slot(
        "Variant",
        slot_type,
        picklist,
        label="Variant",
        min_picks=0,
        max_picks=1,
        assigned_to="gang",
    )
    modifier(
        "Escher: the gang is asked its Variant",
        targets_gang(),
        ef_adds(slot),
        carried_by=escher,
    )
    modifier(
        "Chaos Corrupted: the gang buys from the Chaos Corrupted list",
        targets_gang_alone(),
        ef_adds(lists["variant"]),
        carried_by=corrupted,
    )
    modifier(
        "Chaos Corrupted: its fighters buy from the Chaos Corrupted list",
        targets_every_model(),
        ef_adds(lists["variant"]),
        carried_by=corrupted,
    )
    return corrupted


@pytest.fixture
def gang(escher, variant, owner):
    return found_gang("The Ashen Choir", escher, owner=owner, budget=2000)


@pytest.fixture
def fighter(gang, sister):
    return hire(gang, sister, "Vex")


def take_the_variant(gang, pickable):
    """Answer the gang's open question, as the picker's click does."""
    card = build_gang_card(gang, with_statlines=False)
    computed = compute_gang(
        card, build_modifier_index([node.assignable for node in card.all_nodes()])
    )
    asked = next(
        choice for choice in computed.choices if choice.kind_label == "Variant"
    )
    return choose(asked.anchor.assignment, pickable, slot=asked.slot)


def names(accesses):
    return [access.name for access in accesses]


def set_position(collection, position):
    collection.position = position
    collection.save(update_fields=["position"])


class TestWhichListComesFirst:
    """The lists a card reaches are sorted by position, lowest first;
    a tie keeps the order the walk found them in."""

    def test_the_variant_list_is_reached_the_same_way_as_the_house_list(
        self, gang, fighter, variant, lists
    ):
        take_the_variant(gang, variant)

        held = collections_for(fighter)
        assert {access.name for access in held} == {
            "Escher Equipment List",
            "Chaos Corrupted Equipment List",
        }
        assert all(access.computed for access in held)

    def test_a_tie_keeps_the_order_the_walk_found_them_in(
        self, gang, sister, variant, lists
    ):
        """Two lists at 0 stay in the walk's order — the card's own
        built-in before the computed grant — even where a sort by name
        would swap them, so the tie-break is the walk and not the name."""
        last_by_name = create_collection("Zeta Equipment List")
        add_entry(last_by_name, create_wargear("Zeta blade", price=20))
        add_built_in(sister, last_by_name)
        fighter = hire(gang, sister, "Vex")
        assert last_by_name.position == lists["house"].position == 0

        assert names(collections_for(fighter)) == [
            "Zeta Equipment List",
            "Escher Equipment List",
        ]

    def test_the_lowest_position_comes_first_whatever_the_walk_found(
        self, gang, fighter, variant, lists
    ):
        take_the_variant(gang, variant)

        set_position(lists["variant"], VARIANT_POSITION)
        assert names(collections_for(fighter)) == [
            "Escher Equipment List",
            "Chaos Corrupted Equipment List",
        ]

        set_position(lists["variant"], 0)
        set_position(lists["house"], VARIANT_POSITION)
        assert names(collections_for(fighter)) == [
            "Chaos Corrupted Equipment List",
            "Escher Equipment List",
        ]

    def test_a_built_in_list_still_comes_before_a_grant_on_a_tie(
        self, gang, sister, variant, lists, owner
    ):
        """The walk's own order — the card's stored rows before the
        computed grants — is what a tie falls back to."""
        add_built_in(sister, lists["variant"])
        fighter = hire(gang, sister, "Vex")

        assert names(collections_for(fighter)) == [
            "Chaos Corrupted Equipment List",
            "Escher Equipment List",
        ]

        set_position(lists["variant"], VARIANT_POSITION)
        assert names(collections_for(fighter)) == [
            "Escher Equipment List",
            "Chaos Corrupted Equipment List",
        ]

    def test_the_gangs_own_lists_sort_the_same_way(self, gang, variant, lists):
        take_the_variant(gang, variant)
        set_position(lists["variant"], VARIANT_POSITION)

        assert names(gang_collections(gang)) == [
            "Escher Equipment List",
            "Chaos Corrupted Equipment List",
        ]

        set_position(lists["house"], VARIANT_POSITION + 1)
        assert names(gang_collections(gang)) == [
            "Chaos Corrupted Equipment List",
            "Escher Equipment List",
        ]


class TestTheScreensAgree:
    """Equip opens on the first list; the edit page's links and the
    gang's own equip screen put the lists in the same order."""

    def test_equip_opens_on_the_lowest_positioned_list(
        self, client, owner, gang, fighter, variant, lists
    ):
        take_the_variant(gang, variant)
        set_position(lists["variant"], VARIANT_POSITION)
        client.force_login(owner)

        response = client.get(reverse("n26-equip", args=[fighter.pk]))
        assert response.context["chosen"] == lists["house"]
        assert [str(c) for c in response.context["collections"]] == [
            "Escher Equipment List",
            "Chaos Corrupted Equipment List",
        ]

        set_position(lists["house"], VARIANT_POSITION + 1)
        response = client.get(reverse("n26-equip", args=[fighter.pk]))
        assert response.context["chosen"] == lists["variant"]

    def test_the_edit_page_links_the_lists_in_the_same_order(
        self, client, owner, gang, fighter, variant, lists
    ):
        take_the_variant(gang, variant)
        set_position(lists["variant"], VARIANT_POSITION)
        client.force_login(owner)

        equip = client.get(reverse("n26-equip", args=[fighter.pk]))
        edit = client.get(reverse("n26-edit-fighter", args=[fighter.pk]))

        # The equip strip ends with the library tab, which is no list.
        assert [item["label"] for item in edit.context["equip_lists"]] == [
            tab["label"] for tab in equip.context["collection_tabs"]
        ][:2]
        assert [item["label"] for item in edit.context["equip_lists"]] == [
            "Escher",
            "Chaos Corrupted",
        ]

    def test_the_gang_equip_screen_opens_on_the_gangs_own_list(
        self, client, owner, gang, variant, lists
    ):
        take_the_variant(gang, variant)
        set_position(lists["variant"], VARIANT_POSITION)
        client.force_login(owner)

        response = client.get(reverse("n26-equip-gang", args=[gang.pk]))
        current = [
            tab["label"]
            for tab in response.context["collection_tabs"]
            if tab["current"]
        ]
        assert current == ["Escher"]
        assert response.context["browsing"] == "Escher Equipment List"


class TestTheTradingPostIsLast:
    """The standard Trading Post is the last tab whether or not the
    fighter holds it, and whatever position it carries."""

    @pytest.fixture
    def post(self, default_pack):
        from n26.library.standard_content import STANDARD_CONTENT

        STANDARD_CONTENT["trading-post"].create()
        post = Collection.objects.get(name="Trading Post")
        add_entry(post, create_wargear("Filter plugs", price=10, trade_point_price=1))
        return post

    def test_a_post_nobody_holds_is_appended(self, post, lists):
        assert [str(c) for c in buyable_lists([lists["house"]])] == [
            "Escher Equipment List",
            "Trading Post",
        ]

    def test_a_held_post_is_moved_last_whatever_its_position(
        self, post, lists, gang, fighter, escher
    ):
        modifier(
            "Escher: its fighters may visit the Trading Post",
            targets_every_model(),
            ef_adds(post),
            carried_by=escher,
        )
        set_position(lists["house"], VARIANT_POSITION)
        assert post.position == 0

        held = [access.collection for access in collections_for(fighter)]
        assert [str(c) for c in held] == ["Trading Post", "Escher Equipment List"]
        assert [str(c) for c in buyable_lists(held)] == [
            "Escher Equipment List",
            "Trading Post",
        ]


class TestTheOrderingRepair:
    """The repair reads every collection and how each reaches a card,
    and gives 100 to the ones reached only through picks that are not
    gang archetypes."""

    @pytest.fixture
    def library(self, escher, sister, variant, lists):
        """Beside the house and the variant: an Outcast gang archetype's
        list, a list a variant and an archetype both grant, a list an
        author has already numbered, a menu nothing grants, a list the
        variant hands over inside a hidden bundle, and a list inside a
        bundle nothing hands over."""
        add_built_in(sister, lists["house"])
        bundle = create_hidden("Corruption bundle")
        modifier(
            "Chaos Corrupted: the gang is handed the Corruption bundle",
            targets_gang_alone(),
            ef_adds(bundle),
            carried_by=variant,
        )
        orphan = create_hidden("Orphan bundle")
        archetypes = create_slot_type("Gang Archetype", allows_repeats=False)
        beastmasters = create_pickable(
            "Beastmasters", archetypes, pk=GANG_ARCHETYPE_IDS[0]
        )
        assert str(beastmasters.pk) == GANG_ARCHETYPE_IDS[0]
        for key, name in [
            ("archetype", "Beastmasters Equipment List"),
            ("shared", "Outcast Wanderers Equipment List"),
            ("numbered", "Sup-Pets Equipment List"),
            ("menu", "Variants Menu"),
            ("bundled", "Corruption Bundle Equipment List"),
            ("orphaned", "Orphan Bundle Equipment List"),
        ]:
            lists[key] = create_collection(name)
        set_position(lists["numbered"], 7)
        modifier(
            "Corruption bundle: its fighters buy from the bundle's list",
            targets_every_model(),
            ef_adds(lists["bundled"]),
            carried_by=bundle,
        )
        modifier(
            "Orphan bundle: its fighters buy from the orphan's list",
            targets_every_model(),
            ef_adds(lists["orphaned"]),
            carried_by=orphan,
        )
        modifier(
            "Beastmasters: its fighters buy from the Beastmasters list",
            targets_every_model(),
            ef_adds(lists["archetype"]),
            carried_by=beastmasters,
        )
        modifier(
            "Beastmasters: its fighters buy from the Wanderers list",
            targets_every_model(),
            ef_adds(lists["shared"]),
            carried_by=beastmasters,
        )
        modifier(
            "Chaos Corrupted: its fighters buy from the Wanderers list",
            targets_every_model(),
            ef_adds(lists["shared"]),
            carried_by=variant,
        )
        modifier(
            "Chaos Corrupted: its fighters buy from the Sup-Pets list",
            targets_every_model(),
            ef_adds(lists["numbered"]),
            carried_by=variant,
        )
        return lists

    def test_it_reads_every_collection_and_how_each_is_reached(self, library):
        plan = find()

        by_name = {reading.name: reading for reading in plan.readings}
        assert set(by_name) == {
            "Escher Equipment List",
            "Chaos Corrupted Equipment List",
            "Beastmasters Equipment List",
            "Outcast Wanderers Equipment List",
            "Sup-Pets Equipment List",
            "Variants Menu",
            "Corruption Bundle Equipment List",
            "Orphan Bundle Equipment List",
        }
        # A carrier granting a list twice — to the gang and to every
        # member — is one route, said once.
        assert by_name["Escher Equipment List"].granted == (
            "built into profile Gang Sister; granted by gang type Escher"
        )
        assert by_name["Chaos Corrupted Equipment List"].granted == (
            "granted by pickable Chaos Corrupted (Variant)"
        )
        assert by_name["Beastmasters Equipment List"].granted == (
            "granted by pickable Beastmasters (Gang Archetype, an Outcast gang archetype)"
        )
        assert by_name["Variants Menu"].granted == (
            "not built into anything and granted by nothing"
        )

    def test_a_route_through_a_hidden_bundle_is_followed_back_to_the_pick(
        self, library
    ):
        """A pick that hands over a bundle whose modifier adds a list
        reaches that list as surely as one that adds it outright; the
        bundle is named on the way. A bundle nothing hands over stops
        the route, and the page says so."""
        by_name = {reading.name: reading for reading in find().readings}

        assert by_name["Corruption Bundle Equipment List"].granted == (
            "granted by pickable Chaos Corrupted (Variant) through hidden "
            "assignable Corruption bundle"
        )
        assert by_name["Corruption Bundle Equipment List"].variant_list
        assert by_name["Orphan Bundle Equipment List"].granted == (
            "granted by hidden assignable Orphan bundle, which nothing grants "
            "or builds in"
        )
        assert not by_name["Orphan Bundle Equipment List"].variant_list

    def test_only_lists_reached_by_variant_picks_alone_are_set(self, library):
        plan = find()

        assert [reading.name for reading in plan.to_set] == [
            "Chaos Corrupted Equipment List",
            "Corruption Bundle Equipment List",
        ]
        outcomes = {reading.name: reading.outcome for reading in plan.readings}
        assert outcomes == {
            "Chaos Corrupted Equipment List": f"set to {VARIANT_POSITION}",
            "Corruption Bundle Equipment List": f"set to {VARIANT_POSITION}",
            "Escher Equipment List": "left at 0",
            "Beastmasters Equipment List": "left at 0",
            "Outcast Wanderers Equipment List": "left at 0",
            "Sup-Pets Equipment List": "left at 7, already set",
            "Variants Menu": "left at 0",
            "Orphan Bundle Equipment List": "left at 0",
        }
        assert plan.ok
        assert not plan.nothing_here

    def test_applying_writes_the_numbers_and_a_second_reading_has_nothing_to_do(
        self, library
    ):
        report = apply(find())

        assert report == [
            f"Chaos Corrupted Equipment List (N26): set to {VARIANT_POSITION}",
            f"Corruption Bundle Equipment List (N26): set to {VARIANT_POSITION}",
            "Set 2 lists.",
        ]
        for key in ("variant", "bundled"):
            library[key].refresh_from_db()
            assert library[key].position == VARIANT_POSITION
        for key in ("house", "archetype", "shared", "menu", "orphaned"):
            library[key].refresh_from_db()
            assert library[key].position == 0
        library["numbered"].refresh_from_db()
        assert library["numbered"].position == 7

        again = find()
        assert again.nothing_here
        assert again.preview() == [
            "nothing to set: no list is at 0 and reached only by variant picks"
        ]
        assert apply(again) == again.preview()

    def test_it_refuses_when_a_list_was_renumbered_since_it_was_read(self, library):
        plan = find()
        set_position(library["variant"], 3)

        with pytest.raises(Refused, match="changed since they were read"):
            apply(plan)

        library["variant"].refresh_from_db()
        assert library["variant"].position == 3

    def test_the_reading_costs_the_same_however_many_collections(
        self, library, variant
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def measure():
            with CaptureQueriesContext(connection) as captured:
                assert find().readings
            return len(captured.captured_queries)

        few = measure()
        for index in range(6):
            extra = create_collection(f"Extra list {index}")
            modifier(
                f"Chaos Corrupted: its fighters buy from extra list {index}",
                targets_every_model(),
                ef_adds(extra),
                carried_by=variant,
            )
        assert len(find().to_set) == 8
        assert measure() == few
