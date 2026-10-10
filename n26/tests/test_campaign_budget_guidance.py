"""Owner budget guidance and privacy-preserving campaign links on gang lists."""

from contextlib import contextmanager

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import campaign_operation
from n26.core.models import CampaignParticipant, LedgerEvent
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.flags import CAMPAIGNS
from n26.tests.sandbox.actions import (
    buy,
    create_wargear,
    found_campaign,
    found_gang,
    hire_with_option,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def table(client, campaign_type):
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
    owner = User.objects.create_user("arbitrator")
    campaign = found_campaign("Dust Falls", campaign_type, owner=owner, budget=1000)
    client.force_login(owner)
    return owner, campaign


def join(campaign, gang):
    with campaign_operation(campaign, actor=campaign.owner) as op:
        op.add_gang(gang)


def test_add_gang_explains_unlimited_credits_and_links_to_inspect_and_edit(
    client, table, gang_type
):
    owner, campaign = table
    gang = found_gang("Unlimited gang", gang_type, owner=owner)
    response = client.get(reverse("n26-campaign-add-gang", args=[campaign.pk]))
    soup = BeautifulSoup(response.content, "html.parser")
    assert any(
        link.get_text(strip=True) == gang.name
        for link in soup.find_all("a", href=reverse("n26-gang", args=[gang.pk]))
    )
    assert soup.find(
        "a", href=reverse("n26-edit-gang", args=[gang.pk]) + "#starting-credits"
    )
    assert "credit balances are not tracked" in soup.get_text()
    assert "joining budget is 1000¢" in soup.get_text()
    assert "does not change its credits budget" in soup.get_text()
    gang.refresh_from_db()
    assert gang.starting_credits is None


def test_arbitrator_can_inspect_a_players_gang_but_cannot_change_its_budget(
    client, table, gang_type
):
    _, campaign = table
    player = User.objects.create_user("player")
    CampaignParticipant.objects.create(
        campaign=campaign, user=player, state=CampaignParticipant.State.ACCEPTED
    )
    gang = found_gang("Player gang", gang_type, owner=player)
    soup = BeautifulSoup(
        client.get(reverse("n26-campaign-add-gang", args=[campaign.pk])).content,
        "html.parser",
    )
    assert soup.find("a", href=reverse("n26-gang", args=[gang.pk]))
    assert not soup.find(
        "a", href=reverse("n26-edit-gang", args=[gang.pk]) + "#starting-credits"
    )


def test_joining_leaves_the_budget_unchanged_and_owner_can_explicitly_set_it(
    client, table, gang_type
):
    owner, campaign = table
    gang = found_gang("Unlimited gang", gang_type, owner=owner)
    response = client.post(
        reverse("n26-campaign-add-gang", args=[campaign.pk]),
        {"gang": gang.pk},
        follow=True,
    )
    assert "uses unlimited credits" in response.content.decode()
    gang.refresh_from_db()
    assert gang.starting_credits is None
    sheet_url = reverse("n26-gang", args=[gang.pk])
    assert "Use a custom budget" in client.get(sheet_url).content.decode()
    response = client.post(
        reverse("n26-edit-gang", args=[gang.pk]),
        {"name": gang.name, "starting_credits": 1000, "colour": ""},
    )
    assert response.status_code == 302
    gang.refresh_from_db()
    assert gang.starting_credits == 1000
    assert gang.credits == 1000
    assert "Use a custom budget" not in client.get(sheet_url).content.decode()


@pytest.mark.parametrize("budget", [None, 1500])
def test_budget_guidance_is_only_for_owner_of_a_participating_gang(
    client, table, gang_type, budget
):
    owner, campaign = table
    gang = found_gang("Budget gang", gang_type, owner=owner, budget=budget)
    path = reverse("n26-gang", args=[gang.pk])
    dismiss_path = reverse("n26-dismiss-campaign-budget", args=[gang.pk])
    assert dismiss_path not in client.get(path).content.decode()
    join(campaign, gang)
    assert dismiss_path in client.get(path).content.decode()
    client.logout()
    assert dismiss_path not in client.get(path).content.decode()
    stranger = User.objects.create_user("stranger")
    client.force_login(stranger)
    assert dismiss_path not in client.get(path).content.decode()
    assert (
        client.post(
            reverse("n26-edit-gang", args=[gang.pk]),
            {"name": gang.name, "starting_credits": 1000},
        ).status_code
        == 404
    )


@pytest.mark.parametrize("page", ["n26-gangs", "n26-dashboard"])
def test_indexes_link_to_active_campaigns_the_reader_is_in(
    client, table, gang_type, page
):
    owner, campaign = table
    gang = found_gang("Playing gang", gang_type, owner=owner)
    join(campaign, gang)
    soup = BeautifulSoup(client.get(reverse(page)).content, "html.parser")
    row = soup.select_one("[data-record-row]")
    assert (
        row.find("a", href=reverse("n26-campaign", args=[campaign.pk])).get_text(
            strip=True
        )
        == campaign.name
    )


def test_public_gang_index_does_not_disclose_other_peoples_campaigns(
    client, table, gang_type
):
    owner, campaign = table
    gang = found_gang("Public gang", gang_type, owner=owner)
    join(campaign, gang)
    viewer = User.objects.create_user("viewer")
    client.force_login(viewer)
    path = reverse("n26-gangs") + "?everyone=1"
    html = client.get(path).content.decode()
    assert gang.name in html
    assert campaign.name not in html
    assert reverse("n26-campaign", args=[campaign.pk]) not in html
    CampaignParticipant.objects.create(
        campaign=campaign, user=viewer, state=CampaignParticipant.State.INVITED
    )
    assert campaign.name not in client.get(path).content.decode()
    CampaignParticipant.objects.filter(campaign=campaign, user=viewer).update(
        state=CampaignParticipant.State.ACCEPTED
    )
    assert campaign.name in client.get(path).content.decode()
    FeatureFlag.objects.filter(slug=CAMPAIGNS).update(availability=Availability.OFF)
    assert campaign.name not in client.get(path).content.decode()


def test_more_participating_gangs_do_not_add_index_queries(client, table, gang_type):
    owner, campaign = table

    def add(number):
        gang = found_gang(f"Gang {number}", gang_type, owner=owner)
        join(campaign, gang)

    path = reverse("n26-gangs")
    add(0)
    client.get(path)
    with CaptureQueriesContext(connection) as few:
        assert client.get(path).status_code == 200
    for number in range(1, 9):
        add(number)
    with CaptureQueriesContext(connection) as many:
        assert client.get(path).status_code == 200
    assert len(many) <= len(few)


def test_the_owner_can_use_the_current_campaign_budget_in_one_submission(
    client, table, gang_type
):
    owner, campaign = table
    gang = found_gang("Unlimited gang", gang_type, owner=owner)
    join(campaign, gang)
    path = reverse("n26-use-campaign-budget", args=[gang.pk])
    assert client.get(path).status_code == 405
    assert (
        "Use campaign budget"
        in client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    )
    response = client.post(path, {"starting_credits": 1})
    assert response.url == reverse("n26-gang", args=[gang.pk])
    gang.refresh_from_db()
    assert gang.starting_credits == 1000
    assert gang.credits == 1000
    assert "Use campaign budget" not in client.get(response.url).content.decode()
    assert_reconciled(gang)


@pytest.mark.parametrize(
    "budget,shown",
    [(None, True), (1500, True), (1000, False), (500, False), (0, False)],
)
def test_the_prompt_covers_unlimited_and_above_budget_gangs(
    client, table, gang_type, budget, shown
):
    owner, campaign = table
    gang = found_gang("Budget gang", gang_type, owner=owner, budget=budget)
    join(campaign, gang)
    soup = BeautifulSoup(
        client.get(reverse("n26-gang", args=[gang.pk])).content, "html.parser"
    )
    form = soup.find("form", action=reverse("n26-use-campaign-budget", args=[gang.pk]))
    custom = soup.find(
        "a", href=reverse("n26-edit-gang", args=[gang.pk]) + "#starting-credits"
    )
    dismiss = soup.find(
        "form", action=reverse("n26-dismiss-campaign-budget", args=[gang.pk])
    )
    assert bool(dismiss) == shown
    assert bool(form) == (budget is None)
    assert bool(custom) == (budget is None)
    if shown:
        if budget is None:
            assert (
                form.find("button").get_text(strip=True)
                == "Use campaign budget — 1000¢"
            )
            assert (
                "This gang currently has unlimited credits. Set a budget using the options below:"
                in soup.get_text()
            )
        else:
            assert "Above campaign budget" in soup.get_text()
            assert "credits (1500¢) total 1500¢" in soup.get_text()
            assert "The campaign budget is 1000¢." in soup.get_text()
            assert response_notice(client, gang).variant == "warning"


def response_notice(client, gang):
    return client.get(reverse("n26-gang", args=[gang.pk])).context["budget_notice"]


def dismiss_notice(client, gang):
    return client.post(
        reverse("n26-dismiss-campaign-budget", args=[gang.pk]),
        {"notice_signature": response_notice(client, gang).dismiss_signature},
    )


@pytest.mark.parametrize(
    "change", ["budget", "no_budget", "removed", "archived", "rejoined"]
)
def test_campaign_changes_before_the_budget_lock_are_respected(
    client, table, gang_type, monkeypatch, change
):
    owner, campaign = table
    gang = found_gang("Unlimited gang", gang_type, owner=owner)
    join(campaign, gang)

    @contextmanager
    def changed_before_lock(found, actor=None):
        with campaign_operation(campaign, actor=owner) as op:
            if change == "budget":
                op.set_budget(900)
            elif change == "no_budget":
                op.set_budget(None)
            elif change == "archived":
                op.archive()
            else:
                op.remove_gang(gang.campaign_memberships.get(left__isnull=True))
                if change == "rejoined":
                    op.add_gang(gang)
        with campaign_operation(found, actor=actor) as op:
            yield op

    monkeypatch.setattr("n26.core.campaigns.campaign_operation", changed_before_lock)
    response = client.post(reverse("n26-use-campaign-budget", args=[gang.pk]))
    gang.refresh_from_db()
    if change == "budget":
        assert response.status_code == 302
        assert gang.starting_credits == 900
        assert gang.credits == 900
    else:
        assert response.status_code == 404
        assert gang.starting_credits is None
        assert not LedgerEvent.objects.filter(
            gang=gang, kind=LedgerEvent.Kind.BUDGET_SET
        ).exists()
    assert_reconciled(gang)


@pytest.mark.parametrize("price", [300, 1200])
def test_an_above_budget_gang_keeps_its_models_stash_and_credits(
    client, table, gang_type, make_profile, price
):
    owner, campaign = table
    gang = found_gang("Budget gang", gang_type, owner=owner, budget=1500)
    fighter = hire_with_option(gang, make_profile("Ganger", price=price), "Ash")
    buy(gang.stash, thing=create_wargear("Spare armour", price=100))
    join(campaign, gang)
    path = reverse("n26-use-campaign-budget", args=[gang.pk])
    events = LedgerEvent.objects.filter(gang=gang).count()
    response = client.post(path, {"starting_credits": 2000})
    assert response.url == reverse("n26-gang", args=[gang.pk])
    gang.refresh_from_db()
    assert (gang.starting_credits, gang.credits, gang.rating, gang.stash_rating) == (
        1500,
        1400 - price,
        price,
        100,
    )
    fighter.refresh_from_db()
    assert not fighter.membership.archived
    assert response_notice(client, gang).title == "Above campaign budget"
    client.post(path)
    assert LedgerEvent.objects.filter(gang=gang).count() == events
    assert_reconciled(gang)


def test_an_above_budget_gang_with_adjusted_credits_gets_only_a_warning(
    client, table, gang_type
):
    owner, campaign = table
    gang = found_gang("Extra credits", gang_type, owner=owner, budget=1000)
    with operation(gang, actor=owner) as op:
        op.adjust_credits(200, "Extra credits")
    join(campaign, gang)
    response = client.get(reverse("n26-gang", args=[gang.pk]))
    html = response.content.decode()
    assert "Above campaign budget" in html
    assert "credits (1200¢) total 1200¢" in html
    assert "Use campaign budget" not in html
    assert "Use a custom budget" not in html
    gang.refresh_from_db()
    assert (gang.starting_credits, gang.credits) == (1000, 1200)
    assert_reconciled(gang)


def test_budget_submission_does_not_validate_unrelated_gang_details(
    client, table, gang_type
):
    owner, campaign = table
    gang = found_gang("G" * 150, gang_type, owner=owner)
    join(campaign, gang)
    response = client.post(reverse("n26-use-campaign-budget", args=[gang.pk]))
    assert response.url == reverse("n26-gang", args=[gang.pk])
    gang.refresh_from_db()
    assert gang.starting_credits == 1000
    assert gang.name == "G" * 150
    assert_reconciled(gang)


def test_a_budget_that_cannot_cover_the_gang_keeps_the_prompt_and_budget(
    client, table, gang_type, make_profile
):
    owner, campaign = table
    gang = found_gang("Spent gang", gang_type, owner=owner)
    hire_with_option(gang, make_profile("Leader", price=1200), "Ash")
    join(campaign, gang)
    gang.refresh_from_db()
    before = (gang.starting_credits, gang.credits)
    events = LedgerEvent.objects.filter(
        gang=gang, kind=LedgerEvent.Kind.BUDGET_SET
    ).count()
    response = client.post(
        reverse("n26-use-campaign-budget", args=[gang.pk]), follow=True
    )
    assert response.redirect_chain == [(reverse("n26-gang", args=[gang.pk]), 302)]
    assert "200¢ short" in response.content.decode()
    assert "Use campaign budget — 1000¢" in response.content.decode()
    gang.refresh_from_db()
    assert (gang.starting_credits, gang.credits) == before
    assert (
        LedgerEvent.objects.filter(gang=gang, kind=LedgerEvent.Kind.BUDGET_SET).count()
        == events
    )
    assert_reconciled(gang)


@pytest.mark.parametrize("budget", [None, 1500])
def test_dismissing_the_prompt_leaves_money_unchanged_and_survives_reload(
    client, table, gang_type, budget
):
    owner, campaign = table
    gang = found_gang("Dismissed gang", gang_type, owner=owner, budget=budget)
    join(campaign, gang)
    path = reverse("n26-dismiss-campaign-budget", args=[gang.pk])
    assert client.get(path).status_code == 405
    events = LedgerEvent.objects.filter(gang=gang).count()
    response = dismiss_notice(client, gang)
    assert response.url == reverse("n26-gang", args=[gang.pk])
    assert path not in client.get(response.url).content.decode()
    assert path not in client.get(response.url).content.decode()
    gang.refresh_from_db()
    assert gang.starting_credits == budget
    assert gang.credits == (budget or 0)
    assert LedgerEvent.objects.filter(gang=gang).count() == events
    assert_reconciled(gang)


@pytest.mark.parametrize("change", ["campaign", "gang"])
def test_a_changed_budget_shows_a_dismissed_prompt_again(
    client, table, gang_type, change
):
    owner, campaign = table
    gang = found_gang("Dismissed gang", gang_type, owner=owner)
    join(campaign, gang)
    dismiss_notice(client, gang)
    if change == "campaign":
        with campaign_operation(campaign, actor=owner) as op:
            op.set_budget(900)
    else:
        with operation(gang, actor=owner) as op:
            op.set_budget(1500)
    assert (
        reverse("n26-dismiss-campaign-budget", args=[gang.pk])
        in client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    )


def test_a_new_membership_shows_a_dismissed_prompt_again(client, table, gang_type):
    owner, campaign = table
    gang = found_gang("Dismissed gang", gang_type, owner=owner)
    join(campaign, gang)
    dismiss_notice(client, gang)
    with campaign_operation(campaign, actor=owner) as op:
        op.remove_gang(gang.campaign_memberships.get(left__isnull=True))
    join(campaign, gang)
    assert (
        "Use a custom budget"
        in client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    )


@pytest.mark.parametrize("change", ["campaign", "gang", "membership"])
def test_a_stale_dismissal_does_not_hide_a_new_budget_notice(
    client, table, gang_type, change
):
    owner, campaign = table
    gang = found_gang("Changed notice", gang_type, owner=owner)
    join(campaign, gang)
    signature = response_notice(client, gang).dismiss_signature
    if change == "campaign":
        with campaign_operation(campaign, actor=owner) as op:
            op.set_budget(900)
    elif change == "gang":
        with operation(gang, actor=owner) as op:
            op.set_budget(1500)
    else:
        with campaign_operation(campaign, actor=owner) as op:
            op.remove_gang(gang.campaign_memberships.get(left__isnull=True))
            op.add_gang(gang)
    response = client.post(
        reverse("n26-dismiss-campaign-budget", args=[gang.pk]),
        {"notice_signature": signature},
    )
    assert response.status_code == 302
    assert response_notice(client, gang) is not None
    assert_reconciled(gang)


@pytest.mark.parametrize(
    "route", ["n26-use-campaign-budget", "n26-dismiss-campaign-budget"]
)
@pytest.mark.parametrize("unavailable", ["absent", "left", "archived", "flag"])
def test_budget_actions_need_an_active_available_campaign(
    client, table, gang_type, route, unavailable
):
    owner, campaign = table
    gang = found_gang("Unlimited gang", gang_type, owner=owner)
    if unavailable != "absent":
        join(campaign, gang)
    if unavailable == "left":
        with campaign_operation(campaign, actor=owner) as op:
            op.remove_gang(gang.campaign_memberships.get(left__isnull=True))
    elif unavailable == "archived":
        with campaign_operation(campaign, actor=owner) as op:
            op.archive()
    elif unavailable == "flag":
        FeatureFlag.objects.filter(slug=CAMPAIGNS).update(availability=Availability.OFF)
    assert (
        "Use a custom budget"
        not in client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    )
    assert client.post(reverse(route, args=[gang.pk])).status_code == 404


@pytest.mark.parametrize("budget", [None, 0])
def test_a_campaign_without_a_budget_or_with_zero_has_the_right_controls(
    client, table, gang_type, budget
):
    owner, campaign = table
    with campaign_operation(campaign, actor=owner) as op:
        op.set_budget(budget)
    gang = found_gang("Unlimited gang", gang_type, owner=owner)
    join(campaign, gang)
    html = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    assert "Use a custom budget" in html
    if budget is None:
        assert "Use campaign budget" not in html
        assert (
            client.post(reverse("n26-use-campaign-budget", args=[gang.pk])).status_code
            == 404
        )
    else:
        assert "Use campaign budget — 0¢" in html
        client.post(reverse("n26-use-campaign-budget", args=[gang.pk]))
        gang.refresh_from_db()
        assert gang.starting_credits == 0
        assert_reconciled(gang)


@pytest.mark.parametrize(
    "route", ["n26-use-campaign-budget", "n26-dismiss-campaign-budget"]
)
def test_the_campaign_arbitrator_cannot_set_or_dismiss_a_players_budget(
    client, table, gang_type, route
):
    _, campaign = table
    player = User.objects.create_user("player")
    CampaignParticipant.objects.create(
        campaign=campaign, user=player, state=CampaignParticipant.State.ACCEPTED
    )
    gang = found_gang("Player gang", gang_type, owner=player)
    join(campaign, gang)
    assert client.post(reverse(route, args=[gang.pk])).status_code == 404
    gang.refresh_from_db()
    assert gang.starting_credits is None
