"""A campaign's assets: who holds them, and what holding one does for
the gang.

An asset whose type's ownership is Holding is a holding, not a possession.
The campaign owns the asset; its row says which gang holds it. The gang
never owns it — no assignment, no ledger entry, nothing on its rating — and
assigning or unassigning is the holder changing under the campaign's line
plus a journal-only GAINED or LOST event on the gang. While held, the
campaign's asset is a carrier on the gang's card: its library asset's
modifiers run, credited to it, so a Reputation contribution raises the reading
and a rule appears among the gang's rules for as long as the gang holds it.
See design/campaign-assets.md.
"""

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.history import build, campaign_history
from n26.core.models import CampaignAsset, CampaignEvent, LedgerEvent
from n26.core.operations import Refusal
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_gang
from n26.library.authoring import (
    create_asset,
    create_rule,
    ef_adds,
    ef_contributes_to_counter,
    modifier,
    targets_every_model,
    targets_gang,
)
from n26.library.core_campaign import seed_core_campaign
from n26.library.models import Asset, CampaignType, Counter
from n26.tests.sandbox.actions import (
    add_asset,
    assign_asset,
    found_campaign,
    found_gang,
    hire,
    join_campaign,
    remove_asset,
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
    """The Territory campaign type as it ships: Reputation at 0, a Settlement built
    in, and Territory as its Holding asset type."""
    seed_core_campaign(apps)
    return CampaignType.objects.get(name="Territory campaign")


@pytest.fixture
def old_ruins(core):
    """A territory with Reputation and a named rule that apply while it is held."""
    territory = core.asset_types.get(label_singular="Territory")
    asset = create_asset("Old Ruins", territory, income=30)
    reputation = Counter.objects.get(name="Reputation")
    modifier(
        "Old Ruins: Reputation",
        targets_gang(),
        ef_contributes_to_counter(reputation, 1),
        attach_to=asset,
    )
    modifier(
        "Old Ruins: Salvage",
        targets_gang(),
        ef_adds(create_rule("Salvage")),
        attach_to=asset,
    )
    return asset


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
def campaign_assets(campaign, old_ruins):
    """Old Ruins twice over, the second with a name of its own in this
    campaign."""
    return [
        add_asset(campaign, old_ruins),
        add_asset(campaign, old_ruins, name="Old Ruins by the sump"),
    ]


def sentences(acts):
    return ["".join(span.text for span in act.spans) for act in acts]


def reputation(gang):
    block = render_gang(gang).campaign
    return next(line.value for line in block.counters if line.name == "Reputation")


class TestTheCampaignsAssets:
    """Adding and removing assets are the campaign's own acts: no gang is
    touched, and only the campaign's log records them."""

    def test_both_sit_unclaimed(self, campaign_assets, campaign):
        pool = list(campaign.campaign_assets.all())
        assert [str(campaign_asset) for campaign_asset in pool] == [
            "Old Ruins",
            "Old Ruins by the sump",
        ]
        assert all(
            campaign_asset.holder is None and not campaign_asset.held
            for campaign_asset in pool
        )
        assert [campaign_asset.asset.name for campaign_asset in pool] == [
            "Old Ruins",
            "Old Ruins",
        ]

    def test_the_log_says_what_was_added(self, campaign_assets, campaign):
        assert sentences(campaign_history(campaign))[-2:] == [
            "added the asset Old Ruins",
            "added the asset Old Ruins by the sump",
        ]
        assert LedgerEvent.objects.filter(campaign=campaign).count() == 0

    def test_a_possession_cannot_be_added(self, campaign, core):
        settlement = Asset.objects.get(name="Settlement")
        with pytest.raises(ValueError, match="every gang has its own"):
            add_asset(campaign, settlement)

    def test_an_unclaimed_asset_can_be_removed(self, campaign_assets, campaign):
        remove_asset(campaign_assets[1])
        assert [
            str(campaign_asset) for campaign_asset in campaign.campaign_assets.all()
        ] == ["Old Ruins"]
        assert (
            campaign.events.filter(kind=CampaignEvent.Kind.ASSET_REMOVED).get().note
            == "Old Ruins by the sump"
        )
        assert sentences(campaign_history(campaign))[-1] == (
            "removed the asset Old Ruins by the sump"
        )

    def test_a_held_asset_is_not_removed(self, campaign_assets, gang, campaign):
        assign_asset(campaign_assets[0], gang)
        with pytest.raises(Refusal, match="Unassign it first"):
            remove_asset(campaign_assets[0])
        assert campaign.campaign_assets.count() == 2

    def test_archiving_the_asset_retracts_nothing(
        self, campaign_assets, gang, old_ruins
    ):
        """The campaign lists every asset it has whether or not the library
        still offers it: archiving hides it from new additions only."""
        assign_asset(campaign_assets[0], gang)
        old_ruins.archive()
        pool = list(campaign_assets[0].campaign.campaign_assets.select_related("asset"))
        assert len(pool) == 2
        assert reputation(gang) == 1


class TestAssigningAndUnassigning:
    """Assigning is one column changing under the campaign's line and a
    journal-only event on the gang, GAINED; unassigning is the reverse,
    LOST. Neither moves money."""

    def test_assigning_records_the_holder_and_nothing_else(
        self, campaign_assets, gang, old_ruins
    ):
        campaign_asset = assign_asset(campaign_assets[0], gang)
        assert campaign_asset.holder.gang == gang
        assert campaign_asset.held
        # The Settlement is an assignment; the territory never is.
        assert not gang.assignments.filter(asset=old_ruins).exists()

    def test_the_gang_gets_a_journal_only_event(self, campaign_assets, gang, campaign):
        assign_asset(campaign_assets[0], gang)
        event = LedgerEvent.objects.get(
            gang=gang, kind=LedgerEvent.Kind.GAINED, campaign_asset__isnull=False
        )
        assert event.campaign_asset == campaign_assets[0]
        assert event.assignment is None and event.miniature is None
        assert event.campaign == campaign
        assert (event.credits_delta, event.rating_delta, event.trade_points_delta) == (
            0,
            0,
            0,
        )
        assert event.about == campaign_assets[0]
        gang.refresh_from_db()
        assert gang.rating == 0
        assert_reconciled(gang)

    def test_both_histories_tell_the_gain(
        self, campaign_assets, gang, campaign, arbitrator
    ):
        """The gang's history says what the gang gained, with the actor in
        front as every line has; the campaign's log says where the asset
        went, naming the gang in the sentence and nobody as the actor."""
        assign_asset(campaign_assets[0], gang)
        gang_acts = build(gang)
        assert sentences(gang_acts)[-1] == "gained the territory Old Ruins"
        assert gang_acts[-1].actor == "arbitrator"
        acts = campaign_history(campaign)
        assert sentences(acts)[-1] == "Old Ruins went to The Ashen Choir"
        assert acts[-1].gang_name == ""
        assert acts[-1].actor == ""
        # The asset's name leads to this exact holding, in both.
        anchor = reverse(
            "n26-campaign-asset", args=[campaign.pk, campaign_assets[0].pk]
        )
        assert gang_acts[-1].spans[1].href == anchor
        assert acts[-1].spans[0].href == anchor

    def test_an_asset_another_gang_holds_is_refused(self, campaign_assets, gang, rival):
        assign_asset(campaign_assets[0], gang)
        with pytest.raises(Refusal, match="held by The Ashen Choir"):
            assign_asset(campaign_assets[0], rival)

    def test_assigning_the_same_asset_again_writes_nothing(self, campaign_assets, gang):
        assign_asset(campaign_assets[0], gang)
        assign_asset(campaign_assets[0], gang)
        assert (
            LedgerEvent.objects.filter(
                gang=gang, campaign_asset=campaign_assets[0]
            ).count()
            == 1
        )

    def test_unassigning_frees_the_asset_and_says_so(
        self, campaign_assets, gang, campaign
    ):
        assign_asset(campaign_assets[0], gang)
        campaign_asset = unassign_asset(campaign_assets[0])
        assert campaign_asset.holder is None
        event = LedgerEvent.objects.get(gang=gang, kind=LedgerEvent.Kind.LOST)
        assert event.campaign_asset == campaign_assets[0]
        assert event.campaign == campaign
        assert sentences(build(gang))[-1] == "lost the territory Old Ruins"
        assert sentences(campaign_history(campaign))[-1] == (
            "The Ashen Choir lost Old Ruins"
        )
        assert_reconciled(gang)

    def test_unassigning_an_unclaimed_asset_changes_nothing(
        self, campaign_assets, gang
    ):
        assert unassign_asset(campaign_assets[0]) is None
        assert not LedgerEvent.objects.filter(gang=gang, campaign_asset__isnull=False)

    def test_a_removed_asset_keeps_its_place_in_the_history(
        self, campaign_assets, gang
    ):
        """The campaign's asset goes, the event's link to it goes with it,
        and the note still names what the gang gained and lost."""
        assign_asset(campaign_assets[1], gang)
        unassign_asset(campaign_assets[1])
        remove_asset(campaign_assets[1])
        told = sentences(build(gang))
        assert told[-2:] == [
            "gained Old Ruins by the sump",
            "lost Old Ruins by the sump",
        ]
        assert LedgerEvent.objects.filter(gang=gang).count() >= 2


class TestWhatHoldingDoes:
    """The holding gang's card reads the campaign's asset as a carrier: the
    library asset's computed effects run while it is held and stop when it
    is unassigned, each credited to the campaign's asset by name and type."""

    def test_reputation_reads_one_while_held_and_nought_after(
        self, campaign_assets, gang
    ):
        assert reputation(gang) == 0
        assign_asset(campaign_assets[0], gang)
        assert reputation(gang) == 1
        unassign_asset(campaign_assets[0])
        assert reputation(gang) == 0

    def test_two_assets_count_twice(self, campaign_assets, gang):
        assign_asset(campaign_assets[0], gang)
        assign_asset(campaign_assets[1], gang)
        assert reputation(gang) == 2

    def test_the_rule_shows_among_the_gangs_rules_credited_to_the_asset(
        self, campaign_assets, gang
    ):
        assign_asset(campaign_assets[1], gang)
        sheet = render_gang(gang)
        (salvage,) = [line for line in sheet.rules if line.name == "Salvage"]
        assert salvage.provenance.source == "Old Ruins by the sump"
        assert salvage.provenance.source_kind == "territory"
        assert salvage.provenance.computed
        unassign_asset(campaign_assets[1])
        assert "Salvage" not in [line.name for line in render_gang(gang).rules]

    def test_the_holding_is_drawn_under_the_campaign_with_its_income(
        self, campaign_assets, gang
    ):
        assign_asset(campaign_assets[1], gang)
        block = render_gang(gang).campaign
        assert [(h.type_label, h.name, h.income) for h in block.holdings] == [
            ("Territory", "Old Ruins by the sump", 30)
        ]
        assert block.holdings[0].campaign_asset_id == str(campaign_assets[1].pk)
        # Held, never owned: the gang's own rows do not list it.
        assert "Old Ruins by the sump" not in [row.name for row in block.lines]

    def test_a_modifier_aimed_at_every_model_reaches_the_fighters(
        self, campaign_assets, gang, old_ruins, make_profile, make_statline
    ):
        """The campaign's asset rides each member's card as the gang's guest, so a
        rule the territory gives every model shows on the fighter's card
        — and goes when the territory does."""
        modifier(
            "Old Ruins: Scavengers",
            targets_every_model(),
            ef_adds(create_rule("Scavenger")),
            attach_to=old_ruins,
        )
        profile = make_profile("Ganger", price=50)
        make_statline(profile, movement=5)
        hire(gang, profile, "Vex")
        assign_asset(campaign_assets[0], gang)
        (vex,) = render_gang(gang).models
        assert "Scavenger" in [line.name for line in vex.rules]
        unassign_asset(campaign_assets[0])
        (vex,) = render_gang(gang).models
        assert "Scavenger" not in [line.name for line in vex.rules]

    def test_the_stored_value_is_untouched(self, campaign_assets, gang):
        """A contribution is read, never written: the counter's own value
        stays at what the type opened it at."""
        assign_asset(campaign_assets[0], gang)
        counter = gang.assignments.get(counter__name="Reputation")
        assert counter.counter_value.value == 0

    def test_the_page_draws_it(self, client, campaign_assets, gang):
        assign_asset(campaign_assets[0], gang)
        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "Old Ruins" in body
        assert "income 30¢" not in body
        assert "Territories" in body
        assert (
            next(
                line.value
                for line in render_gang(gang).campaign.counters
                if line.name == "Income"
            )
            == 30
        )
        assert "Salvage" in body


class TestTheAssetsOnTheCampaignPage:
    """The campaign page lists every asset under its asset type with its
    holder; the acts are the arbitrator's, and the holding gang's owner may
    hand an asset back."""

    def test_the_gang_sheet_links_the_campaign_and_its_assets(
        self, client, campaign_assets, gang, campaign
    ):
        """A signed-in reader gets the way through to the campaign and to
        the assets section a holding belongs to."""
        assign_asset(campaign_assets[0], gang)
        client.force_login(gang.owner)

        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert reverse("n26-campaign", args=[campaign.pk]) in body
        assert reverse("n26-campaign", args=[campaign.pk]) + "#assets" in body

    def test_a_rolled_holding_keeps_its_income(
        self, client, campaign, old_ruins, arbitrator
    ):
        from n26.core.campaigns import campaign_operation
        from n26.core.render import render_campaign

        with campaign_operation(campaign, actor=arbitrator) as act:
            table = act.create_table(
                old_ruins.asset_type, "Review territory table", "d3"
            )
            act.add_table_entry(table, old_ruins, roll_low=1, roll_high=3)
            roll = act.roll_asset(table, rolled=1)
        (entry,) = render_campaign(campaign).assets[0].entries
        assert entry.campaign_asset_id == str(roll.campaign_asset.pk)
        assert entry.income == 30
        client.force_login(arbitrator)
        html = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
        assert "30¢" in html
        assert "Boons" not in html

    def test_the_page_lists_held_and_unclaimed_by_asset_type(
        self, client, campaign_assets, gang, campaign, arbitrator
    ):
        assign_asset(campaign_assets[0], gang)
        client.force_login(arbitrator)
        body = client.get(reverse("n26-campaign", args=[campaign.pk])).content
        body = body.decode()
        assert "Territories" in body
        assert "The Ashen Choir" in body
        assert "Unclaimed" in body
        assert "Old Ruins by the sump" in body
        assert "30¢" in body
        assert (
            reverse(
                "n26-campaign-asset-unassign", args=[campaign.pk, campaign_assets[0].pk]
            )
            in body
        )
        assert (
            reverse(
                "n26-campaign-asset-assign", args=[campaign.pk, campaign_assets[1].pk]
            )
            in body
        )
        assert "Add territories" in body
        assert "1 held, 1 unclaimed" in body

    def test_a_player_reads_the_assets_without_the_controls(
        self, client, campaign_assets, gang, campaign, player
    ):
        client.force_login(player)
        body = client.get(reverse("n26-campaign", args=[campaign.pk])).content
        body = body.decode()
        assert "Unclaimed" in body
        assert (
            reverse(
                "n26-campaign-asset-assign", args=[campaign.pk, campaign_assets[1].pk]
            )
            not in body
        )
        assert "Add territories" not in body

    def test_the_arbitrator_adds_an_asset(
        self, client, campaign, old_ruins, arbitrator
    ):
        client.force_login(arbitrator)
        response = client.post(
            reverse("n26-campaign-add-asset", args=[campaign.pk]),
            {"asset": str(old_ruins.pk), "name": "Old Ruins by the sump"},
            follow=True,
        )
        assert "Added Old Ruins by the sump." in response.content.decode()
        assert campaign.campaign_assets.count() == 1

    def test_the_add_beside_an_asset_type_offers_that_type_alone(
        self, client, campaign, old_ruins, arbitrator
    ):
        """The Add beside the Territories table narrows the form to
        territories, and says so; an asset type that is not one of the
        campaign's Holding types is ignored rather than refused."""
        from n26.library.authoring import add_asset_type, create_campaign_type

        racket = add_asset_type(campaign.additions, "Racket", "pooled")
        create_asset("Protection", racket)
        client.force_login(arbitrator)
        address = reverse("n26-campaign-add-asset", args=[campaign.pk])

        body = client.get(f"{address}?type={old_ruins.asset_type_id}").content.decode()
        assert "Add territories" in body
        assert "Old Ruins" in body
        assert "Protection" not in body

        other = create_campaign_type("Law & Misrule")
        turf = add_asset_type(other, "Turf", "pooled")
        body = client.get(f"{address}?type={turf.pk}").content.decode()
        assert "Add assets" in body
        assert "Old Ruins" in body
        assert "Protection" in body

    def test_a_settlement_is_not_on_offer(
        self, client, campaign, old_ruins, arbitrator
    ):
        settlement = Asset.objects.get(name="Settlement")
        client.force_login(arbitrator)
        response = client.post(
            reverse("n26-campaign-add-asset", args=[campaign.pk]),
            {"asset": str(settlement.pk), "name": ""},
        )
        body = response.content.decode()
        assert "not one this campaign deals in" in body
        assert campaign.campaign_assets.count() == 0

    def test_the_add_form_offers_every_holding_of_the_campaign(
        self, client, campaign, old_ruins, arbitrator, core
    ):
        """What the form offers is read through the asset types: every
        Holding asset of the campaign's type and of its own additions, and
        nothing of another campaign type or of a Possession type."""
        from n26.library.authoring import add_asset_type, create_campaign_type

        racket = add_asset_type(campaign.additions, "Racket", "pooled")
        protection = create_asset("Protection", racket)
        other = create_campaign_type("Law & Misrule")
        elsewhere = create_asset(
            "Somebody else's turf", add_asset_type(other, "Turf", "pooled")
        )
        client.force_login(arbitrator)

        body = client.get(
            reverse("n26-campaign-add-asset", args=[campaign.pk])
        ).content.decode()

        assert "Old Ruins" in body
        assert "Protection" in body
        assert "Somebody else" not in body
        settlement = Asset.objects.get(name="Settlement")
        assert f'value="{settlement.pk}"' not in body
        assert protection.pack == campaign.pack
        assert elsewhere.asset_type.campaign_type == other

    def test_an_asset_of_another_type_cannot_be_added(self, campaign, old_ruins):
        from n26.library.authoring import add_asset_type, create_campaign_type

        other = create_campaign_type("Law & Misrule")
        elsewhere = create_asset("Turf", add_asset_type(other, "Turf", "pooled"))

        with pytest.raises(ValueError, match="not of this campaign's type"):
            add_asset(campaign, elsewhere)
        assert campaign.campaign_assets.count() == 0

    def test_the_arbitrator_assigns_an_asset(
        self, client, campaign_assets, gang, campaign, arbitrator
    ):
        client.force_login(arbitrator)
        membership = gang.campaign_memberships.get(left__isnull=True)
        response = client.post(
            reverse(
                "n26-campaign-asset-assign", args=[campaign.pk, campaign_assets[0].pk]
            ),
            {"membership": str(membership.pk)},
            follow=True,
        )
        assert "Assigned Old Ruins to The Ashen Choir." in response.content.decode()
        assert CampaignAsset.objects.get(pk=campaign_assets[0].pk).holder == membership

    @pytest.mark.parametrize("action", ["assign", "unassign", "transfer"])
    def test_asset_dialog_keeps_table_preferences_after_opening_and_submitting(
        self, client, campaign_assets, gang, campaign, arbitrator, player, action
    ):
        from n26.core.campaigns import campaign_operation

        target = gang
        if action != "assign":
            assign_asset(campaign_assets[0], gang)
        if action == "transfer":
            target = found_gang("Other gang", gang.gang_type, owner=player)
            join_campaign(target, campaign)
        with campaign_operation(campaign, actor=arbitrator) as op:
            label = op.add_label("Division", ["Upper"])
            op.set_gang_grouping(str(label.pk), {})
        client.force_login(arbitrator)
        page = reverse("n26-campaign", args=[campaign.pk])
        current = page + "?sort=-rating&group="
        sheet = client.get(current).context["sheet"]
        entry = next(
            entry
            for table in sheet.assets
            for entry in table.entries
            if entry.campaign_asset_id == str(campaign_assets[0].pk)
        )
        link = getattr(entry, action + "_href")
        opened = client.get(
            link,
            HTTP_HX_REQUEST="true",
            HTTP_HX_CURRENT_URL="http://testserver" + current,
        )
        assert opened.context["back"] == current + "#assets"
        payload = (
            {}
            if action == "unassign"
            else {
                "membership": str(target.campaign_memberships.get(left__isnull=True).pk)
            }
        )
        response = client.post(
            opened.context["action"],
            payload,
            HTTP_HX_REQUEST="true",
            HTTP_HX_CURRENT_URL="http://testserver" + opened["HX-Replace-Url"],
        )
        assert response.status_code == 200
        assert response["HX-Replace-Url"] == current
        assert response.context["sheet"].table_sort == "-rating"
        assert response.context["sheet"].table_group == ""
        campaign_assets[0].refresh_from_db()
        assert campaign_assets[0].holder_id == (
            None
            if action == "unassign"
            else target.campaign_memberships.get(left__isnull=True).pk
        )

    def test_assignment_opens_as_a_dialog_with_gang_identity_cards(
        self, client, campaign_assets, gang, campaign, arbitrator
    ):
        client.force_login(arbitrator)
        address = reverse(
            "n26-campaign-asset-assign", args=[campaign.pk, campaign_assets[0].pk]
        )
        response = client.get(address, HTTP_HX_REQUEST="true")
        html = response.content.decode()
        assert response["HX-Replace-Url"] == address
        assert 'id="n26-asset-dialog-host" hx-swap-oob="true"' in html
        assert "hx-post=" in html
        assert gang.name in html
        assert gang.gang_type.name in html
        assert gang.owner.username in html
        assert html.count("<legend") == 1
        assert "until it is unassigned" not in html
        assert "<!DOCTYPE" not in html

    def test_an_invalid_dialog_selection_stays_open_without_assigning(
        self, client, campaign_assets, gang, campaign, arbitrator
    ):
        client.force_login(arbitrator)
        address = reverse(
            "n26-campaign-asset-assign", args=[campaign.pk, campaign_assets[0].pk]
        )
        response = client.post(address, {}, HTTP_HX_REQUEST="true")
        assert response.status_code == 200
        assert "Select a gang." in response.content.decode()
        assert 'hx-swap-oob="delete:#n26-asset-dialog"' in response.content.decode()
        campaign_assets[0].refresh_from_db()
        assert campaign_assets[0].holder_id is None

    def test_assigning_from_the_dialog_updates_the_page_and_closes_it(
        self, client, campaign_assets, gang, campaign, arbitrator
    ):
        client.force_login(arbitrator)
        membership = gang.campaign_memberships.get(left__isnull=True)
        address = reverse(
            "n26-campaign-asset-assign", args=[campaign.pk, campaign_assets[0].pk]
        )
        response = client.post(
            address, {"membership": str(membership.pk)}, HTTP_HX_REQUEST="true"
        )
        assert response.status_code == 200
        html = response.content.decode()
        for host in (
            "n26-campaign-assets",
            "n26-campaign-gangs",
            "n26-campaign-log",
            "n26-asset-dialog-host",
        ):
            assert f'id="{host}"' in html
        assert "Assigned Old Ruins to The Ashen Choir." in response["HX-Trigger"]
        assert response["HX-Replace-Url"] == reverse("n26-campaign", args=[campaign.pk])
        campaign_assets[0].refresh_from_db()
        assert campaign_assets[0].holder == membership

    @pytest.mark.parametrize("arbitrating", [True, False])
    def test_unassigning_in_a_dialog_preserves_the_viewers_permissions(
        self, client, campaign_assets, gang, campaign, player, arbitrator, arbitrating
    ):
        assign_asset(campaign_assets[0], gang)
        client.force_login(arbitrator if arbitrating else player)
        at = reverse(
            "n26-campaign-asset-unassign", args=[campaign.pk, campaign_assets[0].pk]
        )
        question = client.get(at, HTTP_HX_REQUEST="true")
        html = question.content.decode()
        assert "The gang's history and campaign log will record this change." in html
        assert "You can immediately reassign this territory." in html
        assert "The asset becomes unclaimed" not in html
        assert 'id="n26-asset-dialog-host" hx-swap-oob="true"' in html
        assert question["HX-Replace-Url"] == at
        response = client.post(at, HTTP_HX_REQUEST="true")
        assert response.status_code == 200
        campaign_assets[0].refresh_from_db()
        assert campaign_assets[0].holder_id is None
        assert "Unassigned Old Ruins from The Ashen Choir." in response["HX-Trigger"]
        html = response.content.decode()
        assert 'id="n26-asset-dialog-host" hx-swap-oob="true"' in html
        add_type = reverse("n26-campaign-add-asset-type", args=[campaign.pk])
        assert (add_type in html) == arbitrating
        assert response["HX-Replace-Url"] == reverse("n26-campaign", args=[campaign.pk])

    def test_the_holding_gangs_owner_hands_an_asset_back(
        self, client, campaign_assets, gang, campaign, player
    ):
        assign_asset(campaign_assets[0], gang)
        client.force_login(player)
        address = reverse(
            "n26-campaign-asset-unassign", args=[campaign.pk, campaign_assets[0].pk]
        )
        assert client.get(address).status_code == 200
        response = client.post(address, follow=True)
        assert "Unassigned Old Ruins from The Ashen Choir." in response.content.decode()
        assert CampaignAsset.objects.get(pk=campaign_assets[0].pk).holder is None

    def test_nobody_else_may_unassign_an_asset(
        self, client, campaign_assets, gang, campaign
    ):
        assign_asset(campaign_assets[0], gang)
        client.force_login(User.objects.create_user("stranger"))
        address = reverse(
            "n26-campaign-asset-unassign", args=[campaign.pk, campaign_assets[0].pk]
        )
        assert client.get(address).status_code == 404
        assert client.post(address).status_code == 404
        assert CampaignAsset.objects.get(pk=campaign_assets[0].pk).held

    @pytest.mark.parametrize("held", [False, True])
    def test_asset_removal_keeps_table_preferences_on_cancel_and_submission(
        self, client, campaign_assets, gang, campaign, arbitrator, held
    ):
        from bs4 import BeautifulSoup

        from n26.core.campaigns import campaign_operation

        with campaign_operation(campaign, actor=arbitrator) as op:
            label = op.add_label("Division", ["Upper"])
            op.set_gang_grouping(str(label.pk), {})
        client.force_login(arbitrator)
        current = reverse("n26-campaign", args=[campaign.pk]) + "?sort=-rating&group="
        sheet = client.get(current).context["sheet"]
        entry = next(
            entry
            for table in sheet.assets
            for entry in table.entries
            if entry.campaign_asset_id == str(campaign_assets[0].pk)
        )
        opened = client.get(entry.remove_href)
        assert opened.context["back"] == current + "#assets"
        soup = BeautifulSoup(opened.content, "html.parser")
        assert soup.find("a", href=current + "#assets").get_text(strip=True) == "Cancel"
        action = soup.find("form", method="post")["action"]
        assert action == entry.remove_href
        if held:
            assign_asset(campaign_assets[0], gang)
        response = client.post(action)
        assert response.status_code == 302
        assert response["Location"] == current + "#assets"
        assert campaign.campaign_assets.count() == (2 if held else 1)

    def test_removing_a_held_asset_is_refused_in_words(
        self, client, campaign_assets, gang, campaign, arbitrator
    ):
        assign_asset(campaign_assets[0], gang)
        client.force_login(arbitrator)
        response = client.post(
            reverse(
                "n26-campaign-asset-remove", args=[campaign.pk, campaign_assets[0].pk]
            ),
            follow=True,
        )
        assert "Unassign it first." in response.content.decode()
        assert campaign.campaign_assets.count() == 2

    def test_every_act_lands_back_on_the_assets_section(
        self, client, campaign_assets, gang, campaign, arbitrator
    ):
        """Assign, unassign and remove all return to the campaign page
        opened at its assets, since that is where the assets are listed."""
        client.force_login(arbitrator)
        membership = gang.campaign_memberships.get(left__isnull=True)
        back = reverse("n26-campaign", args=[campaign.pk]) + "#assets"

        assigned = client.post(
            reverse(
                "n26-campaign-asset-assign", args=[campaign.pk, campaign_assets[0].pk]
            ),
            {"membership": str(membership.pk)},
        )
        assert assigned["Location"] == back
        unassigned = client.post(
            reverse(
                "n26-campaign-asset-unassign", args=[campaign.pk, campaign_assets[0].pk]
            )
        )
        assert unassigned["Location"] == back
        removed = client.post(
            reverse(
                "n26-campaign-asset-remove", args=[campaign.pk, campaign_assets[1].pk]
            ),
            follow=True,
        )
        assert "Removed Old Ruins by the sump." in removed.content.decode()
        assert campaign.campaign_assets.count() == 1


@pytest.fixture
def asset_with_assignment_effect(old_ruins, person_type, gang_type):
    from n26.library.authoring import create_profile, op_adds_model

    profile = create_profile("Additional fighter", person_type, gang_type, price=50)
    modifier(
        "Old Ruins: adds a model",
        targets_gang(),
        op_adds_model(profile),
        attach_to=old_ruins,
    )
    return old_ruins, profile


class TestHoldingArrival:
    """Holding changes write history. Stored effects run only on assignment."""

    def test_gaining_a_holding_records_history_without_hiring_a_model(
        self, campaign, gang, asset_with_assignment_effect
    ):
        from n26.core.models import Miniature

        asset, profile = asset_with_assignment_effect
        token = add_asset(campaign, asset)
        assignment_ids = set(gang.assignments.values_list("pk", flat=True))
        assign_asset(token, gang)
        assign_asset(token, gang)

        assert not Miniature.objects.filter(
            membership__gang=gang, membership__profile=profile
        ).exists()
        assert set(gang.assignments.values_list("pk", flat=True)) == assignment_ids
        event = LedgerEvent.objects.get(gang=gang, campaign_asset=token)
        assert event.kind == LedgerEvent.Kind.GAINED
        assert event.received_asset_type == asset.asset_type_id
        assert event.assignment_id is None
        assert event.miniature_id is None
        assert (event.credits_delta, event.rating_delta, event.trade_points_delta) == (
            0,
            0,
            0,
        )
        assert sentences(build(gang))[-1] == "gained the territory Old Ruins"
        assert_reconciled(gang)

    def test_transferring_a_holding_records_both_histories_without_hiring(
        self, campaign, gang, rival, asset_with_assignment_effect
    ):
        from n26.core.models import Miniature
        from n26.tests.sandbox.actions import transfer_asset

        asset, profile = asset_with_assignment_effect
        token = add_asset(campaign, asset)
        assign_asset(token, gang)
        transfer_asset(token, rival)

        token.refresh_from_db()
        assert token.holder.gang_id == rival.pk
        assert not Miniature.objects.filter(membership__profile=profile).exists()
        lost = LedgerEvent.objects.get(
            gang=gang, campaign_asset=token, kind=LedgerEvent.Kind.LOST
        )
        gained = LedgerEvent.objects.get(
            gang=rival, campaign_asset=token, kind=LedgerEvent.Kind.GAINED
        )
        assert gained.received_asset_type == asset.asset_type_id
        assert gained.batch == lost.batch
        for event in (lost, gained):
            assert event.assignment_id is None
            assert event.miniature_id is None
            assert (event.credits_delta, event.rating_delta) == (0, 0)
        assert sentences(build(gang))[-1] == "lost the territory Old Ruins"
        assert sentences(build(rival))[-1] == "gained the territory Old Ruins"
        assert_reconciled(gang)
        assert_reconciled(rival)

    def test_gaining_and_transferring_fill_each_gangs_starting_allocation(
        self, campaign, gang, rival, asset_with_assignment_effect
    ):
        from n26.core.campaigns import starting_asset_types_received
        from n26.tests.sandbox.actions import transfer_asset

        asset, _ = asset_with_assignment_effect
        memberships = list(campaign.memberships.filter(left__isnull=True))
        assert starting_asset_types_received(campaign, memberships) == {
            membership.pk: set() for membership in memberships
        }

        token = assign_asset(add_asset(campaign, asset), gang)
        transfer_asset(token, rival)
        unassign_asset(token)

        assert starting_asset_types_received(campaign, memberships) == {
            membership.pk: {asset.asset_type_id} for membership in memberships
        }


class TestCampaignSuppression:
    def test_additions_suppress_a_shared_rule_only_in_their_own_campaign(
        self, core, gang_type, arbitrator, player
    ):
        from n26.core.models import Assignment
        from n26.library.authoring import ef_removes
        from n26.tests.sandbox.actions import add_built_in

        shared_rule = create_rule("Shared campaign rule")
        add_built_in(core, shared_rule)
        first = found_campaign("First", core, owner=arbitrator)
        second = found_campaign("Second", core, owner=arbitrator)
        first_gang = found_gang("First gang", gang_type, owner=player)
        second_gang = found_gang("Second gang", gang_type, owner=player)
        join_campaign(first_gang, first)
        join_campaign(second_gang, second)
        assert shared_rule.name in [
            line.name for line in render_gang(first_gang).campaign.lines
        ]
        modifier(
            "Remove the shared rule here",
            targets_gang(),
            ef_removes(shared_rule),
            attach_to=first.additions,
        )
        assert shared_rule.name not in [
            line.name for line in render_gang(first_gang).campaign.lines
        ]
        assert shared_rule.name in [
            line.name for line in render_gang(second_gang).campaign.lines
        ]
        assert Assignment.objects.filter(
            gang=first_gang, rule=shared_rule, archived=False
        ).exists()
