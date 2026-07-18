"""Golden-equivalence test for the campaign assets page."""

from __future__ import annotations

import pytest
from django.db import models
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/campaign/assets/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _asset_types_queryset(campaign):
    """Rebuild the asset-types queryset exactly as the view GET branch does."""
    from gyrinx.core.models.campaign import CampaignAsset

    campaign_list_ids = campaign.lists.values_list("id", flat=True)
    return campaign.asset_types.prefetch_related(
        models.Prefetch(
            "assets",
            queryset=CampaignAsset.objects.filter(
                models.Q(holder_id__in=campaign_list_ids)
                | models.Q(holder__isnull=True)
            ).select_related("holder", "asset_type"),
        )
    )


def _context(campaign, request):
    return {
        "campaign": campaign,
        "asset_types": _asset_types_queryset(campaign),
        "is_admin": campaign.is_admin(request.user),
    }


@pytest.mark.django_db
def test_campaign_assets_matches_legacy(user, make_user, make_campaign, make_list):
    from gyrinx.core.models.campaign import (
        CampaignAsset,
        CampaignAssetType,
        CampaignSubAsset,
    )

    campaign = make_campaign("Underhive Wars")

    # A fully-populated asset type: description, property + sub-asset schemas.
    territories = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        description="Areas of the <em>underhive</em>",
        property_schema=[
            {"key": "boon", "label": "Boon"},
            {"key": "income", "label": "Income"},
        ],
        sub_asset_schema={
            "structure": {"label": "Structure", "label_plural": "Structures"},
            "worker": {"label": "Worker", "label_plural": "Workers"},
        },
        owner=user,
    )

    # A held asset with description, properties and sub-assets.
    holder = make_list("Cawdor Redemptionists")
    campaign.lists.add(holder)
    the_sump = CampaignAsset.objects.create(
        asset_type=territories,
        name="The Sump",
        description="A grim watering hole",
        holder=holder,
        properties={"boon": "Wealth", "income": "D6"},
        owner=user,
    )
    CampaignSubAsset.objects.create(
        parent_asset=the_sump,
        sub_asset_type="structure",
        name="Generator Hall",
        owner=user,
    )
    CampaignSubAsset.objects.create(
        parent_asset=the_sump, sub_asset_type="worker", name="Ratskin Guide", owner=user
    )

    # An unheld asset with no description/properties (Unowned branch).
    CampaignAsset.objects.create(asset_type=territories, name="The Vents", owner=user)

    # An asset type with no assets at all (empty-table branch, no description).
    CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Relic",
        name_plural="Relics",
        owner=user,
    )

    # Admin, active campaign: full admin controls + actions column.
    request = _request(user)
    assert_equivalent(
        "core/campaign/campaign_assets.html", _context(campaign, request), request
    )

    # Non-admin viewer: no admin links, no actions column.
    other = make_user("spectator", "password")
    other_request = _request(other)
    assert_equivalent(
        "core/campaign/campaign_assets.html",
        _context(campaign, other_request),
        other_request,
    )

    # Archived campaign (admin): no "Copy from" link, no actions column.
    campaign.archived = True
    campaign.save()
    request = _request(user)
    assert_equivalent(
        "core/campaign/campaign_assets.html", _context(campaign, request), request
    )


@pytest.mark.django_db
def test_campaign_assets_no_asset_types_matches_legacy(user, make_campaign):
    campaign = make_campaign("Empty Campaign")
    request = _request(user)
    assert_equivalent(
        "core/campaign/campaign_assets.html", _context(campaign, request), request
    )
