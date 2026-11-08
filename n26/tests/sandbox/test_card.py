"""Verify the in-memory model card tree, ratings, legacy profiles and removal. Fetch
queries must stay constant as existing content kinds grow; traversing hydrated nodes and
reading ratings must issue no extra queries.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.card import build_card
from n26.tests.sandbox.actions import (
    add_legacy_profile,
    assign,
    buy_weapon_profile,
    create_weapon,
    found_gang,
    give_weapon,
    hire,
    remove,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def player():
    return User.objects.create_user("player")


@pytest.fixture
def library(default_pack, person_type, gang_type, make_profile):
    from n26.tests.sandbox.actions import create_wargear

    return {
        "hunt_champion": make_profile("Venator Hunt Champion", price=130),
        "road_captain": make_profile("Orlock Road Captain", price=95),
        "mesh_armour": create_wargear("Mesh Armour"),
        "shotgun": create_weapon(
            "Combat Shotgun", profiles=[("Salvo ammo", 0), ("Firestorm ammo", 30)]
        ),
        "knife": create_weapon("Stiletto Knife", profiles=[("Blade", 0)]),
    }


@pytest.fixture
def yolanda(gang_type, player, library):
    gang = found_gang("The Long Hunt", gang_type, owner=player, budget=1000)
    mini = hire(gang, library["hunt_champion"], "Yolanda", paid=130)
    add_legacy_profile(mini, library["road_captain"])
    shotgun = give_weapon(mini, library["shotgun"], paid=60)
    buy_weapon_profile(shotgun, library["shotgun"].profiles.get(price=30))
    give_weapon(mini, library["knife"], paid=20)
    assign(library["mesh_armour"], miniature=mini, paid=15)
    return mini


class TestBuildingACard:
    def test_it_costs_two_row_queries_and_a_fixed_hydration(
        self, yolanda, django_assert_num_queries
    ):
        """Fetch model and gang assignments, hydrate only relations present on the card,
        and load campaign holdings. Pin this fixture's query total separately from the
        growth test below.
        """
        with django_assert_num_queries(12):
            card = build_card(yolanda)
            # Walking hydrated nodes and reading ratings must issue no extra query.
            assert sum(node.rating for node in card.all_nodes()) == 255

    def test_the_tree_has_the_right_shape(self, yolanda):
        card = build_card(yolanda)

        # Broadcast gang rows supply effects without becoming model possessions.
        assert sorted(node.name for node in card.roots if not node.broadcast) == [
            "Combat Shotgun",
            "Mesh Armour",
            "Orlock Road Captain",
            "Stiletto Knife",
            "Venator Hunt Champion",
        ]
        assert [node.name for node in card.roots if node.broadcast] == ["Escher"]
        shotgun = card.find("Combat Shotgun")
        assert sorted(child.name for child in shotgun.children) == [
            "Firestorm ammo (Combat Shotgun)",
            "Salvo ammo (Combat Shotgun)",
        ]

    def test_a_line_knows_what_it_cost(self, yolanda):
        card = build_card(yolanda)

        assert card.find("Combat Shotgun").rating == 60
        assert card.find("Salvo ammo (Combat Shotgun)").rating == 0
        assert card.find("Firestorm ammo (Combat Shotgun)").rating == 30

    def test_a_weapon_can_total_itself_with_its_extras(self, yolanda):
        card = build_card(yolanda)

        shotgun = card.find("Combat Shotgun")
        assert shotgun.rating == 60
        assert shotgun.rating_with_extras == 90  # Include the paid ammunition rating.
        assert card.find("Stiletto Knife").rating_with_extras == 20

    def test_the_card_total_matches_the_pinned_rating(self, yolanda):
        yolanda.refresh_from_db()
        assert build_card(yolanda).rating == yolanda.rating == 255

    def test_reading_ratings_never_queries(self, yolanda, django_assert_num_queries):
        card = build_card(yolanda)
        with django_assert_num_queries(0):
            for node in card.all_nodes():
                assert isinstance(node.rating, int)
                assert isinstance(node.rating_with_extras, int)
                assert node.name
                assert isinstance(node.children, list)


class TestProfilesOnTheCard:
    def test_the_card_is_drawn_from_the_primary_profile(self, yolanda):
        from n26.core.render import build_model_card

        assert build_model_card(yolanda).profile_type == "Fighter"

    def test_a_legacy_profile_is_not_equipment(self, yolanda, library):
        """A legacy profile contributes to the card without appearing in its equipment
        list.
        """
        from n26.core.render import build_model_card

        names = [line.name for line in build_model_card(yolanda).equipment]
        assert names == ["Mesh Armour"]
        assert library["road_captain"].name not in names


class TestCardsFollowRemoval:
    def test_a_removed_weapon_leaves_the_card(self, yolanda, library):
        card = build_card(yolanda)
        remove(card.find("Combat Shotgun").assignment)

        after = build_card(yolanda)
        assert after.find("Combat Shotgun") is None
        assert after.find("Firestorm ammo (Combat Shotgun)") is None
        assert after.find("Stiletto Knife") is not None

    def test_the_total_follows(self, yolanda):
        remove(build_card(yolanda).find("Combat Shotgun").assignment)
        yolanda.refresh_from_db()

        assert build_card(yolanda).rating == 255 - 90 == yolanda.rating


class TestScaling:
    def test_a_big_card_costs_what_a_small_one_does(self, gang_type, player, library):
        """Grow duplicate content while holding relation kinds constant. Hydration is per
        kind, so adding a new kind would change more than roster size.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        gang = found_gang("The Long Hunt", gang_type, owner=player, budget=5000)
        mini = hire(gang, library["hunt_champion"], "Yolanda", paid=130)

        def arm():
            shotgun = give_weapon(mini, library["shotgun"], paid=60)
            buy_weapon_profile(shotgun, library["shotgun"].profiles.get(price=30))

        def measure():
            with CaptureQueriesContext(connection) as captured:
                card = build_card(mini)
                assert list(card.all_nodes())
            return len(captured.captured_queries)

        arm()
        few = measure()
        for _ in range(9):
            arm()
        many = measure()
        assert few == many
        # Count 31 model nodes and the gang founding node.
        assert len(list(build_card(mini).all_nodes())) == 32
