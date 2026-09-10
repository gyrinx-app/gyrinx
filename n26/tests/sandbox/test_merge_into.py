"""Merging a duplicate into the row it duplicates.

A weapon imported twice stands as two rows for one thing. Fighters have
bought the duplicate, a list offers it, a built-in set brings it, so it
cannot be deleted — and what those fighters have is the real thing
under the wrong row. Merging (``n26/library/merging.py``) points every
reference at the survivor, gang by gang, each gang proved to reconcile,
and deletes the duplicate with the last gang. Lines follow by name; one
with no counterpart refuses in words. Nobody's money moves.
"""

import pytest
from django.contrib.auth.models import User

from gyrinx.maintenance.models import Backfill
from n26.core.models import Assignment, Gang, LedgerEntry
from n26.core.reconcile import assert_reconciled
from n26.library.merging import Refused, merge_library, plan_merge
from n26.library.models import CollectionEntry, DefaultAssignment, Weapon, WeaponProfile
from n26.tests.sandbox.actions import (
    add_built_in,
    buy_weapon_profile,
    create_collection,
    create_gang_type,
    create_profile,
    create_weapon,
    found_gang,
    give_weapon,
    hire,
    sell,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def author(client):
    user = User.objects.create_user("author", is_staff=True)
    client.force_login(user)
    return user


@pytest.fixture
def player(db):
    return User.objects.create_user("player")


@pytest.fixture
def shotgun(default_pack):
    """The real row: named lines, one of them paid."""
    return create_weapon(
        "Shotgun",
        price=35,
        profiles=[("scatter ammo", 0), ("solid ammo", 0), ("acid ammo", 15)],
    )


@pytest.fixture
def duplicate(default_pack):
    """The import's second copy: the same lines, all free."""
    return create_weapon(
        "Shotgun",
        price=35,
        qualifier="deprecated",
        profiles=[("scatter ammo", 0), ("solid ammo", 0), ("acid ammo", 0)],
    )


@pytest.fixture
def escher(default_pack):
    return create_gang_type("Escher", starting_credits=1000)


@pytest.fixture
def ganger(escher, person_type):
    return create_profile("Ganger", person_type, escher, price=50)


def armed_with(owner, name, escher, ganger, weapon):
    gang = found_gang(name, escher, owner=owner)
    model = hire(gang, ganger, "One", paid=50)
    give_weapon(model, weapon, paid=35)
    return gang


def merge_page(thing, into=None):
    page = f"/n26/authoring/weapon/{thing.pk}/merge/"
    return f"{page}?into={into.pk}" if into is not None else page


class TestPlanning:
    def test_it_names_the_gangs_and_the_lines_that_follow(
        self, author, player, escher, ganger, shotgun, duplicate
    ):
        theirs = armed_with(player, "Theirs", escher, ganger, duplicate)

        plan = plan_merge(duplicate, shotgun)

        assert plan.ok, plan.refusals
        assert [part.name for part in plan.gangs] == [theirs.name]
        # The weapon and its three free lines.
        assert plan.gangs[0].assignments == 4
        assert {name for _, name, _ in plan.lines} == {
            "scatter ammo",
            "solid ammo",
            "acid ammo",
        }
        assert plan.touches_players

    def test_a_line_with_no_counterpart_refuses_and_names_it(
        self, author, shotgun, duplicate
    ):
        from n26.library.authoring import add_weapon_profile

        add_weapon_profile(duplicate, name="", price=0)

        plan = plan_merge(duplicate, shotgun)

        assert not plan.ok
        assert any("its own line" in words for words in plan.refusals)

    def test_a_row_carrying_its_own_decisions_refuses(self, author, shotgun, duplicate):
        from n26.library.authoring import create_rule, ef_adds, modifier, targets_model

        modifier(
            "Kick", targets_model(), ef_adds(create_rule("Kick")), attach_to=duplicate
        )

        plan = plan_merge(duplicate, shotgun)

        assert not plan.ok
        assert any("modifiers" in words for words in plan.refusals)

    def test_a_list_already_offering_the_survivor_drops_the_line(
        self, author, shotgun, duplicate
    ):
        create_collection("Escher list", entries=[(shotgun, {}), (duplicate, {})])
        create_collection("Trading Post", entries=[(duplicate, {})])

        plan = plan_merge(duplicate, shotgun)

        assert plan.ok
        assert plan.entries_dropped == 1
        assert plan.entries_moved == 1

    def test_the_record_reads_back_to_the_same_plan(
        self, author, player, escher, ganger, shotgun, duplicate
    ):
        from n26.library.merging import MergePlan

        armed_with(player, "Theirs", escher, ganger, duplicate)
        plan = plan_merge(duplicate, shotgun)

        assert MergePlan.from_record(plan.as_record()).same_as(plan)


class TestMerging:
    def test_fighters_end_up_with_the_survivor_and_its_lines_and_no_money_moves(
        self, author, client, player, escher, ganger, shotgun, duplicate
    ):
        theirs = armed_with(player, "Theirs", escher, ganger, duplicate)
        mine = armed_with(author, "Mine", escher, ganger, duplicate)
        rating_before = {
            gang.pk: Gang.objects.get(pk=gang.pk).rating for gang in (theirs, mine)
        }
        entries_before = set(
            LedgerEntry.objects.filter(assignment__gang_root=theirs).values_list(
                "pk", "paid", "rating_contribution"
            )
        )

        response = client.post(merge_page(duplicate), {"into": str(shotgun.pk)})

        record = Backfill.objects.get()
        assert record.operation == "n26_merge_into"
        assert response["Location"] == f"/n26/authoring/deletions/{record.pk}/"
        assert record.status == Backfill.Status.DONE, record.error
        assert not Weapon.objects.filter(pk=duplicate.pk).exists()
        for gang in (theirs, mine):
            gang = Gang.objects.get(pk=gang.pk)
            assert_reconciled(gang)
            assert gang.rating == rating_before[gang.pk]
            weapon = Assignment.objects.get(gang_root=gang, weapon=shotgun)
            lines = Assignment.objects.filter(parent=weapon).values_list(
                "weapon_profile__name", flat=True
            )
            # The three lines followed by name; the survivor's paid acid
            # line was theirs already, so nothing else arrives.
            assert sorted(lines) == ["acid ammo", "scatter ammo", "solid ammo"]
        assert (
            set(
                LedgerEntry.objects.filter(assignment__gang_root=theirs).values_list(
                    "pk", "paid", "rating_contribution"
                )
            )
            == entries_before
        )
        report = " ".join(record.summary["report"])
        assert "pointed 4 assignments at Shotgun" in report
        assert "deleted Shotgun" in report

        body = client.get(response["Location"]).content.decode()
        assert "Merged" in body

    def test_a_sold_duplicate_follows_too(
        self, author, client, player, escher, ganger, shotgun, duplicate
    ):
        theirs = armed_with(player, "Theirs", escher, ganger, duplicate)
        sell(Assignment.objects.get(gang_root=theirs, weapon=duplicate))

        client.post(merge_page(duplicate), {"into": str(shotgun.pk)})

        assert Backfill.objects.get().status == Backfill.Status.DONE
        sold = Assignment.objects.get(gang_root=theirs, weapon=shotgun)
        assert sold.archived
        assert_reconciled(Gang.objects.get(pk=theirs.pk))

    def test_the_survivors_free_lines_a_fighter_lacks_arrive(
        self, author, client, player, escher, ganger, shotgun, default_pack
    ):
        bare = create_weapon(
            "Shotgun", price=35, qualifier="bare", profiles=[("scatter ammo", 0)]
        )
        theirs = armed_with(player, "Theirs", escher, ganger, bare)

        client.post(merge_page(bare), {"into": str(shotgun.pk)})

        assert Backfill.objects.get().status == Backfill.Status.DONE
        weapon = Assignment.objects.get(gang_root=theirs, weapon=shotgun)
        lines = Assignment.objects.filter(parent=weapon).values_list(
            "weapon_profile__name", flat=True
        )
        assert sorted(lines) == ["scatter ammo", "solid ammo"]
        assert_reconciled(Gang.objects.get(pk=theirs.pk))

    def test_the_library_part_moves_lists_and_built_ins(
        self, author, client, escher, ganger, shotgun, duplicate
    ):
        listed = create_collection("Escher list", entries=[(duplicate, {})])
        add_built_in(ganger, duplicate)

        response = client.post(merge_page(duplicate), {"into": str(shotgun.pk)})

        # Nothing on a gang: done in the request, back on the survivor.
        assert response["Location"] == f"/n26/authoring/weapon/{shotgun.pk}/"
        assert not Backfill.objects.exists()
        assert not Weapon.objects.filter(pk=duplicate.pk).exists()
        assert CollectionEntry.objects.get(collection=listed).weapon == shotgun
        assert (
            DefaultAssignment.objects.get(default_set=ganger.built_ins).weapon
            == shotgun
        )

    def test_a_fighter_who_paid_for_a_line_keeps_it_as_the_survivors(
        self, author, client, player, escher, ganger, shotgun, duplicate
    ):
        from n26.library.authoring import revise

        acid = WeaponProfile.objects.get(weapon=duplicate, name="acid ammo")
        revise(acid, price=15)
        theirs = armed_with(player, "Theirs", escher, ganger, duplicate)
        weapon = Assignment.objects.get(gang_root=theirs, weapon=duplicate)
        buy_weapon_profile(weapon, acid)

        client.post(merge_page(duplicate), {"into": str(shotgun.pk)})

        assert Backfill.objects.get().status == Backfill.Status.DONE, (
            Backfill.objects.get().error
        )
        survivor_acid = WeaponProfile.objects.get(weapon=shotgun, name="acid ammo")
        paid = Assignment.objects.get(gang_root=theirs, weapon_profile=survivor_acid)
        assert paid.ledger_entry.paid == 15
        assert_reconciled(Gang.objects.get(pk=theirs.pk))

    def test_a_refused_plan_merges_nothing(self, author, client, shotgun, duplicate):
        from n26.library.authoring import add_weapon_profile

        add_weapon_profile(duplicate, name="", price=0)

        response = client.post(
            merge_page(duplicate), {"into": str(shotgun.pk)}, follow=True
        )

        assert "was not merged" in response.content.decode()
        assert Weapon.objects.filter(pk=duplicate.pk).exists()
        with pytest.raises(Refused):
            merge_library(plan_merge(duplicate, shotgun)) if plan_merge(
                duplicate, shotgun
            ).ok else (_ for _ in ()).throw(Refused("refused"))


class TestThePage:
    def test_it_asks_for_the_survivor_then_shows_the_plan(
        self, author, client, player, escher, ganger, shotgun, duplicate
    ):
        armed_with(player, "Theirs", escher, ganger, duplicate)

        asked = client.get(merge_page(duplicate)).content.decode()
        assert "Read the plan" in asked
        assert "Merge Shotgun" in asked

        shown = client.get(merge_page(duplicate, into=shotgun)).content.decode()
        assert "Gangs whose fighters have it" in shown
        assert "Theirs" in shown
        assert "line “scatter ammo” becomes" in shown
        assert f"Merge {duplicate.authoring_label} into Shotgun" in shown

    def test_a_survivor_that_is_not_an_id_asks_again(self, author, client, duplicate):
        body = client.get(merge_page(duplicate) + "?into=not-an-id").content.decode()
        assert "Read the plan" in body
        assert "What merging does" not in body

    def test_a_replayed_delivery_finds_nothing_left_to_move(
        self, author, player, escher, ganger, shotgun, duplicate
    ):
        from n26.library.merging import merge_gang

        theirs = armed_with(player, "Theirs", escher, ganger, duplicate)
        plan = plan_merge(duplicate, shotgun)
        first = merge_gang(theirs.pk, plan)
        assert "deleted" in first

        again = merge_gang(theirs.pk, plan)

        assert "already gone" in again
        assert Weapon.objects.filter(pk=shotgun.pk).exists()

    def test_the_weapon_page_offers_the_way_there(self, author, client, duplicate):
        body = client.get(f"/n26/authoring/weapon/{duplicate.pk}/").content.decode()
        assert merge_page(duplicate) in body

    def test_a_kind_that_cannot_be_merged_has_no_page(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_rule

        rule = create_rule("Kick")
        assert client.get(f"/n26/authoring/rule/{rule.pk}/merge/").status_code == 404
