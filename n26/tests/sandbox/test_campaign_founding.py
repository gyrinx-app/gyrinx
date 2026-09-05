"""Founding a campaign on a type, and what joining one gives a gang.

A campaign is founded on a shared campaign type and owns, from that
moment, a pack of its own with an empty additions type in it. A gang
that joins is assigned both types, gang-hosted and granted, and the
shared type's built-ins arrive caused by its carrier — on Territory campaign, a
Settlement and a Reputation counter at 0. The gang sheet draws those
under the campaign's name, credited to the type that brought them, and
a staff edit to the shared type reaches every member gang by the same
propagation that reaches a gang type's members. See
design/campaign-assets.md.

Leaving is not offered until it can return everything, so the one route
that would take a gang out refuses in words.
"""

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaign_packs import give_campaigns_their_packs
from n26.core.campaigns import campaign_operation
from n26.core.history import build, campaign_history
from n26.core.models import (
    Assignment,
    CampaignEvent,
    CampaignMembership,
    LedgerEvent,
    Reason,
)
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_gang
from n26.flags import BUILT_IN_PROPAGATION
from n26.library.authoring import add_built_in, create_counter
from n26.library.core_campaign import seed_core_campaign
from n26.library.models import CampaignType
from n26.tests.sandbox.actions import found_campaign, found_gang, join_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def arbitrator():
    return User.objects.create_user("arbitrator")


@pytest.fixture
def core(default_pack):
    """The Territory campaign type as it ships: Reputation at 0 and a Settlement
    built in. The data migration that creates it never runs under the
    test settings, so the same code seeds it here."""
    seed_core_campaign(apps)
    return CampaignType.objects.get(name="Territory campaign")


@pytest.fixture
def campaign(arbitrator, core):
    return found_campaign("Dust Falls", core, owner=arbitrator, budget=1000)


@pytest.fixture
def gang(gang_type):
    return found_gang(
        "The Ashen Choir", gang_type, owner=User.objects.create_user("player")
    )


@pytest.fixture
def membership(gang, campaign):
    return join_campaign(gang, campaign)


def sentences(acts):
    return ["".join(span.text for span in act.spans) for act in acts]


def caused_by(carrier):
    """What a carrier brought, as ``(name, counter value)`` pairs."""
    return sorted(
        (
            str(row.assignable),
            getattr(getattr(row, "counter_value", None), "value", None),
        )
        for row in Assignment.objects.filter(caused_by=carrier)
    )


class TestFoundingACampaign:
    """Founding writes the campaign, its own pack and its additions type
    together, and opens its log by naming the type."""

    def test_it_is_founded_on_the_type(self, campaign, core):
        assert campaign.campaign_type == core
        assert campaign in core.campaigns.all()

    def test_it_owns_a_pack_the_arbitrator_owns(self, campaign, arbitrator):
        assert campaign.pack.owner == arbitrator
        assert campaign.pack.name == "Dust Falls"
        assert campaign.pack.slug == f"campaign-{str(campaign.pk).lower()}"

    def test_its_additions_type_sits_empty_in_that_pack(self, campaign):
        additions = campaign.additions
        assert additions.pack == campaign.pack
        assert additions.name == "Dust Falls"
        assert additions.built_ins is None
        assert not additions.assets.exists()
        assert additions.additions_to == campaign

    def test_the_additions_type_is_never_offered_to_found_on(self, campaign, core):
        """It lives in a pack somebody owns, which every picker leaves out."""
        offered = list(CampaignType.objects.selectable())
        assert core in offered
        assert campaign.additions not in offered

    def test_two_campaigns_of_one_name_each_get_their_own_pack(self, arbitrator, core):
        first = found_campaign("Dust Falls", core, owner=arbitrator)
        second = found_campaign("Dust Falls", core, owner=arbitrator)
        assert first.pack != second.pack
        assert first.additions != second.additions

    def test_the_log_opens_by_naming_the_type(self, campaign):
        assert [e.kind for e in campaign.events.all()] == [CampaignEvent.Kind.CREATED]
        assert sentences(campaign_history(campaign)) == [
            "set the campaign up on Territory campaign"
        ]

    def test_a_campaign_is_founded_once(self, campaign, core, arbitrator):
        with pytest.raises(ValueError, match="already been founded"):
            with campaign_operation(campaign, actor=arbitrator) as act:
                act.found(core)


class TestJoiningACampaign:
    """Joining puts both of the campaign's types on the gang, granted, and
    lands the shared type's built-ins in the same operation."""

    def test_the_gang_carries_both_types(self, membership, gang, campaign, core):
        type_carrier = membership.type_carrier
        additions_carrier = membership.additions_carrier
        assert type_carrier.assignable == core
        assert additions_carrier.assignable == campaign.additions
        for carrier in (type_carrier, additions_carrier):
            assert carrier.gang == gang
            assert carrier.gang_root == gang
            assert carrier.ledger_entry.reason == Reason.GRANTED
            assert carrier.ledger_entry.rating_contribution == 0
        assert type_carrier.type_carrier_of == membership
        assert additions_carrier.additions_carrier_of == membership

    def test_the_types_built_ins_arrive_caused_by_its_carrier(self, membership):
        assert caused_by(membership.type_carrier) == [
            ("Reputation", 0),
            ("Settlement", None),
        ]
        # An additions type is empty at founding, so its carrier brings
        # nothing until the arbitrator adds to it.
        assert caused_by(membership.additions_carrier) == []

    def test_nothing_is_priced_and_the_books_balance(self, membership, gang):
        gang.refresh_from_db()
        assert gang.rating == 0
        assert_reconciled(gang)

    def test_the_ledger_shows_two_granted_carriers(self, membership, gang, campaign):
        granted = LedgerEvent.objects.filter(
            gang=gang,
            kind=LedgerEvent.Kind.GRANTED,
            assignment__campaign_type__isnull=False,
        )
        assert granted.count() == 2
        assert {e.campaign for e in granted} == {campaign}

    def test_the_gangs_history_tells_the_join_as_one_act(self, membership, gang):
        """The types and their built-ins ride the joining rather than
        standing as acts of their own."""
        acts = build(gang)
        (joined,) = [
            a
            for a in acts
            if "added the gang to Dust Falls" in "".join(s.text for s in a.spans)
        ]
        # The campaign's own type rides the joining unnamed: it wears the
        # campaign's name, and no page names it.
        assert sorted((sub.name, sub.kind) for sub in joined.subs) == [
            ("Reputation", "counter"),
            ("Settlement", "asset"),
            ("Territory campaign", "campaign type"),
        ]
        assert not any("gained" in line for line in sentences(acts))

    def test_the_campaigns_log_reads_the_same_act(self, membership, campaign):
        told = sentences(campaign_history(campaign))
        assert told == [
            "set the campaign up on Territory campaign",
            "added the gang to Dust Falls",
        ]

    def test_joining_again_grants_nothing_twice(self, membership, gang, campaign):
        join_campaign(gang, campaign)
        assert (
            Assignment.objects.filter(gang=gang, campaign_type__isnull=False).count()
            == 2
        )
        assert (
            Assignment.objects.filter(gang=gang, counter__name="Reputation").count()
            == 1
        )


class TestTheGangSheet:
    """What the campaign gave is drawn under the campaign's name, each
    thing credited to the type that brought it, and nowhere else."""

    def test_it_draws_the_campaigns_possessions_under_its_name(self, membership, gang):
        block = render_gang(gang).campaign
        assert block.name == "Dust Falls"
        assert [
            (
                line.type_label,
                line.name,
                line.provenance.source,
                line.provenance.source_kind,
            )
            for line in block.lines
        ] == [("Settlement", "Settlement", "Territory campaign", "campaign type")]
        assert [
            (line.name, line.value, line.provenance.source) for line in block.counters
        ] == [("Reputation", 0, "Territory campaign")]

    def test_the_owner_can_tally_the_campaigns_counter_from_the_sheet(
        self, client, membership, gang
    ):
        client.force_login(gang.owner)
        at = reverse("n26-gang", args=[gang.pk])
        assert "Add one to Reputation" in client.get(at).content.decode()
        (reputation,) = render_gang(gang).campaign.counters

        client.post(
            reverse("n26-tally", args=[reputation.assignment_id]),
            {"change": 1, "back": at},
        )

        assert [line.value for line in render_gang(gang).campaign.counters] == [1]

    def test_a_reader_who_does_not_own_the_gang_gets_no_tally_control(
        self, client, membership, gang
    ):
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "Reputation" in body
        assert "Add one to Reputation" not in body

    def test_a_reader_outside_the_campaigns_feature_gets_the_name_alone(
        self, client, membership, gang, campaign
    ):
        """The campaign pages answer a reader outside the feature with a
        404, so the sheet names the campaign rather than linking to it."""
        client.force_login(gang.owner)

        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert "Dust Falls" in body
        assert reverse("n26-campaign", args=[campaign.pk]) not in body

    def test_the_campaigns_counter_is_drawn_once(self, membership, gang):
        sheet = render_gang(gang)
        assert [reading.name for reading in sheet.counters] == []

    def test_the_carriers_draw_no_line_among_the_gangs_own_rows(self, membership, gang):
        sheet = render_gang(gang)
        names = [row.name for row in sheet.rows]
        assert "Territory campaign" not in names
        assert "Dust Falls" not in names
        assert "Settlement" not in names

    def test_a_gang_in_no_campaign_has_no_block(self, gang):
        assert render_gang(gang).campaign is None

    def test_the_page_draws_it(self, client, membership, gang):
        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "Dust Falls" in body
        assert "Settlement" in body
        assert "Reputation" in body
        assert "From Territory campaign (campaign type)" in body


class TestEditingTheTypeReachesMemberGangs:
    """A staff edit to the shared type's built-ins travels to every gang
    carrying it through the same pass that carries a gang type's edits."""

    @pytest.fixture(autouse=True)
    def flag(self, db):
        return FeatureFlag.objects.create(
            slug=BUILT_IN_PROPAGATION,
            name="Built-in propagation",
            availability=Availability.EVERYONE,
        )

    def test_a_new_built_in_lands_on_a_gang_already_playing(
        self, membership, gang, core, task_queue
    ):
        with task_queue.capture():
            add_built_in(core, create_counter("Meat"), amount=2)
        task_queue.deliver_all()

        assert caused_by(membership.type_carrier) == [
            ("Meat", 2),
            ("Reputation", 0),
            ("Settlement", None),
        ]
        assert_reconciled(gang)


class TestTheLeaveRoute:
    """Not offered: a gang that left would keep what the campaign gave it."""

    @pytest.fixture
    def open_to_everyone(self):
        from n26.flags import CAMPAIGNS

        return FeatureFlag.objects.create(
            slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
        )

    def test_it_refuses_in_words_and_changes_nothing(
        self, client, membership, gang, campaign, arbitrator, open_to_everyone
    ):
        client.force_login(arbitrator)
        address = reverse("n26-campaign-remove-gang", args=[campaign.pk, gang.pk])
        response = client.post(address, follow=True)
        assert "cannot leave Dust Falls" in response.content.decode()
        assert CampaignMembership.objects.get(gang=gang).playing
        assert caused_by(membership.type_carrier) == [
            ("Reputation", 0),
            ("Settlement", None),
        ]


class TestGivingExistingCampaignsTheirPacks:
    """The data migration's logic: a campaign or membership written before
    founding and joining gave anything is brought up to what they give."""

    def test_a_membership_without_carriers_is_given_them(self, gang, campaign):
        # A membership as one was written before joining carried anything:
        # the row and nothing else.
        CampaignMembership.objects.create(campaign=campaign, gang=gang)

        lines = give_campaigns_their_packs(apps)

        membership = CampaignMembership.objects.get(gang=gang)
        assert membership.type_carrier.assignable == campaign.campaign_type
        assert membership.additions_carrier.assignable == campaign.additions
        assert membership.type_carrier.ledger_entry.reason == Reason.GRANTED
        assert caused_by(membership.type_carrier) == [
            ("Reputation", 0),
            ("Settlement", None),
        ]
        assert_reconciled(gang)
        assert any(
            "now carries type_carrier, additions_carrier" in line for line in lines
        )

    def test_what_it_writes_reads_as_a_join_does(self, gang, campaign):
        CampaignMembership.objects.create(campaign=campaign, gang=gang)
        give_campaigns_their_packs(apps)

        block = render_gang(gang).campaign
        assert [(line.type_label, line.name) for line in block.lines] == [
            ("Settlement", "Settlement")
        ]
        assert [(line.name, line.value) for line in block.counters] == [
            ("Reputation", 0)
        ]
        granted = LedgerEvent.objects.filter(gang=gang, kind=LedgerEvent.Kind.GRANTED)
        assert granted.count() == 4
        assert {e.campaign for e in granted} == {campaign}

    def test_a_campaign_joined_the_new_way_is_left_alone(self, membership, gang):
        before = Assignment.objects.filter(gang=gang).count()
        assert give_campaigns_their_packs(apps) == []
        assert Assignment.objects.filter(gang=gang).count() == before

    def test_running_it_twice_changes_nothing_the_second_time(self, gang, campaign):
        CampaignMembership.objects.create(campaign=campaign, gang=gang)
        give_campaigns_their_packs(apps)
        before = Assignment.objects.filter(gang=gang).count()

        assert give_campaigns_their_packs(apps) == []
        assert Assignment.objects.filter(gang=gang).count() == before
