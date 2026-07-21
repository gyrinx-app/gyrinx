"""Classic-style print output wired through PrintConfig (#1726).

The classic renderer (grimdark fixed-size cards, 4 per A4) is reachable from the
real per-list print flow when a PrintConfig has card_style=classic. These tests
cover the branch in ListPrintView: it renders the classic sheet, reuses the
config's fighter filtering, appends blank cards, and applies the theme — while a
default/web config is unchanged.
"""

import pytest
from django.urls import reverse

from gyrinx.core.models import PrintConfig
from gyrinx.core.models.list import ListFighter
from gyrinx.core.print_cards import blank_classic_card


def _classic_config(list_obj, owner, **kwargs):
    return PrintConfig.objects.create(
        list=list_obj,
        owner=owner,
        name="Classic",
        card_style=PrintConfig.CLASSIC,
        **kwargs,
    )


def _print_url(list_obj, config=None):
    url = reverse("core:list-print", kwargs={"id": list_obj.id})
    if config is not None:
        url += f"?config_id={config.id}"
    return url


# ---------------------------------------------------------------------------
# blank_classic_card factory
# ---------------------------------------------------------------------------


def test_blank_classic_card_shapes():
    fighter = blank_classic_card("fighter")
    vehicle = blank_classic_card("vehicle")
    assert fighter.kind == "blank"
    assert vehicle.kind == "blank"
    assert len(fighter.stats) == 12  # humanoid line, headers preserved
    assert len(vehicle.stats) == 7  # vehicle line
    assert all(s.value == "" for s in fighter.stats)
    assert [s.name for s in vehicle.stats][:3] == ["M", "Fr", "Sd"]


# ---------------------------------------------------------------------------
# ListPrintView branch
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_classic_config_renders_classic_sheet(
    client, user, make_list, make_list_fighter
):
    lst = make_list("Gang")
    make_list_fighter(lst, "Grimjaw")
    cfg = _classic_config(lst, user)
    client.force_login(user)

    body = client.get(_print_url(lst, cfg)).content.decode()
    assert "classic-card" in body  # grimdark card markup
    assert "print-sheet" in body  # A4 sheet scaffold
    assert "Grimjaw" in body


@pytest.mark.django_db
def test_default_config_still_renders_web_cards(
    client, user, make_list, make_list_fighter
):
    """No config (the default path) keeps the standard web cards."""
    lst = make_list("Gang")
    make_list_fighter(lst, "Grimjaw")
    client.force_login(user)

    body = client.get(_print_url(lst)).content.decode()
    assert "classic-card" not in body


@pytest.mark.django_db
def test_web_config_still_renders_web_cards(client, user, make_list, make_list_fighter):
    """An explicit web-style config also keeps the web cards."""
    lst = make_list("Gang")
    make_list_fighter(lst, "Grimjaw")
    cfg = PrintConfig.objects.create(
        list=lst, owner=user, name="Web", card_style=PrintConfig.WEB
    )
    client.force_login(user)

    body = client.get(_print_url(lst, cfg)).content.decode()
    assert "classic-card" not in body


@pytest.mark.django_db
def test_classic_uses_base_blank_plate(client, user, make_list, make_list_fighter):
    """Classic cards always render on the base 'blank' plate — there is no theme
    choice."""
    lst = make_list("Gang")
    make_list_fighter(lst, "Alpha")
    cfg = _classic_config(lst, user)
    client.force_login(user)

    body = client.get(_print_url(lst, cfg)).content.decode()
    assert "theme-blank" in body
    assert "theme-dark" not in body


@pytest.mark.django_db
def test_classic_respects_specific_fighter_selection(
    client, user, make_list, make_list_fighter
):
    lst = make_list("Gang")
    alpha = make_list_fighter(lst, "Alpha")
    make_list_fighter(lst, "Bravo")
    cfg = _classic_config(
        lst, user, fighter_selection_mode=PrintConfig.SPECIFIC_FIGHTERS
    )
    cfg.included_fighters.add(alpha)
    client.force_login(user)

    body = client.get(_print_url(lst, cfg)).content.decode()
    assert "Alpha" in body
    assert "Bravo" not in body


@pytest.mark.django_db
def test_classic_excludes_dead_fighters_by_default(
    client, user, make_list, make_list_fighter
):
    lst = make_list("Gang")
    make_list_fighter(lst, "Alive")
    make_list_fighter(lst, "Corpse", injury_state=ListFighter.DEAD)
    cfg = _classic_config(lst, user)  # include_dead_fighters defaults False
    client.force_login(user)

    body = client.get(_print_url(lst, cfg)).content.decode()
    assert "Alive" in body
    assert "Corpse" not in body


@pytest.mark.django_db
def test_classic_omits_stash(
    client, user, content_house, make_list, make_list_fighter, make_content_fighter
):
    """The gang's stash is not a classic card (fighter cards only)."""
    lst = make_list("Gang")
    make_list_fighter(lst, "Alpha")
    stash_cf = make_content_fighter(
        type="Stash",
        category="STASH",
        house=content_house,
        base_cost=0,
        is_stash=True,
    )
    ListFighter.objects.create(
        name="Stash", content_fighter=stash_cf, list=lst, owner=user
    )
    cfg = _classic_config(lst, user)
    client.force_login(user)

    body = client.get(_print_url(lst, cfg)).content.decode()
    assert "Alpha" in body
    assert 'data-kind="stash"' not in body
    assert body.count('class="classic-card') == 1  # only the real fighter


@pytest.mark.django_db
def test_print_config_form_shows_card_style(client, user, make_list):
    """The create form exposes the card-style radios and the theme picker."""
    lst = make_list("Gang")
    client.force_login(user)
    resp = client.get(reverse("core:print-config-create", kwargs={"list_id": lst.id}))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Card style" in body
    assert "Classic cards" in body  # the classic choice label
    assert 'name="card_style"' in body
    assert 'name="card_theme"' not in body  # no theme picker


@pytest.mark.django_db
def test_classic_renders_fighter_portrait(
    client, user, make_list, make_list_fighter, tmp_path, settings
):
    """A fighter with an image gets a portrait (and the space-reserving class);
    a fighter without one gets neither."""
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    settings.MEDIA_ROOT = str(tmp_path)  # isolate the uploaded file

    lst = make_list("Gang")
    with_img = make_list_fighter(lst, "Snap")
    make_list_fighter(lst, "Plain")  # no image
    buf = BytesIO()
    Image.new("RGB", (10, 12), "gray").save(buf, format="PNG")
    with_img.image = SimpleUploadedFile(
        "snap.png", buf.getvalue(), content_type="image/png"
    )
    with_img.save()

    cfg = _classic_config(lst, user)
    client.force_login(user)
    body = client.get(_print_url(lst, cfg)).content.decode()

    assert body.count("cc-portrait") == 1  # only the fighter with an image
    assert "has-portrait" in body


@pytest.mark.django_db
def test_classic_appends_blank_cards(client, user, make_list, make_list_fighter):
    lst = make_list("Gang")
    make_list_fighter(lst, "Alpha")
    cfg = _classic_config(lst, user, blank_fighter_cards=2, blank_vehicle_cards=1)
    client.force_login(user)

    body = client.get(_print_url(lst, cfg)).content.decode()
    # 1 real fighter card + 3 blank cards
    assert body.count('class="classic-card') == 4
    assert body.count('data-kind="blank"') == 3


# ---------------------------------------------------------------------------
# ?style= URL override (the crew page's Print dropdown)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_style_param_selects_classic_without_a_config(
    client, user, make_list, make_list_fighter
):
    """?style=classic renders the classic sheet with no PrintConfig at all —
    how the crew page's Print dropdown offers the classic cards."""
    lst = make_list("Gang")
    make_list_fighter(lst, "Ganger")
    client.force_login(user)

    resp = client.get(_print_url(lst) + "?style=classic")

    assert resp.status_code == 200
    assert "core/list_print_classic.html" in [t.name for t in resp.templates]
    assert len(resp.context["classic_cards"]) == 1  # the fighter, no blanks


@pytest.mark.django_db
def test_style_param_overrides_a_classic_config_back_to_default(
    client, user, make_list, make_list_fighter
):
    """An explicit ?style=default wins over a classic config."""
    lst = make_list("Gang")
    make_list_fighter(lst, "Ganger")
    config = _classic_config(lst, user)
    client.force_login(user)

    resp = client.get(_print_url(lst, config) + "&style=default")

    assert resp.status_code == 200
    assert "core/list_print_classic.html" not in [t.name for t in resp.templates]


@pytest.mark.django_db
def test_crew_print_dropdown_offers_both_styles(client, user, make_list, campaign):
    """The crew page's Print control links both card styles for the crew."""
    from gyrinx.core.models import Battle, List
    from gyrinx.core.models.crew import Crew

    lst = make_list("Gang", status=List.CAMPAIGN_MODE, campaign=campaign)
    campaign.lists.add(lst)
    battle = Battle.objects.create(campaign=campaign, mission="Test", owner=user)
    battle.set_participants([lst])
    crew = Crew.objects.create(battle=battle, list=lst, owner=user)
    client.force_login(user)

    resp = client.get(reverse("core:crew", args=[battle.id, crew.id]))

    assert resp.status_code == 200
    content = resp.content.decode()
    assert f"?crew={crew.id}" in content
    assert f"?crew={crew.id}&style=classic" in content


@pytest.mark.django_db
def test_crew_classic_print_renders_crew_fighters(
    client, user, make_list, make_list_fighter, campaign
):
    """A crew print in classic style shows the crew's fighters as classic cards."""
    from gyrinx.core.models import Battle, List
    from gyrinx.core.models.crew import Crew, CrewMember

    lst = make_list("Gang", status=List.CAMPAIGN_MODE, campaign=campaign)
    campaign.lists.add(lst)
    picked = make_list_fighter(lst, "Picked")
    make_list_fighter(lst, "Benched")
    battle = Battle.objects.create(campaign=campaign, mission="Test", owner=user)
    battle.set_participants([lst])
    crew = Crew.objects.create(battle=battle, list=lst, owner=user, status=Crew.LOCKED)
    CrewMember.objects.create(
        crew=crew, list_fighter=picked, source=CrewMember.CHOSEN, owner=user
    )
    client.force_login(user)

    resp = client.get(_print_url(lst) + f"?crew={crew.id}&style=classic")

    assert resp.status_code == 200
    assert "core/list_print_classic.html" in [t.name for t in resp.templates]
    names = [c.name for c in resp.context["classic_cards"]]
    assert names == ["Picked"]  # crew-narrowed, no bench


@pytest.mark.django_db
def test_unrecognised_style_falls_back_to_the_config(
    client, user, make_list, make_list_fighter
):
    """?style=bogus is a navigation accident: the config's style still applies."""
    lst = make_list("Gang")
    make_list_fighter(lst, "Ganger")
    config = _classic_config(lst, user)
    client.force_login(user)

    resp = client.get(_print_url(lst, config) + "&style=bogus")

    assert resp.status_code == 200
    assert "core/list_print_classic.html" in [t.name for t in resp.templates]


@pytest.mark.django_db
def test_style_classic_with_a_config_keeps_its_blank_cards(
    client, user, make_list, make_list_fighter
):
    """?style=classic alongside a config still appends the config's blanks."""
    lst = make_list("Gang")
    make_list_fighter(lst, "Ganger")
    config = _classic_config(lst, user, blank_fighter_cards=2)
    client.force_login(user)

    resp = client.get(_print_url(lst, config) + "&style=classic")

    assert resp.status_code == 200
    cards = resp.context["classic_cards"]
    assert len(cards) == 3  # the fighter + 2 blanks
    assert [c.kind for c in cards].count("blank") == 2
