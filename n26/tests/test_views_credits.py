"""Manage credits: adding credits to a gang, or removing them, by hand."""

from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core import history
from n26.core.models import Gang, LedgerEvent
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.flags import CAMPAIGNS
from n26.tests.sandbox.actions import found_campaign, found_gang, join_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def feature():
    return FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )


@pytest.fixture
def table(default_pack, gang_type, campaign_type, counter_tracking):
    owner = User.objects.create_user("credits-owner")
    arbitrator = User.objects.create_user("credits-arbitrator")
    campaign = found_campaign("Dust Falls", campaign_type, owner=arbitrator)
    gang = found_gang("Ashen Choir", gang_type, owner=owner, budget=100)
    join_campaign(gang, campaign)
    return SimpleNamespace(
        owner=owner, arbitrator=arbitrator, campaign=campaign, gang=gang
    )


def url(gang):
    return reverse("n26-gang-credits", args=[gang.pk])


def fresh(gang):
    return Gang.objects.get(pk=gang.pk)


def told(gang, viewer):
    return [
        "".join(span.text for span in act.spans)
        for act in history.build(gang, viewer=viewer)
        if act.category == "credits"
    ]


class TestTheOwner:
    """The gang's owner adds and removes credits, and the gang never
    goes below zero."""

    def test_adding_credits_raises_the_balance_and_says_so(self, client, table):
        client.force_login(table.owner)
        response = client.post(
            url(table.gang),
            {"direction": "add", "amount": "40", "note": "Scenario reward"},
        )

        assert response.status_code == 302
        assert response.url == reverse("n26-gang", args=[table.gang.pk])
        assert fresh(table.gang).credits == 140
        assert [str(m) for m in get_messages(response.wsgi_request)] == [
            "Added 40¢ to Ashen Choir."
        ]
        assert_reconciled(fresh(table.gang))

    def test_removing_credits_lowers_the_balance(self, client, table):
        client.force_login(table.owner)
        client.post(url(table.gang), {"direction": "remove", "amount": "30"})

        assert fresh(table.gang).credits == 70
        assert_reconciled(fresh(table.gang))

    def test_the_history_says_added_and_removed_with_the_note(self, client, table):
        client.force_login(table.owner)
        client.post(
            url(table.gang),
            {"direction": "add", "amount": "40", "note": "Scenario reward"},
        )
        client.post(url(table.gang), {"direction": "remove", "amount": "25"})

        assert told(table.gang, table.owner) == [
            "added 40¢ — Scenario reward",
            "removed 25¢",
        ]
        kinds = LedgerEvent.objects.filter(
            gang=table.gang, kind=LedgerEvent.Kind.CREDITS_ADJUSTED
        ).values_list("credits_delta", "campaign", "actor")
        assert sorted(kinds) == sorted(
            [
                (-40, table.campaign.pk, table.owner.pk),
                (25, table.campaign.pk, table.owner.pk),
            ]
        )

    def test_removing_more_than_the_gang_has_is_refused_whole(self, client, table):
        client.force_login(table.owner)
        response = client.post(
            url(table.gang), {"direction": "remove", "amount": "101"}
        )

        assert response.status_code == 200
        assert response.context["form"].errors["amount"] == [
            "You cannot remove more than Ashen Choir has (100¢)."
        ]
        assert fresh(table.gang).credits == 100
        assert not LedgerEvent.objects.filter(
            kind=LedgerEvent.Kind.CREDITS_ADJUSTED
        ).exists()

    def test_removing_everything_leaves_zero(self, client, table):
        client.force_login(table.owner)
        client.post(url(table.gang), {"direction": "remove", "amount": "100"})

        assert fresh(table.gang).credits == 0
        assert_reconciled(fresh(table.gang))

    @pytest.mark.parametrize("amount", ["0", "-5", "", "3000000000"])
    def test_an_amount_below_one_is_a_form_error(self, client, table, amount):
        client.force_login(table.owner)
        response = client.post(url(table.gang), {"direction": "add", "amount": amount})

        assert response.status_code == 200
        assert "amount" in response.context["form"].errors
        assert fresh(table.gang).credits == 100

    def test_an_unknown_direction_is_an_error_and_add_stays_selected(
        self, client, table
    ):
        client.force_login(table.owner)
        response = client.post(url(table.gang), {"direction": "foo", "amount": "5"})

        assert "direction" in response.context["form"].errors
        checked = [d["value"] for d in response.context["directions"] if d["checked"]]
        assert checked == ["add"]
        assert fresh(table.gang).credits == 100

    def test_the_page_shows_the_balance_and_both_choices(self, client, table):
        client.force_login(table.owner)
        response = client.get(url(table.gang))

        assert response.status_code == 200
        page = BeautifulSoup(response.content, "html.parser")
        assert "Ashen Choir has 100¢." in page.get_text()
        radios = page.select('input[type="radio"][name="direction"]')
        assert [(r["value"], r.has_attr("checked")) for r in radios] == [
            ("add", True),
            ("remove", False),
        ]
        history_link = reverse("n26-gang-history", args=[table.gang.pk])
        assert page.select_one(f'a[href="{history_link}?kind=credits"]') is not None

    def test_the_gang_page_offers_manage_credits(self, client, table):
        client.force_login(table.owner)
        response = client.get(reverse("n26-gang", args=[table.gang.pk]))

        page = BeautifulSoup(response.content, "html.parser")
        links = page.select(f'a[href="{url(table.gang)}"]')
        texts = {link.get_text(strip=True) for link in links}
        # The button, and the Credits figure in the wealth strip.
        assert "Manage credits" in texts
        assert "100¢" in texts


class TestUnlimitedCredits:
    """A gang with unlimited credits has no figure to change, so it gets
    no page and no way in."""

    @pytest.fixture
    def gang(self, default_pack, gang_type, owner):
        return found_gang("No Ceiling", gang_type, owner=owner)

    def test_the_page_is_not_there(self, client, owner, gang):
        assert gang.credits_unlimited
        client.force_login(owner)

        assert client.get(url(gang)).status_code == 404
        assert (
            client.post(url(gang), {"direction": "add", "amount": "5"}).status_code
            == 404
        )

    def test_the_gang_page_offers_nothing(self, client, owner, gang):
        client.force_login(owner)
        response = client.get(reverse("n26-gang", args=[gang.pk]))

        assert url(gang).encode() not in response.content
        assert b"Manage credits" not in response.content


class TestTheArbitrator:
    """The arbitrator of the campaign a gang is playing may change its
    credits while the gang is in a campaign still being played."""

    def test_may_add_credits_and_returns_to_the_campaign(self, client, table, feature):
        client.force_login(table.arbitrator)
        response = client.post(url(table.gang), {"direction": "add", "amount": "10"})

        assert response.status_code == 302
        assert response.url == (
            reverse("n26-campaign", args=[table.campaign.pk]) + "#gangs"
        )
        assert fresh(table.gang).credits == 110
        event = LedgerEvent.objects.get(kind=LedgerEvent.Kind.CREDITS_ADJUSTED)
        assert event.actor == table.arbitrator
        assert_reconciled(fresh(table.gang))

    def test_needs_the_campaigns_flag(self, client, table):
        client.force_login(table.arbitrator)

        assert client.get(url(table.gang)).status_code == 404

    def test_loses_the_page_once_the_gang_leaves(self, client, table, feature):
        with operation(table.gang, actor=table.owner) as op:
            op.leave_campaign()
        client.force_login(table.arbitrator)

        assert client.get(url(table.gang)).status_code == 404

    def test_loses_the_page_once_the_campaign_is_archived(self, client, table, feature):
        table.campaign.archived = True
        table.campaign.save(update_fields=["archived"])
        client.force_login(table.arbitrator)

        assert client.get(url(table.gang)).status_code == 404
        assert (
            client.post(
                url(table.gang), {"direction": "add", "amount": "5"}
            ).status_code
            == 404
        )
        assert fresh(table.gang).credits == 100

    def test_the_campaign_table_links_each_gangs_credits(self, client, table, feature):
        client.force_login(table.arbitrator)
        response = client.get(reverse("n26-campaign", args=[table.campaign.pk]))

        page = BeautifulSoup(response.content, "html.parser")
        link = page.select_one(f'a[href="{url(table.gang)}"]')
        assert link is not None
        assert link.get_text(strip=True) == "100¢"


class TestEveryoneElse:
    """Nobody else reaches the page or sees a way in."""

    def test_a_stranger_gets_404(self, client, table, feature):
        client.force_login(User.objects.create_user("stranger"))

        assert client.get(url(table.gang)).status_code == 404
        assert (
            client.post(
                url(table.gang), {"direction": "add", "amount": "5"}
            ).status_code
            == 404
        )
        assert fresh(table.gang).credits == 100

    def test_signed_out_is_sent_to_sign_in(self, client, table):
        response = client.get(url(table.gang))

        assert response.status_code == 302
        assert "login" in response.url

    def test_a_stranger_sees_no_link_on_the_campaign_table(
        self, client, table, feature
    ):
        client.force_login(User.objects.create_user("stranger"))
        response = client.get(reverse("n26-campaign", args=[table.campaign.pk]))

        assert url(table.gang).encode() not in response.content
