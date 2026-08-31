"""Activating and persisting a reader's timezone."""

import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone as dj_tz

from gyrinx.accounts.models import UserProfile
from gyrinx.middleware import TimezoneMiddleware
from gyrinx.timezones import COOKIE_NAME, SESSION_TZ_KEY


def _run(request):
    captured = {}

    def inner(req):
        captured["tz"] = dj_tz.get_current_timezone_name()
        return HttpResponse("ok")

    TimezoneMiddleware(inner)(request)
    return captured["tz"]


@pytest.mark.django_db
def test_saved_profile_timezone_is_activated(user):
    UserProfile.objects.create(user=user, timezone="America/New_York")
    request = RequestFactory().get("/")
    request.user = user
    request.session = {}
    request.is_impersonating = False
    assert _run(request) == "America/New_York"
    assert request.session[SESSION_TZ_KEY] == "America/New_York"


@pytest.mark.django_db
def test_blank_profile_is_filled_from_country_header(user):
    UserProfile.objects.create(user=user)
    request = RequestFactory().get("/", HTTP_CF_IPCOUNTRY="GB")
    request.user = user
    request.session = {}
    request.is_impersonating = False
    assert _run(request) == "Europe/London"
    user.profile.refresh_from_db()
    assert user.profile.timezone == "Europe/London"


@pytest.mark.django_db
def test_blank_profile_is_filled_from_browser_cookie(user):
    UserProfile.objects.create(user=user)
    request = RequestFactory().get("/")
    request.COOKIES[COOKIE_NAME] = "Pacific/Auckland"
    request.user = user
    request.session = {}
    request.is_impersonating = False
    assert _run(request) == "Pacific/Auckland"
    user.profile.refresh_from_db()
    assert user.profile.timezone == "Pacific/Auckland"


@pytest.mark.django_db
def test_blank_profile_is_filled_from_percent_encoded_cookie(user):
    UserProfile.objects.create(user=user)
    request = RequestFactory().get("/")
    request.COOKIES[COOKIE_NAME] = "America%2FNew_York"
    request.user = user
    request.session = {}
    request.is_impersonating = False
    assert _run(request) == "America/New_York"
    user.profile.refresh_from_db()
    assert user.profile.timezone == "America/New_York"


@pytest.mark.django_db
def test_saved_timezone_is_not_overwritten_by_a_guess(user):
    UserProfile.objects.create(user=user, timezone="UTC")
    request = RequestFactory().get("/", HTTP_CF_IPCOUNTRY="GB")
    request.COOKIES[COOKIE_NAME] = "America/Los_Angeles"
    request.user = user
    request.session = {}
    request.is_impersonating = False
    assert _run(request) == "UTC"
    user.profile.refresh_from_db()
    assert user.profile.timezone == "UTC"


@pytest.mark.django_db
def test_impersonation_does_not_persist_a_guess(user, make_user):
    target = make_user("target", "password")
    UserProfile.objects.create(user=target)
    request = RequestFactory().get("/", HTTP_CF_IPCOUNTRY="GB")
    request.user = target
    request.session = {}
    request.is_impersonating = True
    assert _run(request) == "Europe/London"
    target.profile.refresh_from_db()
    assert target.profile.timezone == ""
    assert SESSION_TZ_KEY not in request.session


@pytest.mark.django_db
def test_account_home_renders_after_timezone_is_saved(client, user):
    UserProfile.objects.create(user=user, timezone="Europe/London")
    client.force_login(user)
    response = client.get(reverse("core:account_home"))
    assert response.status_code == 200
    user.profile.refresh_from_db()
    assert user.profile.timezone == "Europe/London"


@pytest.mark.django_db
def test_account_home_fills_timezone_from_percent_encoded_cookie(client, user):
    UserProfile.objects.create(user=user)
    client.force_login(user)
    client.cookies[COOKIE_NAME] = "Europe%2FLondon"
    response = client.get(reverse("core:account_home"))
    assert response.status_code == 200
    user.profile.refresh_from_db()
    assert user.profile.timezone == "Europe/London"
