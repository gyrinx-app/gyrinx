"""Guard: things the admin only has because a module got imported.

Admin registration happens as a side effect of importing the module holding the
``@admin.register`` call. Moving a model between apps can quietly orphan that
import — the model keeps working everywhere except the admin, and no other test
notices. That happened to Event during the platform split (#2093).

The platform registries have the same shape of failure. The edition pushes
growth-chart lines, broadcast audiences and repair operations into the
``gyrinx.{analytics,site,maintenance}`` registries from side-effect-only modules
under ``n23/core/admin/``. Nothing raises if those imports go missing; the chart
just loses its lines, the dropdown its options, the console its repairs. So
assert they arrived.

The admin site itself is assembled the same fragile way — by successive modules
patching ``admin.site.__class__`` in INSTALLED_APPS order — so the composition
is asserted here too.
"""

import pytest
from django.contrib import admin
from django.urls import NoReverseMatch, reverse

from gyrinx.accounts.models import UserProfile
from gyrinx.analytics.models import Event
from gyrinx.analytics.registry import growth_series
from gyrinx.maintenance.models import Backfill
from gyrinx.maintenance.registry import all_operations, operations
from gyrinx.site.models import Banner, ImpersonationLog, Notification
from gyrinx.site.registry import broadcast_audiences


@pytest.mark.parametrize(
    "model", [Event, UserProfile, Banner, ImpersonationLog, Notification, Backfill]
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
    """Retired repairs stay registered so old records read as more than a slug."""
    registered = {op.operation: op for op in all_operations()}
    assert operation in registered, (
        f"Retired operation {operation!r} lost its registration; historical "
        f"Backfill records will render the bare slug."
    )
    assert registered[operation].view is None, (
        f"{operation!r} is retired but still has a view, so it will reappear "
        f"on the maintenance index as a runnable repair."
    )


# ------------------------------------------------- admin site composition


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
    """Each app in the chain adds routes by subclassing the previous site.

    Import one of those modules too early — from an edition, say, which Django
    autodiscovers first — and a later link in the chain overwrites it, taking
    its routes with it. Nothing raises; the URLs just stop existing.
    """
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
