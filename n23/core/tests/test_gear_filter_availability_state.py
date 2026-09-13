"""Tests for the server-rendered availability-dropdown state on the fighter
gear/weapons filter.

This state used to be mirrored client-side in ``core/static/core/js/index.js``
(the "Equipment list filter toggle functionality" block). That JS was removed
(issue #1867) because the server already renders the complete disabled state
in ``core/includes/fighter_gear_filter.html``. These tests pin that
server-rendered behaviour so the deletion stays safe.
"""

import pytest
from bs4 import BeautifulSoup
from django.test import Client
from django.urls import reverse


def _availability_button(html):
    """The availability control, addressed by its stable id."""
    return BeautifulSoup(html, "html.parser").find(
        "button", id="availability-dropdown-button"
    )


@pytest.mark.django_db
def test_availability_disabled_when_equipment_list_filter_on(
    make_list, make_list_fighter, user
):
    """With ?filter=equipment-list the availability dropdown renders disabled,
    drops its dropdown trigger, and the parent group carries the tooltip."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")

    client = Client()
    client.force_login(user)

    url = reverse("core:list-fighter-gear-edit", args=[lst.id, fighter.id])
    response = client.get(url, {"filter": "equipment-list"})
    assert response.status_code == 200
    html = response.content.decode()
    button = _availability_button(html)
    assert button is not None

    # The native disabled attribute is the behaviour browsers enforce.
    assert button.has_attr("disabled")
    # The dropdown trigger is dropped while disabled.
    assert button.get("data-bs-toggle") is None
    # The parent group carries the explanatory tooltip.
    assert 'data-bs-toggle="tooltip"' in html
    assert "Availability filters are disabled" in html


@pytest.mark.django_db
def test_availability_enabled_when_equipment_list_filter_off(
    make_list, make_list_fighter, user
):
    """With ?filter=all the availability dropdown renders enabled with its
    dropdown trigger and no disabled tooltip."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")

    client = Client()
    client.force_login(user)

    url = reverse("core:list-fighter-gear-edit", args=[lst.id, fighter.id])
    response = client.get(url, {"filter": "all"})
    assert response.status_code == 200
    html = response.content.decode()
    button = _availability_button(html)
    assert button is not None

    # Dropdown trigger is present and the button is enabled.
    assert button.get("data-bs-toggle") == "dropdown"
    assert not button.has_attr("disabled")
    assert "Availability filters are disabled" not in html


@pytest.mark.django_db
def test_filter_switch_pairs_checkbox_with_hidden_default(
    make_list, make_list_fighter, user
):
    """The equipment-list filter switch renders a checkbox paired with a hidden
    ``filter`` default. index.js disables the hidden input when the checkbox is
    checked so only one value submits; this pins the markup that pairing relies
    on (issue #1867)."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")

    client = Client()
    client.force_login(user)

    url = reverse("core:list-fighter-gear-edit", args=[lst.id, fighter.id])
    response = client.get(url, {"filter": "all"})
    assert response.status_code == 200
    html = response.content.decode()

    # Hidden default + the toggle checkbox share the name "filter".
    assert '<input type="hidden" name="filter" value="all"' in html
    assert 'id="filter-switch"' in html
    assert 'name="filter"' in html
    assert 'value="equipment-list"' in html
    # The switch auto-submits the search form on change.
    assert 'data-gy-toggle-submit="search"' in html
