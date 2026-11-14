"""What a campaign feed stores: its section, and the token in its address."""

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from n26.core.models import CampaignFeed
from n26.core.test_campaigns import make_campaign
from n26.library.authoring import add_asset_type
from n26.library.models import AssetType

pytestmark = pytest.mark.django_db


@pytest.fixture
def campaign(campaign_type):
    return make_campaign(
        "Dust Falls", User.objects.create_user("arbitrator"), campaign_type
    )


@pytest.fixture
def territories(campaign_type):
    return add_asset_type(
        campaign_type,
        "Territory",
        AssetType.Ownership.HOLDING,
        label_plural="Territories",
    )


class TestTheToken:
    def test_each_feed_gets_its_own_long_random_token(self, campaign):
        first = CampaignFeed.objects.create(
            campaign=campaign, section="gangs", target="google_sites"
        )
        second = CampaignFeed.objects.create(
            campaign=campaign, section="gangs", target="google_sites"
        )

        assert first.token != second.token
        assert len(first.token) >= 20
        assert first.token not in str(first.pk)


class TestTheSection:
    def test_an_assets_feed_is_named_for_its_asset_type(self, campaign, territories):
        feed = CampaignFeed.objects.create(
            campaign=campaign,
            section="assets",
            asset_type=territories,
            target="google_sites",
        )

        assert feed.section_label == "Territories"

    def test_a_gangs_feed_is_named_for_its_section(self, campaign):
        feed = CampaignFeed(campaign=campaign, section="gangs", target="google_sites")

        assert feed.section_label == "Gangs"

    def test_an_assets_feed_must_name_an_asset_type(self, campaign):
        with pytest.raises(IntegrityError), transaction.atomic():
            CampaignFeed.objects.create(
                campaign=campaign, section="assets", target="google_sites"
            )

    def test_only_an_assets_feed_names_an_asset_type(self, campaign, territories):
        with pytest.raises(IntegrityError), transaction.atomic():
            CampaignFeed.objects.create(
                campaign=campaign,
                section="gangs",
                asset_type=territories,
                target="google_sites",
            )
