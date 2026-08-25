"""The campaign screens, and the flag that decides who reaches them.

Here rather than beside the views because opening the flag means writing the
site's own row, and only these tests may reach across to the platform.
"""

import pytest
from django.contrib.auth.models import Group, User

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.models import Campaign
from n26.flags import CAMPAIGNS

pytestmark = pytest.mark.django_db

GROUP_NAME = "N26 Campaigns"


@pytest.fixture
def open_to_everyone():
    """The flag rows are seeded by a data migration, which does not run
    under --nomigrations."""
    return FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )


@pytest.fixture
def shut():
    return FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.OFF
    )


@pytest.fixture
def arbitrator(client):
    person = User.objects.create_user("arbitrator")
    client.force_login(person)
    return person


@pytest.fixture
def campaign(arbitrator):
    return Campaign.objects.create(name="Dust Falls", owner=arbitrator, budget=1000)


#: Every address this feature adds, so a new one cannot skip the gate below.
def addresses(campaign):
    return [
        "/n26/campaigns/",
        "/n26/campaigns/new/",
        f"/n26/campaigns/{campaign.pk}/",
        f"/n26/campaigns/{campaign.pk}/edit/",
        f"/n26/campaigns/{campaign.pk}/archive/",
    ]


class TestWhoReachesCampaignsAtAll:
    def test_a_shut_feature_answers_404_everywhere(self, client, campaign, shut):
        """Not 403, and not a redirect. Which features are being built is
        not something to be probed for."""
        for address in addresses(campaign):
            assert client.get(address).status_code == 404, address

    def test_no_flag_row_answers_404_everywhere(self, client, campaign):
        """Absent is not allowed. A feature whose row has not been created
        is shut."""
        for address in addresses(campaign):
            assert client.get(address).status_code == 404, address

    def test_an_open_feature_lets_the_arbitrator_in(
        self, client, campaign, open_to_everyone
    ):
        for address in addresses(campaign):
            assert client.get(address).status_code == 200, address

    def test_a_visitor_gets_404_rather_than_a_login_redirect(
        self, client, campaign, open_to_everyone
    ):
        """Being sent to sign in would itself say something is there."""
        client.logout()
        for address in addresses(campaign):
            assert client.get(address).status_code == 404, address

    def test_the_allowlist_decides_between_two_accounts(self, client, campaign):
        FeatureFlag.objects.create(
            slug=CAMPAIGNS,
            name="Campaigns",
            availability=Availability.ALLOWLIST,
            group=Group.objects.create(name=GROUP_NAME),
        )
        assert client.get("/n26/campaigns/").status_code == 404
        User.objects.get(username="arbitrator").groups.add(
            Group.objects.get(name=GROUP_NAME)
        )
        assert client.get("/n26/campaigns/").status_code == 200


class TestALongList:
    """A paged list without a pager hides everything past the first page,
    and nothing on the page says so."""

    def _many(self, arbitrator, count):
        from n26.core.views.campaigns import CAMPAIGNS_PER_PAGE

        return [
            Campaign.objects.create(name=f"Campaign {n:03}", owner=arbitrator)
            for n in range(count)
        ], CAMPAIGNS_PER_PAGE

    def test_a_short_list_draws_no_pager(self, client, arbitrator, open_to_everyone):
        Campaign.objects.create(name="Only One", owner=arbitrator)
        assert client.get("/n26/campaigns/").context["pages"] is None

    def test_a_long_list_can_be_turned(self, client, arbitrator, open_to_everyone):
        _, per_page = self._many(arbitrator, 30)

        first = client.get("/n26/campaigns/")
        assert len(first.context["page"].object_list) == per_page

        onward = first.context["pages"]["next"]
        assert onward, "no way off the first page"

        # Followed as a reader would, rather than by guessing the address.
        second = client.get(f"/n26/campaigns/{onward}")
        names = {row.name for row in second.context["page"].object_list}
        assert names, "the second page is empty"
        assert names.isdisjoint({row.name for row in first.context["page"].object_list})

    def test_the_pager_is_drawn_where_there_is_one(
        self, client, arbitrator, open_to_everyone
    ):
        """The context alone is not proof — the markup has to render it."""
        self._many(arbitrator, 30)
        assert "page=2" in client.get("/n26/campaigns/").content.decode()


class TestSettingOneUp:
    def test_it_creates_a_campaign_and_lands_on_its_page(
        self, client, arbitrator, open_to_everyone
    ):
        response = client.post(
            "/n26/campaigns/new/",
            {"name": "Dust Falls", "budget": "1000", "summary": ""},
        )
        made = Campaign.objects.get(name="Dust Falls")
        assert made.owner == arbitrator
        assert made.budget == 1000
        assert response.status_code == 302
        assert response["Location"] == f"/n26/campaigns/{made.pk}/"

    def test_a_blank_budget_means_no_ceiling_rather_than_zero(
        self, client, arbitrator, open_to_everyone
    ):
        """The one answer worth checking: blank is not a default and is not
        a zero, and a campaign that read it as zero would refuse everybody."""
        client.post("/n26/campaigns/new/", {"name": "Open House", "budget": ""})
        assert Campaign.objects.get(name="Open House").budget is None

    def test_a_nameless_campaign_is_refused(self, client, arbitrator, open_to_everyone):
        assert client.post("/n26/campaigns/new/", {"name": ""}).status_code == 200
        assert not Campaign.objects.exists()


class TestSomebodyElsesCampaign:
    """Owner-scoped, and answered with 404 rather than 403 — the same way
    every other page holding player data answers a stranger."""

    @pytest.fixture
    def theirs(self):
        return Campaign.objects.create(
            name="Not Yours", owner=User.objects.create_user("someone-else")
        )

    def test_it_is_not_readable(self, client, arbitrator, theirs, open_to_everyone):
        assert client.get(f"/n26/campaigns/{theirs.pk}/").status_code == 404

    def test_it_is_not_editable(self, client, arbitrator, theirs, open_to_everyone):
        response = client.post(
            f"/n26/campaigns/{theirs.pk}/edit/", {"name": "Mine Now", "budget": ""}
        )
        assert response.status_code == 404
        theirs.refresh_from_db()
        assert theirs.name == "Not Yours"

    def test_it_is_not_archivable(self, client, arbitrator, theirs, open_to_everyone):
        assert client.post(f"/n26/campaigns/{theirs.pk}/archive/").status_code == 404
        theirs.refresh_from_db()
        assert theirs.archived is False

    def test_it_is_not_listed(self, client, arbitrator, theirs, open_to_everyone):
        assert "Not Yours" not in client.get("/n26/campaigns/").content.decode()


class TestEditing:
    def test_it_saves_the_changed_facts(self, client, campaign, open_to_everyone):
        client.post(
            f"/n26/campaigns/{campaign.pk}/edit/",
            {"name": "Dust Falls Reborn", "budget": "1500", "summary": ""},
        )
        campaign.refresh_from_db()
        assert (campaign.name, campaign.budget) == ("Dust Falls Reborn", 1500)

    def test_clearing_the_budget_removes_the_ceiling(
        self, client, campaign, open_to_everyone
    ):
        client.post(
            f"/n26/campaigns/{campaign.pk}/edit/",
            {"name": campaign.name, "budget": ""},
        )
        campaign.refresh_from_db()
        assert campaign.budget is None


class TestArchiving:
    def test_the_question_page_changes_nothing(
        self, client, campaign, open_to_everyone
    ):
        assert client.get(f"/n26/campaigns/{campaign.pk}/archive/").status_code == 200
        campaign.refresh_from_db()
        assert campaign.archived is False

    def test_the_post_archives_rather_than_destroys(
        self, client, campaign, open_to_everyone
    ):
        """The row stays: what a campaign recorded is a true statement about
        what happened, whether or not it is still on show."""
        client.post(f"/n26/campaigns/{campaign.pk}/archive/")
        campaign.refresh_from_db()
        assert campaign.archived is True
        assert Campaign.objects.filter(pk=campaign.pk).exists()

    def test_a_deleted_campaign_stops_opening(self, client, campaign, open_to_everyone):
        client.post(f"/n26/campaigns/{campaign.pk}/archive/")
        assert client.get(f"/n26/campaigns/{campaign.pk}/").status_code == 404
