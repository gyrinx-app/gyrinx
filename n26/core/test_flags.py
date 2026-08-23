import pytest
from django.contrib.auth.models import AnonymousUser, Group, User
from django.http import Http404
from django.test import RequestFactory, override_settings

from n26.core.flags import (
    FLAGS,
    Availability,
    availability,
    enabled,
    requires_flag,
)

pytestmark = pytest.mark.django_db

# The group is created by a data migration, which does not run under
# --nomigrations. Every test that needs it makes its own.
CAMPAIGNS_GROUP = FLAGS["campaigns"].group


@pytest.fixture
def reader():
    return User.objects.create_user("reader")


@pytest.fixture
def invited():
    person = User.objects.create_user("invited")
    person.groups.add(Group.objects.create(name=CAMPAIGNS_GROUP))
    return person


class TestTheKillSwitch:
    """ "off" beats everything else, which is the whole point of it."""

    @override_settings(N26_FLAG_CAMPAIGNS=Availability.OFF)
    def test_it_shuts_out_someone_on_the_allowlist(self, invited):
        assert enabled("campaigns", invited) is False

    @override_settings(N26_FLAG_CAMPAIGNS=Availability.OFF)
    def test_it_shuts_out_an_ordinary_reader(self, reader):
        assert enabled("campaigns", reader) is False

    @override_settings(N26_FLAG_CAMPAIGNS=Availability.OFF)
    def test_it_shuts_out_staff_and_superusers_too(self):
        boss = User.objects.create_user("boss", is_staff=True, is_superuser=True)
        assert enabled("campaigns", boss) is False


class TestTheAllowlist:
    @override_settings(N26_FLAG_CAMPAIGNS=Availability.ALLOWLIST)
    def test_a_member_gets_in(self, invited):
        assert enabled("campaigns", invited) is True

    @override_settings(N26_FLAG_CAMPAIGNS=Availability.ALLOWLIST)
    def test_a_reader_who_is_not_a_member_does_not(self, reader):
        assert enabled("campaigns", reader) is False

    @override_settings(N26_FLAG_CAMPAIGNS=Availability.ALLOWLIST)
    def test_a_visitor_does_not(self):
        assert enabled("campaigns", AnonymousUser()) is False

    @override_settings(N26_FLAG_CAMPAIGNS=Availability.ALLOWLIST)
    def test_being_in_some_other_group_is_not_enough(self, reader):
        reader.groups.add(Group.objects.create(name="Some Other Alpha"))
        assert enabled("campaigns", reader) is False

    @override_settings(N26_FLAG_CAMPAIGNS=Availability.ALLOWLIST)
    def test_a_missing_group_lets_nobody_in(self, reader):
        """A group nobody has created yet is an empty allowlist, not an
        open door — a typo in the name must fail shut."""
        assert not Group.objects.filter(name=CAMPAIGNS_GROUP).exists()
        assert enabled("campaigns", reader) is False


class TestShippingToEveryone:
    @override_settings(N26_FLAG_CAMPAIGNS=Availability.EVERYONE)
    def test_any_signed_in_reader_gets_in(self, reader):
        assert enabled("campaigns", reader) is True

    @override_settings(N26_FLAG_CAMPAIGNS=Availability.EVERYONE)
    def test_a_visitor_still_does_not(self):
        assert enabled("campaigns", AnonymousUser()) is False


class TestMistakesThatAreNotAReadersFault:
    @override_settings(N26_FLAG_CAMPAIGNS="on")
    def test_an_unrecognised_setting_raises_rather_than_guessing(self):
        with pytest.raises(ValueError, match="N26_FLAG_CAMPAIGNS"):
            availability(FLAGS["campaigns"])

    def test_an_unknown_flag_name_raises(self, reader):
        with pytest.raises(ValueError, match="No such feature flag"):
            enabled("teleportation", reader)

    def test_an_absent_setting_is_treated_as_off(self, settings, invited):
        del settings.N26_FLAG_CAMPAIGNS
        assert enabled("campaigns", invited) is False


class TestTheViewGuard:
    def _view(self):
        @requires_flag("campaigns")
        def view(request):
            return "drawn"

        return view

    def _request(self, user):
        request = RequestFactory().get("/n26/campaigns/")
        request.user = user
        return request

    @override_settings(N26_FLAG_CAMPAIGNS=Availability.ALLOWLIST)
    def test_it_draws_the_page_for_someone_allowed(self, invited):
        assert self._view()(self._request(invited)) == "drawn"

    @override_settings(N26_FLAG_CAMPAIGNS=Availability.ALLOWLIST)
    def test_it_answers_404_and_not_403(self, reader):
        """A stranger is told the page is not there. Which features are
        being built is not something to be probed for."""
        with pytest.raises(Http404):
            self._view()(self._request(reader))

    @override_settings(N26_FLAG_CAMPAIGNS=Availability.ALLOWLIST)
    def test_a_visitor_is_not_sent_to_sign_in(self, client):
        """404 rather than a login redirect: being asked to sign in would
        itself say that something is there."""
        with pytest.raises(Http404):
            self._view()(self._request(AnonymousUser()))

    @override_settings(N26_FLAG_CAMPAIGNS=Availability.OFF)
    def test_the_kill_switch_closes_the_page_for_everyone(self, invited):
        with pytest.raises(Http404):
            self._view()(self._request(invited))

    @override_settings(N26_FLAG_CAMPAIGNS=Availability.EVERYONE)
    def test_it_keeps_the_wrapped_views_name(self):
        assert self._view().__name__ == "view"
