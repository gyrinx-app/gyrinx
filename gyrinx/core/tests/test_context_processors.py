import pytest
from unittest.mock import Mock, patch
from django.db import DatabaseError, OperationalError, InterfaceError
from django.test import RequestFactory
from django.core.cache import cache

from gyrinx.core.models import Banner
from gyrinx.core.context_processors import site_banner, BANNER_CACHE_KEY


@pytest.fixture
def request_factory():
    return RequestFactory()


@pytest.mark.django_db
def test_site_banner_with_live_banner(request_factory):
    """Test that a live banner is returned in context."""
    # Create a live banner
    banner = Banner.objects.create(text="Test Banner", is_live=True)

    # Clear cache to ensure fresh fetch
    cache.delete(BANNER_CACHE_KEY)

    request = request_factory.get("/")
    request.session = {}

    context = site_banner(request)

    assert context["banner"] == banner


@pytest.mark.django_db
def test_site_banner_no_live_banner(request_factory):
    """Test that None is returned when no live banner exists."""
    # Ensure no banners exist
    Banner.objects.all().delete()

    # Clear cache
    cache.delete(BANNER_CACHE_KEY)

    request = request_factory.get("/")
    request.session = {}

    context = site_banner(request)

    assert context["banner"] is None


@pytest.mark.django_db
def test_site_banner_dismissed(request_factory):
    """Test that dismissed banners are not shown."""
    banner = Banner.objects.create(text="Test Banner", is_live=True)

    # Clear cache
    cache.delete(BANNER_CACHE_KEY)

    request = request_factory.get("/")
    request.session = {"dismissed_banners": [str(banner.id)]}

    context = site_banner(request)

    assert context["banner"] is None


@pytest.mark.django_db
def test_site_banner_caching(request_factory):
    """Test that banner data is cached."""
    banner = Banner.objects.create(text="Test Banner", is_live=True)

    # Clear cache
    cache.delete(BANNER_CACHE_KEY)

    request = request_factory.get("/")
    request.session = {}

    # First call should fetch from database
    with patch("gyrinx.core.models.Banner.objects.filter") as mock_filter:
        mock_queryset = Mock()
        mock_queryset.first.return_value = banner
        mock_filter.return_value = mock_queryset

        context1 = site_banner(request)
        assert context1["banner"] == banner
        assert mock_filter.called  # Database was queried

    # Second call should use cached value
    with patch("gyrinx.core.models.Banner.objects.filter") as mock_filter:
        context2 = site_banner(request)
        assert context2["banner"] == banner
        assert not mock_filter.called  # Database was NOT queried (cache used)


@pytest.mark.django_db
def test_site_banner_handles_database_error(request_factory):
    """Test that DatabaseError is handled gracefully."""
    # Clear cache
    cache.delete(BANNER_CACHE_KEY)

    request = request_factory.get("/")
    request.session = {}

    with patch("gyrinx.core.models.Banner.objects.filter") as mock_filter:
        mock_filter.side_effect = DatabaseError("Connection failed")

        context = site_banner(request)

        assert context["banner"] is None


@pytest.mark.django_db
def test_site_banner_handles_operational_error(request_factory):
    """Test that OperationalError is handled gracefully."""
    # Clear cache
    cache.delete(BANNER_CACHE_KEY)

    request = request_factory.get("/")
    request.session = {}

    with patch("gyrinx.core.models.Banner.objects.filter") as mock_filter:
        mock_filter.side_effect = OperationalError("Connection failed")

        context = site_banner(request)

        assert context["banner"] is None


@pytest.mark.django_db
def test_site_banner_handles_interface_error(request_factory):
    """Test that InterfaceError is handled gracefully."""
    # Clear cache
    cache.delete(BANNER_CACHE_KEY)

    request = request_factory.get("/")
    request.session = {}

    with patch("gyrinx.core.models.Banner.objects.filter") as mock_filter:
        mock_filter.side_effect = InterfaceError("Connection failed")

        context = site_banner(request)

        assert context["banner"] is None


@pytest.mark.django_db
def test_site_banner_handles_does_not_exist(request_factory):
    """Test that Banner.DoesNotExist is handled gracefully."""
    # Clear cache
    cache.delete(BANNER_CACHE_KEY)

    request = request_factory.get("/")
    request.session = {}

    with patch("gyrinx.core.models.Banner.objects.filter") as mock_filter:
        mock_queryset = Mock()
        mock_queryset.first.side_effect = Banner.DoesNotExist()
        mock_filter.return_value = mock_queryset

        context = site_banner(request)

        assert context["banner"] is None


@pytest.mark.django_db
def test_site_banner_handles_unexpected_exception(request_factory):
    """Test that unexpected exceptions are handled gracefully."""
    # Clear cache
    cache.delete(BANNER_CACHE_KEY)

    request = request_factory.get("/")
    request.session = {}

    with patch("gyrinx.core.models.Banner.objects.filter") as mock_filter:
        mock_filter.side_effect = Exception("Unexpected error")

        context = site_banner(request)

        assert context["banner"] is None


@pytest.mark.django_db
def test_banner_save_clears_cache():
    """Test that saving a banner clears the cache."""
    # Set something in cache
    cache.set(BANNER_CACHE_KEY, "test_value", 300)

    # Create and save a banner
    Banner.objects.create(text="Test Banner", is_live=True)

    # Cache should be cleared
    assert cache.get(BANNER_CACHE_KEY) is None


@pytest.mark.django_db
def test_banner_delete_clears_cache():
    """Test that deleting a banner clears the cache."""
    # Create a banner
    banner = Banner.objects.create(text="Test Banner", is_live=True)

    # Set something in cache
    cache.set(BANNER_CACHE_KEY, "test_value", 300)

    # Delete the banner
    banner.delete()

    # Cache should be cleared
    assert cache.get(BANNER_CACHE_KEY) is None
