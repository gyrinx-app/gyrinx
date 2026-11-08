"""Stored-card projections preserve every independently actionable source."""

import json

from n26.core.listing import Action
from n26.core.model_card_display import model_card_props
from n26.core.render import (
    AssignableLine,
    ChoiceLine,
    CounterLine,
    ModelCard,
    Statline,
    WeaponLine,
    WeaponProfileLine,
)


def sale(key):
    return Action("Sell", "link", f"/equip/?sell={key}", "danger")


def test_owned_menus_keep_sale_neutral_and_move_destructive_actions_after_ordinary_actions():
    card = ModelCard(
        "Vex",
        75,
        Statline(),
        id="model",
        weapons=[
            WeaponLine(
                "Gun",
                30,
                sell=sale("gun"),
                more=(
                    Action("Delete", "link", "/delete/", "danger"),
                    Action("Reassign", "link", "/move/", "secondary"),
                    Action("Refund", "link", "/refund/", "danger"),
                ),
                accessorise=Action("Add accessory", "link", "/accessory/", "secondary"),
            )
        ],
    )
    weapon = model_card_props(card, rename_href="/rename/", status_href="/status/")[
        "weapons"
    ][0]
    assert [
        (action["label"], action["tone"], action.get("separatorBefore", False))
        for action in weapon["actions"]
    ] == [
        ("Sell", "default", False),
        ("Reassign", "secondary", False),
        ("Delete", "danger", True),
        ("Refund", "danger", True),
    ]
    assert weapon["accessorise"]["target"] == "/accessory/"


def test_stored_cards_keep_distinct_gear_profile_and_accessory_controls_without_reads():
    tier = ChoiceLine("Tier", "One", key="tier", href="/tier/", is_tier_ladder=True)
    channel = ChoiceLine("Channel", "Blue", key="channel", href="/channel/")
    card = ModelCard(
        "Vex",
        75,
        Statline(),
        id="model",
        equipment=[
            AssignableLine(
                "Harness", id="first", sell=sale("first"), choices=[tier, channel]
            ),
            AssignableLine("Harness", id="second", sell=sale("second")),
        ],
        weapons=[
            WeaponLine(
                "Gun",
                30,
                id="gun",
                sell=sale("gun"),
                profiles=[
                    WeaponProfileLine("", 0),
                    WeaponProfileLine("Ammo", 10, id="ammo", sell=sale("ammo")),
                ],
                accessories=[AssignableLine("Sight", id="sight", sell=sale("sight"))],
            )
        ],
        notes="Private notes",
        lore="Private lore",
    )
    props = model_card_props(card, rename_href="/rename/", status_href="/status/")
    gear = next(row for row in props["details"] if row["label"] == "Gear")["parts"][0][
        "lines"
    ]
    assert [line["key"] for line in gear] == ["first", "second"]
    assert [line["actions"][0]["target"] for line in gear] == [
        "/equip/?sell=first",
        "/equip/?sell=second",
    ]
    assert gear[0]["tiers"][0]["href"] == "/tier/"
    assert gear[0]["choices"][0]["controls"][0]["href"] == "/channel/"
    gun = props["weapons"][0]
    assert gun["actions"][0]["target"] == "/equip/?sell=gun"
    assert gun["profiles"][0]["actions"][0]["target"] == "/equip/?sell=ammo"
    assert gun["accessories"][0]["actions"][0]["target"] == "/equip/?sell=sight"
    assert props["stored"]["renameHref"] == "/rename/"
    assert props["stored"]["statusHref"] == "/status/"
    encoded = json.dumps(props)
    assert "Private notes" not in encoded and "Private lore" not in encoded
    assert json.loads(encoded) == props


def test_counters_keep_recorded_and_displayed_values_and_choices_keep_dismissal_navigation():
    card = ModelCard(
        "Vex",
        0,
        Statline(),
        id="model",
        counters=[
            CounterLine(
                "Marks",
                8,
                tallied=3,
                assignment_id="counter",
                href="/tally/",
                back="/equip/",
            ),
            CounterLine("Hidden", 4, drawn=False),
        ],
        skill_choices=[
            ChoiceLine(
                "Skills",
                None,
                key="skill",
                href="/choose/",
                dismiss_href="/dismiss/",
                back="/equip/",
            )
        ],
    )
    props = model_card_props(card, rename_href="/rename/", status_href="/status/")
    rows = {row["label"]: row for row in props["details"]}
    assert "Hidden" not in rows
    tally = rows["Marks"]["parts"][0]
    assert tally["value"] == 8
    assert tally["control"]["tallied"] == 3
    assert tally["control"]["assignment"] == "counter"
    choice = next(part for part in rows["Skills"]["parts"] if part["kind"] == "choice")
    assert choice["prompt"] == "Choose skills"
    assert choice["control"]["dismissHref"] == "/dismiss/"
    assert choice["control"]["back"] == "/equip/"
