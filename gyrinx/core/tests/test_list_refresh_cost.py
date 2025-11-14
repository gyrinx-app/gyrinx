"""
Tests for list cost refresh functionality.

Tests the refresh_list_cost view that allows list owners and campaign owners
to manually refresh the cost cache.
"""

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.urls import reverse

from gyrinx.content.models import ContentFighter
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.list import List, ListFighter

User = get_user_model()


@pytest.mark.django_db
def test_refresh_list_cost_as_owner(client, user, content_house):
    """Test that list owner can refresh cost cache."""
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
    )

    client.force_login(user)
    url = reverse("core:list-refresh-cost", args=[lst.id])

    cache = caches["core_list_cache"]
    cache_key = lst.cost_cache_key()
    cache.set(cache_key, 999, settings.CACHE_LIST_TTL)

    response = client.post(url)

    assert response.status_code == 302
    assert response.url == reverse("core:list", args=[lst.id])

    cached_cost = cache.get(cache_key)
    assert cached_cost == lst.cost_int()
    assert cached_cost != 999


@pytest.mark.django_db
def test_refresh_list_cost_as_campaign_owner(client, user, content_house):
    """Test that campaign owner can refresh cost cache for lists in their campaign."""
    campaign_owner = User.objects.create_user(
        username="campaign_owner", email="campaign@example.com", password="testpass"
    )
    list_owner = User.objects.create_user(
        username="list_owner", email="list@example.com", password="testpass"
    )

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=campaign_owner,
    )

    lst = List.objects.create(
        owner=list_owner,
        content_house=content_house,
        name="Test List",
        campaign=campaign,
    )

    client.force_login(campaign_owner)
    url = reverse("core:list-refresh-cost", args=[lst.id])

    cache = caches["core_list_cache"]
    cache_key = lst.cost_cache_key()
    cache.set(cache_key, 999, settings.CACHE_LIST_TTL)

    response = client.post(url)

    assert response.status_code == 302
    assert response.url == reverse("core:list", args=[lst.id])

    cached_cost = cache.get(cache_key)
    assert cached_cost == lst.cost_int()
    assert cached_cost != 999


@pytest.mark.django_db
def test_refresh_list_cost_non_owner(client, user, content_house):
    """Test that non-owners get 404 when trying to refresh cost."""
    owner = User.objects.create_user(
        username="owner", email="owner@example.com", password="testpass"
    )
    non_owner = User.objects.create_user(
        username="non_owner", email="non@example.com", password="testpass"
    )

    lst = List.objects.create(
        owner=owner,
        content_house=content_house,
        name="Test List",
    )

    client.force_login(non_owner)
    url = reverse("core:list-refresh-cost", args=[lst.id])

    response = client.post(url)

    assert response.status_code == 404


@pytest.mark.django_db
def test_refresh_list_cost_unauthenticated(client, user, content_house):
    """Test that unauthenticated users are redirected to login."""
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
    )

    url = reverse("core:list-refresh-cost", args=[lst.id])
    response = client.post(url)

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_refresh_list_cost_updates_cache(client, user, content_house):
    """Test that refresh actually calculates and caches the correct cost."""
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
    )

    fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=50,
    )

    ListFighter.objects.create(
        owner=user,
        list=lst,
        content_fighter=fighter,
        name="Test Fighter",
    )

    client.force_login(user)
    url = reverse("core:list-refresh-cost", args=[lst.id])

    cache = caches["core_list_cache"]
    cache_key = lst.cost_cache_key()
    cache.delete(cache_key)

    response = client.post(url)

    assert response.status_code == 302

    cached_cost = cache.get(cache_key)
    assert cached_cost is not None
    assert cached_cost == 50


@pytest.mark.django_db
def test_refresh_list_cost_get_request_redirects(client, user, content_house):
    """Test that GET requests still redirect (no error)."""
    lst = List.objects.create(
        owner=user,
        content_house=content_house,
        name="Test List",
    )

    client.force_login(user)
    url = reverse("core:list-refresh-cost", args=[lst.id])

    response = client.get(url)

    assert response.status_code == 302
    assert response.url == reverse("core:list", args=[lst.id])
