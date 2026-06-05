"""Tests for the development-only debug views."""

import pytest
from django.test import override_settings
from django.urls import reverse


@override_settings(DEBUG=True)
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
