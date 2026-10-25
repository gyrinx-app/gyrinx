"""Asset names retain their boundaries and counts until a surface draws them."""

from n26.core.effects import StackedName, stacked_name_items, stacked_names
from n26.core.render import CampaignAssetLine, group_campaign_assets


def test_counted_names_keep_punctuation_and_first_seen_order():
    names = ["Ruins, North", "Shop", "Shop", "Ruins, North", "Settlement"]
    assert stacked_name_items(names) == [
        StackedName("Ruins, North", 2),
        StackedName("Shop", 2),
        StackedName("Settlement"),
    ]
    assert stacked_names(names) == "Ruins, North (x2), Shop (x2), Settlement"


def test_identical_names_in_different_types_keep_their_own_counts():
    lines = [
        CampaignAssetLine(
            "Territory",
            "Ruins, North",
            type_plural="Territories",
            asset_type_id="territory",
            display_group="Sites",
        ),
        *[
            CampaignAssetLine(
                "Settlement",
                "Ruins, North",
                type_plural="Settlements",
                asset_type_id="settlement",
                display_group="Sites",
            )
            for _ in range(2)
        ],
    ]
    (group,) = group_campaign_assets(lines)
    assert group.label == "Sites"
    assert group.names == [StackedName("Ruins, North"), StackedName("Ruins, North", 2)]


def test_empty_types_have_no_name_items():
    (group,) = group_campaign_assets([], types=[("territory", "Territories")])
    assert group.names == []


def test_a_literal_none_name_is_an_item():
    (group,) = group_campaign_assets(
        [
            CampaignAssetLine("Territory", "None", type_plural="Territories"),
        ]
    )
    assert group.names == [StackedName("None")]
