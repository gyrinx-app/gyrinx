from types import SimpleNamespace

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
        label_columns=["Division"],
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
    assert "group=label-0" in table.table_headers[1]["href"]


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
    assert table.table_group == "label-0"
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
