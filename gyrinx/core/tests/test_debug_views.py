"""Tests for the development-only debug views."""

import pytest
from django.test import override_settings
from django.urls import reverse

# Under DEBUG=True the django-debug-toolbar middleware activates for the test
# client (its default show callback returns True when REMOTE_ADDR is in
# INTERNAL_IPS) and then fails to reverse its own ``djdt`` URLs (not installed
# in the test URLconf). The toolbar's show callback is resolved once and
# @cache-d, so overriding DEBUG_TOOLBAR_CONFIG is unreliable across tests;
# clearing INTERNAL_IPS is read fresh per request and reliably keeps it off.
_no_toolbar = {"INTERNAL_IPS": []}


@override_settings(DEBUG=True, **_no_toolbar)
@pytest.mark.django_db
def test_design_system_renders_logged_out(client):
    """The design system reference must render without authentication.

    It previously 500'd for anonymous users because the breadcrumb samples
    reversed ``{% url 'core:user' %}`` from ``request.user`` (AnonymousUser has
    no username). The view now supplies a fake breadcrumb owner instead.
    """
    response = client.get(reverse("debug_design_system"))

    assert response.status_code == 200
    # The house icon sample renders the .house-icon class for the CSS preview.
    assert b"house-icon" in response.content


@override_settings(DEBUG=False)
@pytest.mark.django_db
def test_design_system_404_when_debug_disabled(client):
    """Debug views are only reachable in development."""
    response = client.get(reverse("debug_design_system"))

    assert response.status_code == 404


@override_settings(DEBUG=False)
@pytest.mark.django_db
def test_list_actions_404_when_debug_disabled(client, make_list):
    """The list-actions debug view must 404 in production, even for the owner."""
    lst = make_list("Test Gang")
    response = client.get(reverse("debug_list_actions", args=[lst.id]))

    assert response.status_code == 404


@override_settings(DEBUG=True, **_no_toolbar)
@pytest.mark.django_db
def test_list_actions_404_for_anonymous(client, make_list):
    """Anonymous users get a 404 (not another user's activity log)."""
    lst = make_list("Test Gang")
    response = client.get(reverse("debug_list_actions", args=[lst.id]))

    assert response.status_code == 404


@override_settings(DEBUG=True, **_no_toolbar)
@pytest.mark.django_db
def test_list_actions_404_for_non_owner(client, make_list, make_user):
    """A logged-in non-owner cannot view another gang's actions."""
    lst = make_list("Test Gang")
    other = make_user("intruder", "password")
    client.force_login(other)
    response = client.get(reverse("debug_list_actions", args=[lst.id]))

    assert response.status_code == 404


@override_settings(DEBUG=True, **_no_toolbar)
@pytest.mark.django_db
def test_list_actions_visible_to_owner(client, user, make_list):
    """The list owner can view their own actions in development."""
    lst = make_list("Test Gang")
    client.force_login(user)
    response = client.get(reverse("debug_list_actions", args=[lst.id]))

    assert response.status_code == 200


@override_settings(DEBUG=True, **_no_toolbar)
@pytest.mark.django_db
def test_list_actions_visible_to_staff(client, make_list, make_user):
    """Staff can view any list's actions in development."""
    lst = make_list("Test Gang")
    staff = make_user("admin", "password")
    staff.is_staff = True
    staff.save()
    client.force_login(staff)
    response = client.get(reverse("debug_list_actions", args=[lst.id]))

    assert response.status_code == 200
