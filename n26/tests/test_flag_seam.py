"""The seam onto the site's feature flags, and the group migration behind it.

Lives here rather than beside the code because it reaches across to the
platform, which only ``n26/tests/`` may do. What it pins is this edition's
half of the arrangement: the slugs it claims, and the group its allowlist
reads.
"""

import importlib

import pytest
from django.apps import apps
from django.contrib.auth.models import Group, User

from gyrinx.site.flags import enabled, known_flags
from gyrinx.site.models import Availability, FeatureFlag
from n26.flags import BUILT_IN_PROPAGATION, CAMPAIGNS

pytestmark = [pytest.mark.django_db, pytest.mark.core]

GROUP_NAME = "N26 Campaigns"


class TestWhatThisEditionClaims:
    def test_campaigns_is_registered(self):
        """Claimed as the app starts, so a guard written against it works
        wherever it is applied."""
        assert CAMPAIGNS in known_flags()

    def test_built_in_propagation_is_registered(self):
        """The running side of propagation checks this flag; unclaimed,
        that check would raise instead of standing down."""
        assert BUILT_IN_PROPAGATION in known_flags()

    def test_the_seam_answers_for_it(self):
        """A slug with no row is off — the same answer the platform gives,
        reached through this edition's own door."""
        assert enabled(CAMPAIGNS, User.objects.create_user("reader")) is False

    def test_a_row_here_opens_it(self):
        reader = User.objects.create_user("reader")
        FeatureFlag.objects.create(
            slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
        )
        assert enabled(CAMPAIGNS, reader) is True


class TestUndoingTheGroupMigration:
    """Reversing must undo the creation and nothing else. The forward
    operation accepts a group that was already there, so it cannot tell one
    it made from one it found — and deleting somebody's group would take
    every membership with it."""

    def _reverse(self):
        # Imported by name because a module starting with a digit is not a
        # valid identifier, so the import statement cannot reach it.
        mod = importlib.import_module(
            "n26.core.migrations.0023_an_account_may_be_let_into_campaigns_early"
        )
        mod.remove_campaigns_group(apps, None)

    def test_an_empty_group_is_taken_away(self):
        Group.objects.create(name=GROUP_NAME)
        self._reverse()
        assert not Group.objects.filter(name=GROUP_NAME).exists()

    def test_a_group_with_members_is_left_alone(self):
        """Somebody is in it, so it is somebody's."""
        member = User.objects.create_user("member")
        member.groups.add(Group.objects.create(name=GROUP_NAME))

        self._reverse()

        assert Group.objects.filter(name=GROUP_NAME).exists()
        assert member.groups.filter(name=GROUP_NAME).exists()
