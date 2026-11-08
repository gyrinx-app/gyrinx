"""Verify N26 flag registration and safe reversal of the campaign access-group migration.
Platform integration tests belong here because they import shared site services.
"""

import importlib

import pytest
from django.apps import apps
from django.contrib.auth.models import Group, User

from gyrinx.site.flags import enabled, known_flags
from gyrinx.site.models import Availability, FeatureFlag
from n26.flags import BUILT_IN_PROPAGATION, CYCLE_TRACKING, STAGED_CONTENT

pytestmark = [pytest.mark.django_db, pytest.mark.core]

GROUP_NAME = "N26 Campaigns"


class TestWhatThisEditionClaims:
    def test_the_cycle_flag_migration_starts_closed_and_preserves_existing_settings(
        self,
    ):
        mod = importlib.import_module(
            "gyrinx.site.migrations.0011_campaign_cycles_start_closed"
        )
        mod.seed_cycle_flag(apps, None)
        flag = FeatureFlag.objects.get(slug=CYCLE_TRACKING)
        assert flag.availability == Availability.OFF
        flag.availability = Availability.EVERYONE
        flag.save()
        mod.seed_cycle_flag(apps, None)
        flag.refresh_from_db()
        assert flag.availability == Availability.EVERYONE

    def test_built_in_propagation_is_registered(self):
        """Propagation checks require a registered slug; otherwise the platform raises
        ValueError.
        """
        assert BUILT_IN_PROPAGATION in known_flags()

    def test_staged_content_is_registered(self):
        """Register staged-content access before player addition screens check it."""
        assert STAGED_CONTENT in known_flags()

    def test_cycle_tracking_is_registered_but_disabled_without_an_access_record(self):
        reader = User.objects.create_user("cycle-reader")
        assert CYCLE_TRACKING in known_flags()
        assert enabled(CYCLE_TRACKING, reader) is False

    def test_opening_cycle_tracking_does_not_require_gating_campaign_access(self):
        reader = User.objects.create_user("cycle-reader")
        FeatureFlag.objects.create(
            slug=CYCLE_TRACKING,
            name="Campaign cycles",
            availability=Availability.EVERYONE,
        )
        assert enabled(CYCLE_TRACKING, reader) is True
        assert "campaigns" not in known_flags()

    def test_the_released_features_are_no_longer_claimed(self):
        """Campaigns and founding require no feature-flag registration."""
        assert not {"campaigns", "founding"} & known_flags()

    def test_the_seam_answers_for_it(self):
        """A registered feature with no database record remains disabled through the
        edition boundary.
        """
        reader = User.objects.create_user("reader")
        assert enabled(STAGED_CONTENT, reader) is False

    def test_a_row_here_opens_it(self):
        reader = User.objects.create_user("reader")
        FeatureFlag.objects.create(
            slug=STAGED_CONTENT,
            name="Staged content",
            availability=Availability.EVERYONE,
        )
        assert enabled(STAGED_CONTENT, reader) is True


class TestUndoingTheGroupMigration:
    """Remove only an empty access group on migration reversal. Existing memberships must
    survive because the forward operation may reuse a pre-existing group.
    """

    def _reverse(self):
        # Import by string because migration module names begin with digits.
        mod = importlib.import_module(
            "n26.core.migrations.0023_an_account_may_be_let_into_campaigns_early"
        )
        mod.remove_campaigns_group(apps, None)

    def test_an_empty_group_is_taken_away(self):
        Group.objects.create(name=GROUP_NAME)
        self._reverse()
        assert not Group.objects.filter(name=GROUP_NAME).exists()

    def test_a_group_with_members_is_left_alone(self):
        """Preserve the group and its memberships on reversal."""
        member = User.objects.create_user("member")
        member.groups.add(Group.objects.create(name=GROUP_NAME))

        self._reverse()

        assert Group.objects.filter(name=GROUP_NAME).exists()
        assert member.groups.filter(name=GROUP_NAME).exists()
