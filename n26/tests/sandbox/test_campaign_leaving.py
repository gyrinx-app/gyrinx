"""Leaving a campaign, and archiving one, give back everything the campaign
gave.

A gang that joins is given the campaign's two types and what they bring —
a Settlement, the campaign's counters, its labels — and may come to hold
the campaign's assets. Leaving gives all of it back in one act: every held
asset goes back unheld, both carriers are removed with everything they
caused, and the membership closes. The gang's history keeps saying what
happened. Archiving a campaign does the same for every gang still in it.
See design/campaign-assets.md.
"""

import re
from datetime import date
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.apps import apps
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.campaigns import campaign_operation
from n26.core.history import build, campaign_history
from n26.core.models import (
    CampaignEvent,
    CampaignMembership,
    CampaignParticipant,
    LedgerEvent,
    PostBattleReport,
)
from n26.core.post_battle import can_edit_report, start_report
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_campaign, render_gang
from n26.library.authoring import create_asset
from n26.library.core_campaign import seed_core_campaign
from n26.library.models import CampaignType, Pickable
from n26.tests.sandbox.actions import (
    add_asset,
    add_campaign_label,
    archive_campaign,
    assign_asset,
    choose,
    found_campaign,
    found_gang,
    join_campaign,
    remove_from_campaign,
    tally,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def arbitrator():
    return User.objects.create_user("arbitrator")


@pytest.fixture
def core(default_pack):
    seed_core_campaign(apps)
    return CampaignType.objects.get(name="Territory campaign")


@pytest.fixture
def campaign(arbitrator, core):
    return found_campaign("Dust Falls", core, owner=arbitrator, budget=1000)


@pytest.fixture
def alignment(campaign):
    """A label every gang in the campaign picks for."""
    return add_campaign_label(campaign, "Alignment", ["Law Abiding", "Outlaw"])


@pytest.fixture
def gang(gang_type, campaign, alignment):
    gang = found_gang(
        "The Ashen Choir", gang_type, owner=User.objects.create_user("player")
    )
    join_campaign(gang, campaign)
    return gang


@pytest.fixture
def rival(gang_type, campaign, alignment):
    gang = found_gang("The Rust Kings", gang_type, owner=User.objects.create_user("r"))
    join_campaign(gang, campaign)
    return gang


@pytest.fixture
def old_ruins(core, campaign):
    territory = core.asset_types.get(label_singular="Territory")
    return add_asset(campaign, create_asset("Old Ruins", territory, income=30))


def live(gang):
    return gang.assignments.filter(archived=False)


def reputation_counter(gang):
    return live(gang).get(counter__name="Reputation")


def played(gang, alignment, old_ruins):
    """The gang as the issue describes it: a territory held, a Settlement,
    Reputation 4 and an Alignment picked."""
    assign_asset(old_ruins, gang)
    tally(reputation_counter(gang), 4)
    asked = live(gang).get(slot=alignment)
    choose(asked, Pickable.objects.get(name="Outlaw", pack=alignment.pack))
    return gang


def sentences(acts):
    return ["".join(span.text for span in act.spans) for act in acts]


class TestLeaving:
    def test_the_gang_keeps_nothing_the_campaign_gave(
        self, gang, campaign, alignment, old_ruins
    ):
        played(gang, alignment, old_ruins)
        assert live(gang).filter(asset__name="Settlement").exists()

        remove_from_campaign(gang, campaign)

        assert not live(gang).filter(asset__name="Settlement").exists()
        assert not live(gang).filter(counter__name="Reputation").exists()
        assert not live(gang).filter(slot=alignment).exists()
        assert not live(gang).filter(campaign_type__isnull=False).exists()
        # The pick for the label goes with the label.
        assert not live(gang).filter(pickable__name="Outlaw").exists()
        assert render_gang(gang).campaign is None
        assert render_gang(gang).questions == []
        assert_reconciled(gang)

    def test_the_held_asset_goes_back_unheld(
        self, gang, campaign, alignment, old_ruins
    ):
        played(gang, alignment, old_ruins)
        remove_from_campaign(gang, campaign)

        old_ruins.refresh_from_db()
        assert old_ruins.holder is None
        (territories,) = [
            table
            for table in render_campaign(campaign).assets
            if table.plural == "Territories"
        ]
        (entry,) = territories.entries
        assert not entry.held

    def test_the_membership_closes(self, gang, campaign):
        remove_from_campaign(gang, campaign)
        membership = CampaignMembership.objects.get(gang=gang)
        assert not membership.playing
        assert membership.type_carrier is not None
        assert membership.type_carrier.archived

    def test_the_ledger_says_what_went(self, gang, campaign, alignment, old_ruins):
        played(gang, alignment, old_ruins)
        remove_from_campaign(gang, campaign)

        lost = LedgerEvent.objects.get(gang=gang, kind=LedgerEvent.Kind.LOST)
        assert lost.campaign_asset == old_ruins
        assert lost.campaign == campaign
        left = LedgerEvent.objects.get(gang=gang, kind=LedgerEvent.Kind.LEFT_CAMPAIGN)
        assert left.campaign == campaign
        # One act: every record of the leaving shares its mark.
        assert {
            event.batch
            for event in LedgerEvent.objects.filter(
                gang=gang, created__gte=lost.created
            )
        } == {left.batch}

    def test_the_history_reads_as_one_act(self, gang, campaign, alignment, old_ruins):
        played(gang, alignment, old_ruins)
        remove_from_campaign(gang, campaign)

        # What went folds under the leaving, as what came folds under the
        # joining; the asset the gang held has its own line, as gaining it
        # did.
        for acts in (build(gang), campaign_history(campaign)):
            *_, lost, left = acts
            assert sentences([left]) == ["took the gang out of Dust Falls"]
            assert [sub.name for sub in left.subs] == [
                "Territory campaign",
                "Reputation",
                "Settlement",
                "Income",
                "Alignment",
                "Outlaw",
            ]
            assert "Old Ruins" in sentences([lost])[0]

    def test_leaving_twice_writes_nothing_twice(self, gang, campaign):
        membership = CampaignMembership.objects.get(gang=gang)
        remove_from_campaign(gang, campaign)
        before = LedgerEvent.objects.filter(gang=gang).count()

        from n26.core.campaigns import campaign_operation

        with campaign_operation(campaign, actor=campaign.owner) as act:
            assert act.remove_gang(membership) is None
        assert LedgerEvent.objects.filter(gang=gang).count() == before

    def test_the_gang_may_join_again_and_starts_afresh(
        self, gang, campaign, alignment, old_ruins
    ):
        played(gang, alignment, old_ruins)
        remove_from_campaign(gang, campaign)
        join_campaign(gang, campaign)

        assert live(gang).filter(asset__name="Settlement").count() == 1
        assert reputation_counter(gang).counter_value.value == 1
        (choice,) = render_gang(gang).campaign.choices
        assert not choice.chosen
        assert_reconciled(gang)

    def test_another_gang_is_untouched(
        self, gang, rival, campaign, alignment, old_ruins
    ):
        played(gang, alignment, old_ruins)
        remove_from_campaign(gang, campaign)
        assert CampaignMembership.objects.get(gang=rival).playing
        assert live(rival).filter(asset__name="Settlement").exists()


class TestArchivingACampaign:
    def test_every_gang_leaves_first(self, gang, rival, campaign, alignment, old_ruins):
        played(gang, alignment, old_ruins)
        archive_campaign(campaign)

        for member in (gang, rival):
            assert not CampaignMembership.objects.get(gang=member).playing
            assert not live(member).filter(asset__name="Settlement").exists()
            assert not live(member).filter(campaign_type__isnull=False).exists()
            assert_reconciled(member)
        old_ruins.refresh_from_db()
        assert old_ruins.holder is None

    def test_the_campaign_and_its_pack_are_archived(self, gang, campaign):
        archive_campaign(campaign)
        campaign.refresh_from_db()
        assert campaign.archived
        assert campaign.pack.archived
        assert campaign.events.filter(kind=CampaignEvent.Kind.ARCHIVED).exists()

    def test_a_gang_that_left_earlier_is_not_written_to_again(
        self, gang, rival, campaign
    ):
        remove_from_campaign(gang, campaign)
        before = LedgerEvent.objects.filter(gang=gang).count()
        archive_campaign(campaign)
        assert LedgerEvent.objects.filter(gang=gang).count() == before

    def test_an_archived_campaign_takes_no_gangs(self, gang_type, campaign):
        from n26.core.campaigns import campaign_operation
        from n26.core.operations import Refusal

        archive_campaign(campaign)
        late = found_gang("Late", gang_type, owner=User.objects.create_user("late"))
        with pytest.raises(Refusal, match="Dust Falls is archived"):
            with campaign_operation(campaign, actor=campaign.owner) as act:
                act.add_gang(late)
        assert not CampaignMembership.objects.filter(gang=late).exists()


@pytest.fixture
def open_to_everyone(db):
    from gyrinx.site.models import Availability, FeatureFlag
    from n26.flags import CAMPAIGNS

    return FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )


class TestTheConfirmationPage:
    """The page says what the gang loses and what goes back to the campaign,
    each under its own heading."""

    def test_each_thing_is_under_the_right_heading(
        self, client, gang, campaign, alignment, old_ruins, open_to_everyone
    ):
        played(gang, alignment, old_ruins)
        client.force_login(campaign.owner)
        drawn = client.get(
            f"/n26/campaigns/{campaign.pk}/gangs/{gang.pk}/remove/"
        ).content.decode()

        removed, _, returned = drawn.partition("Returned to Dust Falls")
        removed = removed.partition("Removed from The Ashen Choir")[2]
        for label, value in (
            ("Settlement", "Settlement"),
            ("Reputation", "5"),
            ("Alignment", "Outlaw"),
        ):
            assert re.search(
                rf"<dt[^>]*>{label}</dt>\s*<dd[^>]*>\s*{value}\s*</dd>", removed
            ), label
        assert "Old Ruins" not in removed
        assert re.search(
            r"<dt[^>]*>Territory</dt>\s*<dd[^>]*>\s*Old Ruins\s*</dd>", returned
        )
        assert "These will be unassigned." in returned


def seat(campaign, user):
    """An accepted player, as answering an invitation leaves one."""
    with campaign_operation(campaign, actor=campaign.owner) as act:
        act.invite(user)
    with campaign_operation(campaign, actor=user) as act:
        act.answer_invitation(user, accepted=True)


def leave(campaign, user):
    with campaign_operation(campaign, actor=user) as act:
        return act.leave()


def fight(campaign, *gangs):
    """A battle with no result recorded yet."""
    with campaign_operation(campaign, actor=campaign.owner) as act:
        return act.record_battle(date(2026, 10, 1), gangs, scenario="Ambush")


@pytest.fixture
def second(gang, gang_type, campaign):
    """Another gang of the same player's, in the same campaign."""
    other = found_gang("The Grey Hounds", gang_type, owner=gang.owner)
    join_campaign(other, campaign)
    return other


class TestAPlayerLeaving:
    """A player who leaves takes every gang of theirs out, each as removing
    it would, and stops being a player. Nobody else's gang is touched."""

    def test_every_gang_of_theirs_gives_back_what_the_campaign_gave(
        self, gang, second, rival, campaign, alignment, old_ruins
    ):
        played(gang, alignment, old_ruins)
        seat(campaign, gang.owner)

        left = leave(campaign, gang.owner)

        assert {g.pk for g in left} == {gang.pk, second.pk}
        for member in (gang, second):
            assert not CampaignMembership.objects.get(gang=member).playing
            assert not live(member).filter(asset__name="Settlement").exists()
            assert not live(member).filter(campaign_type__isnull=False).exists()
            assert_reconciled(member)
        old_ruins.refresh_from_db()
        assert old_ruins.holder is None
        assert CampaignMembership.objects.get(gang=rival).playing
        assert live(rival).filter(asset__name="Settlement").exists()

    def test_they_stop_being_a_player_and_the_log_says_they_left(self, gang, campaign):
        seat(campaign, gang.owner)
        leave(campaign, gang.owner)

        assert not CampaignParticipant.objects.filter(campaign=campaign).exists()
        event = campaign.events.get(kind=CampaignEvent.Kind.PLAYER_LEFT)
        assert (event.actor, event.about_user) == (gang.owner, gang.owner)
        assert "left the campaign" in sentences(campaign_history(campaign))
        # The gang's own history says it was taken out, as removing it does.
        assert "took the gang out of Dust Falls" in sentences(build(gang))

    def test_leaving_twice_changes_nothing(self, gang, campaign):
        seat(campaign, gang.owner)
        leave(campaign, gang.owner)
        before = (LedgerEvent.objects.count(), CampaignEvent.objects.count())

        assert leave(campaign, gang.owner) is None
        assert (LedgerEvent.objects.count(), CampaignEvent.objects.count()) == before

    def test_the_arbitrator_has_nothing_to_leave(self, gang_type, campaign):
        theirs = found_gang("The Overseers", gang_type, owner=campaign.owner)
        join_campaign(theirs, campaign)

        assert leave(campaign, campaign.owner) is None
        assert CampaignMembership.objects.get(gang=theirs).playing
        assert not campaign.events.filter(kind=CampaignEvent.Kind.PLAYER_LEFT).exists()

    def test_somebody_only_invited_has_nothing_to_leave(self, campaign):
        invited = User.objects.create_user("invited")
        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.invite(invited)

        assert leave(campaign, invited) is None
        assert CampaignParticipant.objects.get(user=invited).state == (
            CampaignParticipant.State.INVITED
        )

    def test_asked_back_their_gang_may_join_again(self, gang, campaign):
        seat(campaign, gang.owner)
        leave(campaign, gang.owner)

        seat(campaign, gang.owner)
        join_campaign(gang, campaign)

        assert CampaignMembership.objects.filter(gang=gang, left__isnull=True).exists()
        assert live(gang).filter(asset__name="Settlement").count() == 1

    def test_a_draft_report_stays_theirs_to_finish(self, gang, rival, campaign):
        seat(campaign, gang.owner)
        battle = fight(campaign, gang, rival)
        report = start_report(
            gang, actor=gang.owner, battle=battle, request_key=uuid4()
        )

        leave(campaign, gang.owner)

        report.refresh_from_db()
        assert report.state == PostBattleReport.State.DRAFT
        assert can_edit_report(report, gang.owner)
        assert not can_edit_report(report, campaign.owner)


class TestTheArbitratorRemovingAPlayer:
    """The arbitrator chooses whether a removed player's gangs keep playing
    or leave with them. Keeping them is the default."""

    def test_their_gangs_keep_playing_unless_asked(self, gang, second, campaign):
        seat(campaign, gang.owner)
        player = CampaignParticipant.objects.get(user=gang.owner)

        with campaign_operation(campaign, actor=campaign.owner) as act:
            assert act.remove_player(player) == []

        assert not CampaignParticipant.objects.exists()
        for member in (gang, second):
            assert CampaignMembership.objects.get(gang=member).playing

    def test_asked_to_their_gangs_leave_with_them(
        self, gang, second, rival, campaign, alignment, old_ruins
    ):
        played(gang, alignment, old_ruins)
        seat(campaign, gang.owner)
        player = CampaignParticipant.objects.get(user=gang.owner)

        with campaign_operation(campaign, actor=campaign.owner) as act:
            removed = act.remove_player(player, with_gangs=True)

        assert {g.pk for g in removed} == {gang.pk, second.pk}
        for member in (gang, second):
            assert not CampaignMembership.objects.get(gang=member).playing
            assert_reconciled(member)
        old_ruins.refresh_from_db()
        assert old_ruins.holder is None
        assert CampaignMembership.objects.get(gang=rival).playing
        assert "removed player from the campaign" in sentences(
            campaign_history(campaign)
        )


class TestTheLeavePage:
    """The question at its own address. It names every gang the player has
    in the campaign and what each loses, and leaving happens only on the
    POST."""

    @pytest.fixture
    def player(self, client, gang, campaign, open_to_everyone):
        seat(campaign, gang.owner)
        client.force_login(gang.owner)
        return gang.owner

    @pytest.fixture
    def address(self, campaign):
        return f"/n26/campaigns/{campaign.pk}/leave/"

    def test_the_page_names_each_gang_and_what_it_loses(
        self, client, player, gang, second, campaign, alignment, old_ruins, address
    ):
        played(gang, alignment, old_ruins)

        drawn = client.get(address).content.decode()

        assert "Your gangs will be removed from Dust Falls" in drawn
        sections = {
            section.h2.get_text(strip=True): section
            for section in BeautifulSoup(drawn, "html.parser").select(
                "[data-leaving-gang]"
            )
        }
        assert sections.keys() == {"The Ashen Choir", "The Grey Hounds"}
        ashen, grey = sections["The Ashen Choir"], sections["The Grey Hounds"]
        assert re.search(
            r"<dt[^>]*>Territory</dt>\s*<dd[^>]*>\s*Old Ruins\s*</dd>", str(ashen)
        )
        assert "Old Ruins" not in str(grey)
        assert re.search(
            r"<dt[^>]*>Settlement</dt>\s*<dd[^>]*>\s*Settlement\s*</dd>", str(grey)
        )

    def test_unfinished_battles_are_listed(
        self, client, player, gang, rival, campaign, address
    ):
        drafted = fight(campaign, gang, rival)
        report = start_report(gang, actor=player, battle=drafted, request_key=uuid4())

        drawn = client.get(address).content.decode()

        assert "Post-battle reports in draft" in drawn
        assert reverse("n26-post-battle-editor", args=[report.pk]) in drawn
        assert "Battles with no result" in drawn
        assert reverse("n26-battle", args=[campaign.pk, drafted.pk]) in drawn

    def test_opening_the_page_changes_nothing(
        self, client, player, gang, campaign, address
    ):
        before = (LedgerEvent.objects.count(), CampaignEvent.objects.count())

        drawn = client.get(address).content.decode()

        assert (LedgerEvent.objects.count(), CampaignEvent.objects.count()) == before
        assert CampaignMembership.objects.get(gang=gang).playing
        # Cancel goes back to the campaign without submitting anything.
        (cancel,) = [
            link
            for link in BeautifulSoup(drawn, "html.parser").find_all("a")
            if link.get_text(strip=True) == "Cancel"
        ]
        assert cancel["href"] == f"/n26/campaigns/{campaign.pk}/"

    def test_leaving_takes_the_gangs_out_and_says_so(
        self, client, player, gang, campaign, address
    ):
        response = client.post(address, follow=True)

        assert response.redirect_chain[-1][0] == f"/n26/campaigns/{campaign.pk}/"
        assert "You and your gang left Dust Falls." in response.content.decode()
        assert not CampaignMembership.objects.get(gang=gang).playing
        assert not CampaignParticipant.objects.filter(user=player).exists()

    def test_a_second_post_finds_nothing_and_changes_nothing(
        self, client, player, campaign, address
    ):
        client.post(address)
        before = (LedgerEvent.objects.count(), CampaignEvent.objects.count())

        assert client.post(address).status_code == 404
        assert (LedgerEvent.objects.count(), CampaignEvent.objects.count()) == before

    def test_the_arbitrator_cannot_leave(
        self, client, gang, campaign, open_to_everyone, address
    ):
        client.force_login(campaign.owner)
        assert client.get(address).status_code == 404
        assert client.post(address).status_code == 404
        assert CampaignMembership.objects.get(gang=gang).playing

    def test_somebody_not_playing_cannot_leave(
        self, client, gang, campaign, open_to_everyone, address
    ):
        client.force_login(User.objects.create_user("onlooker"))
        assert client.get(address).status_code == 404
        assert client.post(address).status_code == 404
        assert CampaignMembership.objects.get(gang=gang).playing

    @pytest.mark.parametrize("answer", [None, False], ids=["invited", "declined"])
    def test_somebody_invited_or_who_declined_cannot_leave(
        self, client, campaign, open_to_everyone, address, answer
    ):
        asked = User.objects.create_user("asked")
        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.invite(asked)
        if answer is not None:
            with campaign_operation(campaign, actor=asked) as act:
                act.answer_invitation(asked, accepted=answer)
        client.force_login(asked)

        assert client.get(address).status_code == 404
        assert client.post(address).status_code == 404
        assert CampaignParticipant.objects.filter(user=asked).exists()

    def test_a_player_removed_since_the_page_opened_is_told_so(
        self, client, player, gang, campaign, address, monkeypatch
    ):
        from n26.core.campaigns import CampaignOperation

        original = CampaignOperation.leave

        def removed_then_leave(op):
            op.remove_player(
                CampaignParticipant.objects.get(campaign=op.campaign, user=op.actor)
            )
            return original(op)

        monkeypatch.setattr(CampaignOperation, "leave", removed_then_leave)
        response = client.post(address, follow=True)

        assert "You are no longer a player in Dust Falls." in (
            response.content.decode()
        )
        assert CampaignMembership.objects.get(gang=gang).playing
        assert not campaign.events.filter(kind=CampaignEvent.Kind.PLAYER_LEFT).exists()

    def test_the_page_costs_the_same_however_many_gangs(
        self, client, player, gang, gang_type, rival, campaign, address
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def cost():
            with CaptureQueriesContext(connection) as queries:
                assert client.get(address).status_code == 200
            return len(queries)

        def with_a_draft(member):
            battle = fight(campaign, member, rival)
            start_report(member, actor=player, battle=battle, request_key=uuid4())

        with_a_draft(gang)
        client.get(address)
        one = cost()

        other = found_gang("The Grey Hounds", gang_type, owner=player)
        join_campaign(other, campaign)
        with_a_draft(other)

        assert cost() == one


class TestTheRemovePlayerPage:
    @pytest.fixture
    def address(self, client, gang, campaign, open_to_everyone):
        seat(campaign, gang.owner)
        client.force_login(campaign.owner)
        return f"/n26/campaigns/{campaign.pk}/players/{gang.owner.pk}/remove/"

    def test_the_page_names_their_gangs_and_offers_the_choice(
        self, client, gang, second, address
    ):
        drawn = client.get(address).content.decode()

        assert "The Ashen Choir" in drawn
        assert "The Grey Hounds" in drawn
        assert re.search(r'value="keep"\s+checked', drawn)
        assert 'value="remove"' in drawn

    def test_with_no_gangs_there_is_no_choice(self, client, gang, campaign, address):
        remove_from_campaign(gang, campaign)

        drawn = client.get(address).content.decode()

        assert 'name="gangs"' not in drawn

    def test_by_default_their_gangs_stay(self, client, gang, address):
        client.post(address, {"gangs": "keep"})

        assert CampaignMembership.objects.get(gang=gang).playing
        assert not CampaignParticipant.objects.exists()

    def test_chosen_their_gangs_leave_with_them(self, client, gang, second, address):
        response = client.post(address, {"gangs": "remove"}, follow=True)

        assert "Removed player and their gangs from Dust Falls." in (
            response.content.decode()
        )
        for member in (gang, second):
            assert not CampaignMembership.objects.get(gang=member).playing

    def test_a_player_who_left_since_the_page_opened_is_not_removed_again(
        self, client, gang, campaign, address, monkeypatch
    ):
        from n26.core.campaigns import CampaignOperation

        original = CampaignOperation.remove_player

        def left_then_remove(op, player, **kwargs):
            CampaignOperation(op.campaign, actor=player.user).leave()
            return original(op, player, **kwargs)

        monkeypatch.setattr(CampaignOperation, "remove_player", left_then_remove)
        response = client.post(address, {"gangs": "remove"}, follow=True)

        assert "player is no longer in Dust Falls." in response.content.decode()
        assert not campaign.events.filter(
            kind=CampaignEvent.Kind.PLAYER_REMOVED
        ).exists()
        assert campaign.events.filter(kind=CampaignEvent.Kind.PLAYER_LEFT).count() == 1
