"""Paper orientation on the print config.

Phones lay print out at their screen width and ignore the orientation picked
in the print dialog, so the sheet has to be sized for the paper before the
dialog opens. These tests cover the saved choice reaching both print stacks.
"""

import pytest
from bs4 import BeautifulSoup
from django.urls import reverse

from n23.core.models import PrintConfig


def _print_url(list_obj, config=None):
    url = reverse("core:list-print", kwargs={"id": list_obj.id})
    if config is not None:
        url += f"?config_id={config.id}"
    return url


def _config(list_obj, owner, **kwargs):
    return PrintConfig.objects.create(
        list=list_obj, owner=owner, name="Print", **kwargs
    )


@pytest.mark.django_db
def test_orientation_defaults_to_portrait(user, make_list):
    config = _config(make_list("Gang"), user)
    assert config.orientation == PrintConfig.PORTRAIT


@pytest.mark.django_db
def test_web_print_without_config_is_portrait(
    client, user, make_list, make_list_fighter
):
    lst = make_list("Gang")
    make_list_fighter(lst, "Grimjaw")
    client.force_login(user)

    body = client.get(_print_url(lst)).content.decode()
    soup = BeautifulSoup(body, "html.parser")
    assert soup.select_one("#content")["data-orientation"] == "portrait"
    assert "size: A4 portrait" in body


@pytest.mark.django_db
def test_web_print_landscape_config_sizes_the_sheet(
    client, user, make_list, make_list_fighter
):
    lst = make_list("Gang")
    make_list_fighter(lst, "Grimjaw")
    config = _config(lst, user, orientation=PrintConfig.LANDSCAPE)
    client.force_login(user)

    body = client.get(_print_url(lst, config)).content.decode()
    soup = BeautifulSoup(body, "html.parser")
    sheet = soup.select_one("#content")
    assert "print-sheet-web" in sheet["class"]
    assert sheet["data-orientation"] == "landscape"
    assert "size: A4 landscape" in body


@pytest.mark.django_db
def test_web_print_cards_carry_print_columns(
    client, user, make_list, make_list_fighter
):
    """Card spans on paper come from print-col, not the screen breakpoints."""
    lst = make_list("Gang")
    make_list_fighter(lst, "Grimjaw")
    client.force_login(user)

    soup = BeautifulSoup(client.get(_print_url(lst)).content, "html.parser")
    cards = soup.select("#content .card.print-col")
    assert any("Grimjaw" in card.get_text() for card in cards)


@pytest.mark.django_db
def test_classic_print_portrait_by_default(client, user, make_list, make_list_fighter):
    lst = make_list("Gang")
    make_list_fighter(lst, "Grimjaw")
    config = _config(lst, user, card_style=PrintConfig.CLASSIC)
    client.force_login(user)

    body = client.get(_print_url(lst, config)).content.decode()
    assert "print-sheet--landscape" not in body
    assert "A4 landscape" not in body


@pytest.mark.django_db
def test_classic_print_landscape(client, user, make_list, make_list_fighter):
    lst = make_list("Gang")
    make_list_fighter(lst, "Grimjaw")
    config = _config(
        lst,
        user,
        card_style=PrintConfig.CLASSIC,
        orientation=PrintConfig.LANDSCAPE,
    )
    client.force_login(user)

    body = client.get(_print_url(lst, config)).content.decode()
    soup = BeautifulSoup(body, "html.parser")
    assert "print-sheet--landscape" in soup.select_one(".print-sheet")["class"]
    assert "size: A4 landscape" in body


@pytest.mark.django_db
def test_form_saves_orientation(client, user, make_list):
    lst = make_list("Gang")
    client.force_login(user)

    resp = client.post(
        reverse("core:print-config-create", kwargs={"list_id": lst.id}),
        {
            "name": "Landscape",
            "card_style": PrintConfig.WEB,
            "orientation": PrintConfig.LANDSCAPE,
            "fighter_selection_mode": PrintConfig.ALL_FIGHTERS,
            "blank_fighter_cards": 0,
            "blank_vehicle_cards": 0,
        },
    )
    assert resp.status_code == 302
    config = PrintConfig.objects.get(list=lst, name="Landscape")
    assert config.orientation == PrintConfig.LANDSCAPE
    assert "Landscape" in config.card_summary()


@pytest.mark.django_db
def test_form_shows_orientation(client, user, make_list):
    lst = make_list("Gang")
    client.force_login(user)
    body = client.get(
        reverse("core:print-config-create", kwargs={"list_id": lst.id})
    ).content.decode()
    assert 'name="orientation"' in body
    assert "Landscape fits three cards across." in body
