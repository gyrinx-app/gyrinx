import pytest
from django.contrib.auth.models import AnonymousUser, Group, User
from django.http import Http404
from django.test import RequestFactory

from n26.core.flags import CAMPAIGNS, enabled, requires_flag
from n26.core.models import Availability, FeatureFlag

pytestmark = pytest.mark.django_db

# The row and its group are seeded by data migrations, which do not run
# under --nomigrations. Every test makes what it needs.
GROUP_NAME = "N26 Campaigns"


@pytest.fixture
def group():
    return Group.objects.create(name=GROUP_NAME)


@pytest.fixture
def make_flag(group):
    def make(availability, with_group=True):
        return FeatureFlag.objects.create(
            slug=CAMPAIGNS,
            name="Campaigns",
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
        """A feature whose row has not been created fails shut. Absent is
        not the same as allowed."""
        assert enabled(CAMPAIGNS, reader) is False

    def test_a_slug_the_code_does_not_know_raises(self, reader):
        """A typo in a guard must be loud. The alternative is a guard that
        is quietly inert on a page it was meant to protect."""
        with pytest.raises(ValueError, match="No such feature flag"):
            enabled("teleportation", reader)

    def test_a_guard_on_an_unknown_slug_refuses_to_be_applied(self):
        """As the guard is applied, not as a request arrives. A mistyped
        slug is a mistake in the code, so the app refuses to start rather
        than serving errors to whoever finds the page first."""
        with pytest.raises(ValueError, match="No such feature flag"):

            @requires_flag("teleportation")
            def view(request):
                pass


class TestOff:
    """Off beats the group, which is the whole point of having it."""

    def test_it_shuts_out_someone_in_the_group(self, make_flag, invited):
        make_flag(Availability.OFF)
        assert enabled(CAMPAIGNS, invited) is False

    def test_it_shuts_out_an_ordinary_reader(self, make_flag, reader):
        make_flag(Availability.OFF)
        assert enabled(CAMPAIGNS, reader) is False

    def test_it_shuts_out_staff_and_superusers_too(self, make_flag):
        make_flag(Availability.OFF)
        boss = User.objects.create_user("boss", is_staff=True, is_superuser=True)
        assert enabled(CAMPAIGNS, boss) is False


class TestTheAllowlist:
    def test_someone_in_the_group_gets_in(self, make_flag, invited):
        make_flag(Availability.ALLOWLIST)
        assert enabled(CAMPAIGNS, invited) is True

    def test_a_reader_outside_it_does_not(self, make_flag, reader):
        make_flag(Availability.ALLOWLIST)
        assert enabled(CAMPAIGNS, reader) is False

    def test_a_visitor_does_not(self, make_flag):
        make_flag(Availability.ALLOWLIST)
        assert enabled(CAMPAIGNS, AnonymousUser()) is False

    def test_being_in_some_other_group_is_not_enough(self, make_flag, reader):
        make_flag(Availability.ALLOWLIST)
        reader.groups.add(Group.objects.create(name="Some Other Alpha"))
        assert enabled(CAMPAIGNS, reader) is False

    def test_no_group_at_all_lets_nobody_in(self, make_flag, reader):
        """An empty allowlist, not an open door."""
        make_flag(Availability.ALLOWLIST, with_group=False)
        assert enabled(CAMPAIGNS, reader) is False

    def test_taking_someone_out_of_the_group_shuts_them_out(
        self, make_flag, invited, group
    ):
        """The admin's other lever: the flag stays as it is and the person
        stops qualifying."""
        make_flag(Availability.ALLOWLIST)
        assert enabled(CAMPAIGNS, invited) is True
        invited.groups.remove(group)
        assert enabled(CAMPAIGNS, invited) is False


class TestAWordNothingCanRead:
    """A value outside Availability must never be a way in."""

    def test_the_database_refuses_to_store_one(self, group):
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            FeatureFlag.objects.create(
                slug=CAMPAIGNS, name="Campaigns", availability="on"
            )

    def test_one_in_hand_is_shut_rather_than_open(self, group, invited):
        """Belt to the constraint's braces. A flag carrying a word nothing
        recognises must refuse a group member rather than fall through to
        the group check and let them in on the strength of it."""
        flag = FeatureFlag(
            slug=CAMPAIGNS, name="Campaigns", availability="on", group=group
        )
        assert flag.open_to(invited) is False


class TestEveryone:
    def test_any_signed_in_reader_gets_in(self, make_flag, reader):
        make_flag(Availability.EVERYONE)
        assert enabled(CAMPAIGNS, reader) is True

    def test_a_visitor_still_does_not(self, make_flag):
        make_flag(Availability.EVERYONE)
        assert enabled(CAMPAIGNS, AnonymousUser()) is False


class TestTheRowItself:
    def test_it_starts_shut(self, group):
        assert FeatureFlag.objects.create(slug=CAMPAIGNS, name="C").availability == (
            Availability.OFF
        )

    def test_a_slug_is_claimed_once(self, make_flag):
        from django.db import IntegrityError

        make_flag(Availability.OFF)
        with pytest.raises(IntegrityError):
            FeatureFlag.objects.create(slug=CAMPAIGNS, name="Campaigns again")

    def test_it_says_what_it_is_and_how_open(self, make_flag):
        assert str(make_flag(Availability.ALLOWLIST)).startswith("Campaigns (Allowlist")

    def test_deleting_the_group_leaves_the_flag_standing_and_shut(
        self, make_flag, invited, group
    ):
        """A deleted group must not take the flag with it, nor quietly
        become an open door."""
        flag = make_flag(Availability.ALLOWLIST)
        group.delete()
        flag.refresh_from_db()
        assert flag.group is None
        assert enabled(CAMPAIGNS, invited) is False


class TestUndoingTheGroupMigration:
    """Reversing must undo the creation and nothing else. The forward
    operation accepts a group that was already there, so it cannot tell one
    it made from one it found — and deleting somebody's group would take
    every membership with it."""

    def _reverse(self):
        # Imported by name because a module starting with a digit is not a
        # valid identifier, so the import statement cannot reach it.
        import importlib

        from django.apps import apps

        mod = importlib.import_module(
            "n26.core.migrations.0023_an_account_may_be_let_into_campaigns_early"
        )
        mod.remove_campaigns_group(apps, None)

    def test_an_empty_group_is_taken_away(self, group):
        self._reverse()
        assert not Group.objects.filter(name=GROUP_NAME).exists()

    def test_a_group_with_members_is_left_alone(self, invited):
        """Somebody is in it, so it is somebody's."""
        self._reverse()
        assert Group.objects.filter(name=GROUP_NAME).exists()
        assert invited.groups.filter(name=GROUP_NAME).exists()


class TestTheAdminPage:
    """The page is the point of the model: opening a feature to another
    player is something somebody does here, not in a deploy."""

    def _admin(self):
        from django.contrib import admin

        from n26.core.models import FeatureFlag as Model

        return admin.site._registry[Model]

    def test_it_is_registered(self):
        assert self._admin() is not None

    def test_the_changelist_shows_how_open_each_feature_is(self):
        assert "availability" in self._admin().list_display
        assert "group" in self._admin().list_display

    def test_the_slug_is_settable_when_creating(self):
        assert "slug" not in self._admin().get_readonly_fields(None, obj=None)

    def test_only_a_slug_the_code_asks_for_may_be_stored(self, group):
        """A row whose slug nothing reads is inert — it sits on the page
        reading as a control over something and controls nothing. The form
        offers the known slugs rather than taking free text."""
        from n26.core.admin import FeatureFlagForm
        from n26.core.flags import KNOWN_FLAGS

        good = FeatureFlagForm(
            data={"slug": CAMPAIGNS, "name": "Campaigns", "availability": "off"}
        )
        assert good.is_valid(), good.errors

        bad = FeatureFlagForm(
            data={"slug": "campiagns", "name": "Typo", "availability": "off"}
        )
        assert not bad.is_valid()
        assert "slug" in bad.errors
        assert set(dict(bad.fields["slug"].choices)) == set(KNOWN_FLAGS)

    def test_the_slug_is_fixed_once_the_row_exists(self, make_flag):
        """Editing it later would not rename a feature — it would turn one
        off and leave a second that nothing reads."""
        flag = make_flag(Availability.OFF)
        assert "slug" in self._admin().get_readonly_fields(None, obj=flag)

    def test_it_keeps_whatever_else_is_already_fixed(self, make_flag, monkeypatch):
        """Pinning the slug adds to the fixed fields rather than replacing
        them, so a field fixed on the class or a mixin later is not
        silently freed."""
        admin = self._admin()
        monkeypatch.setattr(type(admin), "readonly_fields", ["name"], raising=False)
        assert set(admin.get_readonly_fields(None, obj=None)) == {"name"}
        assert set(
            admin.get_readonly_fields(None, obj=make_flag(Availability.OFF))
        ) == {
            "name",
            "slug",
        }

    def test_the_changelist_offers_no_batch_delete(self):
        """Every n26 changelist withholds it; this one is no exception."""
        request = RequestFactory().get("/admin/n26/featureflag/")
        request.user = User.objects.create_user(
            "boss", is_staff=True, is_superuser=True
        )
        assert "delete_selected" not in self._admin().get_actions(request)


class TestTheViewGuard:
    def _view(self):
        @requires_flag(CAMPAIGNS)
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
        """A stranger is told the page is not there. Which features are
        being built is not something to be probed for."""
        make_flag(Availability.ALLOWLIST)
        with pytest.raises(Http404):
            self._view()(self._request(reader))

    def test_a_visitor_is_not_sent_to_sign_in(self, make_flag):
        """404 rather than a login redirect: being asked to sign in would
        itself say that something is there."""
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
