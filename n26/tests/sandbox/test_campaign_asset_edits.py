"""An arbitrator can change one holding without changing another copy."""

from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.campaigns import campaign_operation
from n26.core.history import campaign_history
from n26.core.models import CampaignAsset, CampaignEvent
from n26.core.operations import Refusal
from n26.core.render import render_gang
from n26.library.authoring import create_asset
from n26.library.core_campaign import seed_core_campaign
from n26.library.models import CampaignType, Modifier
from n26.tests.sandbox.actions import found_campaign, found_gang, join_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def campaign(default_pack):
    seed_core_campaign(apps)
    core = CampaignType.objects.get(name="Territory campaign")
    owner = User.objects.create_user("arbitrator")
    return found_campaign("Dust Falls", core, owner=owner)


@pytest.fixture
def holding(campaign):
    kind = campaign.campaign_type.asset_types.get(label_singular="Territory")
    asset = create_asset("Old Ruins", kind, income=30)
    with campaign_operation(campaign, actor=campaign.owner) as op:
        return op.add_asset(asset)


def edit(campaign, holding, **values):
    with campaign_operation(campaign, actor=campaign.owner) as op:
        return op.edit_asset(holding, **values)


def url(campaign, holding):
    return reverse("n26-campaign-asset-edit", args=[campaign.pk, holding.pk])


def detail(campaign, holding):
    return reverse("n26-campaign-asset", args=[campaign.pk, holding.pk])


def test_editing_one_of_a_batch_keeps_the_other_holdings_override(campaign, holding):
    with campaign_operation(campaign, actor=campaign.owner) as op:
        op.add_assets([holding.asset, holding.asset], income=40, request_key=uuid4())
    one, two = campaign.campaign_assets.exclude(pk=holding.pk).order_by("pk")
    shared = one.income_override_id
    assert shared == two.income_override_id
    edited = edit(campaign, one, name="Sump ruins", income=60)
    two.refresh_from_db()
    holding.refresh_from_db()
    assert str(edited) == "Sump ruins"
    assert edited.income_override_id != shared
    assert edited.income_override.contributes_to_counter.amount == 60
    assert two.income_override_id == shared
    assert two.income_override.contributes_to_counter.amount == 40
    assert holding.income_override_id is None
    assert str(holding) == "Old Ruins"


@pytest.mark.parametrize("income", [0, 70])
def test_clearing_an_override_restores_catalogue_income(campaign, holding, income):
    edited = edit(campaign, holding, name="Sump ruins", income=income)
    previous = edited.income_override_id
    assert edited.income_override.contributes_to_counter.amount == income
    restored = edit(campaign, holding)
    assert restored.name == ""
    assert restored.income_override_id is None
    assert str(restored) == "Old Ruins"
    assert not Modifier.objects.filter(pk=previous).exists()


def test_unchanged_saves_create_neither_events_nor_modifiers(campaign, holding):
    edit(campaign, holding, name="Sump ruins", income=0)
    counts = CampaignEvent.objects.count(), Modifier.objects.count()
    assert edit(campaign, holding, name=" Sump ruins ", income=0) is None
    assert (CampaignEvent.objects.count(), Modifier.objects.count()) == counts


def test_history_uses_the_values_read_under_the_campaign_lock(campaign, holding):
    edit(campaign, holding, name="First name", income=40)
    edit(campaign, holding, name="Second name", income=50)
    event = campaign.events.filter(kind=CampaignEvent.Kind.ASSET_EDITED).latest(
        "created"
    )
    assert event.note == "name First name → Second name; income override 40¢ → 50¢"
    text = [
        "".join(span.text for span in act.spans) for act in campaign_history(campaign)
    ]
    assert any(event.note in sentence for sentence in text)


@pytest.mark.parametrize("income", [-1, 2147483648, "30"])
def test_the_operation_rejects_invalid_income(campaign, holding, income):
    before = CampaignEvent.objects.count()
    with pytest.raises(Refusal, match="Income must be"):
        edit(campaign, holding, income=income)
    assert CampaignEvent.objects.count() == before


def test_removed_and_foreign_holdings_cannot_be_edited(campaign, holding):
    other = found_campaign("Elsewhere", campaign.campaign_type, owner=campaign.owner)
    with campaign_operation(other, actor=other.owner) as op:
        with pytest.raises(ValueError, match="another campaign"):
            op.edit_asset(holding, name="Elsewhere")
    with campaign_operation(campaign, actor=campaign.owner) as op:
        op.remove_asset(holding)
    with pytest.raises(Refusal, match="removed"):
        edit(campaign, holding, name="Gone")


@pytest.mark.parametrize("actor", [None, "player"])
def test_the_operation_requires_the_arbitrator(campaign, holding, actor):
    actor = User.objects.create_user(actor) if actor else None
    with campaign_operation(campaign, actor=actor) as op:
        with pytest.raises(Refusal, match="Only the arbitrator"):
            op.edit_asset(holding, name="Changed")


def test_held_income_updates_and_survives_transfer(campaign, holding, gang_type):
    gangs = [
        found_gang(name, gang_type, owner=User.objects.create_user(name))
        for name in ("Rust", "Ash")
    ]
    memberships = [join_campaign(gang, campaign) for gang in gangs]
    with campaign_operation(campaign, actor=campaign.owner) as op:
        op.assign(holding, memberships[0])
    holding.refresh_from_db()
    revision = holding.ownership_revision
    before = next(
        line.value
        for line in render_gang(gangs[0]).campaign.counters
        if line.name == "Income"
    )
    receiving_before = next(
        line.value
        for line in render_gang(gangs[1]).campaign.counters
        if line.name == "Income"
    )
    edited = edit(campaign, holding, name="Sump ruins", income=70)
    assert edited.holder_id == memberships[0].pk
    assert edited.ownership_revision == revision
    block = render_gang(gangs[0]).campaign
    assert (
        next(line.value for line in block.counters if line.name == "Income")
        == before + 40
    )
    with campaign_operation(campaign, actor=campaign.owner) as op:
        op.transfer(holding, memberships[1])
    block = render_gang(gangs[1]).campaign
    assert (
        next(line.value for line in block.counters if line.name == "Income")
        == receiving_before + 70
    )


def test_form_is_prefilled_and_preserves_zero(client, campaign, holding):
    edit(campaign, holding, name="Sump ruins", income=0)
    client.force_login(campaign.owner)
    response = client.get(url(campaign, holding))
    assert response.status_code == 200
    soup = BeautifulSoup(response.content, "html.parser")
    assert soup.select_one('input[name="name"]')["value"] == "Sump ruins"
    assert soup.select_one('input[name="income"]')["value"] == "0"
    assert "Catalogue entry: Old Ruins" in soup.get_text()
    assert "Boon contributions still apply." in soup.get_text()


def test_saving_returns_to_detail_and_keeps_table_preferences(
    client, campaign, holding
):
    client.force_login(campaign.owner)
    response = client.post(
        url(campaign, holding) + "?asset_sort=income&asset_group=none",
        {"name": "Sump ruins", "income": "0"},
    )
    assert response.status_code == 302
    assert (
        response.url
        == detail(campaign, holding) + "?asset_sort=income&asset_group=none"
    )
    holding.refresh_from_db()
    assert holding.name == "Sump ruins"
    assert holding.income_override.contributes_to_counter.amount == 0


@pytest.mark.parametrize("origin", ["", "?from=detail"])
def test_cancel_returns_to_the_origin(client, campaign, holding, origin):
    client.force_login(campaign.owner)
    response = client.get(url(campaign, holding) + origin)
    expected = (
        detail(campaign, holding)
        if origin
        else reverse("n26-campaign", args=[campaign.pk]) + "#assets"
    )
    assert response.context["back"] == expected


@pytest.mark.parametrize("income", ["-1", "2147483648", "bad"])
def test_invalid_posts_redisplay_without_writing(client, campaign, holding, income):
    client.force_login(campaign.owner)
    before = CampaignEvent.objects.count()
    response = client.post(url(campaign, holding), {"name": "Sump", "income": income})
    assert response.status_code == 200
    assert "income" in response.context["form"].errors
    assert CampaignEvent.objects.count() == before
    holding.refresh_from_db()
    assert holding.name == ""


def test_other_users_cannot_get_or_post_the_form(client, campaign, holding):
    client.force_login(User.objects.create_user("player"))
    assert client.get(url(campaign, holding)).status_code == 404
    assert client.post(url(campaign, holding), {"name": "Sump"}).status_code == 404
    client.logout()
    assert client.get(url(campaign, holding)).status_code == 302


def test_foreign_holding_and_csrf_are_checked(campaign, holding):
    client = Client(enforce_csrf_checks=True)
    client.force_login(campaign.owner)
    refused = client.post(url(campaign, holding), {"name": "Sump"})
    assert refused.status_code == 302 and refused.url == "/"
    holding.refresh_from_db()
    assert holding.name == ""
    other = found_campaign("Elsewhere", campaign.campaign_type, owner=campaign.owner)
    assert client.get(url(other, holding)).status_code == 404


def test_edit_page_queries_do_not_grow_with_the_inventory(client, campaign, holding):
    client.force_login(campaign.owner)
    client.get(url(campaign, holding))
    with CaptureQueriesContext(connection) as small:
        assert client.get(url(campaign, holding)).status_code == 200
    with campaign_operation(campaign, actor=campaign.owner) as op:
        for _ in range(8):
            op.add_asset(holding.asset)
    with CaptureQueriesContext(connection) as large:
        assert client.get(url(campaign, holding)).status_code == 200
    assert len(small) == len(large)
    assert CampaignAsset.objects.filter(campaign=campaign).count() == 9
