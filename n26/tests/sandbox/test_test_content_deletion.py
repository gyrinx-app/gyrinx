"""Deleting content, and the test gangs holding it.

An author stages a gang type, founds a gang on it to check the fighters
and their kit, and archives the gang when done. Every row that gang
touched is still protected by it, so nothing the author wrote can be
deleted — until the gang itself goes. The deletion planner
(``n26/library/deletion.py``) names that gang as a test gang and takes it
with the content; a player's gang, or a campaign a player is in, refuses
in words instead.
"""

import datetime

import pytest
from django.contrib.auth.models import User
from django.db import connection

from n26.core.deletion import destroy_gang
from n26.core.models import Assignment, CampaignEvent, Gang, LedgerEvent, Miniature
from n26.core.operations import operation
from n26.library.deletion import DeletionPlan, Refused, apply, plan_deletion
from n26.library.models import GangType, Modifier, Profile, Weapon
from n26.tests.sandbox.actions import (
    create_gang_type,
    create_profile,
    create_rule,
    create_weapon,
    ef_adds,
    found_campaign,
    found_gang,
    give_weapon,
    hire,
    join_campaign,
    modifier,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def author(db):
    return User.objects.create_user("author", is_staff=True)


@pytest.fixture
def player(db):
    return User.objects.create_user("player")


@pytest.fixture
def test_type(default_pack):
    return create_gang_type("Test Gang", starting_credits=1000, staged=True)


@pytest.fixture
def test_fighter(test_type, person_type):
    return create_profile("Tester", person_type, test_type, price=50, staged=True)


@pytest.fixture
def test_weapon(default_pack):
    return create_weapon("Test lasgun", price=15, staged=True)


def check_with(owner, test_type, test_fighter, test_weapon, name="Checking"):
    """Found a gang on the type, hire, equip, and archive — what an author
    does to look at new content, and what a player's Delete gang leaves."""
    gang = found_gang(name, test_type, owner=owner)
    model = hire(gang, test_fighter, "One", paid=50)
    give_weapon(model, test_weapon, paid=15)
    gang.archive()
    return gang


class TestNamingTheTestGangs:
    """A plan says what goes and who holds it, and never writes."""

    def test_an_unused_row_has_no_holders(self, test_type):
        plan = plan_deletion([test_type])
        assert plan.ok
        assert not plan.touches_players
        assert ("library.gangtype", str(test_type.pk)) in plan.targets

    def test_an_authors_archived_gang_is_a_test_gang(
        self, author, test_type, test_fighter, test_weapon
    ):
        gang = check_with(author, test_type, test_fighter, test_weapon)

        plan = plan_deletion([test_type, test_fighter])

        assert plan.ok
        assert [holder.name for holder in plan.test_gangs] == [gang.name]
        assert plan.test_gangs[0].archived
        assert plan.test_gangs[0].owner == "author"
        assert any("Test Gang" in held for held in plan.test_gangs[0].holds)
        assert Gang.objects.filter(pk=gang.pk).exists()

    def test_a_players_gang_refuses_in_words(
        self, player, test_type, test_fighter, test_weapon
    ):
        gang = check_with(player, test_type, test_fighter, test_weapon, "Theirs")

        plan = plan_deletion([test_type, test_fighter])

        assert not plan.ok
        assert not plan.test_gangs
        assert any(gang.name in words and "player" in words for words in plan.refusals)
        assert any("not staff" in words for words in plan.refusals)

    def test_a_purchase_through_a_list_line_does_not_hold_the_line(
        self, player, test_type, test_fighter, test_weapon
    ):
        """A purchase names the line it was bought through, and the
        column is emptied when the line goes: the payment still
        happened. So a player's purchase does not hold a staged line."""
        from n26.library.authoring import create_collection
        from n26.library.models import CollectionEntry
        from n26.tests.sandbox.actions import buy

        listing = create_collection("Test list", entries=[(test_weapon, {})])
        entry = CollectionEntry.objects.get(collection=listing)
        entry.staged = True
        entry.save()
        gang = found_gang("Theirs", test_type, owner=player)
        model = hire(gang, test_fighter, "One", paid=50)
        buy(model, thing=test_weapon, entry=entry, paid=15)

        plan = plan_deletion([entry])

        assert plan.ok
        assert not plan.gangs
        apply(plan)
        assert not CollectionEntry.objects.filter(pk=entry.pk).exists()
        assert Assignment.objects.filter(
            gang_root=gang, weapon=test_weapon, ledger_entry__bought_from=None
        ).exists()

    def test_a_gang_type_refuses_while_its_fighters_stand(
        self, test_type, test_fighter
    ):
        plan = plan_deletion([test_type])

        assert not plan.ok
        assert any("Tester" in words for words in plan.refusals)
        assert any("everything staged" in words for words in plan.refusals)

    def test_a_weapon_a_test_gang_holds_names_the_gang(
        self, author, test_type, test_fighter, test_weapon
    ):
        gang = check_with(author, test_type, test_fighter, test_weapon)

        plan = plan_deletion([test_weapon])

        assert plan.ok
        assert [holder.name for holder in plan.test_gangs] == [gang.name]
        # The weapon's own firing line goes with it, and is promised.
        assert "firing lines" in plan.counts() or "weapons" in plan.counts()

    def test_a_modifier_naming_the_row_goes_when_nothing_standing_carries_it(
        self, author, test_type, test_fighter, test_weapon
    ):
        rule = create_rule("Test rule", staged=True)
        modifier(
            "Test rule brings a lasgun",
            targets_model(),
            ef_adds(test_weapon),
            carried_by=rule,
        )

        # The rule alone: its modifier is not the rule's to take, and
        # stays as a reusable.
        alone = plan_deletion([rule])
        assert alone.ok
        assert not alone.modifier_ids

        # The rule and the weapon together: the modifier names the weapon
        # and its only carrier is going, so it goes too, parts first.
        both = plan_deletion([rule, test_weapon])
        assert both.ok
        assert "modifiers" in both.counts()
        assert both.modifier_ids

    def test_a_modifier_something_else_carries_refuses(
        self, author, test_type, test_fighter, test_weapon
    ):
        rule = create_rule("Test rule", staged=True)
        keeper = create_rule("Kept rule")
        shared = modifier(
            "Brings a lasgun", targets_model(), ef_adds(test_weapon), carried_by=rule
        )
        keeper.modifiers.add(shared)

        plan = plan_deletion([test_weapon])

        assert not plan.ok
        assert any("Kept rule" in words for words in plan.refusals)

    def test_a_staff_gang_in_a_campaign_with_a_player_is_not_a_test_gang(
        self, author, player, test_type, test_fighter, test_weapon, campaign_type
    ):
        mine = check_with(author, test_type, test_fighter, test_weapon, "Mine")
        theirs = found_gang("Theirs", create_gang_type("Escher"), owner=player)
        campaign = found_campaign("Dust Falls", campaign_type, owner=author)
        join_campaign(mine, campaign)
        join_campaign(theirs, campaign)

        plan = plan_deletion([test_type, test_fighter])

        assert not plan.ok
        assert any("Theirs" in words for words in plan.refusals)

    def test_a_staff_gang_in_an_all_staff_campaign_is_a_test_gang(
        self, author, test_type, test_fighter, test_weapon, campaign_type
    ):
        mine = check_with(author, test_type, test_fighter, test_weapon, "Mine")
        campaign = found_campaign("Rehearsal", campaign_type, owner=author)
        join_campaign(mine, campaign)

        plan = plan_deletion([test_type, test_fighter])

        assert plan.ok
        assert [holder.name for holder in plan.test_gangs] == ["Mine"]
        # The campaign stands: nothing being deleted is the campaign's.
        assert not plan.campaigns

    def test_a_staff_gang_that_fought_a_player_is_not_a_test_gang(
        self, author, player, test_type, test_fighter, test_weapon, campaign_type
    ):
        from n26.core.campaigns import campaign_operation

        mine = check_with(author, test_type, test_fighter, test_weapon, "Mine")
        theirs = found_gang("Theirs", create_gang_type("Escher"), owner=player)
        campaign = found_campaign("Dust Falls", campaign_type, owner=author)
        with campaign_operation(campaign, actor=author) as act:
            act.record_battle(datetime.date(2026, 9, 9), gangs=[mine, theirs])

        plan = plan_deletion([test_type, test_fighter])

        assert not plan.ok
        assert any("fought" in words for words in plan.refusals)

    def test_a_test_campaign_goes_with_its_own_type_and_pack(
        self, author, default_pack, test_type, test_fighter, test_weapon
    ):
        from n26.library.authoring import create_campaign_type
        from n26.library.models import CampaignType, ContentPack

        staged_type = create_campaign_type("Test campaign type", staged=True)
        mine = check_with(author, test_type, test_fighter, test_weapon, "Mine")
        campaign = found_campaign("Rehearsal", staged_type, owner=author)
        join_campaign(mine, campaign)

        plan = plan_deletion([staged_type])

        assert plan.ok
        assert [holder.name for holder in plan.test_campaigns] == ["Rehearsal"]
        assert [holder.name for holder in plan.test_gangs] == ["Mine"]
        assert ("library.campaigntype", str(campaign.additions_id)) in [
            (label, pk) for label, pk, _ in plan.rows
        ]
        assert ("library.contentpack", str(campaign.pack_id)) in [
            (label, pk) for label, pk, _ in plan.rows
        ]

        apply(plan)

        assert not CampaignType.objects.filter(pk=staged_type.pk).exists()
        assert not CampaignType.objects.filter(pk=campaign.additions_id).exists()
        assert not ContentPack.objects.filter(pk=campaign.pack_id).exists()
        assert not Gang.objects.filter(pk=mine.pk).exists()

    def test_the_record_reads_back_to_the_same_plan(
        self, author, test_type, test_fighter, test_weapon
    ):
        check_with(author, test_type, test_fighter, test_weapon)
        plan = plan_deletion([test_type, test_fighter])

        again = DeletionPlan.from_record(plan.as_record())

        assert again.same_as(plan)
        assert again.preview() == plan.preview()
        assert [holder.name for holder in again.test_gangs] == ["Checking"]
        # A record read back is what the act checks the library against,
        # so it performs from it too.
        apply(again)
        assert not GangType.objects.filter(pk=test_type.pk).exists()


class TestApplying:
    """The act deletes exactly what the plan names, or nothing."""

    def test_the_test_gang_and_the_content_go_together(
        self, author, test_type, test_fighter, test_weapon
    ):
        gang = check_with(author, test_type, test_fighter, test_weapon)
        plan = plan_deletion([test_type, test_fighter, test_weapon])

        report = apply(plan)

        assert not GangType.objects.filter(pk=test_type.pk).exists()
        assert not Profile.objects.filter(pk=test_fighter.pk).exists()
        assert not Weapon.objects.filter(pk=test_weapon.pk).exists()
        assert not Gang.objects.filter(pk=gang.pk).exists()
        assert not Assignment.objects.filter(gang_root_id=gang.pk).exists()
        assert not Miniature.objects.exists()
        assert any("test gang" in line for line in report)

    def test_a_refused_plan_deletes_nothing(
        self, player, test_type, test_fighter, test_weapon
    ):
        gang = check_with(player, test_type, test_fighter, test_weapon)
        plan = plan_deletion([test_type, test_fighter])

        with pytest.raises(Refused):
            apply(plan)

        assert GangType.objects.filter(pk=test_type.pk).exists()
        assert Gang.objects.filter(pk=gang.pk).exists()

    def test_a_gang_founded_after_the_plan_was_read_refuses(
        self, author, player, test_type, test_fighter, test_weapon
    ):
        mine = check_with(author, test_type, test_fighter, test_weapon, "Mine")
        plan = plan_deletion([test_type, test_fighter])
        theirs = found_gang("Theirs", test_type, owner=player)

        with pytest.raises(Refused, match="changed"):
            apply(plan)

        assert Gang.objects.filter(pk=mine.pk).exists()
        assert Gang.objects.filter(pk=theirs.pk).exists()
        assert GangType.objects.filter(pk=test_type.pk).exists()

    def test_the_shared_modifier_stays_when_its_carrier_goes(
        self, author, test_type, test_fighter, test_weapon
    ):
        rule = create_rule("Test rule", staged=True)
        keeper = create_rule("Kept rule")
        shared = modifier(
            "Brings a lasgun", targets_model(), ef_adds(test_weapon), carried_by=rule
        )
        keeper.modifiers.add(shared)

        apply(plan_deletion([rule]))

        assert Modifier.objects.filter(pk=shared.pk).exists()
        assert keeper.modifiers.filter(pk=shared.pk).exists()

    def test_a_modifier_naming_the_weapon_goes_with_the_weapon_and_its_carrier(
        self, author, test_type, test_fighter, test_weapon
    ):
        rule = create_rule("Test rule", staged=True)
        named = modifier(
            "Brings a lasgun", targets_model(), ef_adds(test_weapon), carried_by=rule
        )

        apply(plan_deletion([rule, test_weapon]))

        assert not Modifier.objects.filter(pk=named.pk).exists()
        assert not Weapon.objects.filter(pk=test_weapon.pk).exists()


def table_counts():
    """Every n26 table's row count, so a delete can be proved to leave
    nothing behind that was only there because of the gang."""
    from django.apps import apps

    return {
        model._meta.label_lower: model.objects.count()
        for model in apps.get_app_config("n26").get_models()
    }


class TestDeletingAGang:
    """The first hard delete of a gang: everything only there because of
    the gang goes, and nothing else moves."""

    def test_everything_hanging_off_the_gang_goes_with_it(
        self, author, player, default_pack, person_type, campaign_type
    ):
        from n26.core.models import PrintConfig, StatOverride
        from n26.library.authoring import add_asset_type, create_asset
        from n26.library.models import AssetType
        from n26.tests.sandbox.actions import add_asset, assign_asset

        escher = create_gang_type("Escher", starting_credits=1000)
        ganger = create_profile("Ganger", person_type, escher, price=50)
        lasgun = create_weapon("Lasgun", price=15)
        before = table_counts()

        theirs = found_gang("Theirs", escher, owner=player)
        campaign = found_campaign("Dust Falls", campaign_type, owner=author)
        join_campaign(theirs, campaign)
        settled = table_counts()

        mine = found_gang("Mine", escher, owner=author)
        model = hire(mine, ganger, "One", paid=50)
        give_weapon(model, lasgun, paid=15)
        join_campaign(mine, campaign)
        PrintConfig.objects.create(gang=mine, name="Table")
        stat = person_type.statline_type.stats.first()
        StatOverride.objects.create(miniature=model, statline_type_stat=stat, value="9")
        asset_type = add_asset_type(
            campaign_type, "Territory", AssetType.Ownership.HOLDING
        )
        asset = create_asset("The Sump", asset_type)
        held = add_asset(campaign, asset)
        assign_asset(held, mine)
        with operation(theirs, actor=player, also=[mine]) as op:
            op.transfer(mine, 10)
        assert table_counts() != settled
        logged = CampaignEvent.objects.count()

        destroy_gang(Gang.objects.get(pk=mine.pk))

        after = table_counts()
        # The campaign's log keeps every line: what happened in it is the
        # campaign's history, whichever gang it was about.
        assert CampaignEvent.objects.count() == logged
        grew = {
            label: after[label] - settled[label]
            for label in after
            if after[label] != settled[label] and label != "n26.campaignevent"
        }
        # The campaign's asset line and the payer's own line stay: the
        # asset is the campaign's, and the payment is the payer's history.
        assert grew == {"n26.campaignasset": 1, "n26.ledgerevent": 1}
        assert (
            LedgerEvent.objects.get(gang=theirs, credits_delta=10).counterpart is None
        )
        assert Gang.objects.filter(pk=theirs.pk).exists()
        assert before.keys() == after.keys()

    def test_the_database_is_left_consistent(self, author, default_pack, person_type):
        escher = create_gang_type("Escher")
        ganger = create_profile("Ganger", person_type, escher, price=50)
        mine = found_gang("Mine", escher, owner=author)
        hire(mine, ganger, "One", paid=50)

        destroy_gang(mine)

        # Every foreign key checked at once, which is what proves no row
        # was left pointing at the gang or its models.
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        assert not Miniature.objects.exists()
