"""The hire preview transports prepared facts without changing their meaning."""

import json

import pytest

from n26.core.model_preview import model_preview_props
from n26.core.render import (
    AssignableLine,
    ChoiceLine,
    CounterLine,
    GearGroup,
    ModelCard,
    Provenance,
    StatCell,
    Statline,
    WeaponLine,
    WeaponProfileLine,
)


def test_the_projection_preserves_formatted_stats_and_their_explanations():
    card = ModelCard(
        "Agent <One>",
        125,
        Statline(
            [
                StatCell("M", "Movement", '5"', highlighted=True),
                StatCell(
                    "T",
                    "Toughness",
                    "4",
                    first_of_group=True,
                    modified_by=[Provenance(source="Armour", source_kind="wargear")],
                    held_at="maximum",
                ),
            ]
        ),
        profile_name="Gang leader",
        profile_type="Fighter",
        subtypes=[AssignableLine("Mounted"), AssignableLine("Leader")],
        xp=0,
    )
    props = model_preview_props(card)
    assert props["name"] == "Agent <One>"
    assert props["rating"] == 125
    assert props["typeLine"] == "Fighter (Leader, Mounted)"
    assert props["xpTarget"] == "–"
    assert props["typeSpan"] == 1
    assert props["statGroups"][0][0]["value"] == '5"'
    assert props["statGroups"][1][0]["explanation"] == (
        "T changed by Armour (wargear). Cannot get any better."
    )
    assert json.loads(json.dumps(props)) == props


def test_detail_rows_keep_counter_visibility_groups_and_distinct_choice_prompts():
    card = ModelCard(
        "Agent",
        0,
        Statline(),
        skills=[AssignableLine("Steady")],
        skill_choices=[ChoiceLine("Skills", None)],
        counters=[
            CounterLine("XP", 3, is_xp=True),
            CounterLine("Hidden", 9, drawn=False),
            CounterLine("Tally", 0),
        ],
        choices=[
            ChoiceLine("Allegiance", "Alpha", is_full=False, takes_several=True),
            ChoiceLine("Allegiance", None),
        ],
        gear_groups=[GearGroup("Armour", [AssignableLine("Mesh")])],
    )
    details = model_preview_props(card)["details"]
    by_label = {row["label"]: row["parts"] for row in details}
    assert "XP" not in by_label
    assert "Hidden" not in by_label
    assert by_label["Tally"] == [{"kind": "counter", "value": 0}]
    assert by_label["Skills"][1] == {
        "kind": "choice",
        "chosen": None,
        "prompt": "Choose skills",
    }
    assert by_label["Allegiance"] == [
        {"kind": "choice", "chosen": "Alpha", "prompt": "Add"},
        {"kind": "choice", "chosen": None, "prompt": "Choose"},
    ]
    assert by_label["Armour"][0]["lines"][0]["text"] == "Mesh"


def test_weapon_profiles_keep_the_main_line_named_profiles_and_item_choices():
    weapon = WeaponLine(
        "Launcher",
        30,
        slots=2,
        profiles=[
            WeaponProfileLine("", 0, Statline()),
            WeaponProfileLine(
                "Focused",
                5,
                Statline([StatCell("S", "Strength", "6")]),
                traits=[AssignableLine("Accurate")],
            ),
        ],
        accessories=[
            AssignableLine(
                "Sight", provenance=Provenance(source="Harness", computed=True)
            )
        ],
        choices=[ChoiceLine("Channel", "Blue"), ChoiceLine("Channel", None)],
        brought_in=("Fang",),
    )
    props = model_preview_props(ModelCard("Agent", 100, Statline(), weapons=[weapon]))
    shown = props["weapons"][0]
    assert shown["name"] == weapon.name + weapon.slot_mark + " (Fang)"
    assert shown["stats"] == []
    assert props["weaponColumns"][0]["shortName"] == "S"
    assert shown["profiles"][0]["stats"][0]["value"] == "6"
    assert shown["profiles"][0]["traits"][0]["text"] == "Accurate"
    assert shown["accessories"][0]["explanation"] == "From Harness"
    assert shown["choices"] == [{"label": "Channel", "values": ["Blue", "—"]}]


def test_the_projection_excludes_owner_actions_and_unshown_editor_prose():
    card = ModelCard(
        "Agent",
        0,
        Statline(),
        notes="<script>private()</script>",
        lore="Private lore",
        skills_href="/skills/",
        equipment=[AssignableLine("Coat", sell=object(), more=(object(),))],
    )
    encoded = json.dumps(model_preview_props(card))
    assert "/skills/" not in encoded
    assert "Private lore" not in encoded
    assert "private()" not in encoded
    assert "Coat" in encoded


def test_a_stored_model_cannot_accidentally_use_the_hire_preview_contract():
    with pytest.raises(ValueError, match="unstored card"):
        model_preview_props(ModelCard("Agent", 0, Statline(), id="stored"))
