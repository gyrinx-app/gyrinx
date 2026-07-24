"""Sorting the campaign page's Gangs table (#1459)."""

import uuid

import pytest
from django.urls import reverse

from gyrinx.core.models.campaign import (
    CampaignAttributeType,
    CampaignAttributeValue,
    CampaignListAttributeAssignment,
    CampaignListResource,
    CampaignResourceType,
)
from gyrinx.core.models.list import List


@pytest.fixture
def gangs(campaign, make_list):
    """Three gangs whose name, rating and wealth orderings are all different.

    +--------+--------+-------+---------+--------+
    | Gang   | Rating | Stash | Credits | Wealth |
    +--------+--------+-------+---------+--------+
    | Alpha  |    300 |     0 |      50 |    350 |
    | Bravo  |    100 |   400 |       0 |    500 |
    | Charlie|    200 |     0 |       0 |    200 |
    +--------+--------+-------+---------+--------+
    """
    figures = {
        "Alpha": (300, 0, 50),
        "Bravo": (100, 400, 0),
        "Charlie": (200, 0, 0),
    }
    lists = {}
    for name, (rating, stash, credits) in figures.items():
        lst = make_list(name)
        campaign.lists.add(lst)
        # The cost figures are cached columns — set them directly rather than
        # building fighters and equipment to hit a particular total.
        List.objects.filter(pk=lst.pk).update(
            rating_current=rating, stash_current=stash, credits_current=credits
        )
        lists[name] = lst
    return lists


def gang_names(response):
    """The gang names in the order the Gangs table will render them."""
    return [lst.name for lst in response.context["sorted_lists"]]


def get_campaign(client, campaign, **params):
    url = reverse("core:campaign", args=(campaign.id,))
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    return client.get(url)


@pytest.mark.django_db
def test_default_sort_is_wealth_highest_first(client, user, campaign, gangs):
    client.force_login(user)

    response = get_campaign(client, campaign)

    assert response.status_code == 200
    assert gang_names(response) == ["Bravo", "Alpha", "Charlie"]
    assert response.context["gang_sort"].token == "-wealth"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "sort,expected",
    [
        ("-rating", ["Alpha", "Charlie", "Bravo"]),
        ("rating", ["Bravo", "Charlie", "Alpha"]),
        ("-stash", ["Bravo", "Alpha", "Charlie"]),
        ("-credits", ["Alpha", "Bravo", "Charlie"]),
        ("wealth", ["Charlie", "Alpha", "Bravo"]),
        ("name", ["Alpha", "Bravo", "Charlie"]),
        ("-name", ["Charlie", "Bravo", "Alpha"]),
    ],
)
def test_sort_query_param(client, user, campaign, gangs, sort, expected):
    client.force_login(user)

    response = get_campaign(client, campaign, sort=sort)

    assert gang_names(response) == expected
    assert response.context["gang_sort"].token == sort


@pytest.mark.django_db
def test_sort_by_resource(client, user, campaign, gangs):
    """Reputation is a resource type, so resources are sortable too."""
    client.force_login(user)
    reputation = CampaignResourceType.objects.create(
        campaign=campaign, name="Reputation", owner=user
    )
    for name, amount in [("Alpha", 3), ("Bravo", 9), ("Charlie", 5)]:
        CampaignListResource.objects.create(
            campaign=campaign,
            resource_type=reputation,
            list=gangs[name],
            amount=amount,
            owner=user,
        )

    response = get_campaign(client, campaign, sort=f"-resource:{reputation.id}")
    assert gang_names(response) == ["Bravo", "Charlie", "Alpha"]

    response = get_campaign(client, campaign, sort=f"resource:{reputation.id}")
    assert gang_names(response) == ["Alpha", "Charlie", "Bravo"]

    # The resource appears as a sort option, alongside the cost figures.
    labels = [option["label"] for option in response.context["gang_sort_options"]]
    assert "Reputation" in labels
    assert "Wealth" in labels


@pytest.mark.django_db
def test_campaign_default_sort_is_used(client, user, campaign, gangs):
    client.force_login(user)
    campaign.default_gang_sort = "name"
    campaign.save()

    response = get_campaign(client, campaign)

    assert gang_names(response) == ["Alpha", "Bravo", "Charlie"]
    assert response.context["gang_sort"].token == "name"


@pytest.mark.django_db
def test_query_param_beats_campaign_default(client, user, campaign, gangs):
    client.force_login(user)
    campaign.default_gang_sort = "name"
    campaign.save()

    response = get_campaign(client, campaign, sort="-rating")

    assert gang_names(response) == ["Alpha", "Charlie", "Bravo"]


@pytest.mark.django_db
@pytest.mark.parametrize("sort", ["nonsense", "-nonsense", "", "resource:not-a-uuid"])
def test_invalid_sort_falls_back_to_wealth(client, user, campaign, gangs, sort):
    client.force_login(user)

    response = get_campaign(client, campaign, sort=sort)

    assert response.status_code == 200
    assert response.context["gang_sort"].token == "-wealth"


@pytest.mark.django_db
def test_default_pointing_at_a_deleted_resource_falls_back(
    client, user, campaign, gangs
):
    """A resource type can be removed after being made the default sort."""
    client.force_login(user)
    campaign.default_gang_sort = f"-resource:{uuid.uuid4()}"
    campaign.save()

    response = get_campaign(client, campaign)

    assert response.status_code == 200
    assert gang_names(response) == ["Bravo", "Alpha", "Charlie"]


@pytest.mark.django_db
def test_gangs_still_joining_sort_last(client, user, campaign, gangs, make_list):
    """A gang still cloning in has no cost figures yet, so it shouldn't rank."""
    client.force_login(user)
    joining = make_list("Zeta")
    campaign.lists.add(joining)
    List.objects.filter(pk=joining.pk).update(status=List.CLONING_IN_PROGRESS)

    assert gang_names(get_campaign(client, campaign)) == [
        "Bravo",
        "Alpha",
        "Charlie",
        "Zeta",
    ]
    # Including when sorting the other way, where its zeroes would come first.
    assert gang_names(get_campaign(client, campaign, sort="wealth")) == [
        "Charlie",
        "Alpha",
        "Bravo",
        "Zeta",
    ]


@pytest.mark.django_db
def test_sort_applies_within_groups(client, user, campaign, gangs):
    """With grouping on, each group's gangs are ordered by the chosen sort."""
    client.force_login(user)
    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign, name="Faction", is_single_select=True, owner=user
    )
    order = CampaignAttributeValue.objects.create(
        attribute_type=attr_type, name="Order", owner=user
    )
    chaos = CampaignAttributeValue.objects.create(
        attribute_type=attr_type, name="Chaos", owner=user
    )
    for value, names in [(order, ["Alpha", "Charlie"]), (chaos, ["Bravo"])]:
        for name in names:
            CampaignListAttributeAssignment.objects.create(
                campaign=campaign, attribute_value=value, list=gangs[name], owner=user
            )
    campaign.group_attribute_type = attr_type
    campaign.save()

    response = get_campaign(client, campaign)

    assert response.context["show_groups"] is True
    groups = {
        group["name"]: [lst.name for lst in group["lists"]]
        for group in response.context["grouped_lists"]
    }
    assert groups == {"Chaos": ["Bravo"], "Order": ["Alpha", "Charlie"]}
    # The grouping attribute gets a heading row, so it isn't also a column.
    assert response.context["visible_attribute_types"] == []


@pytest.mark.django_db
def test_groups_can_be_switched_off_to_sort_across_all_gangs(
    client, user, campaign, gangs
):
    client.force_login(user)
    attr_type = CampaignAttributeType.objects.create(
        campaign=campaign, name="Faction", is_single_select=True, owner=user
    )
    campaign.group_attribute_type = attr_type
    campaign.save()

    response = get_campaign(client, campaign, group=0)

    assert response.context["show_groups"] is False
    assert not response.context["grouped_lists"]
    assert gang_names(response) == ["Bravo", "Alpha", "Charlie"]
    # Group membership stays visible as a column when the groups are off.
    assert [t.name for t in response.context["visible_attribute_types"]] == ["Faction"]


@pytest.mark.django_db
def test_admin_can_save_the_sort_as_the_campaign_default(client, user, campaign, gangs):
    client.force_login(user)

    response = client.post(
        reverse("core:campaign-set-default-gang-sort", args=(campaign.id,)),
        {"sort": "-rating"},
    )

    assert response.status_code == 302
    campaign.refresh_from_db()
    assert campaign.default_gang_sort == "-rating"
    assert gang_names(get_campaign(client, campaign)) == ["Alpha", "Charlie", "Bravo"]


@pytest.mark.django_db
def test_saving_an_invalid_default_sort_is_rejected(client, user, campaign):
    client.force_login(user)

    response = client.post(
        reverse("core:campaign-set-default-gang-sort", args=(campaign.id,)),
        {"sort": "nonsense"},
    )

    assert response.status_code == 302
    campaign.refresh_from_db()
    assert campaign.default_gang_sort == ""


@pytest.mark.django_db
def test_non_admin_cannot_set_the_default_sort(client, campaign, make_user):
    other = make_user("interloper", "password")
    client.force_login(other)

    response = client.post(
        reverse("core:campaign-set-default-gang-sort", args=(campaign.id,)),
        {"sort": "-rating"},
    )

    assert response.status_code == 404
    campaign.refresh_from_db()
    assert campaign.default_gang_sort == ""


@pytest.mark.django_db
def test_sort_control_is_rendered(client, user, campaign, gangs):
    client.force_login(user)

    response = get_campaign(client, campaign)
    content = response.content.decode()
    assert "sort=-rating" in content
    # Already the campaign default, so there's nothing to save.
    assert "Set as default for this Campaign" not in content

    # Looking at something other than the default, an admin is offered it.
    content = get_campaign(client, campaign, sort="-rating").content.decode()
    assert "Set as default for this Campaign" in content


@pytest.mark.django_db
def test_only_admins_are_offered_the_default_sort_control(
    client, campaign, gangs, make_user
):
    other = make_user("bystander", "password")
    client.force_login(other)

    content = get_campaign(client, campaign, sort="-rating").content.decode()

    assert "sort=-wealth" in content
    assert "Set as default for this Campaign" not in content
