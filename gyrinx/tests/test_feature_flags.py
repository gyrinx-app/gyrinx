import pytest
from django.contrib.auth.models import AnonymousUser, Group, User
from django.http import Http404
from django.test import RequestFactory

from gyrinx.site.flags import enabled, register_flags, requires_flag, switched_on
from gyrinx.site.models import Availability, FeatureFlag

pytestmark = pytest.mark.django_db

#: Register an isolated test slug without depending on edition features.
FLAG = "test-only-feature"
register_flags(FLAG)

GROUP_NAME = "Test Feature Alpha"


@pytest.fixture
def group():
    return Group.objects.create(name=GROUP_NAME)


@pytest.fixture
def make_flag(group):
    def make(availability, with_group=True):
        return FeatureFlag.objects.create(
            slug=FLAG,
            name="Test Feature",
            availability=availability,
            group=group if with_group else None,
        )

    return make


@pytest.fixture
def reader():
    return User.objects.create_user("reader")


@pytest.fixture
def invited(group):
    person = User.objects.create_user("invited")
    person.groups.add(group)
    return person


class TestAFeatureNobodyHasOpened:
    def test_a_slug_with_no_row_is_shut(self, reader):
        """Registered features remain disabled until configured."""
        assert enabled(FLAG, reader) is False

    def test_a_slug_the_code_does_not_know_raises(self, reader):
        """Reject unregistered slugs so misspelled guards cannot silently disable features."""
        with pytest.raises(ValueError, match="No such feature flag"):
            enabled("teleportation", reader)

    def test_a_guard_on_an_unknown_slug_refuses_to_be_applied(self):
        """Validate the slug when applying the decorator, before handling requests."""
        with pytest.raises(ValueError, match="No such feature flag"):

            @requires_flag("teleportation")
            def view(request):
                pass


class TestOff:
    """OFF overrides group membership and staff privileges."""

    def test_it_shuts_out_someone_in_the_group(self, make_flag, invited):
        make_flag(Availability.OFF)
        assert enabled(FLAG, invited) is False

    def test_it_shuts_out_an_ordinary_reader(self, make_flag, reader):
        make_flag(Availability.OFF)
        assert enabled(FLAG, reader) is False

    def test_it_shuts_out_staff_and_superusers_too(self, make_flag):
        make_flag(Availability.OFF)
        boss = User.objects.create_user("boss", is_staff=True, is_superuser=True)
        assert enabled(FLAG, boss) is False


class TestTheAllowlist:
    def test_someone_in_the_group_gets_in(self, make_flag, invited):
        make_flag(Availability.ALLOWLIST)
        assert enabled(FLAG, invited) is True

    def test_a_reader_outside_it_does_not(self, make_flag, reader):
        make_flag(Availability.ALLOWLIST)
        assert enabled(FLAG, reader) is False

    def test_a_visitor_does_not(self, make_flag):
        make_flag(Availability.ALLOWLIST)
        assert enabled(FLAG, AnonymousUser()) is False

    def test_being_in_some_other_group_is_not_enough(self, make_flag, reader):
        make_flag(Availability.ALLOWLIST)
        reader.groups.add(Group.objects.create(name="Some Other Alpha"))
        assert enabled(FLAG, reader) is False

    def test_no_group_at_all_lets_nobody_in(self, make_flag, reader):
        """An allowlist with no group grants no access."""
        make_flag(Availability.ALLOWLIST, with_group=False)
        assert enabled(FLAG, reader) is False

    def test_taking_someone_out_of_the_group_shuts_them_out(
        self, make_flag, invited, group
    ):
        """Removing group membership revokes access without changing the flag."""
        make_flag(Availability.ALLOWLIST)
        assert enabled(FLAG, invited) is True
        invited.groups.remove(group)
        assert enabled(FLAG, invited) is False


class TestAWordNothingCanRead:
    """Reject invalid availability values in storage and access checks."""

    def test_the_database_refuses_to_store_one(self, group):
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            FeatureFlag.objects.create(
                slug=FLAG, name="Test Feature", availability="on"
            )

    def test_one_in_hand_is_shut_rather_than_open(self, group, invited):
        """Reject invalid availability on an unsaved object before checking group membership."""
        flag = FeatureFlag(
            slug=FLAG, name="Test Feature", availability="on", group=group
        )
        assert flag.open_to(invited) is False


class TestEveryone:
    def test_any_signed_in_reader_gets_in(self, make_flag, reader):
        make_flag(Availability.EVERYONE)
        assert enabled(FLAG, reader) is True

    def test_a_visitor_still_does_not(self, make_flag):
        make_flag(Availability.EVERYONE)
        assert enabled(FLAG, AnonymousUser()) is False


class TestSwitchedOn:
    """Background work treats ALLOWLIST and EVERYONE as enabled, without checking a user."""

    def test_a_slug_with_no_row_is_off(self):
        assert switched_on(FLAG) is False

    def test_a_slug_the_code_does_not_know_raises(self):
        with pytest.raises(ValueError, match="No such feature flag"):
            switched_on("teleportation")

    def test_off_is_off(self, make_flag):
        make_flag(Availability.OFF)
        assert switched_on(FLAG) is False

    def test_the_allowlist_counts_as_on(self, make_flag):
        make_flag(Availability.ALLOWLIST)
        assert switched_on(FLAG) is True

    def test_everyone_counts_as_on(self, make_flag):
        make_flag(Availability.EVERYONE)
        assert switched_on(FLAG) is True


class TestTheRowItself:
    def test_it_starts_shut(self, group):
        assert FeatureFlag.objects.create(
            slug=FLAG, name="Test Feature"
        ).availability == (Availability.OFF)

    def test_a_slug_is_claimed_once(self, make_flag):
        from django.db import IntegrityError

        make_flag(Availability.OFF)
        with pytest.raises(IntegrityError):
            FeatureFlag.objects.create(slug=FLAG, name="Test Feature again")

    def test_it_says_what_it_is_and_how_open(self, make_flag):
        assert str(make_flag(Availability.ALLOWLIST)).startswith(
            "Test Feature (Allowlist"
        )

    def test_deleting_the_group_leaves_the_flag_standing_and_shut(
        self, make_flag, invited, group
    ):
        """Deleting the allowlist group preserves the flag and revokes access."""
        flag = make_flag(Availability.ALLOWLIST)
        group.delete()
        flag.refresh_from_db()
        assert flag.group is None
        assert enabled(FLAG, invited) is False


class TestTheAdminPage:
    """Configure feature access through the admin."""

    def _admin(self):
        from django.contrib import admin

        from gyrinx.site.models import FeatureFlag as Model

        return admin.site._registry[Model]

    def test_it_is_registered(self):
        assert self._admin() is not None

    def test_the_changelist_shows_how_open_each_feature_is(self):
        assert "availability" in self._admin().list_display
        assert "group" in self._admin().list_display

    def test_the_slug_is_settable_when_creating(self):
        assert "slug" not in self._admin().get_readonly_fields(None, obj=None)

    def test_a_typed_slug_is_cleaned_on_the_way_in(self):
        """Slugify admin input before saving."""
        from gyrinx.site.admin import FeatureFlagForm

        form = FeatureFlagForm(
            data={"slug": "  My Fancy Flag! ", "name": "Fancy", "availability": "off"}
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["slug"] == "my-fancy-flag"

    def test_a_slug_that_cleans_to_nothing_is_refused(self):
        from gyrinx.site.admin import FeatureFlagForm

        form = FeatureFlagForm(
            data={"slug": "!!!", "name": "Noise", "availability": "off"}
        )
        assert not form.is_valid()
        assert "slug" in form.errors

    def test_the_same_flag_cannot_be_configured_twice(self, make_flag):
        """Check uniqueness after normalising the submitted slug."""
        from gyrinx.site.admin import FeatureFlagForm

        make_flag(Availability.OFF)
        dupe = FeatureFlagForm(
            data={"slug": FLAG.upper(), "name": "Again", "availability": "off"}
        )
        assert not dupe.is_valid()
        assert "slug" in dupe.errors

    def test_the_slug_is_fixed_once_the_row_exists(self, make_flag):
        """Keep an existing flag associated with the slug its callers use."""
        flag = make_flag(Availability.OFF)
        assert "slug" in self._admin().get_readonly_fields(None, obj=flag)

    def test_it_keeps_whatever_else_is_already_fixed(self, make_flag, monkeypatch):
        """Preserve inherited read-only fields when adding the slug restriction."""
        admin = self._admin()
        monkeypatch.setattr(type(admin), "readonly_fields", ["name"], raising=False)
        assert set(admin.get_readonly_fields(None, obj=None)) == {"name"}
        assert set(
            admin.get_readonly_fields(None, obj=make_flag(Availability.OFF))
        ) == {
            "name",
            "slug",
        }


class TestTheViewGuard:
    def _view(self):
        @requires_flag(FLAG)
        def view(request):
            return "drawn"

        return view

    def _request(self, user):
        request = RequestFactory().get("/n26/campaigns/")
        request.user = user
        return request

    def test_it_draws_the_page_for_someone_allowed(self, make_flag, invited):
        make_flag(Availability.ALLOWLIST)
        assert self._view()(self._request(invited)) == "drawn"

    def test_it_answers_404_and_not_403(self, make_flag, reader):
        """Hide inaccessible feature pages with 404."""
        make_flag(Availability.ALLOWLIST)
        with pytest.raises(Http404):
            self._view()(self._request(reader))

    def test_a_visitor_is_not_sent_to_sign_in(self, make_flag):
        """Return 404 to anonymous readers without revealing a feature through a login redirect."""
        make_flag(Availability.ALLOWLIST)
        with pytest.raises(Http404):
            self._view()(self._request(AnonymousUser()))

    def test_switching_the_flag_off_closes_the_page(self, make_flag, invited):
        flag = make_flag(Availability.ALLOWLIST)
        assert self._view()(self._request(invited)) == "drawn"
        flag.availability = Availability.OFF
        flag.save()
        with pytest.raises(Http404):
            self._view()(self._request(invited))

    def test_it_keeps_the_wrapped_views_name(self, make_flag):
        make_flag(Availability.EVERYONE)
        assert self._view().__name__ == "view"
