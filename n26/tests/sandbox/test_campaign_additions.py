"""Handing an asset between gangs, and what the arbitrator adds to a
campaign.

A transfer is one asset's holder changing under the campaign's line, then a
journal-only event on each gang inside it — LOST on the one it left, GAINED
on the one it went to — so both histories say what happened, and the
campaign's log reads the pair as one act.

What the arbitrator adds is library content written into the campaign's
own pack and onto its own campaign type: an asset type, an asset under one
of the campaign's asset types, a counter every gang tracks, a label every
gang picks. Nothing here touches the shared type, and nothing reaches
another campaign. A counter or a label built in reaches gangs already
playing through the same propagation pass a gang type's built-ins take,
marked as caught up. The campaign page shows each where it lands — an
asset type as a table, a counter or a label as a column — and never as a
list of its own. See design/campaign-assets.md.
"""

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.history import build, campaign_history
from n26.core.models import CampaignEvent, LedgerEvent
from n26.core.operations import Refusal
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_campaign, render_gang
from n26.flags import BUILT_IN_PROPAGATION, CAMPAIGNS
from n26.library.authoring import add_asset_type, create_asset, create_campaign_type
from n26.library.core_campaign import seed_core_campaign
from n26.library.forms import cross_pack_refusal
from n26.library.models import (
    Asset,
    AssetType,
    CampaignType,
    Counter,
    Pickable,
    Slot,
    SlotType,
)
from n26.tests.sandbox.actions import (
    add_asset,
    add_campaign_asset_type,
    add_campaign_counter,
    add_campaign_label,
    assign_asset,
    choose,
    create_campaign_asset,
    found_campaign,
    found_gang,
    join_campaign,
    transfer_asset,
    unassign_asset,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def arbitrator():
    return User.objects.create_user("arbitrator")


@pytest.fixture
def player():
    return User.objects.create_user("player")


@pytest.fixture
def core(default_pack):
    seed_core_campaign(apps)
    return CampaignType.objects.get(name="Territory campaign")


@pytest.fixture
def old_ruins(core):
    territory = core.asset_types.get(label_singular="Territory")
    return create_asset("Old Ruins", territory, income=30)


@pytest.fixture
def campaign(arbitrator, core):
    return found_campaign("Dust Falls", core, owner=arbitrator, budget=1000)


@pytest.fixture
def gang(gang_type, player, campaign):
    gang = found_gang("The Ashen Choir", gang_type, owner=player)
    join_campaign(gang, campaign)
    return gang


@pytest.fixture
def rival(gang_type, campaign):
    gang = found_gang("The Rust Kings", gang_type, owner=User.objects.create_user("r"))
    join_campaign(gang, campaign)
    return gang


@pytest.fixture
def campaign_asset(campaign, old_ruins, gang):
    """Old Ruins in the campaign, held by the player's gang."""
    return assign_asset(add_asset(campaign, old_ruins), gang)


@pytest.fixture
def open_to_everyone(db):
    return FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )


@pytest.fixture
def propagating(db):
    """The running side of built-in propagation sits behind a flag."""
    return FeatureFlag.objects.create(
        slug=BUILT_IN_PROPAGATION,
        name="Built-in propagation",
        availability=Availability.EVERYONE,
    )


def sentences(acts):
    return ["".join(span.text for span in act.spans) for act in acts]


def holding_events(gang):
    return list(
        LedgerEvent.objects.filter(gang=gang, campaign_asset__isnull=False).order_by(
            "created"
        )
    )


def readings(gang):
    """The campaign counters on the gang's sheet, by name."""
    return {line.name: line.value for line in render_gang(gang).campaign.counters}


class TestTransfer:
    """One asset's holder changing, two records: the loser's says it lost the
    asset, the receiver's says it gained it."""

    def test_the_holder_changes(self, campaign_asset, gang, rival):
        moved = transfer_asset(campaign_asset, rival)
        assert moved.holder.gang == rival
        assert not gang.assignments.filter(asset=campaign_asset.asset).exists()
        assert not rival.assignments.filter(asset=campaign_asset.asset).exists()

    def test_each_gang_gets_its_record(self, campaign_asset, gang, rival, campaign):
        transfer_asset(campaign_asset, rival)
        (gained, lost) = holding_events(gang)
        assert (gained.kind, lost.kind) == (
            LedgerEvent.Kind.GAINED,
            LedgerEvent.Kind.LOST,
        )
        (received,) = holding_events(rival)
        assert received.kind == LedgerEvent.Kind.GAINED
        # One act across two gangs, so the two records share a mark.
        assert lost.batch == received.batch
        for event in (lost, received):
            assert event.campaign == campaign
            assert event.campaign_asset == campaign_asset
            assert event.assignment is None
            assert (event.credits_delta, event.rating_delta) == (0, 0)
        assert_reconciled(gang)
        assert_reconciled(rival)

    def test_both_histories_and_the_log_read_plainly(
        self, campaign_asset, gang, rival, campaign
    ):
        """Each gang's history says what it lost or gained; the campaign's
        log tells the hand-over once, naming both gangs, and counts it
        once."""
        from n26.core.history import campaign_history_size

        before = campaign_history_size(campaign)
        transfer_asset(campaign_asset, rival)
        assert sentences(build(gang))[-1] == "lost the territory Old Ruins"
        assert sentences(build(rival))[-1] == "gained the territory Old Ruins"
        acts = campaign_history(campaign)
        assert sentences(acts)[-1] == (
            "Old Ruins went from The Ashen Choir to The Rust Kings"
        )
        assert acts[-1].gang_name == ""
        assert acts[-1].actor == ""
        assert len(acts) == before + 1
        assert campaign_history_size(campaign) == before + 1

    def test_the_holding_moves_with_the_asset(self, campaign_asset, gang, rival):
        assert [line.name for line in render_gang(gang).campaign.holdings] == [
            "Old Ruins"
        ]
        transfer_asset(campaign_asset, rival)
        assert render_gang(gang).campaign.holdings == []
        assert [line.name for line in render_gang(rival).campaign.holdings] == [
            "Old Ruins"
        ]

    def test_an_asset_nobody_holds_cannot_be_handed_over(
        self, campaign, old_ruins, rival
    ):
        unclaimed = add_asset(campaign, old_ruins)
        with pytest.raises(Refusal, match="not held by any gang"):
            transfer_asset(unclaimed, rival)

    def test_handing_an_asset_to_the_gang_holding_it_is_refused(
        self, campaign_asset, gang
    ):
        with pytest.raises(Refusal, match="already holds"):
            transfer_asset(campaign_asset, gang)
        assert holding_events(gang)[-1].kind == LedgerEvent.Kind.GAINED

    def test_a_gang_outside_the_campaign_is_a_callers_mistake(
        self, campaign_asset, gang_type, arbitrator, core
    ):
        other = found_campaign("Elsewhere", core, owner=arbitrator)
        stranger = found_gang("Strangers", gang_type, owner=arbitrator)
        membership = join_campaign(stranger, other)
        from n26.core.campaigns import campaign_operation

        with pytest.raises(ValueError):
            with campaign_operation(campaign_asset.campaign, actor=arbitrator) as act:
                act.transfer(campaign_asset, membership)


class TestActingForAHolderThatChanged:
    """The holding gang's owner reads the page, and the arbitrator moves the
    asset before they post. Their act was allowed for the gang they read as
    the holder, so it is refused in words rather than done to whoever holds
    the asset now; the arbitrator, who may move any held asset, is not
    held to the holder they read."""

    def test_the_owners_hand_over_is_refused(self, campaign_asset, gang, rival):
        from n26.core.campaigns import campaign_operation

        was_held_by = campaign_asset.holder_id
        transfer_asset(campaign_asset, rival)
        third = found_gang(
            "Third", gang.gang_type, owner=User.objects.create_user("third")
        )
        third_membership = join_campaign(third, campaign_asset.campaign)
        with pytest.raises(Refusal, match="is now held by The Rust Kings"):
            with campaign_operation(campaign_asset.campaign, actor=gang.owner) as act:
                act.transfer(campaign_asset, third_membership, by_holder=was_held_by)
        with pytest.raises(Refusal, match="is now held by The Rust Kings"):
            with campaign_operation(campaign_asset.campaign, actor=gang.owner) as act:
                act.unassign(campaign_asset, by_holder=was_held_by)
        campaign_asset.refresh_from_db()
        assert campaign_asset.holder.gang == rival

    def test_the_arbitrator_is_not_held_to_the_holder_they_read(
        self, campaign_asset, gang, rival
    ):
        transfer_asset(campaign_asset, rival)
        assert unassign_asset(campaign_asset).holder is None

    def test_the_page_refuses_the_owners_stale_post(
        self, client, campaign_asset, gang, rival, open_to_everyone
    ):
        client.force_login(gang.owner)
        address = reverse(
            "n26-campaign-asset-unassign",
            args=[campaign_asset.campaign_id, campaign_asset.pk],
        )
        assert client.get(address).status_code == 200
        transfer_asset(campaign_asset, rival)
        # The page is gone for them — another gang holds the asset now.
        assert client.post(address, follow=True).status_code == 404
        campaign_asset.refresh_from_db()
        assert campaign_asset.holder.gang == rival


class TestTransferOnThePage:
    """The arbitrator transfers; the holding gang's owner hands over;
    nobody else is offered either."""

    @pytest.fixture(autouse=True)
    def flag(self, open_to_everyone):
        return open_to_everyone

    def address(self, campaign_asset):
        return reverse(
            "n26-campaign-asset-transfer",
            args=[campaign_asset.campaign_id, campaign_asset.pk],
        )

    def test_the_arbitrator_sees_transfer(
        self, client, campaign_asset, campaign, rival
    ):
        client.force_login(campaign.owner)
        body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
        assert self.address(campaign_asset) in body
        assert "Transfer" in body
        assert "Hand over" not in body

    def test_the_holding_gangs_owner_sees_hand_over(
        self, client, campaign_asset, gang, campaign
    ):
        client.force_login(gang.owner)
        body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
        assert self.address(campaign_asset) in body
        assert "Hand over" in body

    def test_another_player_sees_neither(self, client, campaign_asset, rival, campaign):
        client.force_login(rival.owner)
        body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
        assert self.address(campaign_asset) not in body
        assert client.get(self.address(campaign_asset)).status_code == 404

    def test_the_form_offers_every_other_gang(
        self, client, campaign_asset, gang, rival
    ):
        client.force_login(gang.owner)
        body = client.get(self.address(campaign_asset)).content.decode()
        assert "Hand over Old Ruins" in body
        assert "The Rust Kings" in body
        assert 'value="' + str(campaign_asset.holder_id) + '"' not in body

    def test_the_owner_hands_the_asset_over(
        self, client, campaign_asset, gang, rival, campaign
    ):
        client.force_login(gang.owner)
        membership = rival.campaign_memberships.get(left__isnull=True)

        response = client.post(
            self.address(campaign_asset),
            {"membership": str(membership.pk)},
            follow=True,
        )

        campaign_asset.refresh_from_db()
        assert campaign_asset.holder == membership
        assert "Old Ruins went from The Ashen Choir to The Rust Kings." in (
            response.content.decode()
        )
        assert holding_events(rival)[-1].actor == gang.owner

    def test_a_stale_link_to_an_unclaimed_asset_says_so(
        self, client, campaign, old_ruins
    ):
        unclaimed = add_asset(campaign, old_ruins)
        client.force_login(campaign.owner)
        response = client.get(self.address(unclaimed), follow=True)
        assert "Old Ruins is not held by any gang." in response.content.decode()


class TestAnAssetType:
    def test_it_lands_on_the_campaigns_own_type_in_its_pack(self, campaign):
        racket = add_campaign_asset_type(campaign, "Racket", plural="Rackets")
        assert racket.campaign_type == campaign.additions
        assert racket.pack == campaign.pack
        assert racket.is_holding
        assert campaign.events.last().kind == CampaignEvent.Kind.ASSET_TYPE_ADDED
        assert sentences(campaign_history(campaign))[-1] == (
            "added the asset type Racket"
        )

    def test_a_label_the_campaign_already_uses_is_refused(self, campaign):
        with pytest.raises(Refusal, match="already has an asset type called"):
            add_campaign_asset_type(campaign, "territory")
        add_campaign_asset_type(campaign, "Racket")
        with pytest.raises(Refusal, match="Racket"):
            add_campaign_asset_type(campaign, "Racket")

    def test_the_sheet_gains_a_column_and_a_table(self, campaign, gang):
        add_campaign_asset_type(campaign, "Racket", plural="Rackets")
        sheet = render_campaign(campaign)
        assert [asset_type.plural for asset_type in sheet.asset_types] == [
            "Settlements",
            "Territories",
            "Rackets",
        ]
        assert [table.plural for table in sheet.assets] == ["Territories", "Rackets"]


class TestAnAsset:
    def test_it_lands_in_the_campaigns_pack_under_a_shared_asset_type(
        self, campaign, core, gang
    ):
        territory = core.asset_types.get(label_singular="Territory")
        made = create_campaign_asset(
            campaign, territory, "Sump Hole", annotation="flooded", income=15
        )
        assert made.pack == campaign.pack
        assert made.asset_type == territory
        assert made.income == 15
        assert str(made) == "Sump Hole (flooded)"
        assert not made.modifiers.exists()
        assert sentences(campaign_history(campaign))[-1] == (
            "created the asset Sump Hole (flooded)"
        )

    def test_it_can_be_added_to_the_campaign_and_assigned(self, campaign, core, gang):
        territory = core.asset_types.get(label_singular="Territory")
        made = create_campaign_asset(campaign, territory, "Sump Hole", income=15)
        entry = assign_asset(add_asset(campaign, made), gang)
        table = next(
            t for t in render_campaign(campaign).assets if t.label == "Territory"
        )
        assert [(c.name, c.income, c.holder) for c in table.entries] == [
            ("Sump Hole", 15, "The Ashen Choir")
        ]
        assert entry.held

    def test_it_can_be_under_the_arbitrators_own_asset_type(self, campaign):
        racket = add_campaign_asset_type(campaign, "Racket")
        made = create_campaign_asset(campaign, racket, "Protection", income=10)
        assert made.asset_type == racket
        assert made.pack == campaign.pack
        # Offered where the campaign's Rackets are added, and nowhere else.
        table = next(t for t in render_campaign(campaign).assets if t.label == "Racket")
        assert table.entries == []
        assert made in campaign.additions.holding_assets()

    def test_a_name_the_pack_already_uses_is_refused(self, campaign, core):
        territory = core.asset_types.get(label_singular="Territory")
        create_campaign_asset(campaign, territory, "Sump Hole")
        with pytest.raises(Refusal, match="already has an asset called"):
            create_campaign_asset(campaign, territory, "sump hole")

    def test_another_campaign_on_the_same_type_never_sees_it(
        self, client, campaign, core, open_to_everyone
    ):
        """An asset written under the shared Territory type belongs to the
        campaign whose pack it is in. A second campaign founded on the same
        type is not offered it, and cannot add it by hand."""
        territory = core.asset_types.get(label_singular="Territory")
        private = create_campaign_asset(campaign, territory, "Sump Hole")
        other_arbitrator = User.objects.create_user("other")
        other = found_campaign("Elsewhere", core, owner=other_arbitrator)
        client.force_login(other_arbitrator)

        address = reverse("n26-campaign-add-asset", args=[other.pk])
        assert "Sump Hole" not in client.get(address).content.decode()
        response = client.post(address, {"asset": str(private.pk)})
        assert response.status_code == 200
        assert "not one this campaign deals in" in str(response.context["form"].errors)
        assert not other.campaign_assets.exists()

        with pytest.raises(ValueError):
            add_asset(other, private)
        # The campaign it belongs to still deals in it.
        client.force_login(campaign.owner)
        assert (
            "Sump Hole"
            in client.get(
                reverse("n26-campaign-add-asset", args=[campaign.pk])
            ).content.decode()
        )

    def test_another_campaign_types_asset_type_is_a_callers_mistake(
        self, campaign, default_pack
    ):
        dominion = create_campaign_type("Dominion")
        relic = add_asset_type(dominion, "Relic", "pooled")
        with pytest.raises(ValueError):
            create_campaign_asset(campaign, relic, "The Skull")


class TestSystemContentNeverPointsAtAnArbitratorsAsset:
    """Pack content may reference system content; the reverse is refused
    by the authoring forms. An arbitrator's asset is pack content."""

    def test_the_rule_refuses_it(self, campaign, core, default_pack):
        territory = core.asset_types.get(label_singular="Territory")
        made = create_campaign_asset(campaign, territory, "Sump Hole")
        assert "has an owner" in cross_pack_refusal(default_pack, made)
        assert cross_pack_refusal(campaign.pack, made) is None

    def test_the_system_types_page_refuses_it_as_a_built_in(
        self, client, campaign, core
    ):
        territory = core.asset_types.get(label_singular="Territory")
        made = create_campaign_asset(campaign, territory, "Sump Hole")
        staff = User.objects.create_user("staff", is_staff=True)
        client.force_login(staff)

        response = client.post(
            f"/n26/authoring/campaign-type/{core.pk}/",
            {
                "act": "built_in",
                "thing_kind": "asset",
                "thing_asset": str(made.pk),
                "amount": "0",
            },
        )

        assert response.status_code == 200
        assert "which has an owner" in response.content.decode()
        assert not core.built_in_members.filter(asset=made).exists()


class TestACounter:
    """A counter every gang tracks: created in the pack, built into the
    campaign's own type at its opening value, and delivered to gangs already playing
    by the propagation pass."""

    def test_it_is_built_into_the_campaigns_own_type_at_its_opening_value(
        self, campaign
    ):
        meat = add_campaign_counter(campaign, "Meat", opening=3)
        assert meat.pack == campaign.pack
        (member,) = campaign.additions.built_in_members.all()
        assert member.counter == meat
        assert member.amount == 3
        assert member.pack == campaign.pack
        assert campaign.additions.built_ins.pack == campaign.pack
        assert sentences(campaign_history(campaign))[-1] == (
            "added the counter Meat, opening at 3"
        )

    def test_a_gang_joining_afterwards_starts_at_the_opening_value(
        self, campaign, gang_type
    ):
        add_campaign_counter(campaign, "Meat", opening=3)
        late = found_gang("Late", gang_type, owner=User.objects.create_user("late"))
        join_campaign(late, campaign)
        assert readings(late) == {"Reputation": 0, "Meat": 3}

    def test_gangs_already_playing_catch_up(
        self, campaign, gang, rival, propagating, task_queue
    ):
        with task_queue.capture():
            add_campaign_counter(campaign, "Meat", opening=3)
        task_queue.deliver_all()

        assert readings(gang) == {"Reputation": 0, "Meat": 3}
        assert readings(rival) == {"Reputation": 0, "Meat": 3}
        caught_up = LedgerEvent.objects.filter(
            gang=gang, kind=LedgerEvent.Kind.CAUGHT_UP
        )
        assert [event.assignment.assignable.name for event in caught_up] == ["Meat"]
        membership = gang.campaign_memberships.get(left__isnull=True)
        assert caught_up.get().assignment.caused_by == membership.additions_carrier
        assert_reconciled(gang)

    def test_the_sheet_shows_the_column_before_the_pass_and_the_values_after(
        self, campaign, gang, propagating, task_queue
    ):
        with task_queue.capture():
            add_campaign_counter(campaign, "Meat", opening=3)
        sheet = render_campaign(campaign)
        assert sheet.counter_columns == ["Reputation", "Meat"]
        (line,) = sheet.gangs
        assert [c.value if c else None for c in line.counters] == [0, None]

        task_queue.deliver_all()

        (line,) = render_campaign(campaign).gangs
        assert [c.value if c else None for c in line.counters] == [0, 3]

    def test_a_name_the_pack_already_uses_is_refused(self, campaign):
        add_campaign_counter(campaign, "Meat")
        with pytest.raises(Refusal, match="already has a counter called"):
            add_campaign_counter(campaign, "meat")
        assert Counter.objects.filter(pack=campaign.pack).count() == 1

    def test_a_counter_the_shared_type_already_gives_is_refused(self, campaign):
        """Reputation is the system pack's and every gang already has it;
        a second one in the campaign's pack would read the same and share
        its column on the gangs table."""
        with pytest.raises(Refusal, match="already has a counter called"):
            add_campaign_counter(campaign, "reputation")
        assert not Counter.objects.filter(pack=campaign.pack).exists()


class TestALabel:
    """A question every gang picks one option for: a slot type, its
    pickables, a picklist and a gang-hosted slot, all in the campaign's
    pack and built into the additions."""

    def test_it_writes_the_four_rows_into_the_pack(self, campaign):
        slot = add_campaign_label(campaign, "Alignment", ["Law Abiding", "Outlaw"])
        pack = campaign.pack
        assert slot.pack == pack and slot.choice_label == "Alignment"
        assert slot.slot_type == SlotType.objects.get(pack=pack, name="Alignment")
        assert slot.picklist.pack == pack
        assert [
            str(m.pickable) for m in slot.picklist.members.order_by("position")
        ] == [
            "Law Abiding",
            "Outlaw",
        ]
        assert Pickable.objects.filter(pack=pack).count() == 2
        (member,) = campaign.additions.built_in_members.all()
        assert member.slot == slot
        assert sentences(campaign_history(campaign))[-1] == (
            "added the label Alignment, with the options Law Abiding, Outlaw"
        )

    def test_two_labels_may_share_an_option(self, campaign):
        add_campaign_label(campaign, "Alignment", ["None", "Outlaw"])
        add_campaign_label(campaign, "Allegiance", ["None", "Guild"])
        assert Pickable.objects.filter(pack=campaign.pack, name="None").count() == 2

    def test_a_question_already_asked_is_refused(self, campaign):
        add_campaign_label(campaign, "Alignment", ["Outlaw"])
        with pytest.raises(Refusal, match="already has a label called"):
            add_campaign_label(campaign, "alignment", ["Law Abiding"])
        assert Slot.objects.filter(pack=campaign.pack).count() == 1

    def test_every_gang_gains_the_question_and_its_owner_picks(
        self, campaign, gang, gang_type, propagating, task_queue
    ):
        with task_queue.capture():
            slot = add_campaign_label(campaign, "Alignment", ["Law Abiding", "Outlaw"])
        task_queue.deliver_all()
        late = found_gang("Late", gang_type, owner=User.objects.create_user("late"))
        join_campaign(late, campaign)

        for member in (gang, late):
            (choice,) = render_gang(member).choices
            assert choice.kind_label == "Alignment"
            assert not choice.chosen

        asked = gang.assignments.get(slot=slot, archived=False)
        outlaw = Pickable.objects.get(pack=campaign.pack, name="Outlaw")
        choose(asked, outlaw)

        (choice,) = render_gang(gang).choices
        assert choice.chosen == "Outlaw"
        # The label is a column of the gangs table, filled with each
        # gang's pick and a dash where a gang has not picked yet.
        sheet = render_campaign(campaign)
        assert sheet.label_columns == ["Alignment"]
        assert {line.name: line.labels for line in sheet.gangs} == {
            gang.name: ["Outlaw"],
            late.name: [""],
        }
        assert_reconciled(gang)


class TestTheArbitratorsControlsOnThePage:
    """Four small pages, the arbitrator's alone, each landing back on the
    part of the campaign page where what it added shows."""

    @pytest.fixture(autouse=True)
    def flag(self, open_to_everyone):
        return open_to_everyone

    def test_the_arbitrator_sees_the_controls_and_a_player_does_not(
        self, client, campaign, gang
    ):
        """What the arbitrator adds shows where it lands — a counter as a
        column of the gangs table — and the controls that add more sit on
        those headings, for the arbitrator alone."""
        add_campaign_counter(campaign, "Meat", opening=3)
        page = reverse("n26-campaign", args=[campaign.pk])

        client.force_login(campaign.owner)
        body = client.get(page).content.decode()
        assert 'id="additions"' not in body
        assert "Meat" in body
        for name in (
            "n26-campaign-add-asset-type",
            "n26-campaign-add-counter",
            "n26-campaign-add-label",
        ):
            assert reverse(name, args=[campaign.pk]) in body
        assert reverse("n26-campaign-new-asset", args=[campaign.pk]) + "?type=" in body

        client.force_login(gang.owner)
        body = client.get(page).content.decode()
        assert "Meat" in body
        for name in (
            "n26-campaign-add-asset-type",
            "n26-campaign-add-counter",
            "n26-campaign-add-label",
            "n26-campaign-new-asset",
        ):
            assert reverse(name, args=[campaign.pk]) not in body

    def test_the_pages_are_the_arbitrators_alone(self, client, campaign, gang):
        client.force_login(gang.owner)
        for name in (
            "n26-campaign-add-asset-type",
            "n26-campaign-new-asset",
            "n26-campaign-add-counter",
            "n26-campaign-add-label",
        ):
            address = reverse(name, args=[campaign.pk])
            assert client.get(address).status_code == 404
            assert client.post(address, {"name": "Meat"}).status_code == 404

    def test_adding_an_asset_type(self, client, campaign):
        client.force_login(campaign.owner)
        response = client.post(
            reverse("n26-campaign-add-asset-type", args=[campaign.pk]),
            {
                "label_singular": "Racket",
                "label_plural": "Rackets",
                "ownership": "pooled",
            },
        )
        assert response.status_code == 302
        assert response["Location"].endswith("#assets")
        assert (
            AssetType.objects.get(campaign_type=campaign.additions).plural == "Rackets"
        )

    def test_creating_an_asset_under_an_asset_type_picked_in_the_address(
        self, client, campaign, core
    ):
        territory = core.asset_types.get(label_singular="Territory")
        client.force_login(campaign.owner)
        address = reverse("n26-campaign-new-asset", args=[campaign.pk])

        body = client.get(f"{address}?type={territory.pk}").content.decode()
        assert f'value="{territory.pk}"' in body
        assert "checked" in body

        response = client.post(
            address,
            {
                "asset_type": str(territory.pk),
                "name": "Sump Hole",
                "annotation": "",
                "income": "15",
            },
        )
        assert response.status_code == 302
        made = Asset.objects.get(name="Sump Hole")
        assert made.pack == campaign.pack and made.income == 15

    def test_a_refusal_lands_on_the_form(self, client, campaign):
        add_campaign_counter(campaign, "Meat")
        client.force_login(campaign.owner)
        response = client.post(
            reverse("n26-campaign-add-counter", args=[campaign.pk]),
            {"name": "Meat", "opening": "3"},
        )
        assert response.status_code == 200
        assert "already has a counter called Meat" in response.content.decode()
        assert Counter.objects.filter(pack=campaign.pack).count() == 1

    def test_adding_a_counter_and_a_label(self, client, campaign):
        client.force_login(campaign.owner)
        client.post(
            reverse("n26-campaign-add-counter", args=[campaign.pk]),
            {"name": "Meat", "opening": "3"},
        )
        response = client.post(
            reverse("n26-campaign-add-label", args=[campaign.pk]),
            {"name": "Alignment", "options": "Law Abiding\n\n Outlaw \n"},
        )
        assert response.status_code == 302
        # The pages wrote onto their own copy of the campaign's own type;
        # this one still believes it has no built-ins set.
        campaign.refresh_from_db()
        members = campaign.additions.built_in_members.order_by("position")
        assert [str(m.assignable) for m in members] == ["Meat", "Alignment"]
        assert [str(p) for p in Pickable.objects.filter(pack=campaign.pack)] == [
            "Law Abiding",
            "Outlaw",
        ]

    def test_options_listed_twice_are_refused(self, client, campaign):
        client.force_login(campaign.owner)
        response = client.post(
            reverse("n26-campaign-add-label", args=[campaign.pk]),
            {"name": "Alignment", "options": "Outlaw\noutlaw"},
        )
        assert response.status_code == 200
        assert "outlaw is listed twice." in response.content.decode()
        assert not Slot.objects.filter(pack=campaign.pack).exists()


class TestTheCampaignsOwnTypeIsInvisible:
    """The campaign type that holds what the arbitrator adds wears the
    campaign's name and is nobody's to found on or author against, so no
    staff listing names it and the founding form never offers it."""

    @pytest.fixture(autouse=True)
    def flag(self, open_to_everyone):
        return open_to_everyone

    def test_the_authoring_listing_and_menu_leave_it_out(self, client, campaign, core):
        staff = User.objects.create_user("staff", is_staff=True)
        client.force_login(staff)

        listing = client.get("/n26/authoring/campaign-type/").content.decode()
        assert "Territory campaign" in listing
        assert f"/n26/authoring/campaign-type/{core.pk}/" in listing
        assert f"/n26/authoring/campaign-type/{campaign.additions.pk}/" not in listing

        menu = client.get("/n26/authoring/").content.decode()
        # The count beside the kind is of the shared types alone.
        assert CampaignType.objects.count() == 2
        assert "Dust Falls" not in menu

    def test_a_sibling_switcher_leaves_it_out(self, client, campaign, core):
        staff = User.objects.create_user("staff", is_staff=True)
        client.force_login(staff)
        page = client.get(f"/n26/authoring/campaign-type/{core.pk}/").content.decode()
        assert f"/n26/authoring/campaign-type/{campaign.additions.pk}/" not in page

    def test_the_founding_form_never_offers_it(self, client, campaign, arbitrator):
        client.force_login(arbitrator)
        body = client.get("/n26/campaigns/new/").content.decode()
        assert f'value="{campaign.additions.pk}"' not in body


class TestTheArbitratorTallies:
    """The one act on a gang that is not its owner's: the arbitrator moving
    a campaign counter on any gang at the table, from the campaign page."""

    @pytest.fixture(autouse=True)
    def flag(self, open_to_everyone):
        return open_to_everyone

    def reputation_of(self, gang):
        (line,) = [
            line
            for line in render_gang(gang).campaign.counters
            if line.name == "Reputation"
        ]
        return line

    def test_the_arbitrator_moves_a_campaign_counter(self, client, campaign, gang):
        client.force_login(campaign.owner)
        page = reverse("n26-campaign", args=[campaign.pk])
        body = client.get(page).content.decode()
        assert "Add one to Reputation" in body

        response = client.post(
            reverse("n26-tally", args=[self.reputation_of(gang).assignment_id]),
            {"change": "1", "back": page + "#gangs"},
        )

        assert response.status_code == 302
        assert response["Location"] == page + "#gangs"
        assert self.reputation_of(gang).value == 1
        tallied = LedgerEvent.objects.get(gang=gang, kind=LedgerEvent.Kind.TALLIED)
        assert tallied.actor == campaign.owner
        assert tallied.campaign == campaign
        assert_reconciled(gang)

    def test_a_player_gets_no_control_on_another_gang(
        self, client, campaign, gang, rival
    ):
        client.force_login(rival.owner)
        body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
        # Their own row carries the control; the other gang's does not.
        assert body.count("Add one to Reputation") == 1
        response = client.post(
            reverse("n26-tally", args=[self.reputation_of(gang).assignment_id]),
            {"change": "1"},
        )
        assert response.status_code == 404
        assert self.reputation_of(gang).value == 0

    def test_the_arbitrator_may_not_move_a_gangs_own_counter(
        self, client, campaign, gang, default_pack
    ):
        from n26.library.authoring import create_counter
        from n26.tests.sandbox.actions import assign

        kills = assign(create_counter("Kill Count"), gang=gang)
        client.force_login(campaign.owner)
        response = client.post(reverse("n26-tally", args=[kills.pk]), {"change": "1"})
        assert response.status_code == 404

    def test_another_arbitrator_has_no_say(self, client, campaign, gang, core):
        other = User.objects.create_user("other")
        found_campaign("Elsewhere", core, owner=other)
        client.force_login(other)
        response = client.post(
            reverse("n26-tally", args=[self.reputation_of(gang).assignment_id]),
            {"change": "1"},
        )
        assert response.status_code == 404
