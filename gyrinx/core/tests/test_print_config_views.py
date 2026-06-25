"""Tests for the URL-driven print-configuration create/edit views.

The fighter-selection mode is a server-rendered variant chosen by navigation
(``?fighter_selection_mode=...``). The ``included_fighters`` section is rendered
only for the "specific" variant, and the server stays the source of truth for
clearing it in the other modes. These tests exercise the variants without any
JavaScript, asserting the right section renders per URL and that posting works
in each mode.
"""

import pytest
from django.urls import reverse

from gyrinx.core.models import PrintConfig


def _create_url(list_):
    return reverse("core:print-config-create", kwargs={"list_id": list_.id})


def _edit_url(list_, config):
    return reverse(
        "core:print-config-edit",
        kwargs={"list_id": list_.id, "config_id": config.id},
    )


# ---------------------------------------------------------------------------
# Create view — GET variants
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_get_default_hides_fighter_checkboxes(
    client, user, make_list, make_list_fighter
):
    """Default mode (all) renders no fighter checkbox section."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Ganger A")
    client.force_login(user)

    response = client.get(_create_url(lst))

    assert response.status_code == 200
    form = response.context["form"]
    assert "included_fighters" not in form.fields
    assert 'id="fighter-checkboxes"' not in response.content.decode()
    # The mode picker is always present so the user can switch variants.
    assert 'name="fighter_selection_mode"' in response.content.decode()
    assert fighter.name not in response.content.decode()


@pytest.mark.django_db
def test_create_get_specific_shows_fighter_checkboxes(
    client, user, make_list, make_list_fighter
):
    """?fighter_selection_mode=specific renders the fighter checkbox section."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Ganger A")
    client.force_login(user)

    response = client.get(
        _create_url(lst), {"fighter_selection_mode": PrintConfig.SPECIFIC_FIGHTERS}
    )

    assert response.status_code == 200
    form = response.context["form"]
    assert "included_fighters" in form.fields
    content = response.content.decode()
    assert 'id="fighter-checkboxes"' in content
    assert fighter.name in content


@pytest.mark.django_db
def test_create_get_none_hides_fighter_checkboxes(
    client, user, make_list, make_list_fighter
):
    """?fighter_selection_mode=none renders no fighter checkbox section."""
    lst = make_list("Gang")
    make_list_fighter(lst, "Ganger A")
    client.force_login(user)

    response = client.get(
        _create_url(lst), {"fighter_selection_mode": PrintConfig.NO_FIGHTERS}
    )

    assert response.status_code == 200
    assert "included_fighters" not in response.context["form"].fields
    assert 'id="fighter-checkboxes"' not in response.content.decode()


@pytest.mark.django_db
def test_create_get_invalid_mode_falls_back_to_default(client, user, make_list):
    """An unknown mode value falls back to the default (all) variant."""
    lst = make_list("Gang")
    client.force_login(user)

    response = client.get(_create_url(lst), {"fighter_selection_mode": "bogus"})

    assert response.status_code == 200
    assert response.context["form"].selection_mode == PrintConfig.ALL_FIGHTERS
    assert "included_fighters" not in response.context["form"].fields


# ---------------------------------------------------------------------------
# Create view — POST variants
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_post_all_succeeds_without_fighters(client, user, make_list):
    """Posting in 'all' mode with no fighters creates the config."""
    lst = make_list("Gang")
    client.force_login(user)

    response = client.post(
        _create_url(lst),
        {
            "name": "All Fighters Config",
            "fighter_selection_mode": PrintConfig.ALL_FIGHTERS,
            "blank_fighter_cards": 0,
            "blank_vehicle_cards": 0,
        },
    )

    assert response.status_code == 302
    config = PrintConfig.objects.get(list=lst, name="All Fighters Config")
    assert config.fighter_selection_mode == PrintConfig.ALL_FIGHTERS
    assert config.included_fighters.count() == 0


@pytest.mark.django_db
def test_create_post_none_succeeds_without_fighters(client, user, make_list):
    """Posting in 'none' mode with no fighters creates the config."""
    lst = make_list("Gang")
    client.force_login(user)

    response = client.post(
        _create_url(lst),
        {
            "name": "No Fighters Config",
            "fighter_selection_mode": PrintConfig.NO_FIGHTERS,
            "blank_fighter_cards": 0,
            "blank_vehicle_cards": 0,
        },
    )

    assert response.status_code == 302
    config = PrintConfig.objects.get(list=lst, name="No Fighters Config")
    assert config.fighter_selection_mode == PrintConfig.NO_FIGHTERS
    assert config.included_fighters.count() == 0


@pytest.mark.django_db
def test_create_post_specific_without_fighters_errors(
    client, user, make_list, make_list_fighter
):
    """Posting 'specific' with zero fighters surfaces the validation error."""
    lst = make_list("Gang")
    make_list_fighter(lst, "Ganger A")
    client.force_login(user)

    response = client.post(
        _create_url(lst),
        {
            "name": "Specific Config",
            "fighter_selection_mode": PrintConfig.SPECIFIC_FIGHTERS,
            "blank_fighter_cards": 0,
            "blank_vehicle_cards": 0,
        },
    )

    assert response.status_code == 200
    assert "included_fighters" in response.context["form"].errors
    assert not PrintConfig.objects.filter(list=lst, name="Specific Config").exists()


@pytest.mark.django_db
def test_create_post_specific_with_fighters_succeeds(
    client, user, make_list, make_list_fighter
):
    """Posting 'specific' with a fighter selected creates the config."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Ganger A")
    client.force_login(user)

    response = client.post(
        _create_url(lst),
        {
            "name": "Specific Config",
            "fighter_selection_mode": PrintConfig.SPECIFIC_FIGHTERS,
            "included_fighters": [str(fighter.id)],
            "blank_fighter_cards": 0,
            "blank_vehicle_cards": 0,
        },
    )

    assert response.status_code == 302
    config = PrintConfig.objects.get(list=lst, name="Specific Config")
    assert config.fighter_selection_mode == PrintConfig.SPECIFIC_FIGHTERS
    assert list(config.included_fighters.all()) == [fighter]


# ---------------------------------------------------------------------------
# Edit view — GET variants
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_edit_get_uses_saved_mode_specific(client, user, make_list, make_list_fighter):
    """Editing a 'specific' config defaults the variant to its saved mode."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Ganger A")
    config = PrintConfig.objects.create(
        name="Saved Specific",
        list=lst,
        owner=user,
        fighter_selection_mode=PrintConfig.SPECIFIC_FIGHTERS,
    )
    config.included_fighters.add(fighter)
    client.force_login(user)

    response = client.get(_edit_url(lst, config))

    assert response.status_code == 200
    form = response.context["form"]
    assert form.selection_mode == PrintConfig.SPECIFIC_FIGHTERS
    assert "included_fighters" in form.fields
    assert 'id="fighter-checkboxes"' in response.content.decode()


@pytest.mark.django_db
def test_edit_get_uses_saved_mode_all(client, user, make_list, make_list_fighter):
    """Editing an 'all' config hides the fighter checkbox section by default."""
    lst = make_list("Gang")
    make_list_fighter(lst, "Ganger A")
    config = PrintConfig.objects.create(
        name="Saved All",
        list=lst,
        owner=user,
        fighter_selection_mode=PrintConfig.ALL_FIGHTERS,
    )
    client.force_login(user)

    response = client.get(_edit_url(lst, config))

    assert response.status_code == 200
    assert response.context["form"].selection_mode == PrintConfig.ALL_FIGHTERS
    assert "included_fighters" not in response.context["form"].fields


@pytest.mark.django_db
def test_edit_get_url_overrides_saved_mode(client, user, make_list, make_list_fighter):
    """The URL mode wins over the saved mode when switching variants."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Ganger A")
    config = PrintConfig.objects.create(
        name="Saved All",
        list=lst,
        owner=user,
        fighter_selection_mode=PrintConfig.ALL_FIGHTERS,
    )
    client.force_login(user)

    response = client.get(
        _edit_url(lst, config),
        {"fighter_selection_mode": PrintConfig.SPECIFIC_FIGHTERS},
    )

    assert response.status_code == 200
    assert response.context["form"].selection_mode == PrintConfig.SPECIFIC_FIGHTERS
    assert "included_fighters" in response.context["form"].fields
    assert fighter.name in response.content.decode()


# ---------------------------------------------------------------------------
# Edit view — POST variants
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_edit_post_switch_to_all_clears_fighters(
    client, user, make_list, make_list_fighter
):
    """Switching a saved 'specific' config to 'all' clears included_fighters."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Ganger A")
    config = PrintConfig.objects.create(
        name="Was Specific",
        list=lst,
        owner=user,
        fighter_selection_mode=PrintConfig.SPECIFIC_FIGHTERS,
    )
    config.included_fighters.add(fighter)
    client.force_login(user)

    response = client.post(
        _edit_url(lst, config),
        {
            "name": "Was Specific",
            "fighter_selection_mode": PrintConfig.ALL_FIGHTERS,
            "blank_fighter_cards": 0,
            "blank_vehicle_cards": 0,
        },
    )

    assert response.status_code == 302
    config.refresh_from_db()
    assert config.fighter_selection_mode == PrintConfig.ALL_FIGHTERS
    assert config.included_fighters.count() == 0


@pytest.mark.django_db
def test_edit_post_specific_without_fighters_errors(
    client, user, make_list, make_list_fighter
):
    """Posting 'specific' on edit with zero fighters surfaces the error."""
    lst = make_list("Gang")
    make_list_fighter(lst, "Ganger A")
    config = PrintConfig.objects.create(
        name="Cfg",
        list=lst,
        owner=user,
        fighter_selection_mode=PrintConfig.ALL_FIGHTERS,
    )
    client.force_login(user)

    response = client.post(
        _edit_url(lst, config),
        {
            "name": "Cfg",
            "fighter_selection_mode": PrintConfig.SPECIFIC_FIGHTERS,
            "blank_fighter_cards": 0,
            "blank_vehicle_cards": 0,
        },
    )

    assert response.status_code == 200
    assert "included_fighters" in response.context["form"].errors
    config.refresh_from_db()
    assert config.fighter_selection_mode == PrintConfig.ALL_FIGHTERS


@pytest.mark.django_db
def test_edit_post_switch_to_specific_with_fighters(
    client, user, make_list, make_list_fighter
):
    """Switching to 'specific' on edit with a fighter persists the selection."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Ganger A")
    config = PrintConfig.objects.create(
        name="Cfg",
        list=lst,
        owner=user,
        fighter_selection_mode=PrintConfig.ALL_FIGHTERS,
    )
    client.force_login(user)

    response = client.post(
        _edit_url(lst, config),
        {
            "name": "Cfg",
            "fighter_selection_mode": PrintConfig.SPECIFIC_FIGHTERS,
            "included_fighters": [str(fighter.id)],
            "blank_fighter_cards": 0,
            "blank_vehicle_cards": 0,
        },
    )

    assert response.status_code == 302
    config.refresh_from_db()
    assert config.fighter_selection_mode == PrintConfig.SPECIFIC_FIGHTERS
    assert list(config.included_fighters.all()) == [fighter]
