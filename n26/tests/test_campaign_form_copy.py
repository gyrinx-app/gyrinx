"""Campaign form wording and ownership cards remain readable and consistent."""

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.forms import AddAssetTypeForm, AddCounterForm, AddLabelForm
from n26.flags import CAMPAIGNS
from n26.library.authoring import add_asset_type
from n26.library.models import AssetType
from n26.tests.sandbox.actions import found_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def campaign(client, campaign_type):
    owner = User.objects.create_user("arbitrator")
    client.force_login(owner)
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
    return found_campaign("Dust Falls", campaign_type, owner=owner)


def page(client, route, campaign):
    response = client.get(reverse(route, args=[campaign.pk]))
    assert response.status_code == 200
    return BeautifulSoup(response.content, "html.parser")


class TestCampaignFormCopy:
    def test_counter_has_a_reputation_example_and_starting_value(
        self, client, campaign
    ):
        form = AddCounterForm()
        assert form.fields["name"].help_text == 'e.g. "Reputation".'
        assert form.fields["opening"].label == "Starting value"
        assert not form.fields["opening"].help_text
        text = page(client, "n26-campaign-add-counter", campaign).get_text(
            " ", strip=True
        )
        assert "A value every gang in the campaign tracks, such as Reputation." in text
        assert 'e.g. "Reputation".' in text
        assert "Starting value" in text
        assert "Opening value" not in text
        assert "What every gang starts at." not in text

    def test_label_has_a_faction_example_and_one_sentence_lead(self, client, campaign):
        assert AddLabelForm().fields["name"].help_text == (
            'What the choice is called, e.g. "Faction".'
        )
        text = page(client, "n26-campaign-add-label", campaign).get_text(
            " ", strip=True
        )
        assert (
            "An optional set of categories gangs can be placed into, such as factions."
            in text
        )
        assert 'e.g. "Faction".' in text
        assert "Alignment" not in text

    def test_player_action_says_invite(self, client, campaign):
        document = page(client, "n26-campaign", campaign)
        invite = document.find(
            "a", href=reverse("n26-campaign-add-player", args=[campaign.pk])
        )
        assert invite is not None
        assert invite.get_text(" ", strip=True) == "Invite players"


class TestOwnershipCopy:
    def test_new_labels_keep_the_stored_values(self):
        expected = [("held-one-each", "Inherent"), ("pooled", "Transferable")]
        assert AssetType.Ownership.choices == expected
        assert list(AddAssetTypeForm().fields["ownership"].choices) == expected
        for value, label in expected:
            assert AssetType(ownership=value).get_ownership_display() == label

    def test_missing_ownership_names_the_visible_choices(self):
        form = AddAssetTypeForm({"label_singular": "Territory"})
        assert not form.is_valid()
        assert form.errors["ownership"] == ["Select Inherent or Transferable."]

    def test_ownership_cards_wrap_the_full_descriptions(self, client, campaign):
        document = page(client, "n26-campaign-add-asset-type", campaign)
        expected = {
            "pooled": (
                "Transferable",
                "One gang holds it at a time, and it can change hands.",
            ),
            "held-one-each": ("Inherent", "Every gang has its own."),
        }
        radios = document.select('input[type="radio"][name="ownership"]')
        assert len(radios) == 2
        for radio in radios:
            card = radio.find_parent("label")
            title, description = expected[radio["value"]]
            assert title in card.get_text(" ", strip=True)
            assert description in card.get_text(" ", strip=True)
            assert not card.select(".truncate")

    def test_asset_type_cards_wrap_and_use_the_same_labels(self, client, campaign):
        for ownership in AssetType.Ownership:
            add_asset_type(
                campaign.campaign_type,
                f"A long asset type name with {ownership.label.lower()} ownership",
                ownership,
            )
        document = page(client, "n26-campaign-new-asset", campaign)
        radios = document.select('input[type="radio"][name="asset_type"]')
        assert len(radios) == 2
        for radio in radios:
            card = radio.find_parent("label")
            asset_type = AssetType.objects.get(pk=radio["value"])
            description = f"{campaign.campaign_type} · {asset_type.get_ownership_display().lower()}"
            assert description in card.get_text(" ", strip=True)
            assert not card.select(".truncate")

    def test_assets_empty_state_uses_transferable(self, client, campaign):
        text = page(client, "n26-campaign", campaign).get_text(" ", strip=True)
        assert "has no transferable asset types." in text
        assert "Holding ownership" not in text

    def test_tables_empty_state_uses_inherent(self, client, campaign):
        add_asset_type(
            campaign.campaign_type, "Settlement", AssetType.Ownership.POSSESSION
        )
        text = page(client, "n26-campaign-tables", campaign).get_text(" ", strip=True)
        assert "is inherent. Each gang has its own assets" in text
        assert "possession" not in text
