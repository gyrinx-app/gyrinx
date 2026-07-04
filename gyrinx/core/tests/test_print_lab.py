"""Tests for the classic-mode print lab (#1726)."""

import pytest
from django.test import override_settings
from django.urls import reverse

from gyrinx.core.views.print_lab import (
    PRESET_LABELS,
    ClassicCard,
    card_from_fighter,
    synthetic_presets,
)


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_lab_hidden_from_anonymous_when_not_debug(client):
    """With DEBUG off and no staff, the lab is a 404 (not a 500 or a leak)."""
    with override_settings(DEBUG=False):
        assert client.get(reverse("debug_print_lab")).status_code == 404
        assert client.get(reverse("debug_print_lab_sheet")).status_code == 404


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_lab_available_in_debug(client):
    assert client.get(reverse("debug_print_lab")).status_code == 200
    assert client.get(reverse("debug_print_lab_sheet")).status_code == 200


@pytest.mark.django_db
def test_lab_available_to_staff_without_debug(client, make_user):
    staff = make_user("staffer", "pw")
    staff.is_staff = True
    staff.save()
    client.force_login(staff)
    with override_settings(DEBUG=False):
        assert client.get(reverse("debug_print_lab")).status_code == 200
        assert client.get(reverse("debug_print_lab_sheet")).status_code == 200


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_sheet_allows_sameorigin_framing(client):
    """The sheet must be embeddable in the harness iframe (project default is DENY)."""
    resp = client.get(reverse("debug_print_lab_sheet"))
    assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"


# ---------------------------------------------------------------------------
# Sheet rendering
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_sheet_preset_gallery_renders_all(client):
    resp = client.get(reverse("debug_print_lab_sheet"))
    body = resp.content.decode()
    # one card per preset
    assert body.count("classic-card") >= len(synthetic_presets())
    assert "Bo &#x27;Two-Guns&#x27; Marr" in body or "Two-Guns" in body


@pytest.mark.django_db
@override_settings(DEBUG=True)
@pytest.mark.parametrize("preset_key", list(PRESET_LABELS))
def test_sheet_single_preset_renders(client, preset_key):
    url = reverse("debug_print_lab_sheet") + f"?source=preset&preset={preset_key}"
    resp = client.get(url)
    assert resp.status_code == 200
    assert "classic-card" in resp.content.decode()


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_sheet_paged_mode_adds_class(client):
    resp = client.get(reverse("debug_print_lab_sheet") + "?paged=1")
    assert "print-sheet--paged" in resp.content.decode()


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_sheet_bad_fighter_id_is_graceful(client):
    """A bad id shows an error message, never a 500."""
    resp = client.get(
        reverse("debug_print_lab_sheet") + "?source=fighter&fighter=not-a-uuid"
    )
    assert resp.status_code == 200
    assert "No fighter found" in resp.content.decode()


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_sheet_real_fighter_renders(client, make_list, make_list_fighter):
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Grimjaw")
    url = reverse("debug_print_lab_sheet") + f"?source=fighter&fighter={fighter.id}"
    resp = client.get(url)
    assert resp.status_code == 200
    assert "Grimjaw" in resp.content.decode()


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_sheet_real_gang_renders_all_fighters(client, make_list, make_list_fighter):
    lst = make_list("Squad")
    make_list_fighter(lst, "Alpha")
    make_list_fighter(lst, "Bravo")
    url = reverse("debug_print_lab_sheet") + f"?source=list&list={lst.id}"
    body = client.get(url).content.decode()
    assert "Alpha" in body
    assert "Bravo" in body
    assert body.count("classic-card") == 2


# ---------------------------------------------------------------------------
# Card data builder
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_card_from_real_fighter_has_statline(make_list, make_list_fighter):
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Ripper")
    card = card_from_fighter(fighter, lst)
    assert isinstance(card, ClassicCard)
    assert card.name == "Ripper"
    # the default content_fighter fixture carries the legacy 12-stat humanoid line
    assert len(card.stats) == 12
    assert [s.name for s in card.stats][:3] == ["M", "WS", "BS"]
    # mental stats are highlighted
    assert any(s.highlight for s in card.stats)
    # the group divider is detected from the statline classes
    assert any(s.first_of_group for s in card.stats)


@pytest.mark.django_db
def test_card_from_fighter_save_prefers_save_roll(make_list, make_list_fighter):
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Warden", save_roll="4+ inv")
    card = card_from_fighter(fighter, lst)
    assert card.save == "4+ inv"


# ---------------------------------------------------------------------------
# Synthetic presets
# ---------------------------------------------------------------------------


def test_presets_cover_expected_keys():
    presets = synthetic_presets()
    assert set(presets) == set(PRESET_LABELS)


def test_preset_column_counts():
    """Presets exercise the three real statline shapes (12 / 7 / 5 columns)."""
    presets = synthetic_presets()
    assert len(presets["ganger"].stats) == 12
    assert len(presets["vehicle"].stats) == 7
    assert len(presets["crew"].stats) == 5


def test_vehicle_preset_has_save_column_and_box():
    card = synthetic_presets()["vehicle"]
    assert "Sv" in [s.name for s in card.stats]
    assert card.save  # save box also populated


def test_overflow_preset_is_dense():
    """The stress preset carries enough content to exercise clipping."""
    card = synthetic_presets()["overflow"]
    assert len(card.weapons) >= 6
    assert len(card.skills) >= 6
    assert len(card.wargear) >= 5


def test_blank_preset_is_empty_but_structured():
    card = synthetic_presets()["blank"]
    assert card.name == ""
    assert len(card.stats) == 12  # headers still present for a fillable card
    assert all(s.value == "" for s in card.stats)


def test_psyker_preset_splits_powers_and_gear_categories():
    """Wyrd powers and each special gear category are their own rows,
    kept distinct from skills and general wargear."""
    card = synthetic_presets()["psyker"]
    assert card.powers  # wyrd powers populated
    # skills stay separate from powers
    assert not (set(card.skills) & set(card.powers))
    # special categories each carry a labelled row, distinct from wargear
    labels = [label for label, _ in card.gear_categories]
    assert "Legendary Names" in labels
    general = set(card.wargear)
    for _, items in card.gear_categories:
        assert not (set(items) & general)


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_psyker_sheet_shows_power_and_category_rows(client):
    """The rendered card labels the powers and gear-category rows."""
    url = reverse("debug_print_lab_sheet") + "?source=preset&preset=psyker"
    body = client.get(url).content.decode()
    assert "Wyrd Powers" in body
    assert "Legendary Names" in body


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_all_presets_render_without_error(client):
    """Every preset (incl. overflow + blank) renders in the sheet."""
    for key in PRESET_LABELS:
        url = reverse("debug_print_lab_sheet") + f"?source=preset&preset={key}"
        assert client.get(url).status_code == 200
