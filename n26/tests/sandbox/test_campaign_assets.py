"""A campaign's pool of assets: tokens, who holds them, and what holding
one does for the gang.

A pooled asset is a holding, not a possession. The campaign owns one token
per copy in its pool; the token says which gang holds it. The gang never
owns it — no assignment, no ledger entry, nothing on its rating — and a
grant or a taking away is the token changing hands under the campaign's
line plus a journal-only event on the gang. While held, the token is a
carrier on the gang's card: its asset's modifiers run, credited to the
token, so a Reputation boon raises the reading and a rule appears among
the gang's rules for as long as the gang holds it. See
design/campaign-assets.md.
"""

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.history import build, campaign_history
from n26.core.models import CampaignAsset, CampaignEvent, LedgerEvent
from n26.core.operations import Refusal
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_gang
from n26.flags import CAMPAIGNS
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
    add_to_pool,
    drop_asset,
    found_campaign,
    found_gang,
    grant_asset,
    hire,
    join_campaign,
    take_away_asset,
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
    """The N26 core type as it ships: Reputation at 0, a Settlement built
    in, and Territory as its pooled kind."""
    seed_core_campaign(apps)
    return CampaignType.objects.get(name="N26 core")


@pytest.fixture
def old_ruins(core):
    """A Territory in the core catalogue with the two boons a territory
    can carry: Reputation while held, and a named rule for the gang."""
    territory = core.asset_kinds.get(label_singular="Territory")
    asset = create_asset("Old Ruins", territory, income=30)
    core.assets.add(asset)
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
def tokens(campaign, old_ruins):
    """Two copies of Old Ruins in the pool, the second with a name of
    its own."""
    return [
        add_to_pool(campaign, old_ruins),
        add_to_pool(campaign, old_ruins, name="Old Ruins by the sump"),
    ]


def sentences(acts):
    return ["".join(span.text for span in act.spans) for act in acts]


def reputation(gang):
    block = render_gang(gang).campaign
    return next(line.value for line in block.counters if line.name == "Reputation")


class TestThePool:
    """Adding and dropping copies are the campaign's own acts: no gang is
    touched, and only the campaign's log records them."""

    def test_two_copies_sit_in_the_pool_unclaimed(self, tokens, campaign):
        pool = list(campaign.pool.all())
        assert [str(token) for token in pool] == ["Old Ruins", "Old Ruins by the sump"]
        assert all(token.holder is None and not token.held for token in pool)
        assert [token.asset.name for token in pool] == ["Old Ruins", "Old Ruins"]

    def test_the_log_says_what_was_added(self, tokens, campaign):
        assert sentences(campaign_history(campaign))[-2:] == [
            "added Old Ruins to the pool",
            "added Old Ruins by the sump to the pool",
        ]
        assert LedgerEvent.objects.filter(campaign=campaign).count() == 0

    def test_a_held_one_each_asset_has_no_pool_to_sit_in(self, campaign, core):
        settlement = Asset.objects.get(name="Settlement")
        with pytest.raises(ValueError, match="every gang holds one"):
            add_to_pool(campaign, settlement)

    def test_an_unclaimed_copy_can_be_dropped(self, tokens, campaign):
        drop_asset(tokens[1])
        assert [str(token) for token in campaign.pool.all()] == ["Old Ruins"]
        assert (
            campaign.events.filter(kind=CampaignEvent.Kind.ASSET_DROPPED).get().note
            == "Old Ruins by the sump"
        )
        assert sentences(campaign_history(campaign))[-1] == (
            "dropped Old Ruins by the sump from the pool"
        )

    def test_a_held_copy_is_not_dropped(self, tokens, gang, campaign):
        grant_asset(tokens[0], gang)
        with pytest.raises(Refusal, match="Take it away first"):
            drop_asset(tokens[0])
        assert campaign.pool.count() == 2

    def test_archiving_the_asset_retracts_nothing(self, tokens, gang, old_ruins):
        """A pool lists what it holds whether or not the library still
        offers the asset: archiving hides it from new grants only."""
        grant_asset(tokens[0], gang)
        old_ruins.archive()
        pool = list(tokens[0].campaign.pool.select_related("asset"))
        assert len(pool) == 2
        assert reputation(gang) == 1


class TestGrantingAndTakingAway:
    """A grant is one column changing under the campaign's line and a
    journal-only event on the gang, GRANTED; taking away is the reverse,
    TOOK_AWAY. Neither moves money."""

    def test_a_grant_records_the_holder_and_nothing_else(self, tokens, gang, old_ruins):
        token = grant_asset(tokens[0], gang)
        assert token.holder.gang == gang
        assert token.held
        # The Settlement is an assignment; the territory never is.
        assert not gang.assignments.filter(asset=old_ruins).exists()

    def test_the_gang_gets_a_journal_only_event(self, tokens, gang, campaign):
        grant_asset(tokens[0], gang)
        event = LedgerEvent.objects.get(
            gang=gang, kind=LedgerEvent.Kind.GRANTED, campaign_asset__isnull=False
        )
        assert event.campaign_asset == tokens[0]
        assert event.assignment is None and event.miniature is None
        assert event.campaign == campaign
        assert (event.credits_delta, event.rating_delta, event.trade_points_delta) == (
            0,
            0,
            0,
        )
        assert event.about == tokens[0]
        gang.refresh_from_db()
        assert gang.rating == 0
        assert_reconciled(gang)

    def test_both_histories_tell_the_grant(self, tokens, gang, campaign, arbitrator):
        grant_asset(tokens[0], gang)
        assert (
            sentences(build(gang))[-1] == "granted the territory Old Ruins to the gang"
        )
        acts = campaign_history(campaign)
        assert sentences(acts)[-1] == "granted the territory Old Ruins to the gang"
        assert acts[-1].gang_name == "The Ashen Choir"
        assert acts[-1].actor == "arbitrator"
        # The token's name leads to the pool it belongs to.
        assert acts[-1].spans[1].href == reverse(
            "n26-campaign-pool", args=[campaign.pk]
        )

    def test_a_copy_another_gang_holds_is_refused(self, tokens, gang, rival):
        grant_asset(tokens[0], gang)
        with pytest.raises(Refusal, match="held by The Ashen Choir"):
            grant_asset(tokens[0], rival)

    def test_granting_the_same_copy_again_writes_nothing(self, tokens, gang):
        grant_asset(tokens[0], gang)
        grant_asset(tokens[0], gang)
        assert (
            LedgerEvent.objects.filter(gang=gang, campaign_asset=tokens[0]).count() == 1
        )

    def test_taking_away_returns_the_copy_and_says_so(self, tokens, gang, campaign):
        grant_asset(tokens[0], gang)
        token = take_away_asset(tokens[0])
        assert token.holder is None
        event = LedgerEvent.objects.get(gang=gang, kind=LedgerEvent.Kind.TOOK_AWAY)
        assert event.campaign_asset == tokens[0]
        assert event.campaign == campaign
        assert sentences(build(gang))[-1] == (
            "took the territory Old Ruins away from the gang"
        )
        assert sentences(campaign_history(campaign))[-1] == (
            "took the territory Old Ruins away from the gang"
        )
        assert_reconciled(gang)

    def test_taking_away_an_unclaimed_copy_changes_nothing(self, tokens, gang):
        assert take_away_asset(tokens[0]) is None
        assert not LedgerEvent.objects.filter(gang=gang, campaign_asset__isnull=False)

    def test_a_dropped_copy_keeps_its_place_in_the_history(self, tokens, gang):
        """The token goes, the event's link to it goes with it, and the
        note still names what changed hands."""
        grant_asset(tokens[1], gang)
        take_away_asset(tokens[1])
        drop_asset(tokens[1])
        told = sentences(build(gang))
        assert told[-2:] == [
            "granted Old Ruins by the sump to the gang",
            "took Old Ruins by the sump away from the gang",
        ]
        assert LedgerEvent.objects.filter(gang=gang).count() >= 2


class TestWhatHoldingDoes:
    """The holding gang's card reads the token as a carrier: the asset's
    computed effects run while it is held and stop when it is taken away,
    each credited to the token by name and kind."""

    def test_reputation_reads_one_while_held_and_nought_after(self, tokens, gang):
        assert reputation(gang) == 0
        grant_asset(tokens[0], gang)
        assert reputation(gang) == 1
        take_away_asset(tokens[0])
        assert reputation(gang) == 0

    def test_two_copies_count_twice(self, tokens, gang):
        grant_asset(tokens[0], gang)
        grant_asset(tokens[1], gang)
        assert reputation(gang) == 2

    def test_the_rule_shows_among_the_gangs_rules_credited_to_the_token(
        self, tokens, gang
    ):
        grant_asset(tokens[1], gang)
        sheet = render_gang(gang)
        (salvage,) = [line for line in sheet.rules if line.name == "Salvage"]
        assert salvage.provenance.source == "Old Ruins by the sump"
        assert salvage.provenance.source_kind == "territory"
        assert salvage.provenance.computed
        take_away_asset(tokens[1])
        assert "Salvage" not in [line.name for line in render_gang(gang).rules]

    def test_the_holding_is_drawn_under_the_campaign_with_its_income(
        self, tokens, gang
    ):
        grant_asset(tokens[1], gang)
        block = render_gang(gang).campaign
        assert [(h.kind_label, h.name, h.income) for h in block.holdings] == [
            ("Territory", "Old Ruins by the sump", 30)
        ]
        assert block.holdings[0].campaign_asset_id == str(tokens[1].pk)
        # Held, never owned: the gang's own rows do not list it.
        assert "Old Ruins by the sump" not in [row.name for row in block.lines]

    def test_a_modifier_aimed_at_every_model_reaches_the_fighters(
        self, tokens, gang, old_ruins, make_profile, make_statline
    ):
        """The token rides each member's card as the gang's guest, so a
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
        grant_asset(tokens[0], gang)
        (vex,) = render_gang(gang).models
        assert "Scavenger" in [line.name for line in vex.rules]
        take_away_asset(tokens[0])
        (vex,) = render_gang(gang).models
        assert "Scavenger" not in [line.name for line in vex.rules]

    def test_the_stored_value_is_untouched(self, tokens, gang):
        """A contribution is read, never written: the counter's own value
        stays at what the type opened it at."""
        grant_asset(tokens[0], gang)
        counter = gang.assignments.get(counter__name="Reputation")
        assert counter.counter_value.value == 0

    def test_the_page_draws_it(self, client, tokens, gang):
        grant_asset(tokens[0], gang)
        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "Old Ruins" in body
        assert "income 30¢" in body
        assert "Salvage" in body


class TestThePoolPages:
    """The pool page lists every copy with its holder; the acts are the
    arbitrator's, and the holding gang's owner may hand a copy back."""

    @pytest.fixture(autouse=True)
    def open_to_everyone(self):
        return FeatureFlag.objects.create(
            slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
        )

    def test_the_gang_sheet_links_the_campaign_and_the_pool(
        self, client, tokens, gang, campaign
    ):
        """A reader inside the campaigns feature gets the way through to
        the campaign and to the pool a holding belongs to."""
        grant_asset(tokens[0], gang)
        client.force_login(gang.owner)

        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert reverse("n26-campaign", args=[campaign.pk]) in body
        assert reverse("n26-campaign-pool", args=[campaign.pk]) in body

    def test_the_pool_lists_held_and_unclaimed_by_kind(
        self, client, tokens, gang, campaign, arbitrator
    ):
        grant_asset(tokens[0], gang)
        client.force_login(arbitrator)
        body = client.get(reverse("n26-campaign-pool", args=[campaign.pk])).content
        body = body.decode()
        assert "Territories" in body
        assert "The Ashen Choir" in body
        assert "Unclaimed" in body
        assert "Old Ruins by the sump" in body
        assert "income 30¢" in body
        assert "Take away" in body
        assert "Grant" in body

    def test_a_player_reads_the_pool_without_the_controls(
        self, client, tokens, gang, campaign, player
    ):
        client.force_login(player)
        body = client.get(reverse("n26-campaign-pool", args=[campaign.pk])).content
        body = body.decode()
        assert "Unclaimed" in body
        assert "Grant" not in body
        assert "Add to pool" not in body

    def test_the_arbitrator_adds_a_copy(self, client, campaign, old_ruins, arbitrator):
        client.force_login(arbitrator)
        response = client.post(
            reverse("n26-campaign-pool-add", args=[campaign.pk]),
            {"asset": str(old_ruins.pk), "name": "Old Ruins by the sump"},
            follow=True,
        )
        assert "Added Old Ruins by the sump to the pool." in response.content.decode()
        assert campaign.pool.count() == 1

    def test_a_settlement_is_not_on_offer(
        self, client, campaign, old_ruins, arbitrator
    ):
        settlement = Asset.objects.get(name="Settlement")
        client.force_login(arbitrator)
        response = client.post(
            reverse("n26-campaign-pool-add", args=[campaign.pk]),
            {"asset": str(settlement.pk), "name": ""},
        )
        body = response.content.decode()
        assert "not in this campaign" in body and "catalogue" in body
        assert campaign.pool.count() == 0

    def test_the_arbitrator_grants_a_copy(
        self, client, tokens, gang, campaign, arbitrator
    ):
        client.force_login(arbitrator)
        membership = gang.campaign_memberships.get(left__isnull=True)
        response = client.post(
            reverse("n26-campaign-asset-grant", args=[campaign.pk, tokens[0].pk]),
            {"membership": str(membership.pk)},
            follow=True,
        )
        assert "Granted Old Ruins to The Ashen Choir." in response.content.decode()
        assert CampaignAsset.objects.get(pk=tokens[0].pk).holder == membership

    def test_the_holding_gangs_owner_hands_a_copy_back(
        self, client, tokens, gang, campaign, player
    ):
        grant_asset(tokens[0], gang)
        client.force_login(player)
        address = reverse(
            "n26-campaign-asset-take-away", args=[campaign.pk, tokens[0].pk]
        )
        assert client.get(address).status_code == 200
        response = client.post(address, follow=True)
        assert "Took Old Ruins away from The Ashen Choir." in response.content.decode()
        assert CampaignAsset.objects.get(pk=tokens[0].pk).holder is None

    def test_nobody_else_may_take_a_copy_away(self, client, tokens, gang, campaign):
        grant_asset(tokens[0], gang)
        client.force_login(User.objects.create_user("stranger"))
        address = reverse(
            "n26-campaign-asset-take-away", args=[campaign.pk, tokens[0].pk]
        )
        assert client.get(address).status_code == 404
        assert client.post(address).status_code == 404
        assert CampaignAsset.objects.get(pk=tokens[0].pk).held

    def test_dropping_a_held_copy_is_refused_in_words(
        self, client, tokens, gang, campaign, arbitrator
    ):
        grant_asset(tokens[0], gang)
        client.force_login(arbitrator)
        response = client.post(
            reverse("n26-campaign-asset-drop", args=[campaign.pk, tokens[0].pk]),
            follow=True,
        )
        assert "Take it away first." in response.content.decode()
        assert campaign.pool.count() == 2

    def test_the_campaign_page_leads_to_the_pool(self, client, tokens, gang, campaign):
        grant_asset(tokens[0], gang)
        client.force_login(campaign.owner)
        body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
        assert "2 assets in the pool" in body
        assert "1 held, 1 unclaimed" in body
        assert reverse("n26-campaign-pool", args=[campaign.pk]) in body
