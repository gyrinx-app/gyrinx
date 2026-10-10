"""An arbitrator edits the asset types their campaign added itself.

The labels can change at any time. Ownership fixes how every asset of the
type behaves, so it is fixed once the type has any assets. Asset types that
come with the campaign type are library content and are not edited here.
"""

import pytest
from bs4 import BeautifulSoup
from django.apps import apps
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import campaign_operation
from n26.core.history import campaign_history
from n26.core.models import CampaignEvent
from n26.core.operations import Refusal
from n26.core.views.campaigns import more_actions
from n26.flags import CAMPAIGNS
from n26.library.core_campaign import seed_core_campaign
from n26.library.models import AssetType, CampaignType, DefaultAssignment
from n26.tests.sandbox.actions import (
    add_campaign_asset_type,
    create_campaign_asset,
    create_campaign_table,
    found_campaign,
    found_gang,
    join_campaign,
)

pytestmark = pytest.mark.django_db

HOLDING = AssetType.Ownership.HOLDING
POSSESSION = AssetType.Ownership.POSSESSION


@pytest.fixture(autouse=True)
def open_to_everyone(db):
    return FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )


@pytest.fixture
def core(default_pack):
    seed_core_campaign(apps)
    return CampaignType.objects.get(name="Territory campaign")


@pytest.fixture
def campaign(core):
    owner = User.objects.create_user("arbitrator")
    return found_campaign("Dust Falls", core, owner=owner, budget=1000)


@pytest.fixture
def racket(campaign):
    return add_campaign_asset_type(campaign, "Rakit", plural="Rakits")


def sentences(acts):
    return ["".join(span.text for span in act.spans) for act in acts]


def edit(campaign, asset_type, label, ownership, plural=""):
    with campaign_operation(campaign, actor=campaign.owner) as act:
        return act.edit_asset_type(asset_type, label, ownership, label_plural=plural)


def edit_url(campaign, asset_type):
    return reverse("n26-campaign-edit-asset-type", args=[campaign.pk, asset_type.pk])


def tab_url(campaign):
    return reverse("n26-edit-campaign", args=[campaign.pk]) + "?tab=asset-types"


class TestEditingAnAssetType:
    def test_new_labels_are_saved_and_logged_with_the_old_name(self, campaign, racket):
        edit(campaign, racket, "Racket", HOLDING, plural="Rackets")
        racket.refresh_from_db()
        assert (racket.label_singular, racket.plural) == ("Racket", "Rackets")
        assert campaign.events.last().kind == CampaignEvent.Kind.ASSET_TYPE_EDITED
        assert sentences(campaign_history(campaign))[-1] == (
            "edited the asset type Rakit, now called Racket"
        )

    def test_a_plural_alone_is_logged_under_the_label(self, campaign, racket):
        edit(campaign, racket, "Rakit", HOLDING, plural="Rakitz")
        assert sentences(campaign_history(campaign))[-1] == (
            "edited the asset type Rakit"
        )

    def test_saving_what_is_there_writes_nothing(self, campaign, racket):
        before = campaign.events.count()
        assert edit(campaign, racket, " Rakit ", HOLDING, plural="Rakits") is None
        assert campaign.events.count() == before

    def test_the_log_names_the_label_as_it_stands_not_as_the_page_read_it(
        self, campaign, racket
    ):
        read_earlier = AssetType.objects.get(pk=racket.pk)
        edit(campaign, racket, "Racket", HOLDING)
        edit(campaign, read_earlier, "Rackit", HOLDING)
        assert sentences(campaign_history(campaign))[-1] == (
            "edited the asset type Racket, now called Rackit"
        )

    def test_ownership_changes_while_the_type_has_no_assets(self, campaign, racket):
        edit(campaign, racket, "Rakit", POSSESSION, plural="Rakits")
        racket.refresh_from_db()
        assert racket.ownership == POSSESSION

    def test_ownership_is_fixed_once_the_type_has_an_asset(self, campaign, racket):
        create_campaign_asset(campaign, racket, "Still")
        with pytest.raises(
            Refusal,
            match="You cannot change the ownership now. Dust Falls already has rakits.",
        ):
            edit(campaign, racket, "Rakit", POSSESSION, plural="Rakits")
        racket.refresh_from_db()
        assert racket.ownership == HOLDING
        # The labels still change.
        edit(campaign, racket, "Racket", HOLDING, plural="Rackets")
        racket.refresh_from_db()
        assert racket.label_singular == "Racket"

    def test_ownership_is_fixed_once_the_type_has_a_table(self, campaign, racket):
        create_campaign_table(campaign, racket, "Rakit table")
        with pytest.raises(
            Refusal,
            match=(
                "You cannot change the ownership now. "
                "Dust Falls already has a table of rakits."
            ),
        ):
            edit(campaign, racket, "Rakit", POSSESSION, plural="Rakits")
        racket.refresh_from_db()
        assert racket.ownership == HOLDING

    def test_an_asset_made_from_an_earlier_read_takes_the_ownership_as_it_is(
        self, campaign, racket
    ):
        read_earlier = AssetType.objects.get(pk=racket.pk)
        edit(campaign, racket, "Rakit", POSSESSION, plural="Rakits")
        still = create_campaign_asset(campaign, read_earlier, "Still")
        assert still.asset_type.ownership == POSSESSION
        assert DefaultAssignment.objects.filter(
            default_set_id=campaign.additions.built_ins_id, asset=still
        ).exists()

    def test_a_table_made_from_an_earlier_read_is_refused_once_inherent(
        self, campaign, racket
    ):
        read_earlier = AssetType.objects.get(pk=racket.pk)
        edit(campaign, racket, "Rakit", POSSESSION, plural="Rakits")
        with pytest.raises(Refusal, match="You cannot make a table of Rakits."):
            create_campaign_table(campaign, read_earlier, "Rakit table")

    def test_a_label_the_campaign_already_uses_is_refused(self, campaign, racket):
        with pytest.raises(Refusal, match="already has an asset type called"):
            edit(campaign, racket, "territory", HOLDING)
        add_campaign_asset_type(campaign, "Hideout")
        with pytest.raises(Refusal, match="already has an asset type called hideout"):
            edit(campaign, racket, "hideout", HOLDING)
        # Its own label in another case is its own, not taken.
        edit(campaign, racket, "RAKIT", HOLDING, plural="Rakits")

    def test_a_blank_label_is_refused(self, campaign, racket):
        with pytest.raises(Refusal, match="Give the asset type a label."):
            edit(campaign, racket, "  ", HOLDING)

    def test_a_shared_asset_type_is_not_the_campaigns_to_edit(self, campaign, core):
        territory = core.asset_types.get(label_singular="Territory")
        with pytest.raises(ValueError):
            edit(campaign, territory, "Turf", HOLDING)


class TestTheAssetTypesTab:
    def test_it_lists_the_campaigns_own_types_and_names_the_shared_ones(
        self, client, campaign, racket
    ):
        add_campaign_asset_type(campaign, "Hideout", ownership=POSSESSION)
        client.force_login(campaign.owner)
        response = client.get(tab_url(campaign))
        assert response.context["tab"] == "asset-types"
        assert response.context["asset_types"] == [
            {
                "label": "Rakit",
                "plural": "Rakits",
                "ownership": "Transferable",
                "href": edit_url(campaign, racket),
            },
            {
                "label": "Hideout",
                "plural": "Hideouts",
                "ownership": "Inherent",
                "href": edit_url(
                    campaign, AssetType.objects.get(label_singular="Hideout")
                ),
            },
        ]
        body = response.content.decode()
        assert (
            "Settlements and Territories come with Territory campaign. "
            "You cannot edit them here."
        ) in body
        assert reverse("n26-campaign-add-asset-type", args=[campaign.pk]) in body
        assert "Save campaign" not in body

    def test_it_says_when_the_campaign_has_none_of_its_own(self, client, campaign):
        client.force_login(campaign.owner)
        body = client.get(tab_url(campaign)).content.decode()
        assert "This campaign has no asset types of its own yet." in body

    def test_the_more_actions_menu_opens_it(self, campaign):
        assert tab_url(campaign) in [
            a.target for a in more_actions(campaign, yours=True)
        ]
        assert tab_url(campaign) not in [
            a.target for a in more_actions(campaign, yours=False)
        ]


class TestTheEditPage:
    def test_it_opens_filled_in_and_saves(self, client, campaign, racket):
        client.force_login(campaign.owner)
        page = client.get(edit_url(campaign, racket))
        assert page.status_code == 200
        soup = BeautifulSoup(page.content, "html.parser")
        assert soup.find("input", {"name": "label_singular"})["value"] == "Rakit"
        assert soup.find("input", {"name": "label_plural"})["value"] == "Rakits"
        checked = soup.find("input", {"name": "ownership", "checked": True})
        assert checked["value"] == HOLDING

        response = client.post(
            edit_url(campaign, racket),
            {"label_singular": "Racket", "label_plural": "", "ownership": HOLDING},
            follow=True,
        )
        assert response.redirect_chain[-1][0] == tab_url(campaign)
        assert "Saved the asset type Racket." in response.content.decode()
        racket.refresh_from_db()
        assert racket.plural == "Rackets"

    def test_an_unchanged_save_says_so(self, client, campaign, racket):
        client.force_login(campaign.owner)
        response = client.post(
            edit_url(campaign, racket),
            {"label_singular": "Rakit", "label_plural": "Rakits", "ownership": HOLDING},
            follow=True,
        )
        assert "Nothing changed." in response.content.decode()

    def test_a_refusal_stays_on_the_form(self, client, campaign, racket):
        client.force_login(campaign.owner)
        response = client.post(
            edit_url(campaign, racket),
            {"label_singular": "Territory", "ownership": HOLDING},
        )
        assert response.status_code == 200
        assert "Dust Falls already has an asset type called Territory." in (
            response.content.decode()
        )

    def test_a_fixed_ownership_is_stated_and_cannot_be_posted(
        self, client, campaign, racket
    ):
        create_campaign_asset(campaign, racket, "Still")
        client.force_login(campaign.owner)
        page = client.get(edit_url(campaign, racket)).content.decode()
        soup = BeautifulSoup(page, "html.parser")
        assert soup.find("input", {"name": "ownership"}) is None
        assert (
            "Transferable. You cannot change this now. Dust Falls already has rakits."
        ) in page

        response = client.post(
            edit_url(campaign, racket),
            {"label_singular": "Racket", "ownership": POSSESSION},
        )
        assert response.status_code == 302
        racket.refresh_from_db()
        assert (racket.label_singular, racket.ownership) == ("Racket", HOLDING)

    def test_a_table_fixes_the_ownership_on_the_page_too(
        self, client, campaign, racket
    ):
        create_campaign_table(campaign, racket, "Rakit table")
        client.force_login(campaign.owner)
        page = client.get(edit_url(campaign, racket)).content.decode()
        soup = BeautifulSoup(page, "html.parser")
        assert soup.find("input", {"name": "ownership"}) is None
        assert (
            "Transferable. You cannot change this now. "
            "Dust Falls already has a table of rakits."
        ) in page

    def test_a_shared_type_has_no_edit_page(self, client, campaign, core):
        territory = core.asset_types.get(label_singular="Territory")
        client.force_login(campaign.owner)
        assert client.get(edit_url(campaign, territory)).status_code == 404

    def test_the_pages_are_the_arbitrators_alone(
        self, client, campaign, racket, gang_type
    ):
        player = User.objects.create_user("player")
        join_campaign(found_gang("The Ashen Choir", gang_type, owner=player), campaign)
        client.force_login(player)
        assert client.get(tab_url(campaign)).status_code == 404
        assert client.get(edit_url(campaign, racket)).status_code == 404
        response = client.post(
            edit_url(campaign, racket),
            {"label_singular": "Mine", "ownership": HOLDING},
        )
        assert response.status_code == 404
        racket.refresh_from_db()
        assert racket.label_singular == "Rakit"
