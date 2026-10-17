"""Inventory props keep each holding's identity and prepared facts."""

from types import SimpleNamespace

import pytest

from n26.core.campaign_table import asset_table_props, prepare_inventory
from n26.core.render import CampaignAssetEntry, CampaignAssetTable


def inventory():
    table = CampaignAssetTable("territory", "Territory", "Territories")
    table.entries = [
        CampaignAssetEntry(
            "b",
            "Ruins",
            boon="Armour",
            income=20,
            held=True,
            holder="Zulu",
            holder_gang_id="z",
        ),
        CampaignAssetEntry("c", "Workshop", boon="Income", income=30),
        CampaignAssetEntry(
            "a",
            "Ruins",
            boon="Income",
            income=10,
            held=True,
            holder="Alpha",
            holder_gang_id="a",
        ),
        CampaignAssetEntry("d", "Cave", income=5),
    ]
    return SimpleNamespace(assets=[table])


def test_inventory_props_keep_repeated_holdings_and_their_prepared_facts():
    sheet = inventory()
    prepare_inventory(
        sheet, {"asset_sort": "-income", "asset_group": "holder"}, "/campaign/"
    )
    props = asset_table_props(sheet.assets[0])
    assert (props["sort"], props["group"], props["href"]) == (
        "-income",
        "holder",
        "/campaign/",
    )
    assert [
        (entry["id"], entry["boon"], entry["sortValues"]["income"], entry["holderId"])
        for entry in props["entries"]
    ] == [
        ("b", "Armour", 20, "z"),
        ("c", "Income", 30, ""),
        ("a", "Income", 10, "a"),
        ("d", "", 5, ""),
    ]


@pytest.mark.parametrize(
    ("query", "sort", "group"),
    [
        ({}, "name", "status"),
        ({"asset_sort": "-income", "asset_group": ""}, "-income", ""),
        (
            {
                "sort": "-rating",
                "group": "",
                "asset_sort": "unknown",
                "asset_group": "unknown",
            },
            "name",
            "status",
        ),
    ],
)
def test_inventory_preferences_are_validated_independently(query, sort, group):
    sheet = inventory()
    prepare_inventory(sheet, query, "/campaign/")
    assert sheet.inventory_view == {"href": "/campaign/", "sort": sort, "group": group}
    assert sheet.assets[0].inventory_view == sheet.inventory_view
