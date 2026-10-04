"""Campaign settings tabs, their owner boundary and addition return paths."""

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import campaign_operation
from n26.flags import CAMPAIGNS
from n26.library.authoring import add_built_in, create_counter
from n26.tests.sandbox.actions import found_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def campaign(client, campaign_type):
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
    add_built_in(campaign_type, create_counter("Reputation"), amount=2)
    owner = User.objects.create_user("settings-arbitrator")
    found = found_campaign("Dust Falls", campaign_type, owner=owner)
    with campaign_operation(found, actor=owner) as act:
        act.add_counter("Meat", opening=3)
        act.add_label("Faction", ["Law Abiding", "Outlaw"])
    client.force_login(owner)
    return found


def settings_url(campaign):
    return reverse("n26-edit-campaign", args=[campaign.pk]) + "?tab=counters-and-labels"


def test_general_settings_and_definitions_have_separate_url_tabs(client, campaign):
    edit = reverse("n26-edit-campaign", args=[campaign.pk])
    general = client.get(edit)
    assert general.context["tab"] == "general"
    assert 'name="summary"' in general.content.decode()
    assert settings_url(campaign) in general.content.decode()
    definitions = client.get(settings_url(campaign))
    assert definitions.status_code == 200
    assert definitions.context["tab"] == "counters-and-labels"
    assert definitions.context["form"] is None
    assert {
        item["name"]: item["opening"] for item in definitions.context["counters"]
    } == {"Reputation": 2, "Meat": 3}
    assert definitions.context["labels"] == [{"name": "Faction"}]
    assert 'name="summary"' not in definitions.content.decode()
    assert "tinymce.min.js" not in definitions.content.decode()
    assert "Save campaign" not in definitions.content.decode()
    assert client.get(edit + "?tab=unknown").context["tab"] == "general"


def test_the_dropdown_opens_management_and_does_not_offer_additions_on_the_header(
    client, campaign
):
    html = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
    assert settings_url(campaign) in html
    for route in ("n26-campaign-add-counter", "n26-campaign-add-label"):
        assert reverse(route, args=[campaign.pk]) not in html


@pytest.mark.parametrize(
    "route, payload",
    [
        ("n26-campaign-add-counter", {"name": "Victories", "opening": "0"}),
        ("n26-campaign-add-label", {"name": "Objective", "options": "Wealth\nPower"}),
    ],
)
def test_add_and_cancel_return_to_the_management_tab(client, campaign, route, payload):
    at = reverse(route, args=[campaign.pk])
    assert client.get(at).context["back"] == settings_url(campaign)
    response = client.post(at, payload)
    assert response.status_code == 302
    assert response.url == settings_url(campaign)
    assert payload["name"] in client.get(response.url).content.decode()


def test_general_save_and_validation_still_use_the_general_tab(client, campaign):
    edit = reverse("n26-edit-campaign", args=[campaign.pk])
    response = client.post(edit, {"name": "", "budget": "1000", "summary": ""})
    assert response.status_code == 200
    assert response.context["tab"] == "general"
    assert response.context["form"].errors["name"]
    response = client.post(
        edit,
        {"name": "New Dust Falls", "budget": "0", "summary": "<p>Campaign notes</p>"},
    )
    assert response.status_code == 302
    campaign.refresh_from_db()
    assert campaign.name == "New Dust Falls"
    assert campaign.budget == 0
    assert "Campaign notes" in campaign.summary


def test_another_account_cannot_read_the_settings_tab(client, campaign):
    client.force_login(User.objects.create_user("settings-reader"))
    assert client.get(settings_url(campaign)).status_code == 404


def test_more_counter_and_label_definitions_do_not_grow_page_queries(client, campaign):
    at = settings_url(campaign)
    client.get(at)
    with CaptureQueriesContext(connection) as small:
        assert client.get(at).status_code == 200
    with campaign_operation(campaign, actor=campaign.owner) as act:
        for number in range(6):
            act.add_counter(f"Counter {number}")
            act.add_label(f"Label {number}", ["One", "Two"])
    client.get(at)
    with CaptureQueriesContext(connection) as large:
        response = client.get(at)
        assert response.status_code == 200
    assert len(response.context["counters"]) == 8
    assert len(response.context["labels"]) == 7
    assert len(large) <= len(small)
