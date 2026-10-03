"""Listing control props contain only display values, never live domain objects."""

from n26.core.templatetags.record_tables import record_table_controls


def test_listing_controls_preserve_the_server_query_and_serialise_choices():
    assert record_table_controls(
        "/n26/gangs/", "RUST", "gangs", "gang", [{"value": 7, "label": "Goliath"}]
    ) == {
        "action": "/n26/gangs/",
        "query": "RUST",
        "noun": "gangs",
        "singular": "gang",
        "typeOptions": [{"value": "7", "label": "Goliath"}],
    }
