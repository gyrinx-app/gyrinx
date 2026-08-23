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

    def test_the_slug_is_fixed_once_the_row_exists(self, make_flag):
        """Editing it later would not rename a feature — it would turn one
        off and leave a second that nothing reads."""
        flag = make_flag(Availability.OFF)
        assert "slug" in self._admin().get_readonly_fields(None, obj=flag)

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
