"""A whole fake gang, end to end: found it, hire a leader, arm them.

This is the first full pass through the stack — content library, assignments,
hosts, roots, ledger — and it doubles as the shape the design docs describe
in prose. If this test reads badly, the design reads badly.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.models import Assignment, LedgerEntry, LedgerEvent, ProfileRole
from n26.core.reconcile import (
    assert_reconciled,
    ledger_for_gang,
    ledger_for_miniature,
    recomputed_rating,
)
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

pytestmark = [pytest.mark.django_db, pytest.mark.core]


@pytest.fixture
def player():
    return User.objects.create_user("player")


@pytest.fixture
def library(default_pack, person_type, gang_type, make_profile):
    """A tiny, entirely fake content library."""
    from n26.tests.sandbox.actions import create_wargear

    return {
        "hunt_champion": make_profile("Venator Hunt Champion", price=130),
        "road_captain": make_profile("Orlock Road Captain", price=95),
        "mesh_armour": create_wargear("Mesh Armour"),
        "shotgun": create_weapon(
            "Combat Shotgun",
            profiles=[("Salvo ammo", 0), ("Firestorm ammo", 30)],
        ),
    }


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Long Hunt", gang_type, owner=player, budget=1000)


def build_the_tree(gang, library):
    """The worked example from the design conversation."""
    yolanda = hire(gang, library["hunt_champion"], "Yolanda", paid=130)
    add_legacy_profile(yolanda, library["road_captain"], paid=0)
    shotgun = give_weapon(yolanda, library["shotgun"], paid=60)
    buy_weapon_profile(shotgun, library["shotgun"].profiles.get(price=30))
    assign(library["mesh_armour"], miniature=yolanda, paid=15)
    return yolanda, shotgun


class TestBuildingTheGang:
    def test_hiring_makes_the_membership_an_assignment(self, gang, library):
        yolanda = hire(gang, library["hunt_champion"], "Yolanda", paid=130)

        assert yolanda.membership.gang == gang
        assert yolanda.membership.assignable == library["hunt_champion"]
        assert yolanda.gang == gang
        assert yolanda.membership.profile_role.role == ProfileRole.Role.PRIMARY

    def test_the_hire_is_ledgered_against_the_profile(self, gang, library):
        yolanda = hire(gang, library["hunt_champion"], "Yolanda", paid=130)

        entry = yolanda.membership.ledger_entry
        assert entry.assignable == library["hunt_champion"]
        assert (entry.paid, entry.rating_contribution) == (130, 130)

    def test_a_weapon_brings_its_free_profile_with_it(self, gang, library):
        yolanda = hire(gang, library["hunt_champion"], "Yolanda", paid=130)
        shotgun = give_weapon(yolanda, library["shotgun"], paid=60)

        free = shotgun.children.get()
        assert str(free.assignable) == "Salvo ammo (Combat Shotgun)"
        assert free.ledger_entry.paid == 0
        assert free.caused_by == shotgun

    def test_a_paid_profile_is_its_own_purchase(self, gang, library):
        yolanda = hire(gang, library["hunt_champion"], "Yolanda", paid=130)
        shotgun = give_weapon(yolanda, library["shotgun"], paid=60)
        firestorm = buy_weapon_profile(
            shotgun, library["shotgun"].profiles.get(price=30)
        )

        assert firestorm.parent == shotgun
        assert firestorm.ledger_entry.paid == 30
        assert firestorm.caused_by is None  # the player chose to buy it

    def test_the_whole_tree(self, gang, library):
        yolanda, shotgun = build_the_tree(gang, library)

        # Excluding the gang's founding, which is not something a player bought.
        assert Assignment.objects.filter(gang_type__isnull=True).count() == 6
        assert sorted(str(entry.assignable) for entry in ledger_for_gang(gang)) == [
            "Combat Shotgun",
            "Escher",  # the gang's founding, ledgered free
            "Firestorm ammo (Combat Shotgun)",
            "Mesh Armour",
            "Orlock Road Captain",
            "Salvo ammo (Combat Shotgun)",
            "Venator Hunt Champion",
        ]


class TestRoots:
    def test_every_assignment_knows_its_gang_and_model(self, gang, library):
        yolanda, _ = build_the_tree(gang, library)

        for assignment in Assignment.objects.all():
            assert assignment.gang_root == gang

        # The membership is hosted on the gang, but it is *about* Yolanda —
        # so the hire cost counts towards her rating.
        assert yolanda.membership.gang == gang
        assert yolanda.membership.miniature_root == yolanda
        assert Assignment.objects.filter(miniature_root=yolanda).count() == 6

    def test_roots_reach_through_nesting(self, gang, library):
        yolanda, shotgun = build_the_tree(gang, library)
        firestorm = shotgun.children.get(ledger_entry__paid=30)

        assert firestorm.parent == shotgun
        assert firestorm.miniature_root == yolanda
        assert firestorm.gang_root == gang

    def test_the_gang_ledger_is_one_query(
        self, gang, library, django_assert_num_queries
    ):
        build_the_tree(gang, library)
        with django_assert_num_queries(1):
            # Six purchases plus the gang's founding.
            assert len(list(ledger_for_gang(gang))) == 7

    def test_the_model_ledger_is_one_query(
        self, gang, library, django_assert_num_queries
    ):
        yolanda, _ = build_the_tree(gang, library)
        with django_assert_num_queries(1):
            assert len(list(ledger_for_miniature(yolanda))) == 6


class TestHosts:
    def test_an_assignment_must_have_a_host(self, library):
        from django.db import IntegrityError, transaction

        with pytest.raises(IntegrityError), transaction.atomic():
            Assignment.objects.create(assignable=library["mesh_armour"])

    def test_an_assignment_cannot_have_two_hosts(self, gang, library):
        from django.db import IntegrityError, transaction

        yolanda = hire(gang, library["hunt_champion"], "Yolanda", paid=130)
        with pytest.raises(IntegrityError), transaction.atomic():
            Assignment.objects.create(
                assignable=library["mesh_armour"], gang=gang, miniature=yolanda
            )

    def test_clean_reports_a_missing_host_readably(self, library):
        from django.core.exceptions import ValidationError

        with pytest.raises(ValidationError, match="exactly one host"):
            Assignment(assignable=library["mesh_armour"]).clean()


class TestRating:
    def test_rating_is_live_without_anyone_asking(self, gang, library):
        """Operations repin at their boundary — no manual recompute needed."""
        yolanda, _ = build_the_tree(gang, library)
        gang.refresh_from_db()
        yolanda.refresh_from_db()

        assert gang.rating == 130 + 60 + 30 + 15
        assert yolanda.rating == 235  # the hire counts towards the model
        assert recomputed_rating(gang) == 235
        assert_reconciled(gang)

    def test_credits_are_live_too(self, gang, library):
        build_the_tree(gang, library)
        gang.refresh_from_db()

        assert gang.credits == 1000 - 235
        assert gang.wealth == 235 + 765

    def test_a_wrong_pin_is_caught(self, gang, library):
        from n26.core.reconcile import Discrepancy

        build_the_tree(gang, library)
        gang.refresh_from_db()
        gang.rating = 999
        gang.save()

        with pytest.raises(Discrepancy, match="rating pinned 999"):
            assert_reconciled(gang)

    def test_wrong_credits_are_caught(self, gang, library):
        from n26.core.reconcile import Discrepancy

        build_the_tree(gang, library)
        gang.refresh_from_db()
        gang.credits = 5
        gang.save()

        with pytest.raises(Discrepancy, match="credits pinned 5"):
            assert_reconciled(gang)

    def test_a_ledger_entry_disagreeing_with_its_events_is_caught(self, gang, library):
        from n26.core.reconcile import Discrepancy

        build_the_tree(gang, library)
        entry = LedgerEntry.objects.get(assignment__wargear=library["mesh_armour"])
        entry.paid = 999
        entry.save()

        with pytest.raises(Discrepancy, match="events fold to"):
            assert_reconciled(gang)

    def test_reconcile_repairs_what_it_reports(self, gang, library):
        from n26.core.reconcile import repin_everything

        build_the_tree(gang, library)
        gang.refresh_from_db()
        gang.rating, gang.credits = 999, 5
        gang.save()

        repin_everything(gang)
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestRemoval:
    """Removal archives — the ledger is append-only, so history survives."""

    def test_removing_a_weapon_takes_its_profiles_with_it(self, gang, library):
        yolanda, shotgun = build_the_tree(gang, library)
        remove(shotgun)

        live = Assignment.objects.filter(archived=False)
        assert sorted(str(a.assignable) for a in live) == [
            "Escher",  # the gang's founding
            "Mesh Armour",
            "Orlock Road Captain",
            "Venator Hunt Champion",
        ]

    def test_the_ledger_keeps_what_was_removed(self, gang, library):
        yolanda, shotgun = build_the_tree(gang, library)
        remove(shotgun, note="sold to a rival")

        # Nothing is ever deleted. Seven: six purchases and the founding.
        assert LedgerEntry.objects.count() == 7
        # Excluding the gang's founding, which is not something a player bought.
        assert Assignment.objects.filter(gang_type__isnull=True).count() == 6
        removed = LedgerEvent.objects.filter(kind=LedgerEvent.Kind.REMOVED)
        assert removed.count() == 3
        assert removed.first().note == "sold to a rival"

    def test_the_entry_still_says_what_it_was_worth(self, gang, library):
        yolanda, shotgun = build_the_tree(gang, library)
        remove(shotgun)

        shotgun.ledger_entry.refresh_from_db()
        assert shotgun.ledger_entry.rating_contribution == 60

    def test_removing_drops_the_rating_but_not_the_spend(self, gang, library):
        yolanda, shotgun = build_the_tree(gang, library)
        remove(shotgun)
        gang.refresh_from_db()
        yolanda.refresh_from_db()

        # The shotgun and its 30cr ammo stop counting.
        assert gang.rating == 130 + 15
        assert yolanda.rating == 145
        # But removing is not a refund — the money stays spent.
        assert gang.credits == 1000 - 235
        assert_reconciled(gang)

    def test_removing_the_membership_archives_it(self, gang, library):
        yolanda, _ = build_the_tree(gang, library)
        remove(yolanda.membership)
        yolanda.refresh_from_db()

        assert yolanda.membership.archived is True
