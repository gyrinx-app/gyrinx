"""Tests for the badge selection form, account page, and inline profile render."""

import pytest
from django.urls import reverse

from gyrinx.core.badges import HIDE_BADGE
from gyrinx.core.forms import BadgeSelectionForm
from gyrinx.core.models.auth import PatreonStatus, UserProfile

BADGE_URL = reverse("core:badge-settings")


def _profile(user, **kwargs):
    return UserProfile.objects.create(user=user, **kwargs)


# --- Form ---


@pytest.mark.django_db
def test_form_offers_only_unlocked_badges(user):
    _profile(user, patreon_status=PatreonStatus.ACTIVE, patreon_tier="Scummer")
    form = BadgeSelectionForm(user=user)
    values = [v for v, _ in form.fields["selected_badge"].choices]
    assert values == ["scummer", HIDE_BADGE]


@pytest.mark.django_db
def test_form_preselects_current_tier_by_default(user):
    # With no explicit choice, the form pre-selects the current-tier badge.
    _profile(user, patreon_status=PatreonStatus.ACTIVE, patreon_tier="Guilder")
    form = BadgeSelectionForm(user=user)
    assert form.fields["selected_badge"].initial == "guilder"


@pytest.mark.django_db
def test_form_accepts_eligible_selection(user):
    _profile(user, patreon_status=PatreonStatus.ACTIVE, patreon_tier="Uphiver")
    form = BadgeSelectionForm({"selected_badge": "guilder"}, user=user)
    assert form.is_valid()
    form.save()
    user.profile.refresh_from_db()
    assert user.profile.selected_badge == "guilder"


@pytest.mark.django_db
def test_form_rejects_ineligible_selection(user):
    _profile(user, patreon_status=PatreonStatus.ACTIVE, patreon_tier="Scummer")
    form = BadgeSelectionForm({"selected_badge": "uphiver"}, user=user)
    assert not form.is_valid()
    assert "selected_badge" in form.errors


@pytest.mark.django_db
def test_form_allows_hiding_badge(user):
    _profile(
        user,
        patreon_status=PatreonStatus.ACTIVE,
        patreon_tier="Uphiver",
        selected_badge="uphiver",
    )
    form = BadgeSelectionForm({"selected_badge": HIDE_BADGE}, user=user)
    assert form.is_valid()
    form.save()
    user.profile.refresh_from_db()
    assert user.profile.selected_badge == HIDE_BADGE
    # Opt-out hides the badge — verified on a fresh instance in test_badges.py
    # (display_badge is a cached_property, so the form's pre-save read would
    # otherwise mask the change on this reused instance).
    assert UserProfile.objects.get(pk=user.profile.pk).display_badge is None


# --- View ---


@pytest.mark.django_db
def test_badge_page_requires_login(client):
    response = client.get(BADGE_URL)
    assert response.status_code == 302
    assert "/accounts/login" in response.url or "login" in response.url


@pytest.mark.django_db
def test_badge_page_shows_unlocked_badges(client, user):
    _profile(user, patreon_status=PatreonStatus.ACTIVE, patreon_tier="Uphiver")
    client.force_login(user)
    response = client.get(BADGE_URL)
    content = response.content.decode()
    assert response.status_code == 200
    assert "Scummer" in content
    assert "Guilder" in content
    assert "Uphiver" in content
    assert "Hide badge" in content
    # The opt-out radio carries the sentinel value from context, not a literal.
    assert f'value="{HIDE_BADGE}"' in content


@pytest.mark.django_db
def test_badge_page_empty_state_for_non_supporter(client, user):
    client.force_login(user)
    response = client.get(BADGE_URL)
    content = response.content.decode()
    assert response.status_code == 200
    assert "don't have any badges yet" in content


@pytest.mark.django_db
def test_badge_page_post_saves_selection(client, user):
    _profile(user, patreon_status=PatreonStatus.ACTIVE, patreon_tier="Guilder")
    client.force_login(user)
    response = client.post(BADGE_URL, {"selected_badge": "guilder"})
    assert response.status_code == 302
    user.profile.refresh_from_db()
    assert user.profile.selected_badge == "guilder"


@pytest.mark.django_db
def test_badge_page_post_rejects_ineligible(client, user):
    _profile(user, patreon_status=PatreonStatus.ACTIVE, patreon_tier="Scummer")
    client.force_login(user)
    response = client.post(BADGE_URL, {"selected_badge": "uphiver"})
    assert response.status_code == 200  # re-render with errors
    user.profile.refresh_from_db()
    assert user.profile.selected_badge == ""


# --- Inline render on the public profile page ---


@pytest.mark.django_db
def test_profile_page_shows_badge_for_supporter(client, user):
    _profile(
        user,
        patreon_status=PatreonStatus.ACTIVE,
        patreon_tier="Guilder",
        selected_badge="guilder",
    )
    url = reverse("core:user", args=[user.username])
    response = client.get(url)
    content = response.content.decode()
    assert response.status_code == 200
    assert 'data-bs-title="Gyrinx supporter — Guilder tier"' in content


@pytest.mark.django_db
def test_profile_page_shows_default_badge_without_selection(client, user):
    # Active patron who never opened the picker still shows their tier badge.
    _profile(user, patreon_status=PatreonStatus.ACTIVE, patreon_tier="Guilder")
    url = reverse("core:user", args=[user.username])
    response = client.get(url)
    content = response.content.decode()
    assert response.status_code == 200
    assert 'title="Guilder"' in content


@pytest.mark.django_db
def test_profile_page_hides_badge_when_opted_out(client, user):
    _profile(
        user,
        patreon_status=PatreonStatus.ACTIVE,
        patreon_tier="Guilder",
        selected_badge=HIDE_BADGE,
    )
    url = reverse("core:user", args=[user.username])
    response = client.get(url)
    content = response.content.decode()
    assert response.status_code == 200
    assert "user-badge" not in content


@pytest.mark.django_db
def test_profile_page_hides_badge_for_former_supporter(client, user):
    _profile(
        user,
        patreon_status=PatreonStatus.FORMER,
        patreon_tier="Guilder",
        selected_badge="guilder",
    )
    url = reverse("core:user", args=[user.username])
    response = client.get(url)
    content = response.content.decode()
    assert response.status_code == 200
    assert "user-badge" not in content


# --- Inline render in the breadcrumb (list detail page) ---


@pytest.mark.django_db
def test_breadcrumb_shows_badge_for_supporter(client, user, make_list):
    _profile(
        user,
        patreon_status=PatreonStatus.ACTIVE,
        patreon_tier="Guilder",
        selected_badge="guilder",
    )
    lst = make_list("Badge Breadcrumb List", public=True)
    response = client.get(reverse("core:list", args=[lst.id]))
    content = response.content.decode()
    assert response.status_code == 200
    assert 'data-bs-title="Gyrinx supporter — Guilder tier"' in content


@pytest.mark.django_db
def test_breadcrumb_hides_badge_for_non_supporter(client, user, make_list):
    _profile(user)  # no Patreon data
    lst = make_list("No Badge Breadcrumb List", public=True)
    response = client.get(reverse("core:list", args=[lst.id]))
    content = response.content.decode()
    assert response.status_code == 200
    assert "user-badge" not in content
