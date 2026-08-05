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
def test_list_actions_404_when_debug_disabled(client, user, make_list):
    """The list-actions debug view must 404 in production, even for the owner."""
    lst = make_list("Test Gang")
    client.force_login(user)
    response = client.get(reverse("core:debug_list_actions", args=[lst.id]))

    assert response.status_code == 404


@override_settings(DEBUG=False)
@pytest.mark.django_db
def test_list_actions_visible_to_staff_in_production(client, make_list, make_user):
    """Staff retain access in production — the view is admin support tooling.

    Regression test: the original security fix 404'd on DEBUG=False before the
    staff check ever ran, locking admins out in production.
    """
    lst = make_list("Test Gang")
    staff = make_user("admin", "password")
    staff.is_staff = True
    staff.save()
    client.force_login(staff)
    response = client.get(reverse("core:debug_list_actions", args=[lst.id]))

    assert response.status_code == 200


@override_settings(DEBUG=True, **_no_toolbar)
@pytest.mark.django_db
def test_list_actions_404_for_anonymous(client, make_list):
    """Anonymous users get a 404 (not another user's activity log)."""
    lst = make_list("Test Gang")
    response = client.get(reverse("core:debug_list_actions", args=[lst.id]))

    assert response.status_code == 404


@override_settings(DEBUG=True, **_no_toolbar)
@pytest.mark.django_db
def test_list_actions_404_for_non_owner(client, make_list, make_user):
    """A logged-in non-owner cannot view another gang's actions."""
    lst = make_list("Test Gang")
    other = make_user("intruder", "password")
    client.force_login(other)
    response = client.get(reverse("core:debug_list_actions", args=[lst.id]))

    assert response.status_code == 404


@override_settings(DEBUG=True, **_no_toolbar)
@pytest.mark.django_db
def test_list_actions_visible_to_owner(client, user, make_list):
    """The list owner can view their own actions in development."""
    lst = make_list("Test Gang")
    client.force_login(user)
    response = client.get(reverse("core:debug_list_actions", args=[lst.id]))

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
    response = client.get(reverse("core:debug_list_actions", args=[lst.id]))

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Balance-sheet debug view (cost-pinning programme, #1826)
# ---------------------------------------------------------------------------

from django.db import connection  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402

from n23.core.models.list import ListFighter  # noqa: E402
from n23.core.tests.test_balance_sheet import (  # noqa: E402
    buy_equipment,
    hire_fighter,
)


@pytest.fixture
def sheet_list(user, make_list, content_fighter, make_equipment):
    """A list built through real flows, for balance-sheet view tests."""
    lst = make_list("Sheet Gang")
    fighter = hire_fighter(user, lst, content_fighter, name="Bob")
    equipment = make_equipment("Lasgun", cost=15)
    buy_equipment(user, lst, fighter, equipment)
    lst.refresh_from_db()
    return lst, fighter


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_balance_sheet_visible_to_staff_in_production(client, sheet_list, make_user):
    """Staff can pull the balance sheet for any list in any environment."""
    lst, _ = sheet_list
    staff = make_user("staffuser", "password")
    staff.is_staff = True
    staff.save()
    client.force_login(staff)
    response = client.get(reverse("core:debug_list_balance_sheet", args=[lst.id]))
    assert response.status_code == 200
    assert b"Reconciles." in response.content


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_balance_sheet_404_for_owner_in_production(client, user, sheet_list):
    lst, _ = sheet_list
    client.force_login(user)
    response = client.get(reverse("core:debug_list_balance_sheet", args=[lst.id]))
    assert response.status_code == 404


@pytest.mark.django_db
@override_settings(DEBUG=True, **_no_toolbar)
def test_balance_sheet_404_for_anonymous(client, sheet_list):
    lst, _ = sheet_list
    response = client.get(reverse("core:debug_list_balance_sheet", args=[lst.id]))
    assert response.status_code == 404


@pytest.mark.django_db
@override_settings(DEBUG=True, **_no_toolbar)
def test_balance_sheet_404_for_non_owner(client, sheet_list, make_user):
    lst, _ = sheet_list
    other = make_user("other", "password")
    client.force_login(other)
    response = client.get(reverse("core:debug_list_balance_sheet", args=[lst.id]))
    assert response.status_code == 404


@pytest.mark.django_db
@override_settings(DEBUG=True, **_no_toolbar)
def test_balance_sheet_owner_sees_healthy_list_reconciling(client, user, sheet_list):
    lst, _ = sheet_list
    client.force_login(user)
    response = client.get(reverse("core:debug_list_balance_sheet", args=[lst.id]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Reconciles." in content
    assert "Lasgun" in content
    assert "reconciliation problem" not in content


@pytest.mark.django_db
@override_settings(DEBUG=True, **_no_toolbar)
def test_balance_sheet_highlights_drift(client, user, sheet_list):
    """A tampered cache renders as a highlighted reconciliation problem."""
    lst, fighter = sheet_list
    ListFighter.objects.filter(pk=fighter.pk).update(
        rating_current=fighter.rating_current + 45
    )
    client.force_login(user)
    response = client.get(reverse("core:debug_list_balance_sheet", args=[lst.id]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "reconciliation problem" in content
    assert "fighter &#x27;Bob&#x27;" in content or "fighter 'Bob'" in content
    assert "Reconciles." not in content


@pytest.mark.django_db
@override_settings(DEBUG=True, **_no_toolbar)
def test_balance_sheet_view_is_read_only_and_bounded(client, user, sheet_list):
    """The view issues no writes and a bounded number of queries."""
    lst, _ = sheet_list
    client.force_login(user)
    url = reverse("core:debug_list_balance_sheet", args=[lst.id])
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
    assert response.status_code == 200
    writes = [
        q["sql"]
        for q in ctx.captured_queries
        if q["sql"].split(" ", 1)[0].upper() in ("INSERT", "UPDATE", "DELETE")
        # The test client's session handling may write; only fail on app tables.
        and "core_" in q["sql"]
    ]
    assert writes == []
    assert len(ctx.captured_queries) < 80, (
        f"query count blew the ceiling: {len(ctx.captured_queries)}"
    )


@pytest.mark.django_db
@override_settings(DEBUG=True, **_no_toolbar)
def test_balance_sheet_and_actions_pages_interlink(client, user, sheet_list):
    """The two internal views link to each other."""
    lst, _ = sheet_list
    client.force_login(user)

    sheet_url = reverse("core:debug_list_balance_sheet", args=[lst.id])
    actions_url = reverse("core:debug_list_actions", args=[lst.id])

    assert actions_url in client.get(sheet_url).content.decode()
    assert sheet_url in client.get(actions_url).content.decode()


@pytest.mark.django_db
@override_settings(DEBUG=True, **_no_toolbar)
def test_list_dropdown_internal_section_links_balance_sheet(
    client, sheet_list, make_user
):
    """Staff see the Balance Sheet item next to Actions in the list dropdown."""
    lst, _ = sheet_list
    staff = make_user("staffuser2", "password")
    staff.is_staff = True
    staff.save()
    client.force_login(staff)
    content = client.get(reverse("core:list", args=[lst.id])).content.decode()
    assert reverse("core:debug_list_balance_sheet", args=[lst.id]) in content
    assert reverse("core:debug_list_actions", args=[lst.id]) in content
