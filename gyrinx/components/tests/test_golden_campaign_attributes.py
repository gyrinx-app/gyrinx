"""Golden-equivalence test: campaign attributes page matches its legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.campaign import (
    CampaignAttributeType,
    CampaignAttributeValue,
    CampaignListAttributeAssignment,
)


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _build_context(campaign, user):
    """Reproduce the ``campaign_attributes`` view GET-branch context."""
    attribute_types = campaign.attribute_types.prefetch_related(
        "values",
        "values__list_assignments",
        "values__list_assignments__list",
    ).order_by("name")

    is_admin = campaign.is_admin(user)
    user_lists = campaign.lists.filter(owner=user)
    user_list_ids = set(user_lists.values_list("id", flat=True))

    assignment_lookup = {}
    for attr_type in attribute_types:
        type_assignments = {}
        for value in attr_type.values.all():
            for assignment in value.list_assignments.all():
                type_assignments.setdefault(assignment.list_id, []).append(assignment)
        assignment_lookup[attr_type.id] = type_assignments

    campaign_lists = campaign.lists.order_by("name")
    single_select_attribute_types = [
        at for at in attribute_types if at.is_single_select
    ]

    return {
        "campaign": campaign,
        "attribute_types": attribute_types,
        "single_select_attribute_types": single_select_attribute_types,
        "campaign_lists": campaign_lists,
        "is_admin": is_admin,
        "user_lists": user_lists,
        "user_list_ids": user_list_ids,
        "assignment_lookup": assignment_lookup,
    }


@pytest.mark.django_db
def test_campaign_attributes_matches_legacy(user, make_campaign, make_list):
    campaign = make_campaign("Underhive Wars")

    # Two gangs in the campaign — one with a theme colour, one without — so the
    # gang cells exercise both branches of {% list_with_theme %}.
    list_a = make_list("Alpha Gang", owner=user, theme_color="#123456")
    list_b = make_list("Bravo Gang", owner=user)
    campaign.lists.add(list_a, list_b)

    # Multi-select type with a value + assignment (excluded from group dropdown).
    alliances = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Alliances",
        is_single_select=False,
        owner=user,
    )
    coalition = CampaignAttributeValue.objects.create(
        attribute_type=alliances, name="Coalition", owner=user
    )
    CampaignListAttributeAssignment.objects.create(
        campaign=campaign, attribute_value=coalition, list=list_b, owner=user
    )

    # Single-select type with a description + coloured/uncoloured values.
    faction = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        description="Choose your allegiance",
        is_single_select=True,
        owner=user,
    )
    order = CampaignAttributeValue.objects.create(
        attribute_type=faction, name="Order", colour="#FF5733", owner=user
    )
    CampaignAttributeValue.objects.create(
        attribute_type=faction, name="Chaos", owner=user
    )
    CampaignListAttributeAssignment.objects.create(
        campaign=campaign, attribute_value=order, list=list_a, owner=user
    )

    # Single-select type with no values yet (empty-values branch), still in the
    # group dropdown.
    CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Team",
        is_single_select=True,
        owner=user,
    )

    # A chosen group attribute marks one dropdown option as selected.
    campaign.group_attribute_type = faction
    campaign.save()

    request = _request(user)
    context = _build_context(campaign, user)
    assert_equivalent("core/campaign/campaign_attributes.html", context, request)
