"""Tests for the server-rendered availability-dropdown state on the fighter
gear/weapons filter.

This state used to be mirrored client-side in ``core/static/core/js/index.js``
(the "Equipment list filter toggle functionality" block). That JS was removed
(issue #1867) because the server already renders the complete disabled state
in ``core/includes/fighter_gear_filter.html``. These tests pin that
server-rendered behaviour so the deletion stays safe.
"""

import pytest
from django.test import Client
from django.urls import reverse


def _availability_button_html(html):
    """Slice out just the availability dropdown <button ...> element so
    assertions don't collide with the unrelated theme-switcher dropdown."""
    start = html.index('id="availability-dropdown-button"')
    # Walk back to the opening "<button" and forward to the closing ">".
    open_idx = html.rindex("<button", 0, start)
    close_idx = html.index(">", start)
    return html[open_idx : close_idx + 1]


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
    button = _availability_button_html(html)
    # Collapse runs of whitespace so attribute assertions don't depend on
    # template indentation / djlint formatting.
    button_compact = " ".join(button.split())

    # The button is disabled and styled as such: both the `disabled` class
    # (in the class list) and the bare `disabled` attribute are rendered.
    assert "dropdown-toggle disabled" in button_compact
    assert "disabled >" in button_compact
    # The dropdown trigger is dropped while disabled.
    assert 'data-bs-toggle="dropdown"' not in button_compact
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
    button_compact = " ".join(_availability_button_html(html).split())

    # Dropdown trigger is present and the button is not marked disabled.
    assert 'data-bs-toggle="dropdown"' in button_compact
    assert "dropdown-toggle disabled" not in button_compact
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
