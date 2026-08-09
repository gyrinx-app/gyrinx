"""The admin analytics dashboard, and the growth chart it builds from the registry.

The chart's lines are contributed by the edition (``n23/core/admin/analytics.py``)
through ``gyrinx.analytics.registry``. Registration failures are silent — the
page still renders, just with an empty chart — so these tests assert the data
actually plots, not merely that the page returns 200.
"""

import json

import pytest
from django.urls import reverse

from gyrinx.analytics.registry import (
    GrowthSeries,
    daily_counts_by_date,
    growth_series,
    register_growth_series,
)


@pytest.fixture
def dashboard_admin(make_user):
    u = make_user("dashboard-admin", "password")
    u.is_staff = True
    u.is_superuser = True
    u.save()
    return u


def _cumulative(response):
    return json.loads(response.context["cumulative_data"])


@pytest.mark.django_db
def test_dashboard_renders_for_staff(client, dashboard_admin):
    client.force_login(dashboard_admin)
    resp = client.get(reverse("admin:analytics_dashboard"))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_growth_chart_has_a_line_per_registered_series(client, dashboard_admin):
    client.force_login(dashboard_admin)
    resp = client.get(reverse("admin:analytics_dashboard"))

    data = _cumulative(resp)
    assert [d["label"] for d in data["datasets"]] == [s.label for s in growth_series()]
    # Every line is plotted over the same x-axis as the chart's labels.
    for dataset in data["datasets"]:
        assert len(dataset["data"]) == len(data["labels"])


@pytest.mark.django_db
def test_growth_chart_counts_the_editions_objects(
    client, dashboard_admin, make_list, make_list_fighter, make_campaign
):
    lst = make_list("Growth Gang")
    make_list_fighter(lst, "Growth Fighter")
    make_campaign("Growth Campaign")

    client.force_login(dashboard_admin)
    resp = client.get(reverse("admin:analytics_dashboard"))

    totals = {d["label"]: d["data"][-1] for d in _cumulative(resp)["datasets"]}
    assert totals["N23 Fighters (Cumulative)"] >= 1
    assert totals["N23 Lists (Cumulative)"] >= 1
    assert totals["N23 Campaigns (Cumulative)"] >= 1


@pytest.mark.django_db
def test_series_values_accumulate_and_never_fall(client, dashboard_admin, make_list):
    make_list("Cumulative Gang")

    client.force_login(dashboard_admin)
    resp = client.get(reverse("admin:analytics_dashboard"))

    for dataset in _cumulative(resp)["datasets"]:
        values = dataset["data"]
        assert values == sorted(values), f"{dataset['label']} is not cumulative"


@pytest.mark.django_db
def test_daily_counts_by_date_groups_by_creation_day(make_campaign):
    """The helper editions build their series from."""
    from datetime import timedelta

    from django.utils import timezone

    from n23.core.models import Campaign

    make_campaign("Counted One")
    make_campaign("Counted Two")

    counts = daily_counts_by_date(
        Campaign.objects.all(), timezone.now() - timedelta(days=1)
    )
    assert sum(counts.values()) == 2
    assert set(counts) == {timezone.now().date()}


@pytest.mark.django_db
def test_picking_an_edition_leaves_only_that_editions_lines(client, dashboard_admin):
    """Two products on one chart: whichever one you asked for is the one you
    get, because adding their lines together would describe neither."""
    client.force_login(dashboard_admin)
    resp = client.get(reverse("admin:analytics_dashboard") + "?edition=n26")

    labels = [d["label"] for d in _cumulative(resp)["datasets"]]
    assert labels == [s.label for s in growth_series("n26")]
    assert not any(label.startswith("N23") for label in labels)


@pytest.mark.django_db
def test_an_edition_nobody_has_heard_of_shows_everything(client, dashboard_admin):
    client.force_login(dashboard_admin)
    resp = client.get(reverse("admin:analytics_dashboard") + "?edition=nonsense")

    labels = [d["label"] for d in _cumulative(resp)["datasets"]]
    assert labels == [s.label for s in growth_series()]


@pytest.mark.django_db
def test_registering_a_key_twice_replaces_rather_than_duplicates():
    """Re-registration overrides in place — a series can't be double-plotted."""
    before = len(growth_series())
    series = GrowthSeries(
        key="test_dupe",
        label="First",
        border_color="rgb(0, 0, 0)",
        background_color="rgba(0, 0, 0, 0.2)",
        daily_counts=lambda start: {},
        edition="n23",
    )
    register_growth_series(series)
    try:
        register_growth_series(
            GrowthSeries(
                key="test_dupe",
                label="Second",
                border_color="rgb(1, 1, 1)",
                background_color="rgba(1, 1, 1, 0.2)",
                daily_counts=lambda start: {},
                edition="n23",
            )
        )
        registered = growth_series()
        assert len(registered) == before + 1
        assert registered[-1].label == "Second"
    finally:
        from gyrinx.analytics import registry

        registry._series.pop("test_dupe", None)
