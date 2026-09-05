"""Handing a copy between gangs, and what the arbitrator adds to a campaign.

A transfer is one token changing hands under the campaign's line, then a
journal-only event on each gang inside it — the copy went from one, the
copy came to the other — so both histories say what happened.

The arbitrator's additions are library content written into the campaign's
own pack and onto its additions type: a kind of asset, an asset under one
of the campaign's kinds, a counter every gang tracks, a label every gang
picks. Nothing here touches the shared type, and nothing reaches another
campaign. A counter or a label built into the additions reaches gangs
already playing through the same propagation pass a gang type's built-ins
take, marked as caught up. See design/campaign-assets.md.
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
from n26.library.authoring import add_asset_kind, create_asset, create_campaign_type
from n26.library.core_campaign import seed_core_campaign
from n26.library.forms import cross_pack_refusal
from n26.library.models import (
    Asset,
    AssetKind,
    CampaignType,
    Counter,
    Pickable,
    Slot,
    SlotType,
)
from n26.tests.sandbox.actions import (
    add_asset,
    add_campaign_counter,
    add_campaign_label,
    add_kind,
    choose,
    create_campaign_asset,
    found_campaign,
    found_gang,
    grant_asset,
    join_campaign,
    transfer_asset,
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
    territory = core.asset_kinds.get(label_singular="Territory")
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
def token(campaign, old_ruins, gang):
    """One copy of Old Ruins, held by the player's gang."""
    return grant_asset(add_asset(campaign, old_ruins), gang)


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
    """One token changing hands, two records: the loser's says the copy
    went, the receiver's says it came."""

    def test_the_holder_changes(self, token, gang, rival):
        moved = transfer_asset(token, rival)
        assert moved.holder.gang == rival
        assert not gang.assignments.filter(asset=token.asset).exists()
        assert not rival.assignments.filter(asset=token.asset).exists()

    def test_each_gang_gets_its_record(self, token, gang, rival, campaign):
        transfer_asset(token, rival)
        (granted, lost) = holding_events(gang)
        assert (granted.kind, lost.kind) == (
            LedgerEvent.Kind.GRANTED,
            LedgerEvent.Kind.TOOK_AWAY,
        )
        (received,) = holding_events(rival)
        assert received.kind == LedgerEvent.Kind.GRANTED
        for event in (lost, received):
            assert event.campaign == campaign
            assert event.campaign_asset == token
            assert event.assignment is None
            assert (event.credits_delta, event.rating_delta) == (0, 0)
        assert_reconciled(gang)
        assert_reconciled(rival)

    def test_both_histories_and_the_log_read_plainly(
        self, token, gang, rival, campaign
    ):
        transfer_asset(token, rival)
        assert (
            sentences(build(gang))[-1]
            == "took the territory Old Ruins away from the gang"
        )
        assert (
            sentences(build(rival))[-1] == "granted the territory Old Ruins to the gang"
        )
        acts = campaign_history(campaign)
        told = [
            (act.gang_name, sentence)
            for act, sentence in zip(acts, sentences(acts), strict=True)
        ]
        assert told[-2:] == [
            ("The Ashen Choir", "took the territory Old Ruins away from the gang"),
            ("The Rust Kings", "granted the territory Old Ruins to the gang"),
        ]
        assert acts[-1].actor == "arbitrator"

    def test_the_holding_moves_with_the_copy(self, token, gang, rival):
        assert [line.name for line in render_gang(gang).campaign.holdings] == [
            "Old Ruins"
        ]
        transfer_asset(token, rival)
        assert render_gang(gang).campaign.holdings == []
        assert [line.name for line in render_gang(rival).campaign.holdings] == [
            "Old Ruins"
        ]

    def test_a_copy_nobody_holds_cannot_be_handed_over(
        self, campaign, old_ruins, rival
    ):
        unclaimed = add_asset(campaign, old_ruins)
        with pytest.raises(Refusal, match="not held by any gang"):
            transfer_asset(unclaimed, rival)

    def test_handing_a_copy_to_the_gang_holding_it_is_refused(self, token, gang):
        with pytest.raises(Refusal, match="already holds"):
            transfer_asset(token, gang)
        assert holding_events(gang)[-1].kind == LedgerEvent.Kind.GRANTED

    def test_a_gang_outside_the_campaign_is_a_callers_mistake(
        self, token, gang_type, arbitrator, core
    ):
        other = found_campaign("Elsewhere", core, owner=arbitrator)
        stranger = found_gang("Strangers", gang_type, owner=arbitrator)
        membership = join_campaign(stranger, other)
        from n26.core.campaigns import campaign_operation

        with pytest.raises(ValueError):
            with campaign_operation(token.campaign, actor=arbitrator) as act:
                act.transfer(token, membership)


class TestTransferOnThePage:
    """The arbitrator transfers; the holding gang's owner hands over;
    nobody else is offered either."""

    @pytest.fixture(autouse=True)
    def flag(self, open_to_everyone):
        return open_to_everyone

    def address(self, token):
        return reverse(
            "n26-campaign-asset-transfer", args=[token.campaign_id, token.pk]
        )

    def test_the_arbitrator_sees_transfer(self, client, token, campaign, rival):
        client.force_login(campaign.owner)
        body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
        assert self.address(token) in body
        assert "Transfer" in body
        assert "Hand over" not in body

    def test_the_holding_gangs_owner_sees_hand_over(
        self, client, token, gang, campaign
    ):
        client.force_login(gang.owner)
        body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
        assert self.address(token) in body
        assert "Hand over" in body

    def test_another_player_sees_neither(self, client, token, rival, campaign):
        client.force_login(rival.owner)
        body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
        assert self.address(token) not in body
        assert client.get(self.address(token)).status_code == 404

    def test_the_form_offers_every_other_gang(self, client, token, gang, rival):
        client.force_login(gang.owner)
        body = client.get(self.address(token)).content.decode()
        assert "Hand over Old Ruins" in body
        assert "The Rust Kings" in body
        assert 'value="' + str(token.holder_id) + '"' not in body

    def test_the_owner_hands_the_copy_over(self, client, token, gang, rival, campaign):
        client.force_login(gang.owner)
        membership = rival.campaign_memberships.get(left__isnull=True)

        response = client.post(
            self.address(token), {"membership": str(membership.pk)}, follow=True
        )

        token.refresh_from_db()
        assert token.holder == membership
        assert "Old Ruins went from The Ashen Choir to The Rust Kings." in (
            response.content.decode()
        )
        assert holding_events(rival)[-1].actor == gang.owner

    def test_a_stale_link_to_an_unclaimed_copy_says_so(
        self, client, campaign, old_ruins
    ):
        unclaimed = add_asset(campaign, old_ruins)
        client.force_login(campaign.owner)
        response = client.get(self.address(unclaimed), follow=True)
        assert "Old Ruins is not held by any gang." in response.content.decode()


class TestAKindOfAsset:
    def test_it_lands_on_the_additions_in_the_campaigns_pack(self, campaign):
        racket = add_kind(campaign, "Racket", plural="Rackets")
        assert racket.campaign_type == campaign.additions
        assert racket.pack == campaign.pack
        assert racket.is_pooled
        assert campaign.events.last().kind == CampaignEvent.Kind.KIND_ADDED
        assert sentences(campaign_history(campaign))[-1] == (
            "added the kind of asset Racket"
        )

    def test_a_label_the_campaign_already_uses_is_refused(self, campaign):
        with pytest.raises(Refusal, match="already has a kind of asset called"):
            add_kind(campaign, "territory")
        add_kind(campaign, "Racket")
        with pytest.raises(Refusal, match="Racket"):
            add_kind(campaign, "Racket")

    def test_the_sheet_gains_a_column_and_a_table(self, campaign, gang):
        add_kind(campaign, "Racket", plural="Rackets")
        sheet = render_campaign(campaign)
        assert [kind.plural for kind in sheet.asset_kinds] == [
            "Settlements",
            "Territories",
            "Rackets",
        ]
        assert [table.plural for table in sheet.assets] == ["Territories", "Rackets"]
        assert [line.name for line in sheet.added.kinds] == ["Racket"]
        assert sheet.added.kinds[0].detail == "changes hands"


class TestAnAsset:
    def test_it_lands_in_the_campaigns_pack_under_a_shared_kind(
        self, campaign, core, gang
    ):
        territory = core.asset_kinds.get(label_singular="Territory")
        made = create_campaign_asset(
            campaign, territory, "Sump Hole", annotation="flooded", income=15
        )
        assert made.pack == campaign.pack
        assert made.kind == territory
        assert made.income == 15
        assert str(made) == "Sump Hole (flooded)"
        assert not made.modifiers.exists()
        assert sentences(campaign_history(campaign))[-1] == (
            "created the asset Sump Hole (flooded)"
        )

    def test_it_can_be_added_as_a_copy_and_granted(self, campaign, core, gang):
        territory = core.asset_kinds.get(label_singular="Territory")
        made = create_campaign_asset(campaign, territory, "Sump Hole", income=15)
        copy = grant_asset(add_asset(campaign, made), gang)
        table = next(
            t for t in render_campaign(campaign).assets if t.label == "Territory"
        )
        assert [(c.name, c.income, c.holder) for c in table.copies] == [
            ("Sump Hole", 15, "The Ashen Choir")
        ]
        assert copy.held

    def test_it_can_be_under_the_arbitrators_own_kind(self, campaign):
        racket = add_kind(campaign, "Racket")
        made = create_campaign_asset(campaign, racket, "Protection", income=10)
        assert made.kind == racket
        assert [
            (line.name, line.detail) for line in render_campaign(campaign).added.assets
        ] == [("Protection", "Racket · income 10¢")]

    def test_a_name_the_pack_already_uses_is_refused(self, campaign, core):
        territory = core.asset_kinds.get(label_singular="Territory")
        create_campaign_asset(campaign, territory, "Sump Hole")
        with pytest.raises(Refusal, match="already has an asset called"):
            create_campaign_asset(campaign, territory, "sump hole")

    def test_another_campaign_on_the_same_type_never_sees_it(
        self, client, campaign, core, open_to_everyone
    ):
        """An asset written under the shared Territory kind belongs to the
        campaign whose pack it is in. A second campaign founded on the same
        type is not offered it, and cannot add a copy of it by hand."""
        territory = core.asset_kinds.get(label_singular="Territory")
        private = create_campaign_asset(campaign, territory, "Sump Hole")
        other_arbitrator = User.objects.create_user("other")
        other = found_campaign("Elsewhere", core, owner=other_arbitrator)
        client.force_login(other_arbitrator)

        address = reverse("n26-campaign-add-asset", args=[other.pk])
        assert "Sump Hole" not in client.get(address).content.decode()
        response = client.post(address, {"asset": str(private.pk)})
        assert response.status_code == 200
        assert "not one this campaign deals in" in str(response.context["form"].errors)
        assert not other.pool.exists()

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

    def test_another_types_kind_is_a_callers_mistake(self, campaign, default_pack):
        dominion = create_campaign_type("Dominion")
        kind = add_asset_kind(dominion, "Relic", "pooled")
        with pytest.raises(ValueError):
            create_campaign_asset(campaign, kind, "The Skull")


class TestSystemContentNeverPointsAtAnArbitratorsAsset:
    """Pack content may reference system content; the reverse is refused
    by the authoring forms. An arbitrator's asset is pack content."""

    def test_the_rule_refuses_it(self, campaign, core, default_pack):
        territory = core.asset_kinds.get(label_singular="Territory")
        made = create_campaign_asset(campaign, territory, "Sump Hole")
        assert "has an owner" in cross_pack_refusal(default_pack, made)
        assert cross_pack_refusal(campaign.pack, made) is None

    def test_the_system_types_page_refuses_it_as_a_built_in(
        self, client, campaign, core
    ):
        territory = core.asset_kinds.get(label_singular="Territory")
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
    additions at its opening value, and delivered to gangs already playing
    by the propagation pass."""

    def test_it_is_built_into_the_additions_at_its_opening_value(self, campaign):
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
        assert [
            (a.name, a.detail) for a in render_campaign(campaign).added.counters
        ] == [("Meat", "opens at 3")]

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
        assert [(a.name, a.detail) for a in render_campaign(campaign).added.labels] == [
            ("Alignment", "Law Abiding, Outlaw")
        ]
        assert_reconciled(gang)


class TestTheAdditionsOnThePage:
    """Four small pages, the arbitrator's alone, each landing back on the
    campaign page's additions section."""

    @pytest.fixture(autouse=True)
    def flag(self, open_to_everyone):
        return open_to_everyone

    def test_the_arbitrator_sees_the_section_and_a_player_does_not(
        self, client, campaign, gang
    ):
        add_campaign_counter(campaign, "Meat", opening=3)
        page = reverse("n26-campaign", args=[campaign.pk])

        client.force_login(campaign.owner)
        body = client.get(page).content.decode()
        assert 'id="additions"' in body
        assert "opens at 3" in body
        for name in (
            "n26-campaign-add-kind",
            "n26-campaign-new-asset",
            "n26-campaign-add-counter",
            "n26-campaign-add-label",
        ):
            assert reverse(name, args=[campaign.pk]) in body

        client.force_login(gang.owner)
        body = client.get(page).content.decode()
        assert 'id="additions"' not in body
        assert reverse("n26-campaign-add-counter", args=[campaign.pk]) not in body

    def test_the_pages_are_the_arbitrators_alone(self, client, campaign, gang):
        client.force_login(gang.owner)
        for name in (
            "n26-campaign-add-kind",
            "n26-campaign-new-asset",
            "n26-campaign-add-counter",
            "n26-campaign-add-label",
        ):
            address = reverse(name, args=[campaign.pk])
            assert client.get(address).status_code == 404
            assert client.post(address, {"name": "Meat"}).status_code == 404

    def test_adding_a_kind(self, client, campaign):
        client.force_login(campaign.owner)
        response = client.post(
            reverse("n26-campaign-add-kind", args=[campaign.pk]),
            {"label_singular": "Racket", "label_plural": "Rackets", "mode": "pooled"},
        )
        assert response.status_code == 302
        assert response["Location"].endswith("#additions")
        assert (
            AssetKind.objects.get(campaign_type=campaign.additions).plural == "Rackets"
        )

    def test_creating_an_asset_under_a_kind_picked_in_the_address(
        self, client, campaign, core
    ):
        territory = core.asset_kinds.get(label_singular="Territory")
        client.force_login(campaign.owner)
        address = reverse("n26-campaign-new-asset", args=[campaign.pk])

        body = client.get(f"{address}?kind={territory.pk}").content.decode()
        assert f'value="{territory.pk}"' in body
        assert "checked" in body

        response = client.post(
            address,
            {
                "kind": str(territory.pk),
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
        # The pages wrote onto their own copy of the additions; this one
        # still believes the type has no built-ins set.
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
