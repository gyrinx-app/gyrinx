"""Tests for the classic-mode print lab (#1726)."""

import pytest
from django.test import override_settings
from django.urls import reverse

from n23.core.print_cards import DetailGroup
from n23.core.views.print_lab import (
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
        assert client.get(reverse("core:debug_print_lab")).status_code == 404
        assert client.get(reverse("core:debug_print_lab_sheet")).status_code == 404


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_lab_available_in_debug(client):
    assert client.get(reverse("core:debug_print_lab")).status_code == 200
    assert client.get(reverse("core:debug_print_lab_sheet")).status_code == 200


@pytest.mark.django_db
def test_lab_available_to_staff_without_debug(client, make_user):
    staff = make_user("staffer", "pw")
    staff.is_staff = True
    staff.save()
    client.force_login(staff)
    with override_settings(DEBUG=False):
        assert client.get(reverse("core:debug_print_lab")).status_code == 200
        assert client.get(reverse("core:debug_print_lab_sheet")).status_code == 200


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_sheet_allows_sameorigin_framing(client):
    """The sheet must be embeddable in the harness iframe (project default is DENY)."""
    resp = client.get(reverse("core:debug_print_lab_sheet"))
    assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"


# ---------------------------------------------------------------------------
# Sheet rendering
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_sheet_preset_gallery_renders_all(client):
    resp = client.get(reverse("core:debug_print_lab_sheet"))
    body = resp.content.decode()
    # one card per preset
    assert body.count("classic-card") >= len(synthetic_presets())
    assert "Bo &#x27;Two-Guns&#x27; Marr" in body or "Two-Guns" in body


@pytest.mark.django_db
@override_settings(DEBUG=True)
@pytest.mark.parametrize("preset_key", list(PRESET_LABELS))
def test_sheet_single_preset_renders(client, preset_key):
    url = reverse("core:debug_print_lab_sheet") + f"?source=preset&preset={preset_key}"
    resp = client.get(url)
    assert resp.status_code == 200
    assert "classic-card" in resp.content.decode()


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_sheet_paged_mode_adds_class(client):
    resp = client.get(reverse("core:debug_print_lab_sheet") + "?paged=1")
    assert "print-sheet--paged" in resp.content.decode()


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_xp_renders_as_bold_value_in_kills_row(client):
    """XP is a bold value in the XP/Kills row, not a statline column."""
    import re

    url = reverse("core:debug_print_lab_sheet") + "?source=preset&preset=overflow"
    body = client.get(url).content.decode()
    assert "cc-stat--xp" not in body  # no longer a statline column
    m = re.search(r"cc-kills__xp[^>]*>([^<]*)</span>", body)
    assert m is not None, "XP should render as a cc-kills__xp value"
    assert m.group(1).strip() == "52"


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_sheet_bad_fighter_id_is_graceful(client):
    """A bad id shows an error message, never a 500."""
    resp = client.get(
        reverse("core:debug_print_lab_sheet") + "?source=fighter&fighter=not-a-uuid"
    )
    assert resp.status_code == 200
    assert "No fighter found" in resp.content.decode()


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_sheet_real_fighter_renders(client, make_list, make_list_fighter):
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Grimjaw")
    url = (
        reverse("core:debug_print_lab_sheet") + f"?source=fighter&fighter={fighter.id}"
    )
    resp = client.get(url)
    assert resp.status_code == 200
    assert "Grimjaw" in resp.content.decode()


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_sheet_real_gang_renders_all_fighters(client, make_list, make_list_fighter):
    lst = make_list("Squad")
    make_list_fighter(lst, "Alpha")
    make_list_fighter(lst, "Bravo")
    url = reverse("core:debug_print_lab_sheet") + f"?source=list&list={lst.id}"
    body = client.get(url).content.decode()
    assert "Alpha" in body
    assert "Bravo" in body
    # count card elements (not the .classic-card selector in the fit script)
    assert body.count('class="classic-card') == 2


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_sheet_real_gang_excludes_dead_and_stash(
    client, content_house, make_list, make_list_fighter, make_content_fighter
):
    """The real-gang preview mirrors the actual classic print flow: dead
    fighters and the stash are left out, so the lab shows what will print."""
    from n23.core.models.list import ListFighter

    lst = make_list("Squad")
    make_list_fighter(lst, "Alive")
    make_list_fighter(lst, "Corpse", injury_state=ListFighter.DEAD)
    stash_cf = make_content_fighter(
        type="Stash",
        category="STASH",
        house=content_house,
        base_cost=0,
        is_stash=True,
    )
    ListFighter.objects.create(
        name="Stash", content_fighter=stash_cf, list=lst, owner=lst.owner
    )

    url = reverse("core:debug_print_lab_sheet") + f"?source=list&list={lst.id}"
    body = client.get(url).content.decode()
    assert "Alive" in body
    assert "Corpse" not in body
    assert 'data-kind="stash"' not in body
    assert body.count('class="classic-card') == 1  # only the live fighter


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
    url = reverse("core:debug_print_lab_sheet") + "?source=preset&preset=psyker"
    body = client.get(url).content.decode()
    assert "Wyrd Powers" in body
    assert "Legendary Names" in body


# ---------------------------------------------------------------------------
# Injuries strip (top of card)
# ---------------------------------------------------------------------------


def test_injuries_live_in_their_own_field_not_notes():
    """Injuries go in their own row, not folded into the Notes block."""
    card = synthetic_presets()["overflow"]
    assert card.injuries  # populated
    assert not any("injur" in line.lower() for line in card.notes_lines), (
        "injuries must not be duplicated into notes"
    )


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_sheet_always_shows_injuries_label(client):
    """Even a blank card carries the labelled Injuries write-in box."""
    url = reverse("core:debug_print_lab_sheet") + "?source=preset&preset=blank"
    body = client.get(url).content.decode()
    assert "Injuries" in body
    assert "cc-injuries" in body


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_bottom_fields_have_writein_boxes(client):
    """Kills, Notes, and Injuries each get a hand-fillable write-in box."""
    url = reverse("core:debug_print_lab_sheet") + "?source=preset&preset=blank"
    body = client.get(url).content.decode()
    # three write-in boxes: kills, notes, injuries
    assert body.count("cc-writein") >= 3


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_real_fighter_injuries_render_on_card(
    client, list_with_campaign, make_list_fighter
):
    """A campaign fighter's lasting injuries are pulled onto the card."""
    from n23.content.models import ContentInjury, ContentInjuryDefaultOutcome
    from n23.core.models.list import ListFighterInjury
    from n23.core.views.print_lab import card_from_fighter

    fighter = make_list_fighter(list_with_campaign, "Scarface")
    injury, _ = ContentInjury.objects.get_or_create(
        name="Humiliated",
        defaults={"phase": ContentInjuryDefaultOutcome.NO_CHANGE},
    )
    ListFighterInjury.objects.create(
        fighter=fighter, injury=injury, owner=fighter.owner
    )

    card = card_from_fighter(fighter, list_with_campaign)
    assert "Humiliated" in card.injuries
    # ...and it renders in the sheet
    url = (
        reverse("core:debug_print_lab_sheet") + f"?source=fighter&fighter={fighter.id}"
    )
    assert "Humiliated" in client.get(url).content.decode()


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_all_presets_render_without_error(client):
    """Every preset (incl. overflow + blank) renders in the sheet."""
    for key in PRESET_LABELS:
        url = reverse("core:debug_print_lab_sheet") + f"?source=preset&preset={key}"
        assert client.get(url).status_code == 200


# ---------------------------------------------------------------------------
# Detail block columns
#
# The two columns are split in Python rather than by CSS multi-column layout,
# because WebKit collapses a multicol nested inside a fragmentation context —
# printing from iOS Safari lost the two-column layout entirely.
# ---------------------------------------------------------------------------


def test_detail_groups_cover_every_labelled_row():
    card = synthetic_presets()["psyker"]
    labels = [g.label for g in card.detail_groups]
    assert labels[:3] == ["Skills", "Rules", "Gear"]
    assert "Wyrd Powers" in labels
    for category_label, _ in card.gear_categories:
        assert category_label in labels


def test_detail_group_text_joins_items():
    group = DetailGroup("Skills", ["Nerves of Steel", "Spring Up"])
    assert group.text == "Nerves of Steel, Spring Up"


def test_detail_columns_split_into_two_without_losing_groups():
    card = synthetic_presets()["overflow"]
    columns = card.detail_columns
    assert len(columns) == 2
    flattened = [g.label for col in columns for g in col]
    assert flattened == [g.label for g in card.detail_groups]  # order preserved


def test_detail_columns_balance_the_taller_column():
    """The split point is chosen to keep the taller column as short as it can
    be — a naive fixed split would pile everything into column one."""
    card = ClassicCard(
        skills=["A very long list of skills " * 4],
        rules=["Short"],
        wargear=["Also short"],
    )
    left, right = card.detail_columns
    assert [g.label for g in left] == ["Skills"]
    assert [g.label for g in right] == ["Rules", "Gear"]


def test_detail_columns_never_returns_an_empty_column():
    """An empty column is still a flex item, so it would claim half the width."""
    for key in PRESET_LABELS:
        for column in synthetic_presets()[key].detail_columns:
            assert column


def test_blank_card_keeps_one_full_width_detail_column():
    card = synthetic_presets()["blank"]
    assert len(card.detail_columns) == 1
    assert [g.label for g in card.detail_columns[0]] == ["Skills", "Rules", "Gear"]


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_sheet_renders_two_detail_columns(client):
    url = reverse("core:debug_print_lab_sheet") + "?source=preset&preset=psyker"
    body = client.get(url).content.decode()
    assert body.count('class="cc-detail__col"') == 2
