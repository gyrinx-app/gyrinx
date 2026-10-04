"""Selecting campaign holdings and retrying a submitted batch."""

from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import campaign_operation
from n26.core.models import CampaignAsset, CampaignEvent
from n26.flags import CAMPAIGNS
from n26.library.authoring import add_asset_type, create_asset
from n26.library.models import AssetType
from n26.tests.sandbox.actions import found_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def batch(client, campaign_type):
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
    owner = User.objects.create_user("batch-arbitrator")
    campaign = found_campaign("Batch review", campaign_type, owner=owner)
    kind = add_asset_type(
        campaign_type,
        "Territory",
        AssetType.Ownership.HOLDING,
        label_plural="Territories",
    )
    assets = [create_asset("Old Ruins", kind), create_asset("Market", kind)]
    client.force_login(owner)
    return campaign, kind, assets


def post(client, batch, **changes):
    campaign, kind, assets = batch
    return client.post(
        reverse("n26-campaign-add-asset", args=[campaign.pk]) + f"?type={kind.pk}",
        {
            "asset": [str(asset.pk) for asset in assets],
            "request_key": str(uuid4()),
            **changes,
        },
    )


class TestBatchSelection:
    def test_the_selected_assets_are_added_together_and_unclaimed(self, client, batch):
        response = post(client, batch)
        assert response.status_code == 302
        campaign, _, assets = batch
        holdings = list(CampaignAsset.objects.filter(campaign=campaign))
        assert {holding.asset_id for holding in holdings} == {
            asset.pk for asset in assets
        }
        assert all(holding.holder_id is None for holding in holdings)
        events = CampaignEvent.objects.filter(
            campaign=campaign, kind=CampaignEvent.Kind.ASSET_ADDED
        )
        assert events.count() == 2
        assert len(set(events.values_list("batch", flat=True))) == 1

    def test_a_repeated_post_does_not_add_or_record_a_second_batch(self, client, batch):
        key = str(uuid4())
        post(client, batch, request_key=key)
        campaign, _, _ = batch
        before = campaign.events.count()
        response = post(client, batch, request_key=key)
        assert response.status_code == 302
        assert campaign.campaign_assets.count() == 2
        assert campaign.events.count() == before

    def test_retrying_after_removal_does_not_recreate_the_holdings(self, client, batch):
        key = str(uuid4())
        post(client, batch, request_key=key)
        campaign, _, _ = batch
        with campaign_operation(campaign, actor=campaign.owner) as act:
            for holding in campaign.campaign_assets.all():
                act.remove_asset(holding)
        post(client, batch, request_key=key)
        assert not campaign.campaign_assets.exists()

    def test_another_visit_can_add_another_copy(self, client, batch):
        post(client, batch)
        post(client, batch)
        assert batch[0].campaign_assets.count() == 4

    def test_a_name_is_refused_for_multiple_assets_without_a_partial_write(
        self, client, batch
    ):
        response = post(client, batch, name="Both territories")
        assert response.status_code == 200
        assert "Select one asset" in response.content.decode()
        assert not batch[0].campaign_assets.exists()

    def test_a_single_selection_keeps_its_optional_name(self, client, batch):
        response = post(client, batch, asset=[str(batch[2][0].pk)], name="By the sump")
        assert response.status_code == 302
        assert batch[0].campaign_assets.get().name == "By the sump"

    def test_each_selected_asset_can_have_its_own_name(self, client, batch):
        first, second = batch[2]
        response = post(
            client,
            batch,
            **{
                f"name_{first.pk}": " By the sump ",
                f"name_{second.pk}": "Eastern market",
            },
        )
        assert response.status_code == 302
        holdings = batch[0].campaign_assets
        assert holdings.get(asset=first).name == "By the sump"
        assert holdings.get(asset=second).name == "Eastern market"
        key = batch[0].events.first().batch
        post(client, batch, request_key=str(key), **{f"name_{first.pk}": "Retry name"})
        assert holdings.count() == 2
        assert holdings.get(asset=first).name == "By the sump"

    def test_blank_names_keep_the_library_names(self, client, batch):
        first, second = batch[2]
        assert (
            post(
                client, batch, **{f"name_{first.pk}": " ", f"name_{second.pk}": ""}
            ).status_code
            == 302
        )
        assert all(not holding.name for holding in batch[0].campaign_assets.all())

    def test_an_invalid_name_rejects_the_batch_and_preserves_each_draft(
        self, client, batch
    ):
        first, second = batch[2]
        response = post(
            client,
            batch,
            **{
                f"name_{first.pk}": "x" * 201,
                f"name_{second.pk}": "Eastern market",
            },
        )
        assert response.status_code == 200
        assert not batch[0].campaign_assets.exists()
        props = response.context["selection"]
        by_id = {item["value"]: item for item in props["options"]}
        assert by_id[str(first.pk)]["name"] == "x" * 201
        assert by_id[str(first.pk)]["nameErrors"]
        assert by_id[str(second.pk)]["name"] == "Eastern market"

    def test_an_invalid_member_rejects_the_whole_selection(self, client, batch):
        response = post(
            client, batch, asset=[str(batch[2][0].pk), "01ARZ3NDEKTSV4RRFFQ69G5FAV"]
        )
        assert response.status_code == 200
        assert not batch[0].campaign_assets.exists()

    def test_the_page_title_is_plural_and_does_not_repeat_the_type_heading(
        self, client, batch
    ):
        campaign, kind, _ = batch
        response = client.get(
            reverse("n26-campaign-add-asset", args=[campaign.pk]) + f"?type={kind.pk}"
        )
        html = response.content.decode()
        assert "Add territories" in html
        assert "The territories this campaign deals in" not in html
        assert 'type="checkbox"' in html
        assert 'name="request_key"' in html

    def test_an_unrelated_account_cannot_add_a_batch(self, client, batch):
        client.force_login(User.objects.create_user("other-player"))
        assert post(client, batch).status_code == 404
        assert not batch[0].campaign_assets.exists()
