import pytest
from django.contrib.auth.models import AnonymousUser, Group, User
from django.http import Http404
from django.test import RequestFactory

from gyrinx.site.flags import enabled, register_flags, requires_flag, switched_on
from gyrinx.site.models import Availability, FeatureFlag

pytestmark = pytest.mark.django_db

#: A slug of this suite's own. The platform never names an edition's
#: features, so these tests claim one the way an edition claims its real
#: ones, and nothing here depends on which editions are installed.
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
        """A feature whose row has not been created fails shut. Absent is
        not the same as allowed."""
        assert enabled(FLAG, reader) is False

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
        """An empty allowlist, not an open door."""
        make_flag(Availability.ALLOWLIST, with_group=False)
        assert enabled(FLAG, reader) is False

    def test_taking_someone_out_of_the_group_shuts_them_out(
        self, make_flag, invited, group
    ):
        """The admin's other lever: the flag stays as it is and the person
        stops qualifying."""
        make_flag(Availability.ALLOWLIST)
        assert enabled(FLAG, invited) is True
        invited.groups.remove(group)
        assert enabled(FLAG, invited) is False


class TestAWordNothingCanRead:
    """A value outside Availability must never be a way in."""

    def test_the_database_refuses_to_store_one(self, group):
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            FeatureFlag.objects.create(
                slug=FLAG, name="Test Feature", availability="on"
            )

    def test_one_in_hand_is_shut_rather_than_open(self, group, invited):
        """Belt to the constraint's braces. A flag carrying a word nothing
        recognises must refuse a group member rather than fall through to
        the group check and let them in on the strength of it."""
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
    """The user-free question background work asks: is the feature on
    at all. Any availability but off counts, because a feature open to
    even one account needs the machinery behind it running."""

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
        """A deleted group must not take the flag with it, nor quietly
        become an open door."""
        flag = make_flag(Availability.ALLOWLIST)
        group.delete()
        flag.refresh_from_db()
        assert flag.group is None
        assert enabled(FLAG, invited) is False


class TestTheAdminPage:
    """The page is the point of the model: opening a feature to another
    player is something somebody does here, not in a deploy."""

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

    def test_only_a_slug_the_code_asks_for_may_be_stored(self, group):
        """A row whose slug nothing reads is inert — it sits on the page
        reading as a control over something and controls nothing. The form
        offers the known slugs rather than taking free text."""
        from gyrinx.site.admin import FeatureFlagForm
        from gyrinx.site.flags import known_flags

        good = FeatureFlagForm(
            data={"slug": FLAG, "name": "Test Feature", "availability": "off"}
        )
        assert good.is_valid(), good.errors

        bad = FeatureFlagForm(
            data={"slug": "campiagns", "name": "Typo", "availability": "off"}
        )
        assert not bad.is_valid()
        assert "slug" in bad.errors
        assert set(dict(bad.fields["slug"].choices)) == set(known_flags())

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
