"""The reach conversion's decisions, pinned.

Migration 0061 converts every stored targets-the-model scope to whichever
reach preserves what it was doing, read off its carriers. The suite never
runs data migrations (--nomigrations), so the decision function is proven
here directly, against content authored the way the library authors it.
"""

from importlib import import_module

import pytest
from django.apps import apps as live_apps
from django.contrib.auth.models import User

from n26.library.authoring import (
    attach_modifiers_to,
    create_affiliation,
    create_profile,
    create_rule,
    modifier,
    targets_model,
)
from n26.library.models import AddsAssignable, TargetsMiniature

pytestmark = pytest.mark.django_db

say_the_reach = import_module(
    "n26.library.migrations.0061_reach_is_said_not_implied"
).say_the_reach


def _model_scoped(name):
    """A bearer-reach modifier, the shape every pre-conversion row has."""
    return modifier(
        name,
        targets_model(),
        AddsAssignable.objects.create(rule=create_rule(f"{name} rule")),
    )


class TestWhatTheConversionDecides:
    def test_a_gang_side_carrier_means_all_models(self, default_pack):
        made = _model_scoped("Alliance payload")
        attach_modifiers_to(create_affiliation("Iron Guild"), [made])

        say_the_reach(live_apps)

        made.scope.refresh_from_db()
        assert made.scope.reach == TargetsMiniature.Reach.EVERY_MODEL

    def test_a_fighter_side_carrier_stays_the_bearer(
        self, person_type, gang_type, default_pack
    ):
        made = _model_scoped("Entry payload")
        profile = create_profile("Hunter", person_type, gang_type, price=50)
        attach_modifiers_to(profile, [made])

        say_the_reach(live_apps)

        made.scope.refresh_from_db()
        assert made.scope.reach == TargetsMiniature.Reach.BEARER

    def test_a_rule_used_on_a_gang_means_all_models(self, gang_type, default_pack):
        from n26.tests.sandbox.actions import assign, found_gang

        made = _model_scoped("House payload")
        rule = create_rule("House charter")
        attach_modifiers_to(rule, [made])
        gang = found_gang(
            "The Bad Girls", gang_type, owner=User.objects.create_user("player")
        )
        assign(rule, gang=gang)

        say_the_reach(live_apps)

        made.scope.refresh_from_db()
        assert made.scope.reach == TargetsMiniature.Reach.EVERY_MODEL

    def test_a_rule_nothing_uses_on_a_gang_stays_the_bearer(self, default_pack):
        made = _model_scoped("Quiet payload")
        attach_modifiers_to(create_rule("Fighter-side rule"), [made])

        say_the_reach(live_apps)

        made.scope.refresh_from_db()
        assert made.scope.reach == TargetsMiniature.Reach.BEARER

    def test_a_pickable_nobody_has_picked_for_a_gang_stays_the_bearer(
        self, default_pack
    ):
        """A pickable cannot be built in, so only its live picks say
        where it is used — and with none, the decision is the bearer,
        reached without a crash."""
        from n26.library.authoring import create_pickable, create_slot_type

        made = _model_scoped("Guild payload")
        pickable = create_pickable("Water Guild", create_slot_type("Alliance"))
        attach_modifiers_to(pickable, [made])

        say_the_reach(live_apps)

        made.scope.refresh_from_db()
        assert made.scope.reach == TargetsMiniature.Reach.BEARER

    def test_an_unattached_modifier_stays_the_bearer(self, default_pack):
        made = _model_scoped("Spare payload")

        say_the_reach(live_apps)

        made.scope.refresh_from_db()
        assert made.scope.reach == TargetsMiniature.Reach.BEARER
