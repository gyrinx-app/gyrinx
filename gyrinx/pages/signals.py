from django.contrib.flatpages.models import FlatPage
from django.core.cache import cache
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from .models import FlatPageVisibility


def clear_flatpages_cache():
    """Clear all flatpages cache entries."""
    # Since we use a pattern like "flatpages:site_*:depth_*:*",
    # we need to clear all keys that start with "flatpages:"

    # Try different approaches based on the cache backend
    cache_backend = (
        cache._cache.__class__.__name__ if hasattr(cache, "_cache") else None
    )

    if cache_backend == "LocMemCache" and hasattr(cache._cache, "_cache"):
        # For LocMemCache (Django's local memory cache)
        keys_to_delete = [
            key for key in cache._cache._cache.keys() if key.startswith("flatpages:")
        ]
        cache.delete_many(keys_to_delete)
    elif hasattr(cache, "delete_pattern"):
        # For Redis cache backends that support pattern deletion
        cache.delete_pattern("flatpages:*")
    elif hasattr(cache, "keys") and hasattr(cache, "delete_many"):
        # For cache backends that support key listing
        keys = cache.keys("flatpages:*")
        if keys:
            cache.delete_many(keys)
    else:
        # Fallback: delete known patterns
        # This is less efficient but ensures cache is cleared
        from django.contrib.sites.models import Site

        # Clear for all possible sites and depths
        try:
            for site in Site.objects.all():
                for depth in range(10):  # Reasonable depth limit
                    # Clear various cache key patterns
                    cache.delete(f"flatpages:site_{site.pk}:depth_{depth}:anon")
                    cache.delete(
                        f"flatpages:site_{site.pk}:depth_{depth}:prefix_/:anon"
                    )
        except Exception:
            # If Site model is not available or there's an error,
            # just try to clear some common patterns
            for site_id in range(1, 5):  # Common site IDs
                for depth in range(5):  # Common depths
                    cache.delete(f"flatpages:site_{site_id}:depth_{depth}:anon")


@receiver(post_save, sender=FlatPage)
def clear_cache_on_flatpage_save(sender, instance, **kwargs):
    """Clear flatpages cache when a flatpage is saved."""
    clear_flatpages_cache()


@receiver(post_delete, sender=FlatPage)
def clear_cache_on_flatpage_delete(sender, instance, **kwargs):
    """Clear flatpages cache when a flatpage is deleted."""
    clear_flatpages_cache()


@receiver(m2m_changed, sender=FlatPage.sites.through)
def clear_cache_on_flatpage_sites_change(sender, instance, **kwargs):
    """Clear flatpages cache when flatpage sites are changed."""
    if kwargs.get("action") in ["post_add", "post_remove", "post_clear"]:
        clear_flatpages_cache()


@receiver(post_save, sender=FlatPageVisibility)
def clear_cache_on_visibility_save(sender, instance, **kwargs):
    """Clear flatpages cache when visibility rules are saved."""
    clear_flatpages_cache()


@receiver(post_delete, sender=FlatPageVisibility)
def clear_cache_on_visibility_delete(sender, instance, **kwargs):
    """Clear flatpages cache when visibility rules are deleted."""
    clear_flatpages_cache()


@receiver(m2m_changed, sender=FlatPageVisibility.groups.through)
def clear_cache_on_visibility_groups_change(sender, instance, **kwargs):
    """Clear flatpages cache when visibility groups are changed."""
    if kwargs.get("action") in ["post_add", "post_remove", "post_clear"]:
        clear_flatpages_cache()
