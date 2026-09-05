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
        # Seed before function fixtures, as a previous banner test would.
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
    """Test that a live banner is returned in context."""
    # Create a live banner
    banner = Banner.objects.create(text="Test Banner", live_n23=True)

    # Clear cache to ensure fresh fetch
    clear_banner_cache()

    request = request_factory.get("/")
    request.session = {}

    context = site_banner(request)

    assert context["banner"] == banner


@pytest.mark.django_db
def test_site_banner_is_chosen_per_edition(request_factory):
    """Each side of the site sees only the banner live on that side."""
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
    """A banner live only on n23 never shows under /n26/, and vice versa."""
    Banner.objects.create(text="Classic only", live_n23=True)

    clear_banner_cache()
    request = request_factory.get("/n26/gangs/")
    request.session = {}
    assert site_banner(request)["banner"] is None


@pytest.mark.django_db
def test_site_banner_live_on_both_shows_on_both(request_factory):
    """A banner live on both sides shows everywhere."""
    banner = Banner.objects.create(text="Everywhere", live_n23=True, live_n26=True)

    clear_banner_cache()
    for path in ("/", "/n26/gangs/"):
        request = request_factory.get(path)
        request.session = {}
        assert site_banner(request)["banner"] == banner


@pytest.mark.django_db
def test_going_live_takes_only_that_sides_slot():
    """Setting a banner live on one side demotes the previous holder of that
    side's slot — and leaves the other side's untouched."""
    both = Banner.objects.create(text="First", live_n23=True, live_n26=True)
    Banner.objects.create(text="Second", live_n23=True)

    both.refresh_from_db()
    assert not both.live_n23
    assert both.live_n26


@pytest.mark.django_db
def test_site_banner_no_live_banner(request_factory):
    """Test that None is returned when no live banner exists."""
    # Ensure no banners exist
    Banner.objects.all().delete()

    clear_banner_cache()

    request = request_factory.get("/")
    request.session = {}

    context = site_banner(request)

    assert context["banner"] is None


@pytest.mark.django_db
def test_site_banner_dismissed(request_factory):
    """Test that dismissed banners are not shown."""
    banner = Banner.objects.create(text="Test Banner", live_n23=True)

    clear_banner_cache()

    request = request_factory.get("/")
    request.session = {"dismissed_banners": [str(banner.id)]}

    context = site_banner(request)

    assert context["banner"] is None


@pytest.mark.django_db
def test_site_banner_caching(request_factory):
    """Test that banner data is cached."""
    banner = Banner.objects.create(text="Test Banner", live_n23=True)

    clear_banner_cache()

    request = request_factory.get("/")
    request.session = {}

    # First call should fetch from database
    with patch("gyrinx.site.models.Banner.objects.filter") as mock_filter:
        mock_queryset = Mock()
        mock_queryset.first.return_value = banner
        mock_filter.return_value = mock_queryset

        context1 = site_banner(request)
        assert context1["banner"] == banner
        assert mock_filter.called  # Database was queried

    # Second call should use cached value
    with patch("gyrinx.site.models.Banner.objects.filter") as mock_filter:
        context2 = site_banner(request)
        assert context2["banner"] == banner
        assert not mock_filter.called  # Database was NOT queried (cache used)


@pytest.mark.django_db
def test_site_banner_handles_database_error(request_factory):
    """Test that DatabaseError is handled gracefully."""
    clear_banner_cache()

    request = request_factory.get("/")
    request.session = {}

    with patch("gyrinx.site.models.Banner.objects.filter") as mock_filter:
        mock_filter.side_effect = DatabaseError("Connection failed")

        context = site_banner(request)

        assert context["banner"] is None


@pytest.mark.django_db
def test_site_banner_handles_operational_error(request_factory):
    """Test that OperationalError is handled gracefully."""
    clear_banner_cache()

    request = request_factory.get("/")
    request.session = {}

    with patch("gyrinx.site.models.Banner.objects.filter") as mock_filter:
        mock_filter.side_effect = OperationalError("Connection failed")

        context = site_banner(request)

        assert context["banner"] is None


@pytest.mark.django_db
def test_site_banner_handles_interface_error(request_factory):
    """Test that InterfaceError is handled gracefully."""
    clear_banner_cache()

    request = request_factory.get("/")
    request.session = {}

    with patch("gyrinx.site.models.Banner.objects.filter") as mock_filter:
        mock_filter.side_effect = InterfaceError("Connection failed")

        context = site_banner(request)

        assert context["banner"] is None


@pytest.mark.django_db
def test_site_banner_handles_does_not_exist(request_factory):
    """Test that Banner.DoesNotExist is handled gracefully."""
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
    """Test that unexpected exceptions are handled gracefully."""
    clear_banner_cache()

    request = request_factory.get("/")
    request.session = {}

    with patch("gyrinx.site.models.Banner.objects.filter") as mock_filter:
        mock_filter.side_effect = Exception("Unexpected error")

        context = site_banner(request)

        assert context["banner"] is None


@pytest.mark.django_db
def test_banner_save_clears_cache():
    """Test that saving a banner clears the caches for both editions."""
    # Set something in both caches
    for key in BANNER_CACHE_KEYS.values():
        cache.set(key, "test_value", 300)

    # Create and save a banner
    Banner.objects.create(text="Test Banner", live_n23=True)

    # Caches should be cleared
    for key in BANNER_CACHE_KEYS.values():
        assert cache.get(key) is None


@pytest.mark.django_db
def test_banner_delete_clears_cache():
    """Test that deleting a banner clears the caches for both editions."""
    # Create a banner
    banner = Banner.objects.create(text="Test Banner", live_n23=True)

    # Set something in both caches
    for key in BANNER_CACHE_KEYS.values():
        cache.set(key, "test_value", 300)

    # Delete the banner
    banner.delete()

    # Caches should be cleared
    for key in BANNER_CACHE_KEYS.values():
        assert cache.get(key) is None
