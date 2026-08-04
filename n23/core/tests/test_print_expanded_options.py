"""Expanded print options (#1816).

Three things the print flow gained, all about the two sheets showing the same
information:

* the classic sheet grew a **gang plate** carrying resources, assets,
  attributes and the stash — everything the web sheet puts in its header and
  side cards, which the classic sheet previously dropped on the floor;
* the web sheet can show **XP** on fighter cards, which the classic card has
  always printed;
* **lore and notes** get their own printout, in either style.
"""

import pytest
from django.urls import reverse

from n23.content.models import ContentAttribute, ContentAttributeValue
from n23.core.models import PrintConfig
from n23.core.models.campaign import (
    CampaignAsset,
    CampaignAssetType,
    CampaignListResource,
    CampaignResourceType,
)
from n23.core.models.list import ListAttributeAssignment
from n23.core.print_cards import (
    gang_card_from_list,
    lore_card_from_fighter,
    lore_card_from_list,
)


def _classic_config(list_obj, owner, **kwargs):
    return PrintConfig.objects.create(
        list=list_obj,
        owner=owner,
        name="Classic",
        card_style=PrintConfig.CLASSIC,
        **kwargs,
    )


def _print_url(list_obj, config=None, **params):
    url = reverse("core:list-print", kwargs={"id": list_obj.id})
    query = dict(params)
    if config is not None:
        query["config_id"] = str(config.id)
    if query:
        url += "?" + "&".join(f"{k}={v}" for k, v in query.items())
    return url


def _lore_url(list_obj, **params):
    url = reverse("core:list-print-lore-notes", kwargs={"id": list_obj.id})
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    return url


def _give_resource(list_obj, name="Reputation", amount=5):
    resource_type = CampaignResourceType.objects.create(
        campaign=list_obj.campaign,
        owner=list_obj.owner,
        name=name,
        default_amount=0,
    )
    return CampaignListResource.objects.create(
        campaign=list_obj.campaign,
        resource_type=resource_type,
        list=list_obj,
        amount=amount,
        owner=list_obj.owner,
    )


def _give_asset(list_obj, name="Old Factory", type_name="Territory"):
    asset_type = CampaignAssetType.objects.create(
        campaign=list_obj.campaign,
        owner=list_obj.owner,
        name_singular=type_name,
        name_plural=f"{type_name}s",
    )
    return CampaignAsset.objects.create(
        asset_type=asset_type,
        owner=list_obj.owner,
        name=name,
        holder=list_obj,
    )


def _give_attribute(list_obj, name="Alignment", value="Outlaw"):
    attribute = ContentAttribute.objects.create(name=name, is_single_select=True)
    attr_value = ContentAttributeValue.objects.create(attribute=attribute, name=value)
    ListAttributeAssignment.objects.create(list=list_obj, attribute_value=attr_value)
    return attr_value


def _give_stash(list_obj, equipment, make_content_fighter, make_list_fighter):
    """Attach a stash fighter holding ``equipment``."""
    stash_content_fighter = make_content_fighter(
        type="Stash",
        category="STASH",
        house=list_obj.content_house,
        base_cost=0,
        is_stash=True,
    )
    stash = make_list_fighter(list_obj, "Stash", content_fighter=stash_content_fighter)
    stash.assign(equipment)
    return stash


# ---------------------------------------------------------------------------
# gang_card_from_list
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_gang_card_gathers_the_gang_level_sections(list_with_campaign):
    lst = list_with_campaign
    resource = _give_resource(lst, "Reputation", 7)
    asset = _give_asset(lst, "Old Factory", "Territory")

    card = gang_card_from_list(
        lst,
        resources=[resource],
        held_assets=[asset],
        attributes=[{"name": "Alignment", "assignments": ["Outlaw"]}],
    )

    assert card.kind == "gang"
    assert card.name == lst.name
    assert card.has_content
    labels = [g.label for g in card.sections]
    assert labels == ["Resources", "Assets", "Alignment"]
    assert card.sections[0].text == "Reputation: 7"
    assert card.sections[1].text == "Old Factory (Territory)"
    assert card.sections[2].text == "Outlaw"


@pytest.mark.django_db
def test_gang_card_skips_empty_sections(list_with_campaign):
    """An attribute with no assigned value is not a section."""
    card = gang_card_from_list(
        list_with_campaign,
        resources=[],
        held_assets=[],
        attributes=[{"name": "Alignment", "assignments": []}],
    )

    assert card.sections == []
    assert not card.has_content


@pytest.mark.django_db
def test_gang_card_columns_are_balanced(list_with_campaign):
    """Sections split across the plate's two columns, keeping reading order."""
    card = gang_card_from_list(
        list_with_campaign,
        attributes=[
            {"name": f"Attr {i}", "assignments": [f"Value {i}"]} for i in range(4)
        ],
    )

    columns = card.detail_columns
    assert len(columns) == 2
    flattened = [g.label for column in columns for g in column]
    assert flattened == ["Attr 0", "Attr 1", "Attr 2", "Attr 3"]


# ---------------------------------------------------------------------------
# The gang plate on the classic sheet
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_classic_sheet_shows_resources_and_assets(
    client, user, list_with_campaign, make_list_fighter
):
    """The whole point of #1816: classic used to drop these entirely."""
    lst = list_with_campaign
    _give_resource(lst, "Reputation", 7)
    _give_asset(lst, "Old Factory", "Territory")
    make_list_fighter(lst, "Grimjaw")
    cfg = _classic_config(lst, user)
    client.force_login(user)

    body = client.get(_print_url(lst, cfg)).content.decode()

    assert 'data-kind="gang"' in body
    assert "Reputation: 7" in body
    assert "Old Factory (Territory)" in body
    assert "Grimjaw" in body  # fighter cards still render


@pytest.mark.django_db
def test_classic_gang_plate_honours_the_asset_toggle(
    client, user, list_with_campaign, make_list_fighter
):
    lst = list_with_campaign
    _give_resource(lst, "Reputation", 7)
    make_list_fighter(lst, "Grimjaw")
    cfg = _classic_config(lst, user, include_assets=False)
    client.force_login(user)

    body = client.get(_print_url(lst, cfg)).content.decode()

    assert "Reputation" not in body
    assert 'data-kind="gang"' not in body  # nothing left to put on it


@pytest.mark.django_db
def test_classic_gang_plate_honours_the_attribute_toggle(
    client, user, list_with_campaign
):
    lst = list_with_campaign
    _give_attribute(lst, "Alignment", "Outlaw")
    cfg = _classic_config(lst, user)
    client.force_login(user)

    body = client.get(_print_url(lst, cfg)).content.decode()
    assert "Outlaw" in body

    cfg.include_attributes = False
    cfg.save()
    body = client.get(_print_url(lst, cfg)).content.decode()
    assert "Outlaw" not in body


@pytest.mark.django_db
def test_classic_gang_plate_carries_the_stash(
    client,
    user,
    list_with_campaign,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    """The stash has no fighter card, so its contents ride on the gang plate."""
    lst = list_with_campaign
    _give_stash(
        lst,
        make_equipment("Spare Autogun", cost=25),
        make_content_fighter,
        make_list_fighter,
    )

    cfg = _classic_config(lst, user)
    client.force_login(user)

    body = client.get(_print_url(lst, cfg)).content.decode()
    assert "Spare Autogun" in body

    cfg.include_stash = False
    cfg.save()
    body = client.get(_print_url(lst, cfg)).content.decode()
    assert "Spare Autogun" not in body


@pytest.mark.django_db
def test_classic_sheet_without_gang_content_has_no_gang_plate(
    client, user, make_list, make_list_fighter
):
    """A non-campaign gang has no resources, assets or stash to show."""
    lst = make_list("Gang")
    make_list_fighter(lst, "Grimjaw")
    cfg = _classic_config(lst, user)
    client.force_login(user)

    body = client.get(_print_url(lst, cfg)).content.decode()

    assert 'data-kind="gang"' not in body
    assert "Grimjaw" in body


# ---------------------------------------------------------------------------
# XP on the web sheet
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_web_print_shows_xp_by_default(client, user, make_list, make_list_fighter):
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Grimjaw")
    fighter.xp_current = 12
    fighter.save()
    client.force_login(user)

    body = client.get(_print_url(lst)).content.decode()

    assert "12 XP" in body
    # ...but no way to edit it from a printout.
    assert "Edit XP" not in body


@pytest.mark.django_db
def test_web_print_xp_toggle(client, user, make_list, make_list_fighter):
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Grimjaw")
    fighter.xp_current = 12
    fighter.save()
    cfg = PrintConfig.objects.create(
        list=lst, owner=user, name="No XP", include_xp=False
    )
    client.force_login(user)

    body = client.get(_print_url(lst, cfg)).content.decode()

    assert "12 XP" not in body


@pytest.mark.django_db
def test_classic_card_xp_follows_the_same_toggle(
    client, user, make_list, make_list_fighter
):
    """The toggle governs both sheets — the classic card has an XP region too."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Grimjaw")
    fighter.xp_current = 12
    fighter.save()
    cfg = _classic_config(lst, user)
    client.force_login(user)

    body = client.get(_print_url(lst, cfg)).content.decode()
    assert ">12<" in body  # the classic card's XP value

    cfg.include_xp = False
    cfg.save()
    body = client.get(_print_url(lst, cfg)).content.decode()
    assert ">12<" not in body


@pytest.mark.django_db
def test_print_config_defaults_to_showing_xp(client, user, make_list):
    lst = make_list("Gang")
    client.force_login(user)

    response = client.get(
        reverse("core:print-config-create", kwargs={"list_id": lst.id})
    )

    assert response.context["form"].initial["include_xp"] is True


@pytest.mark.django_db
def test_card_summary_mentions_xp(user, make_list):
    lst = make_list("Gang")
    cfg = PrintConfig.objects.create(list=lst, owner=user, name="Everything")

    assert "XP" in cfg.card_summary()

    cfg.include_xp = False
    assert "XP" not in cfg.card_summary()


# ---------------------------------------------------------------------------
# Lore and notes printout
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_lore_notes_print_renders_gang_and_fighter_prose(
    client, user, make_list, make_list_fighter
):
    lst = make_list("Gang")
    lst.narrative = "<p>Founded in the ash wastes.</p>"
    lst.notes = "<p>Owes the Guilders.</p>"
    lst.save()
    fighter = make_list_fighter(lst, "Grimjaw")
    fighter.narrative = "<p>Grew up underhive.</p>"
    fighter.notes = "<p>Hates rats.</p>"
    fighter.save()
    client.force_login(user)

    body = client.get(_lore_url(lst)).content.decode()

    assert "Founded in the ash wastes." in body
    assert "Owes the Guilders." in body
    assert "Grimjaw" in body
    assert "Grew up underhive." in body
    assert "Hates rats." in body


@pytest.mark.django_db
def test_lore_notes_print_omits_fighters_with_nothing_written(
    client, user, make_list, make_list_fighter
):
    lst = make_list("Gang")
    make_list_fighter(lst, "Silent Bob")
    told = make_list_fighter(lst, "Grimjaw")
    told.narrative = "<p>Grew up underhive.</p>"
    told.save()
    client.force_login(user)

    response = client.get(_lore_url(lst))

    names = [e["fighter"].name for e in response.context["entries"]]
    assert names == ["Grimjaw"]
    assert "Silent Bob" not in response.content.decode()


@pytest.mark.django_db
def test_lore_notes_print_keeps_private_notes_owner_only(
    client, user, make_user, make_list, make_list_fighter
):
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Grimjaw")
    fighter.notes = "<p>Hates rats.</p>"
    fighter.private_notes = "<p>Actually a spy.</p>"
    fighter.save()

    client.force_login(user)
    assert "Actually a spy." in client.get(_lore_url(lst)).content.decode()

    other = make_user("nosy", "password")
    client.force_login(other)
    body = client.get(_lore_url(lst)).content.decode()
    assert "Actually a spy." not in body
    assert "Hates rats." in body  # public notes still print


@pytest.mark.django_db
def test_lore_notes_print_classic_style(client, user, make_list, make_list_fighter):
    lst = make_list("Gang")
    lst.narrative = "<p>Founded in the ash wastes.</p>"
    lst.save()
    fighter = make_list_fighter(lst, "Grimjaw")
    fighter.narrative = "<p>Grew up underhive.</p>"
    fighter.save()
    client.force_login(user)

    body = client.get(_lore_url(lst, style="classic")).content.decode()

    assert "classic-card" in body
    assert 'data-kind="lore"' in body
    assert "print-sheet" in body
    # Rich text is flattened onto the plate.
    assert "Grew up underhive." in body
    assert "<p>Grew up underhive.</p>" not in body


@pytest.mark.django_db
def test_lore_notes_print_empty_gang(client, user, make_list):
    lst = make_list("Gang")
    client.force_login(user)

    body = client.get(_lore_url(lst)).content.decode()

    assert "No lore or notes have been written" in body


@pytest.mark.django_db
def test_lore_cards_flatten_rich_text(make_list, make_list_fighter):
    lst = make_list("Gang")
    lst.narrative = "<p>Founded in the <strong>ash wastes</strong>.</p>"
    lst.save()
    fighter = make_list_fighter(lst, "Grimjaw")
    fighter.narrative = "<p>Grew up underhive.</p>"
    fighter.private_notes = "<p>Actually a spy.</p>"
    fighter.save()

    gang_card = lore_card_from_list(lst)
    assert gang_card.kind == "lore"
    assert gang_card.sections[0].text == "Founded in the ash wastes."
    # Prose plates run one full-width column.
    assert len(gang_card.detail_columns) == 1

    public = lore_card_from_fighter(fighter)
    assert [g.label for g in public.sections] == ["Lore", "Notes"]

    private = lore_card_from_fighter(fighter, include_private=True)
    assert [g.label for g in private.sections] == ["Lore", "Notes", "Private notes"]


@pytest.mark.django_db
def test_lore_plates_flatten_prose_readably(make_list, make_list_fighter):
    """Rich text has to survive the trip to plain text.

    Stripping tags alone runs paragraphs together and leaves entities encoded,
    so an ampersand typed in the editor would print as "&amp;".
    """
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Grimjaw")
    fighter.narrative = "<p>First para.</p><p>Second para.</p>"
    fighter.notes = "<p>Bob &amp; Sons, the &#39;finest&#39; gang</p>"
    fighter.save()

    card = lore_card_from_fighter(fighter)
    lore, notes = card.sections[0], card.sections[1]

    assert lore.text == "First para. Second para."
    assert notes.text == "Bob & Sons, the 'finest' gang"


@pytest.mark.django_db
def test_lore_plates_leave_room_to_write(make_list, make_list_fighter):
    """Lore and Notes always get a write-in box, filled in or not."""
    lst = make_list("Gang")
    lst.narrative = "<p>Founded in the ash wastes.</p>"
    lst.save()
    fighter = make_list_fighter(lst, "Grimjaw")
    fighter.narrative = "<p>Grew up underhive.</p>"
    fighter.save()

    for card in (lore_card_from_list(lst), lore_card_from_fighter(fighter)):
        writeins = [g.label for g in card.sections if g.writein]
        assert writeins == ["Lore", "Notes"]

    # An empty Notes section still earns its box...
    fighter_card = lore_card_from_fighter(fighter)
    notes = next(g for g in fighter_card.sections if g.label == "Notes")
    assert notes.items == []
    assert notes.writein

    # ...but a plate of nothing but empty boxes isn't worth printing.
    blank = lore_card_from_fighter(make_list_fighter(lst, "Silent Bob"))
    assert not blank.has_content

    # The gang plate's sections are data, not write-in space.
    gang = gang_card_from_list(
        lst, attributes=[{"name": "Alignment", "assignments": ["Outlaw"]}]
    )
    assert not any(g.writein for g in gang.sections)


@pytest.mark.django_db
def test_lore_sheet_renders_the_write_in_boxes(
    client, user, make_list, make_list_fighter
):
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Grimjaw")
    fighter.narrative = "<p>Grew up underhive.</p>"
    fighter.save()
    client.force_login(user)

    body = client.get(_lore_url(lst, style="classic")).content.decode()

    assert "cc-writein--lore" in body
    # One per section, on the fighter plate: Lore and Notes.
    assert body.count("cc-writein--lore") == 2


# ---------------------------------------------------------------------------
# Lore & Notes cards on the main print sheet
# ---------------------------------------------------------------------------


def _lore_config(list_obj, owner, **kwargs):
    kwargs.setdefault("include_lore_notes", True)
    return PrintConfig.objects.create(
        list=list_obj, owner=owner, name="With lore", **kwargs
    )


@pytest.fixture
def gang_with_prose(make_list, make_list_fighter):
    lst = make_list("Gang")
    lst.narrative = "<p>Founded in the ash wastes.</p>"
    lst.save()
    fighter = make_list_fighter(lst, "Grimjaw")
    fighter.narrative = "<p>Grew up underhive.</p>"
    fighter.notes = "<p>Hates rats.</p>"
    fighter.private_notes = "<p>Actually a spy.</p>"
    fighter.save()
    make_list_fighter(lst, "Silent Bob")
    return lst


@pytest.mark.django_db
def test_web_sheet_prints_lore_notes_cards_when_asked(client, user, gang_with_prose):
    cfg = _lore_config(gang_with_prose, user)
    client.force_login(user)

    body = client.get(_print_url(gang_with_prose, cfg)).content.decode()

    # Fighter cards and note cards, on the one sheet.
    assert "Grew up underhive." in body
    assert "Hates rats." in body
    assert "Founded in the ash wastes." in body  # the gang's own card
    assert "Grimjaw" in body
    # A fighter with nothing written gets no note card.
    assert body.count("Silent Bob") == 1  # their fighter card only


@pytest.mark.django_db
def test_web_sheet_omits_lore_notes_cards_by_default(client, user, gang_with_prose):
    client.force_login(user)

    # No config at all...
    body = client.get(_print_url(gang_with_prose)).content.decode()
    assert "Grew up underhive." not in body

    # ...and a config that doesn't ask for them.
    cfg = _lore_config(gang_with_prose, user, include_lore_notes=False)
    body = client.get(_print_url(gang_with_prose, cfg)).content.decode()
    assert "Grew up underhive." not in body


@pytest.mark.django_db
def test_classic_sheet_tiles_lore_plates_after_the_fighter_cards(
    client, user, gang_with_prose
):
    cfg = _lore_config(gang_with_prose, user, card_style=PrintConfig.CLASSIC)
    client.force_login(user)

    body = client.get(_print_url(gang_with_prose, cfg)).content.decode()

    assert 'data-kind="lore"' in body
    assert "Grew up underhive." in body
    # Fighter plates come first, lore plates after.
    assert body.index('data-kind="fighter"') < body.index('data-kind="lore"')


@pytest.mark.django_db
def test_print_sheet_lore_cards_keep_private_notes_owner_only(
    client, user, make_user, gang_with_prose
):
    cfg = _lore_config(gang_with_prose, user)

    client.force_login(user)
    assert (
        "Actually a spy."
        in client.get(_print_url(gang_with_prose, cfg)).content.decode()
    )

    client.force_login(make_user("nosy", "password"))
    body = client.get(_print_url(gang_with_prose, cfg)).content.decode()
    assert "Actually a spy." not in body
    assert "Hates rats." in body


@pytest.mark.django_db
def test_lore_notes_cards_follow_the_fighter_selection(
    client, user, gang_with_prose, make_list_fighter
):
    """A fighter left out of the print has no note card either."""
    other = make_list_fighter(gang_with_prose, "Vex")
    other.narrative = "<p>Came down from the spire.</p>"
    other.save()
    cfg = _lore_config(
        gang_with_prose,
        user,
        fighter_selection_mode=PrintConfig.SPECIFIC_FIGHTERS,
    )
    cfg.included_fighters.set([other])
    client.force_login(user)

    body = client.get(_print_url(gang_with_prose, cfg)).content.decode()

    assert "Came down from the spire." in body
    assert "Grew up underhive." not in body


@pytest.mark.django_db
def test_card_summary_mentions_lore_notes(user, make_list):
    lst = make_list("Gang")
    cfg = PrintConfig.objects.create(
        list=lst, owner=user, name="Everything", include_lore_notes=True
    )
    assert "Lore & Notes" in cfg.card_summary()

    cfg.include_lore_notes = False
    assert "Lore & Notes" not in cfg.card_summary()


@pytest.mark.django_db
def test_lore_notes_print_linked_from_the_lore_and_notes_pages(client, user, make_list):
    lst = make_list("Gang")
    client.force_login(user)
    print_url = reverse("core:list-print-lore-notes", kwargs={"id": lst.id})

    for page in ("core:list-about", "core:list-notes"):
        body = client.get(reverse(page, kwargs={"id": lst.id})).content.decode()
        assert print_url in body
        assert f"{print_url}?style=classic" in body
