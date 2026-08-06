"""Guard: things the admin only has because a module got imported.

Admin registration happens as a side effect of importing the module holding the
``@admin.register`` call. Moving a model between apps can quietly orphan that
import — the model keeps working everywhere except the admin, and no other test
notices. That happened to Event during the platform split (#2093).

The platform registries have the same shape of failure. The edition pushes
growth-chart lines and broadcast audiences into ``gyrinx.analytics.registry``
and ``gyrinx.site.registry`` from side-effect-only modules under
``n23/core/admin/``. Nothing raises if those imports go missing; the chart just
loses its lines and the dropdown its options. So assert they arrived.
"""

import pytest
from django.contrib import admin

from gyrinx.accounts.models import UserProfile
from gyrinx.analytics.models import Event
from gyrinx.analytics.registry import growth_series
from gyrinx.site.models import Banner, ImpersonationLog, Notification
from gyrinx.site.registry import broadcast_audiences


@pytest.mark.parametrize(
    "model", [Event, UserProfile, Banner, ImpersonationLog, Notification]
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
