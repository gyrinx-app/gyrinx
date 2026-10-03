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

import pytest
from django.apps import apps
from django.contrib.auth.models import User

from n26.core.history import build, campaign_history
from n26.core.models import CampaignEvent, CampaignMembership, LedgerEvent
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
        assert reputation_counter(gang).counter_value.value == 0
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


class TestTheConfirmationPage:
    """The page says what the gang loses and what goes back to the campaign,
    each under its own heading."""

    @pytest.fixture
    def open_to_everyone(self, db):
        from gyrinx.site.models import Availability, FeatureFlag
        from n26.flags import CAMPAIGNS

        return FeatureFlag.objects.create(
            slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
        )

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
            ("Reputation", "4"),
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
