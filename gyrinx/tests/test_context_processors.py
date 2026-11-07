import time
from unittest.mock import Mock, patch

import pytest
from django.core.cache import cache
from django.db import DatabaseError, InterfaceError, OperationalError
from django.test import RequestFactory

from gyrinx.context_processors import site_banner
from gyrinx.site.models import BANNER_CACHE_KEYS, BANNER_CACHE_TIMEOUT, Banner


@pytest.fixture
def request_factory():
    return RequestFactory()


def clear_banner_cache():
    for key in BANNER_CACHE_KEYS.values():
        cache.delete(key)


@pytest.mark.django_db
class TestBannerCacheIsolation:
    @pytest.fixture(scope="class", autouse=True)
    def prior_banner_cache(self):
        # Seed at class scope to reproduce cache state left by an earlier test.
        for key in BANNER_CACHE_KEYS.values():
            cache.set(key, False, BANNER_CACHE_TIMEOUT)

    @pytest.mark.parametrize("path", ["/", "/n26/gangs/"])
    def test_banner_expiry_cannot_add_a_query(
        self, path, request_factory, django_assert_num_queries
    ):
        request = request_factory.get(path)
        request.session = {}
        after_expiry = time.time() + BANNER_CACHE_TIMEOUT + 1
        with patch("django.core.cache.backends.locmem.time") as clock:
            clock.time.return_value = after_expiry
            with django_assert_num_queries(0):
                assert site_banner(request) == {"banner": None}


@pytest.mark.django_db
def test_site_banner_with_live_banner(request_factory):

    banner = Banner.objects.create(text="Test Banner", live_n23=True)

    clear_banner_cache()

    request = request_factory.get("/")
    request.session = {}

    context = site_banner(request)

    assert context["banner"] == banner


@pytest.mark.django_db
def test_site_banner_is_chosen_per_edition(request_factory):

    classic = Banner.objects.create(text="Classic side", live_n23=True)
    modern = Banner.objects.create(text="New side", live_n26=True)

    clear_banner_cache()
    request = request_factory.get("/")
    request.session = {}
    assert site_banner(request)["banner"] == classic

    clear_banner_cache()
    request = request_factory.get("/n26/gangs/")
    request.session = {}
    assert site_banner(request)["banner"] == modern


@pytest.mark.django_db
def test_site_banner_live_on_one_side_is_absent_from_the_other(request_factory):

    Banner.objects.create(text="Classic only", live_n23=True)

    clear_banner_cache()
    request = request_factory.get("/n26/gangs/")
    request.session = {}
    assert site_banner(request)["banner"] is None


@pytest.mark.django_db
def test_site_banner_live_on_both_shows_on_both(request_factory):

    banner = Banner.objects.create(text="Everywhere", live_n23=True, live_n26=True)

    clear_banner_cache()
    for path in ("/", "/n26/gangs/"):
        request = request_factory.get(path)
        request.session = {}
        assert site_banner(request)["banner"] == banner


@pytest.mark.django_db
def test_going_live_takes_only_that_sides_slot():

    both = Banner.objects.create(text="First", live_n23=True, live_n26=True)
    Banner.objects.create(text="Second", live_n23=True)

    both.refresh_from_db()
    assert not both.live_n23
    assert both.live_n26


@pytest.mark.django_db
def test_site_banner_no_live_banner(request_factory):

    Banner.objects.all().delete()

    clear_banner_cache()

    request = request_factory.get("/")
    request.session = {}

    context = site_banner(request)

    assert context["banner"] is None


@pytest.mark.django_db
def test_site_banner_dismissed(request_factory):

    banner = Banner.objects.create(text="Test Banner", live_n23=True)

    clear_banner_cache()

    request = request_factory.get("/")
    request.session = {"dismissed_banners": [str(banner.id)]}

    context = site_banner(request)

    assert context["banner"] is None


@pytest.mark.django_db
def test_site_banner_caching(request_factory):

    banner = Banner.objects.create(text="Test Banner", live_n23=True)

    clear_banner_cache()

    request = request_factory.get("/")
    request.session = {}

    with patch("gyrinx.site.models.Banner.objects.filter") as mock_filter:
        mock_queryset = Mock()
        mock_queryset.first.return_value = banner
        mock_filter.return_value = mock_queryset

        context1 = site_banner(request)
        assert context1["banner"] == banner
        assert mock_filter.called  # Database was queried

    with patch("gyrinx.site.models.Banner.objects.filter") as mock_filter:
        context2 = site_banner(request)
        assert context2["banner"] == banner
        assert not mock_filter.called  # Database was NOT queried (cache used)


@pytest.mark.django_db
def test_site_banner_handles_database_error(request_factory):

    clear_banner_cache()

    request = request_factory.get("/")
    request.session = {}

    with patch("gyrinx.site.models.Banner.objects.filter") as mock_filter:
        mock_filter.side_effect = DatabaseError("Connection failed")

        context = site_banner(request)

        assert context["banner"] is None


@pytest.mark.django_db
def test_site_banner_handles_operational_error(request_factory):

    clear_banner_cache()

    request = request_factory.get("/")
    request.session = {}

    with patch("gyrinx.site.models.Banner.objects.filter") as mock_filter:
        mock_filter.side_effect = OperationalError("Connection failed")

        context = site_banner(request)

        assert context["banner"] is None


@pytest.mark.django_db
def test_site_banner_handles_interface_error(request_factory):

    clear_banner_cache()

    request = request_factory.get("/")
    request.session = {}

    with patch("gyrinx.site.models.Banner.objects.filter") as mock_filter:
        mock_filter.side_effect = InterfaceError("Connection failed")

        context = site_banner(request)

        assert context["banner"] is None


@pytest.mark.django_db
def test_site_banner_handles_does_not_exist(request_factory):

    clear_banner_cache()

    request = request_factory.get("/")
    request.session = {}

    with patch("gyrinx.site.models.Banner.objects.filter") as mock_filter:
        mock_queryset = Mock()
        mock_queryset.first.side_effect = Banner.DoesNotExist()
        mock_filter.return_value = mock_queryset

        context = site_banner(request)

        assert context["banner"] is None


@pytest.mark.django_db
def test_site_banner_handles_unexpected_exception(request_factory):

    clear_banner_cache()

    request = request_factory.get("/")
    request.session = {}

    with patch("gyrinx.site.models.Banner.objects.filter") as mock_filter:
        mock_filter.side_effect = Exception("Unexpected error")

        context = site_banner(request)

        assert context["banner"] is None


@pytest.mark.django_db
def test_banner_save_clears_cache():

    for key in BANNER_CACHE_KEYS.values():
        cache.set(key, "test_value", 300)

    Banner.objects.create(text="Test Banner", live_n23=True)

    for key in BANNER_CACHE_KEYS.values():
        assert cache.get(key) is None


@pytest.mark.django_db
def test_banner_delete_clears_cache():

    banner = Banner.objects.create(text="Test Banner", live_n23=True)

    for key in BANNER_CACHE_KEYS.values():
        cache.set(key, "test_value", 300)

    banner.delete()

    for key in BANNER_CACHE_KEYS.values():
        assert cache.get(key) is None
