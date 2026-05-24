"""Tests for the pin (private) and star (public, counted) features on lists and campaigns."""

import pytest
from django.urls import reverse

from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.list import List


# ---------------------------------------------------------------------------
# List star toggle
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_toggle_list_star_adds_and_removes(client, user, make_list):
    lst = make_list("Star List")
    client.force_login(user)
    url = reverse("core:list-star", args=[lst.id])

    resp = client.post(url)
    assert resp.status_code == 302
    assert lst.starred_by.filter(pk=user.pk).exists()
    assert lst.starred_by.count() == 1

    # Toggling again removes the star.
    client.post(url)
    assert not lst.starred_by.filter(pk=user.pk).exists()
    assert lst.starred_by.count() == 0


@pytest.mark.django_db
def test_toggle_list_star_requires_login(client, make_list):
    lst = make_list("Star List")
    resp = client.post(reverse("core:list-star", args=[lst.id]))
    # Anonymous users are redirected to login, not allowed to star.
    assert resp.status_code == 302
    assert "/accounts/login" in resp.url
    assert lst.starred_by.count() == 0


@pytest.mark.django_db
def test_anyone_can_star_another_users_list(client, user, make_user, make_list):
    lst = make_list("Public List")  # owned by `user`, public by default
    other = make_user("other", "password")
    client.force_login(other)

    client.post(reverse("core:list-star", args=[lst.id]))
    assert lst.starred_by.filter(pk=other.pk).exists()
    assert lst.starred_by.count() == 1


@pytest.mark.django_db
def test_get_does_not_toggle_star(client, user, make_list):
    lst = make_list("Star List")
    client.force_login(user)
    client.get(reverse("core:list-star", args=[lst.id]))
    assert lst.starred_by.count() == 0


# ---------------------------------------------------------------------------
# List pin toggle
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_toggle_list_pin_adds_and_removes(client, user, make_list):
    lst = make_list("Pin List")
    client.force_login(user)
    url = reverse("core:list-pin", args=[lst.id])

    client.post(url)
    assert lst.pinned_by.filter(pk=user.pk).exists()

    client.post(url)
    assert not lst.pinned_by.filter(pk=user.pk).exists()


# ---------------------------------------------------------------------------
# Campaign star / pin toggle
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_toggle_campaign_star_adds_and_removes(client, user, make_campaign):
    camp = make_campaign("Star Campaign")
    client.force_login(user)
    url = reverse("core:campaign-star", args=[camp.id])

    client.post(url)
    assert camp.starred_by.count() == 1

    client.post(url)
    assert camp.starred_by.count() == 0


@pytest.mark.django_db
def test_toggle_campaign_pin_adds_and_removes(client, user, make_campaign):
    camp = make_campaign("Pin Campaign")
    client.force_login(user)
    url = reverse("core:campaign-pin", args=[camp.id])

    client.post(url)
    assert camp.pinned_by.filter(pk=user.pk).exists()

    client.post(url)
    assert not camp.pinned_by.filter(pk=user.pk).exists()


# ---------------------------------------------------------------------------
# Detail page context
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_detail_exposes_star_state(client, user, make_list):
    lst = make_list("Detail List")
    lst.starred_by.add(user)
    client.force_login(user)

    resp = client.get(reverse("core:list", args=[lst.id]))
    assert resp.status_code == 200
    assert resp.context["star_count"] == 1
    assert resp.context["is_starred"] is True
    assert resp.context["is_pinned"] is False


@pytest.mark.django_db
def test_campaign_detail_exposes_star_state(client, user, make_campaign):
    camp = make_campaign("Detail Campaign")
    camp.pinned_by.add(user)
    client.force_login(user)

    resp = client.get(reverse("core:campaign", args=[camp.id]))
    assert resp.status_code == 200
    assert resp.context["star_count"] == 0
    assert resp.context["is_pinned"] is True
    assert resp.context["is_starred"] is False


# ---------------------------------------------------------------------------
# Sorting on the lists index
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_lists_sort_alphabetical(client, user, make_list):
    make_list("Bravo")
    make_list("Alpha")
    client.force_login(user)

    resp = client.get(reverse("core:lists"), {"sort": "name", "my": "1"})
    names = [lst.name for lst in resp.context["lists"]]
    assert names == sorted(names, key=str.lower)
    assert names[0] == "Alpha"


@pytest.mark.django_db
def test_lists_sort_by_stars(client, user, make_list):
    popular = make_list("Bravo")
    make_list("Alpha")
    popular.starred_by.add(user)
    client.force_login(user)

    resp = client.get(reverse("core:lists"), {"sort": "stars", "my": "1"})
    lists = list(resp.context["lists"])
    assert lists[0].name == "Bravo"
    assert lists[0].star_count == 1


@pytest.mark.django_db
def test_lists_default_sort_recent_runs(client, user, make_list):
    # Default (recent) sort uses an action-time annotation; ensure it works.
    make_list("One")
    make_list("Two")
    client.force_login(user)

    resp = client.get(reverse("core:lists"), {"my": "1"})
    assert resp.status_code == 200
    assert resp.context["current_sort"] == "recent"
    assert len(resp.context["lists"]) == 2


# ---------------------------------------------------------------------------
# Sorting on the campaigns index
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_campaigns_sort_alphabetical(client, user, make_campaign):
    make_campaign("Bravo")
    make_campaign("Alpha")
    client.force_login(user)

    resp = client.get(reverse("core:campaigns"), {"sort": "name", "my": "1"})
    names = [c.name for c in resp.context["campaigns"]]
    assert names[0] == "Alpha"


@pytest.mark.django_db
def test_campaigns_sort_by_stars(client, user, make_campaign):
    popular = make_campaign("Bravo")
    make_campaign("Alpha")
    popular.starred_by.add(user)
    client.force_login(user)

    resp = client.get(reverse("core:campaigns"), {"sort": "stars", "my": "1"})
    campaigns = list(resp.context["campaigns"])
    assert campaigns[0].name == "Bravo"
    assert campaigns[0].star_count == 1


# ---------------------------------------------------------------------------
# Home page pinned sections
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_home_shows_pinned_list_and_excludes_from_recent(client, user, make_list):
    pinned = make_list("Pinned List", status=List.LIST_BUILDING)
    make_list("Plain List", status=List.LIST_BUILDING)
    pinned.pinned_by.add(user)
    client.force_login(user)

    resp = client.get(reverse("core:index"))
    assert resp.status_code == 200
    pinned_ids = {lst.id for lst in resp.context["pinned_lists"]}
    recent_ids = {lst.id for lst in resp.context["lists"]}
    assert pinned.id in pinned_ids
    # Pinned lists are not duplicated in the recently-edited column.
    assert pinned.id not in recent_ids


@pytest.mark.django_db
def test_home_shows_pinned_campaign(client, user, make_campaign):
    camp = make_campaign("Pinned Campaign")
    camp.pinned_by.add(user)
    client.force_login(user)

    resp = client.get(reverse("core:index"))
    pinned_ids = {c.id for c in resp.context["pinned_campaigns"]}
    assert camp.id in pinned_ids


@pytest.mark.django_db
def test_home_pinned_gang_appears_in_gang_column(
    client, user, make_list, make_campaign
):
    campaign = make_campaign("Camp", status=Campaign.IN_PROGRESS)
    gang = make_list("My Gang", status=List.CAMPAIGN_MODE, campaign=campaign)
    gang.pinned_by.add(user)
    client.force_login(user)

    resp = client.get(reverse("core:index"))
    pinned_gang_ids = {lst.id for lst in resp.context["pinned_gangs"]}
    assert gang.id in pinned_gang_ids
