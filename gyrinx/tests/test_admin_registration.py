"""Admin model, registry and route registration through app imports.

Assert that side-effect registrations reach the dashboard, broadcast and
maintenance surfaces. Check the composed admin site and its routes.
"""

import pytest
from django.contrib import admin
from django.urls import NoReverseMatch, reverse

from gyrinx.accounts.models import UserProfile
from gyrinx.analytics.models import Event
from gyrinx.analytics.registry import growth_series
from gyrinx.maintenance.models import Backfill
from gyrinx.maintenance.registry import all_operations, operations
from gyrinx.site.models import (
    Banner,
    ChangelogEntry,
    ChangelogEntryTag,
    ImpersonationLog,
    Notification,
)
from gyrinx.site.registry import broadcast_audiences


@pytest.mark.parametrize(
    "model",
    [
        Event,
        UserProfile,
        Banner,
        ImpersonationLog,
        Notification,
        Backfill,
        ChangelogEntry,
        ChangelogEntryTag,
    ],
)
def test_moved_model_is_still_registered_in_admin(model):
    assert model in admin.site._registry, (
        f"{model.__name__} has no ModelAdmin. The module holding its "
        f"@admin.register is probably no longer imported — check the admin "
        f"package __init__ for the app that owns it."
    )


@pytest.mark.parametrize("key", ["n23_fighters", "n23_lists", "n23_campaigns"])
def test_edition_growth_series_reaches_the_dashboard(key):
    assert key in {s.key for s in growth_series()}, (
        f"Growth series {key!r} is not registered, so the analytics "
        f"dashboard's growth chart will be missing a line. Check that "
        f"n23/core/admin/__init__.py still imports .analytics."
    )


@pytest.mark.parametrize("key", ["all_active", "with_list", "campaign"])
def test_broadcast_audience_is_offered(key):
    assert key in {a.key for a in broadcast_audiences()}, (
        f"Broadcast audience {key!r} is not registered, so it will be missing "
        f"from the notification broadcast dropdown. Edition audiences come "
        f"from n23/core/admin/broadcast.py."
    )


@pytest.mark.parametrize(
    "operation", ["migrate_persistent_stash", "reconcile_lists", "backfill_pins"]
)
def test_maintenance_operation_is_runnable(operation):
    assert operation in {op.operation for op in operations()}, (
        f"Maintenance operation {operation!r} is not registered, so its page "
        f"is gone from /admin/maintenance/. Edition repairs come from "
        f"n23/core/admin/maintenance.py."
    )


@pytest.mark.parametrize(
    "operation",
    [
        "fix_stat_advancements",
        "normalise_stat_formats",
        "materialise_statlines",
        "migrate_stat_overrides",
    ],
)
def test_retired_operation_keeps_its_label(operation):

    registered = {op.operation: op for op in all_operations()}
    assert operation in registered, (
        f"Retired operation {operation!r} lost its registration; historical "
        f"Backfill records will render the bare slug."
    )
    assert registered[operation].view is None, (
        f"{operation!r} is retired but still has a view, so it will reappear "
        f"on the maintenance index as a runnable repair."
    )


@pytest.mark.parametrize(
    "url_name",
    [
        "admin:index",
        "admin:analytics_dashboard",
        "admin:maintenance_index",
        "admin:maintenance_backfill_pins",
        "admin:maintenance_persistent_stash",
        "admin:maintenance_reconcile_lists",
    ],
)
def test_admin_route_is_mounted(url_name):
    """Keep routes from each admin-site subclass after app autodiscovery."""
    try:
        reverse(url_name)
    except NoReverseMatch:  # pragma: no cover - the failure we're guarding
        pytest.fail(
            f"{url_name} is not routed. The admin.site.__class__ chain "
            f"(analytics -> maintenance) has probably been broken by an "
            f"import-order change; see gyrinx/maintenance/admin.py."
        )


def test_admin_site_composes_analytics_and_maintenance():
    names = [k.__name__ for k in admin.site.__class__.__mro__]
    assert "AnalyticsAdminSite" in names and "MaintenanceAdminSite" in names, (
        f"Expected the maintenance site stacked on the analytics site, got "
        f"{names}. INSTALLED_APPS must keep gyrinx.maintenance after "
        f"gyrinx.analytics."
    )
