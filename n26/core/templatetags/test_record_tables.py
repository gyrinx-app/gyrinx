"""Listing control props contain only display values, never live domain objects."""

import pytest

from n26.core.templatetags.record_tables import record_table_controls


def test_listing_controls_preserve_the_server_query_and_serialise_choices():
    assert record_table_controls(
        "/n26/gangs/", "RUST", "gangs", "gang", [{"value": 7, "label": "Goliath"}]
    ) == {
        "action": "/n26/gangs/",
        "query": "RUST",
        "noun": "gangs",
        "singular": "gang",
        "mineOnly": None,
        "typeOptions": [{"value": "7", "label": "Goliath"}],
    }


@pytest.mark.parametrize("mine_only", [True, False])
def test_listing_controls_preserve_the_ownership_scope(mine_only):
    controls = record_table_controls(
        "/n26/gangs/", "rust", "gangs", "gang", [], mine_only
    )
    assert controls["mineOnly"] is mine_only
