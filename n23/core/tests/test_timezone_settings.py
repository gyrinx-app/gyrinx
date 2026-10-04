"""Timezone account settings."""

import pytest
from django.urls import reverse

from gyrinx.account_forms import TimezoneForm
from gyrinx.accounts.models import UserProfile

TZ_URL = reverse("core:timezone-settings")


def _profile(user, **kwargs):
    return UserProfile.objects.create(user=user, **kwargs)


@pytest.mark.django_db
def test_form_preselects_saved_timezone(user):
    _profile(user, timezone="America/New_York")
    form = TimezoneForm(user=user)
    assert form.fields["timezone"].initial == "America/New_York"


@pytest.mark.django_db
def test_form_rejects_unknown_zone(user):
    _profile(user)
    form = TimezoneForm({"timezone": "Not/A_Zone"}, user=user)
    assert not form.is_valid()
    assert "timezone" in form.errors


@pytest.mark.django_db
def test_form_saves_a_valid_zone(user):
    _profile(user)
    form = TimezoneForm({"timezone": "Europe/London"}, user=user)
    assert form.is_valid()
    form.save()
    user.profile.refresh_from_db()
    assert user.profile.timezone == "Europe/London"


@pytest.mark.django_db
def test_page_requires_login(client):
    response = client.get(TZ_URL, follow=True)
    assert response.redirect_chain
    assert "login" in response.redirect_chain[0][0]


@pytest.mark.django_db
def test_page_shows_the_picker(client, user):
    _profile(user, timezone="UTC")
    client.force_login(user)
    response = client.get(TZ_URL, follow=True)
    content = response.content.decode()
    assert response.status_code == 200
    assert "Time zone" in content
    assert "Europe/London" in content
    assert "America/New_York" in content


@pytest.mark.django_db
def test_page_post_saves_selection(client, user):
    _profile(user)
    client.force_login(user)
    response = client.post(TZ_URL, {"timezone": "Australia/Sydney"})
    assert response.status_code == 302
    assert response.url == reverse("core:account_home")
    user.profile.refresh_from_db()
    assert user.profile.timezone == "Australia/Sydney"


@pytest.mark.django_db
def test_tabs_link_to_combined_settings(client, user):
    client.force_login(user)
    response = client.get(reverse("core:account_home"))
    content = response.content.decode()
    assert reverse("account-settings") in content
    assert "Settings" in content
