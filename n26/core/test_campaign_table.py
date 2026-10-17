from types import SimpleNamespace

import pytest
from django.test import RequestFactory

from n26.core.campaign_table import prepare_gang_table


def sheet():
    def gang(name, rating, credits, label, counter):
        return SimpleNamespace(
            gang_id=name,
            name=name,
            gang_type="Escher",
            owner=None,
            rating=rating,
            credits=credits,
            credits_unlimited=credits is None,
            wealth=rating,
            labels=[label],
            counters=[SimpleNamespace(value=counter) if counter is not None else None],
        )

    return SimpleNamespace(
        gangs=[
            gang("Beta", 200, None, "Lower", None),
            gang("Alpha", 100, 10, "Upper", 3),
            gang("Gamma", 300, 20, "", 1),
        ],
        counter_columns=["Reputation"],
        counter_keys=["rep"],
        label_columns=["Division"],
        label_ids=["division"],
    )


def test_numeric_sort_keeps_unlimited_credits_last_in_both_directions():
    for sort, names in [
        ("credits", ["Alpha", "Gamma", "Beta"]),
        ("-credits", ["Gamma", "Alpha", "Beta"]),
    ]:
        table = sheet()
        prepare_gang_table(
            table, RequestFactory().get("/", {"sort": sort}), "/campaign/"
        )
        assert [line.name for line in table.gangs] == names


def test_groups_keep_sorted_lines_and_unset_labels_visible():
    table = sheet()
    prepare_gang_table(
        table,
        RequestFactory().get("/", {"sort": "-counter-0", "group": "label-0"}),
        "/campaign/",
    )
    assert [group["label"] for group in table.table_groups] == [
        "Lower",
        "Upper",
        "Not set",
    ]
    assert [line.name for line in table.gangs] == ["Alpha", "Gamma", "Beta"]
    assert "group=label%3Adivision" in table.table_headers[1]["href"]


def test_stale_controls_fall_back_to_the_name_order():
    table = sheet()
    prepare_gang_table(
        table,
        RequestFactory().get("/", {"sort": "counter-99", "group": "label-9"}),
        "/campaign/",
    )
    assert table.table_sort == "name"
    assert table.table_group == ""
    assert [line.name for line in table.gangs] == ["Alpha", "Beta", "Gamma"]


def test_partial_redraw_keeps_the_current_page_order_and_group():
    table = sheet()
    request = RequestFactory().post(
        "/roll/",
        headers={
            "HX-Request": "true",
            "HX-Current-URL": "http://localhost/campaign/?sort=-rating&group=label-0",
        },
    )
    prepare_gang_table(table, request, "/campaign/")
    assert table.table_sort == "-rating"
    assert table.table_group == "label:division"
    assert [line.name for line in table.gangs] == ["Gamma", "Beta", "Alpha"]


def test_grouped_label_is_omitted_from_each_gangs_details():
    from n26.core.render import CampaignGangLine

    line = CampaignGangLine(
        "gang",
        "Rust Kings",
        "Goliath",
        None,
        100,
        0,
        100,
        labels=["Upper"],
        label_names=["Division"],
        grouped_label_index=0,
    )
    assert not line.details
    line.grouped_label_index = None
    assert [(detail.label, detail.text) for detail in line.details] == [
        ("Division", "Upper")
    ]


def test_partial_redraw_preserves_no_grouping_over_the_shared_default():
    table = sheet()
    table.label_ids = ["division"]
    table.default_group = "division"
    request = RequestFactory().post(
        "/roll/",
        headers={
            "HX-Request": "true",
            "HX-Current-URL": "http://localhost/campaign/?sort=-rating&group=",
        },
    )
    prepare_gang_table(table, request, "/campaign/")
    assert table.table_group == ""
    assert table.table_href == "/campaign/?sort=-rating&group="


def test_a_default_view_keeps_its_canonical_url_after_redraw():
    table = sheet()
    prepare_gang_table(
        table,
        RequestFactory().post("/roll/", headers={"HX-Request": "true"}),
        "/campaign/",
    )
    assert table.table_href == "/campaign/"


def test_a_counter_dialog_uses_its_return_url_for_table_preferences():
    table = sheet()
    table.label_ids = ["division"]
    table.default_group = "division"
    prepare_gang_table(
        table,
        RequestFactory().post(
            "/tally/",
            headers={
                "HX-Request": "true",
                "HX-Current-URL": "http://localhost/tally/?back=campaign",
            },
        ),
        "/campaign/",
        current_url="/campaign/?sort=-counter-0&group=",
    )
    assert [line.name for line in table.gangs] == ["Alpha", "Gamma", "Beta"]
    assert table.table_group == ""
    assert table.table_href == "/campaign/?sort=-counter%3Arep&group="


def test_stable_selections_survive_an_earlier_column_being_archived():
    table = sheet()
    table.counter_keys.insert(0, "earlier")
    table.counter_columns.insert(0, "Earlier")
    table.label_ids.insert(0, "earlier")
    table.label_columns.insert(0, "Earlier")
    for line in table.gangs:
        line.counters.insert(0, None)
        line.labels.insert(0, "Ignored")
    request = RequestFactory().get(
        "/", {"sort": "-counter:rep", "group": "label:division"}
    )
    prepare_gang_table(table, request, "/campaign/")
    assert table.table_sort == "-counter:rep"
    assert table.table_group == "label:division"
    assert [line.name for line in table.gangs] == ["Alpha", "Gamma", "Beta"]
    table.counter_keys.pop(0)
    table.counter_columns.pop(0)
    table.label_ids.pop(0)
    table.label_columns.pop(0)
    for line in table.gangs:
        line.counters.pop(0)
        line.labels.pop(0)
    prepare_gang_table(table, request, "/campaign/")
    assert table.table_sort == "-counter:rep"
    assert table.table_group == "label:division"
    table.counter_keys = []
    table.counter_columns = []
    table.label_ids = []
    table.label_columns = []
    for line in table.gangs:
        line.counters = []
        line.labels = []
    prepare_gang_table(table, request, "/campaign/")
    assert table.table_sort == "name" and table.table_group == ""


def test_stale_dialog_links_take_the_visible_query_and_keep_their_other_parameters():
    from n26.core.views.campaigns import _table_action_href

    request = RequestFactory().get(
        "/assign/?sort=name&group=old&from=detail",
        headers={
            "HX-Request": "true",
            "HX-Current-URL": "http://testserver/campaign/?sort=-rating&group=",
        },
    )
    assert _table_action_href(request) == "/assign/?from=detail&sort=-rating&group="
    request = RequestFactory().get(
        "/assign/?sort=name&group=old&from=detail",
        headers={"HX-Request": "true", "HX-Current-URL": "http://testserver/campaign/"},
    )
    assert _table_action_href(request) == "/assign/?from=detail"


def test_artwork_is_safe_and_shared_by_content_not_a_gang_types_display_name():
    from n26.core.campaign_table import gang_table_props
    from n26.core.render import CampaignGangLine, CampaignSheet

    first = CampaignGangLine(
        "first",
        "First",
        "Same type",
        None,
        0,
        0,
        0,
        type_icon='<svg viewBox="0 0 24 24" onload="bad()"><circle r="1" /><script>bad()</script></svg>',
    )
    second = CampaignGangLine(
        "second",
        "Second",
        "Same type",
        None,
        0,
        0,
        0,
        type_icon='<svg viewBox="0 0 24 24"><path d="M0 0h1" /></svg>',
    )
    third = CampaignGangLine(
        "third", "Third", "Another type", None, 0, 0, 0, type_icon=first.type_icon
    )
    data = gang_table_props(
        CampaignSheet("Campaign", "campaign", "Type", "", gangs=[first, second, third])
    )
    keys = [gang["artwork"] for gang in data["gangs"]]
    assert keys[0] != keys[1] and keys[0] == keys[2]
    assert len(data["artwork"]) == 2
    tree = data["artwork"][keys[0]]
    assert "onload" not in tree["props"]
    assert [child["tag"] for child in tree["children"]] == ["circle"]


@pytest.mark.parametrize(
    "markup, child_props",
    [
        (
            '<svg viewBox="0 0 24 24"><rect width="24" height="24" /></svg>',
            {"width": "24", "height": "24"},
        ),
        (
            '<svg viewBox="0 0 24 24"><path d="M0 0h24" fill="#000000" '
            'stroke="#ffffff" /><path fill="none" /></svg>',
            {"d": "M0 0h24", "fill": "currentColor", "stroke": "currentColor"},
        ),
        (
            '<svg width="24" height="24" shape-rendering="crispEdges">'
            '<rect x="11" y="0" width="2" height="1" fill="#000000" /></svg>',
            {"x": "11", "y": "0", "width": "2", "height": "1", "fill": "currentColor"},
        ),
    ],
    ids=["inherited-colour", "explicit-colours", "intrinsic-dimensions"],
)
def test_gang_artwork_scales_and_matches_the_surrounding_text(markup, child_props):
    from n26.core.campaign_table import gang_table_props
    from n26.core.render import CampaignGangLine, CampaignSheet

    line = CampaignGangLine(
        "gang", "Acid Cats", "Escher", None, 0, 0, 0, type_icon=markup
    )
    data = gang_table_props(
        CampaignSheet("Campaign", "campaign", "Type", "", gangs=[line])
    )
    tree = data["artwork"][data["gangs"][0]["artwork"]]
    assert tree["props"]["viewBox"] == "0 0 24 24"
    assert tree["props"]["fill"] == "currentColor"
    assert "width" not in tree["props"] and "height" not in tree["props"]
    assert tree["children"][0]["props"] == child_props
    if len(tree["children"]) > 1:
        assert tree["children"][1]["props"]["fill"] == "none"
    if "crispEdges" in markup:
        assert tree["props"]["shapeRendering"] == "crispEdges"
