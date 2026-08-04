"""Guard: models that moved to platform apps must still reach the admin.

Admin registration happens as a side effect of importing the module holding the
``@admin.register`` call. Moving a model between apps can quietly orphan that
import — the model keeps working everywhere except the admin, and no other test
notices. That happened to Event during the platform split (#2093).
"""

import pytest
from django.contrib import admin

from gyrinx.accounts.models import UserProfile
from gyrinx.analytics.models import Event
from gyrinx.site.models import Banner, ImpersonationLog


@pytest.mark.parametrize("model", [Event, UserProfile, Banner, ImpersonationLog])
def test_moved_model_is_still_registered_in_admin(model):
    assert model in admin.site._registry, (
        f"{model.__name__} has no ModelAdmin. The module holding its "
        f"@admin.register is probably no longer imported — check the admin "
        f"package __init__ for the app that owns it."
    )
