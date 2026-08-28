"""The campaign screens, and the flag that decides who reaches them.

Here rather than beside the views because opening the flag means writing the
site's own row, and only these tests may reach across to the platform.
"""

import pytest
from django.contrib.auth.models import Group, User

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.models import Battle, Campaign, CampaignEvent, CampaignMembership
from n26.core.views.campaigns import LOG_ON_THE_PAGE
from n26.flags import CAMPAIGNS
from n26.tests.sandbox.actions import found_gang

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


class TestTheDashboardTab:
    """The home page's Campaigns tab is a place only some readers have. It
    must not offer a way to an address that would answer them 404."""

    def test_a_reader_without_the_feature_sees_the_old_panel(
        self, client, arbitrator, shut
    ):
        Campaign.objects.create(name="Dust Falls", owner=arbitrator)
        body = client.get("/n26/").content.decode()

        assert "/n26/campaigns/new/" not in body
        assert "Dust Falls" not in body, "a campaign leaked into a shut tab"
        assert "working hard on it" in body

    def test_a_reader_with_it_gets_their_campaigns(
        self, client, arbitrator, open_to_everyone
    ):
        Campaign.objects.create(name="Dust Falls", owner=arbitrator)
        body = client.get("/n26/").content.decode()

        assert "Dust Falls" in body
        assert "/n26/campaigns/new/" in body

    def test_it_shows_only_the_readers_own(self, client, arbitrator, open_to_everyone):
        Campaign.objects.create(
            name="Not Yours", owner=User.objects.create_user("someone-else")
        )
        assert "Not Yours" not in client.get("/n26/").content.decode()


class TestSearchingTheList:
    """The same box the gangs list has, answered the same way."""

    def test_it_narrows_to_what_was_asked_for(
        self, client, arbitrator, open_to_everyone
    ):
        Campaign.objects.create(name="Dust Falls", owner=arbitrator)
        Campaign.objects.create(name="Sump City Nights", owner=arbitrator)

        body = client.get("/n26/campaigns/?q=dust").content.decode()

        assert "Dust Falls" in body
        assert "Sump City Nights" not in body

    def test_a_query_that_matches_nothing_says_so(
        self, client, arbitrator, open_to_everyone
    ):
        Campaign.objects.create(name="Dust Falls", owner=arbitrator)
        assert "No campaigns match that" in (
            client.get("/n26/campaigns/?q=zzzz").content.decode()
        )


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

    def test_the_form_opens_with_a_thousand_credit_budget(
        self, client, arbitrator, open_to_everyone
    ):
        response = client.get("/n26/campaigns/new/")
        assert response.context["form"]["budget"].value() == 1000
        body = response.content.decode()
        assert 'value="1000"' in body
        # The field still says what clearing it does, which is the one thing
        # a reader cannot see from a box that already holds a figure.
        assert "Blank sets none." in body

    def test_a_blank_budget_means_no_limit_rather_than_zero(
        self, client, arbitrator, open_to_everyone
    ):
        """Blank is not a zero, and a campaign that read it as zero would
        refuse everybody. Clearing the default is how a table that has
        not agreed a limit says so."""
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

    def test_clearing_the_budget_removes_the_limit(
        self, client, campaign, open_to_everyone
    ):
        client.post(
            f"/n26/campaigns/{campaign.pk}/edit/",
            {"name": campaign.name, "budget": ""},
        )
        campaign.refresh_from_db()
        assert campaign.budget is None

    def test_an_unlimited_campaign_stays_blank_on_the_edit_form(
        self, client, arbitrator, open_to_everyone
    ):
        """The 1000 default is for a campaign being set up. Filling it in
        on edit would make a campaign that had no limit look as if it did."""
        campaign = Campaign.objects.create(
            name="Open House", owner=arbitrator, budget=None
        )
        response = client.get(f"/n26/campaigns/{campaign.pk}/edit/")
        assert response.context["form"]["budget"].value() is None
        assert 'id="campaign-budget"' in response.content.decode()
        assert 'value="1000"' not in response.content.decode()

    def test_a_zero_budget_stays_zero_on_the_edit_form(
        self, client, arbitrator, open_to_everyone
    ):
        """Nought is a figure, not an absence: `default` would draw the
        box empty and a save would clear the limit."""
        campaign = Campaign.objects.create(
            name="Broke House", owner=arbitrator, budget=0
        )
        response = client.get(f"/n26/campaigns/{campaign.pk}/edit/")
        assert response.context["form"]["budget"].value() == 0
        assert 'value="0"' in response.content.decode()


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


class TestTheLogOnTheCampaignsPage:
    """What the arbitrator changed, read back off the page they changed it
    on. Rendered markup rather than a status code: a section that draws
    nothing still answers 200."""

    def page(self, client, campaign):
        return client.get(f"/n26/campaigns/{campaign.pk}/").content.decode()

    def test_a_fresh_campaign_says_its_log_is_empty(
        self, client, arbitrator, open_to_everyone
    ):
        made = Campaign.objects.create(name="Quiet Start", owner=arbitrator)
        drawn = self.page(client, made)
        assert "Log" in drawn
        assert "Nothing yet." in drawn

    def test_setting_one_up_writes_its_first_line(
        self, client, arbitrator, open_to_everyone
    ):
        client.post(
            "/n26/campaigns/new/",
            {"name": "Dust Falls", "budget": "1000", "summary": ""},
        )
        made = Campaign.objects.get(name="Dust Falls")
        assert [event.kind for event in made.events.all()] == [
            CampaignEvent.Kind.CREATED
        ]
        assert "set the campaign up" in self.page(client, made)

    def test_editing_writes_what_changed_and_the_page_says_it(
        self, client, campaign, open_to_everyone
    ):
        client.post(
            f"/n26/campaigns/{campaign.pk}/edit/",
            {"name": "Dust Falls II", "budget": "1200", "summary": ""},
        )
        drawn = self.page(client, campaign)
        assert "renamed the campaign Dust Falls to Dust Falls II" in drawn
        assert "set the gang budget to 1200¢" in drawn

    def test_saving_an_untouched_form_writes_nothing(
        self, client, campaign, open_to_everyone
    ):
        """A form submits every box it holds. Only what moved is an act."""
        client.post(
            f"/n26/campaigns/{campaign.pk}/edit/",
            {"name": campaign.name, "budget": "1000", "summary": campaign.summary},
        )
        assert not campaign.events.exists()

    def test_the_arbitrator_reads_their_own_acts_as_their_own(
        self, client, campaign, open_to_everyone
    ):
        client.post(
            f"/n26/campaigns/{campaign.pk}/edit/",
            {"name": "Dust Falls II", "budget": "1000", "summary": ""},
        )
        assert "You" in self.page(client, campaign)

    def test_only_the_most_recent_acts_are_drawn(
        self, client, campaign, open_to_everyone
    ):
        """The page is a campaign, not its history."""
        for number in range(1, 15):
            client.post(
                f"/n26/campaigns/{campaign.pk}/edit/",
                {"name": f"Dust Falls {number}", "budget": "1000", "summary": ""},
            )
        drawn = self.page(client, campaign)
        assert drawn.count("renamed the campaign") == LOG_ON_THE_PAGE
        assert "and 4 earlier acts" in drawn

    def test_the_newest_act_is_drawn_first(self, client, campaign, open_to_everyone):
        client.post(
            f"/n26/campaigns/{campaign.pk}/edit/",
            {"name": "Dust Falls II", "budget": "1000", "summary": ""},
        )
        client.post(
            f"/n26/campaigns/{campaign.pk}/edit/",
            {"name": "Dust Falls II", "budget": "1500", "summary": ""},
        )
        drawn = self.page(client, campaign)
        assert drawn.index("set the gang budget") < drawn.index("renamed the campaign")

    def test_archiving_is_recorded_even_though_the_page_shuts(
        self, client, campaign, open_to_everyone
    ):
        client.post(f"/n26/campaigns/{campaign.pk}/archive/")
        assert [event.kind for event in campaign.events.all()] == [
            CampaignEvent.Kind.ARCHIVED
        ]


class TestTheRollOfGangs:
    """Who is playing, added by the link a player sent."""

    @pytest.fixture
    def gang(self, gang_type):
        player = User.objects.create_user("player")
        return found_gang("The Ashen Choir", gang_type, owner=player)

    def page(self, client, campaign):
        return client.get(f"/n26/campaigns/{campaign.pk}/").content.decode()

    def test_a_campaign_with_nobody_in_it_says_so(
        self, client, campaign, open_to_everyone
    ):
        drawn = self.page(client, campaign)
        assert "Gangs" in drawn
        assert "No gangs yet." in drawn

    def test_a_gang_is_added_by_its_id(self, client, campaign, gang, open_to_everyone):
        response = client.post(
            f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": str(gang.pk)}
        )
        assert response.status_code == 302
        assert CampaignMembership.objects.filter(
            campaign=campaign, gang=gang, left__isnull=True
        ).exists()

    def test_a_gang_is_added_by_the_link_a_player_sent(
        self, client, campaign, gang, open_to_everyone
    ):
        """A pasted address names the same gang as a bare id — a reader who
        pasted their address bar should not have to tidy it."""
        client.post(
            f"/n26/campaigns/{campaign.pk}/gangs/add/",
            {"gang": f"http://example.test/n26/gangs/{gang.pk}/"},
        )
        assert CampaignMembership.objects.filter(campaign=campaign, gang=gang).exists()

    def test_the_roll_draws_the_gang(self, client, campaign, gang, open_to_everyone):
        client.post(f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": str(gang.pk)})
        assert "The Ashen Choir" in self.page(client, campaign)

    def test_the_log_says_the_gang_joined(
        self, client, campaign, gang, open_to_everyone
    ):
        client.post(f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": str(gang.pk)})
        assert "added the gang to Dust Falls" in self.page(client, campaign)

    def test_an_address_naming_nothing_is_refused_in_words(
        self, client, campaign, open_to_everyone
    ):
        response = client.post(
            f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": "not-a-gang"}
        )
        assert response.status_code == 200
        assert "No gang with that address" in response.content.decode()
        assert not CampaignMembership.objects.exists()

    def test_a_gang_already_playing_elsewhere_is_refused_in_words(
        self, client, campaign, gang, arbitrator, open_to_everyone
    ):
        elsewhere = Campaign.objects.create(name="Sump City", owner=arbitrator)
        client.post(f"/n26/campaigns/{elsewhere.pk}/gangs/add/", {"gang": str(gang.pk)})

        response = client.post(
            f"/n26/campaigns/{campaign.pk}/gangs/add/",
            {"gang": str(gang.pk)},
            follow=True,
        )
        assert "already playing Sump City" in response.content.decode()
        assert CampaignMembership.objects.filter(gang=gang).count() == 1

    def test_the_question_page_removes_nothing(
        self, client, campaign, gang, open_to_everyone
    ):
        client.post(f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": str(gang.pk)})
        address = f"/n26/campaigns/{campaign.pk}/gangs/{gang.pk}/remove/"
        assert client.get(address).status_code == 200
        assert CampaignMembership.objects.get(gang=gang).playing

    def test_the_post_takes_the_gang_out(
        self, client, campaign, gang, open_to_everyone
    ):
        client.post(f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": str(gang.pk)})
        client.post(f"/n26/campaigns/{campaign.pk}/gangs/{gang.pk}/remove/")

        membership = CampaignMembership.objects.get(gang=gang)
        assert not membership.playing
        drawn = self.page(client, campaign)
        assert "No gangs yet." in drawn
        assert "took the gang out of Dust Falls" in drawn

    def test_removing_a_gang_that_is_not_playing_answers_404(
        self, client, campaign, gang, open_to_everyone
    ):
        assert (
            client.post(
                f"/n26/campaigns/{campaign.pk}/gangs/{gang.pk}/remove/"
            ).status_code
            == 404
        )

    def test_somebody_elses_campaign_takes_no_gangs(
        self, client, gang, open_to_everyone
    ):
        theirs = Campaign.objects.create(
            name="Not Yours", owner=User.objects.create_user("someone-else")
        )
        assert (
            client.post(
                f"/n26/campaigns/{theirs.pk}/gangs/add/", {"gang": str(gang.pk)}
            ).status_code
            == 404
        )
        assert not CampaignMembership.objects.exists()

    def test_the_gang_routes_are_shut_when_the_feature_is(
        self, client, campaign, gang, shut
    ):
        for address in (
            f"/n26/campaigns/{campaign.pk}/gangs/add/",
            f"/n26/campaigns/{campaign.pk}/gangs/{gang.pk}/remove/",
        ):
            assert client.get(address).status_code == 404, address


class TestBattlesOnTheCampaignsPage:
    @pytest.fixture
    def gang(self, gang_type):
        player = User.objects.create_user("player")
        return found_gang("The Ashen Choir", gang_type, owner=player)

    def page(self, client, campaign):
        return client.get(f"/n26/campaigns/{campaign.pk}/").content.decode()

    def test_a_campaign_with_no_battles_says_so(
        self, client, campaign, open_to_everyone
    ):
        drawn = self.page(client, campaign)
        assert "Battles" in drawn
        assert "No battles yet." in drawn

    def test_recording_one_draws_it_and_logs_it(
        self, client, campaign, gang, open_to_everyone
    ):
        client.post(f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": str(gang.pk)})
        response = client.post(
            f"/n26/campaigns/{campaign.pk}/battles/new/",
            {"date": "2026-08-03", "gangs": [str(gang.pk)]},
        )
        assert response.status_code == 302

        drawn = self.page(client, campaign)
        assert "3 Aug 2026" in drawn
        assert "recorded a battle fought on 3 August" in drawn
        assert Battle.objects.get(campaign=campaign).gangs.count() == 1

    def test_a_battle_with_nobody_named_still_draws(
        self, client, campaign, open_to_everyone
    ):
        client.post(
            f"/n26/campaigns/{campaign.pk}/battles/new/", {"date": "2026-08-03"}
        )
        assert "Nobody named" in self.page(client, campaign)

    def test_only_this_campaigns_gangs_are_offered(
        self, client, campaign, gang, arbitrator, open_to_everyone
    ):
        """A picker over every gang there is would let an arbitrator record a
        battle between gangs that were never in the campaign."""
        elsewhere = Campaign.objects.create(name="Sump City", owner=arbitrator)
        client.post(f"/n26/campaigns/{elsewhere.pk}/gangs/add/", {"gang": str(gang.pk)})

        drawn = client.get(
            f"/n26/campaigns/{campaign.pk}/battles/new/"
        ).content.decode()
        # The gang's id rather than its name: a flash message from the last
        # request carries the name and would match wherever the picker stood.
        assert f'value="{gang.pk}"' not in drawn
        assert "No gangs in this campaign yet" in drawn

    def test_a_battle_needs_a_date(self, client, campaign, open_to_everyone):
        response = client.post(f"/n26/campaigns/{campaign.pk}/battles/new/", {})
        assert response.status_code == 200
        assert not Battle.objects.exists()

    def test_the_question_page_removes_nothing(
        self, client, campaign, open_to_everyone
    ):
        client.post(
            f"/n26/campaigns/{campaign.pk}/battles/new/", {"date": "2026-08-03"}
        )
        battle = Battle.objects.get()
        address = f"/n26/campaigns/{campaign.pk}/battles/{battle.pk}/remove/"
        assert client.get(address).status_code == 200
        assert Battle.objects.exists()

    def test_the_post_removes_it(self, client, campaign, open_to_everyone):
        client.post(
            f"/n26/campaigns/{campaign.pk}/battles/new/", {"date": "2026-08-03"}
        )
        battle = Battle.objects.get()
        client.post(f"/n26/campaigns/{campaign.pk}/battles/{battle.pk}/remove/")

        assert not Battle.objects.exists()
        drawn = self.page(client, campaign)
        assert "No battles yet." in drawn
        assert "removed the battle of 2026-08-03" in drawn

    def test_another_campaigns_battle_is_not_reachable(
        self, client, campaign, arbitrator, open_to_everyone
    ):
        elsewhere = Campaign.objects.create(name="Sump City", owner=arbitrator)
        client.post(
            f"/n26/campaigns/{elsewhere.pk}/battles/new/", {"date": "2026-08-03"}
        )
        battle = Battle.objects.get()
        assert (
            client.get(
                f"/n26/campaigns/{campaign.pk}/battles/{battle.pk}/remove/"
            ).status_code
            == 404
        )

    def test_the_battle_routes_are_shut_when_the_feature_is(
        self, client, campaign, shut
    ):
        assert (
            client.get(f"/n26/campaigns/{campaign.pk}/battles/new/").status_code == 404
        )


class TestTheCampaignInTheBar:
    """Every screen belonging to one campaign names it in the app header, as
    a link, with the switcher beside it — the same as a gang's screens. Read
    off the rendered markup, because a component that draws nothing still
    answers 200."""

    @pytest.fixture
    def gang(self, gang_type):
        player = User.objects.create_user("player")
        return found_gang("The Ashen Choir", gang_type, owner=player)

    def screens(self, campaign, gang, battle):
        return [
            f"/n26/campaigns/{campaign.pk}/",
            f"/n26/campaigns/{campaign.pk}/edit/",
            f"/n26/campaigns/{campaign.pk}/archive/",
            f"/n26/campaigns/{campaign.pk}/gangs/add/",
            f"/n26/campaigns/{campaign.pk}/gangs/{gang.pk}/remove/",
            f"/n26/campaigns/{campaign.pk}/battles/new/",
            f"/n26/campaigns/{campaign.pk}/battles/{battle.pk}/remove/",
        ]

    def test_every_screen_carries_it(
        self, client, campaign, gang, arbitrator, open_to_everyone
    ):
        client.post(f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": str(gang.pk)})
        client.post(
            f"/n26/campaigns/{campaign.pk}/battles/new/", {"date": "2026-08-03"}
        )
        battle = Battle.objects.get()

        for address in self.screens(campaign, gang, battle):
            drawn = client.get(address).content.decode()
            # The switcher's own menu label: the list page has a search
            # box with the same placeholder, so that would not tell them apart.
            assert "Switch to another campaign" in drawn, address
            assert f'href="/n26/campaigns/{campaign.pk}/"' in drawn, address

    def test_it_offers_the_readers_other_campaigns(
        self, client, campaign, arbitrator, open_to_everyone
    ):
        Campaign.objects.create(name="Sump City", owner=arbitrator)
        drawn = client.get(f"/n26/campaigns/{campaign.pk}/").content.decode()
        assert "Sump City" in drawn

    def test_the_list_and_the_setup_screen_keep_the_places_switcher(
        self, client, arbitrator, open_to_everyone
    ):
        """Neither is one campaign, so neither names one in the bar."""
        for address in ("/n26/campaigns/", "/n26/campaigns/new/"):
            drawn = client.get(address).content.decode()
            assert "Switch to another campaign" not in drawn, address
