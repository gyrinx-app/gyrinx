"""The campaign screens, and the flag that decides who reaches them.

Here rather than beside the views because opening the flag means writing the
site's own row, and only these tests may reach across to the platform.
"""

from importlib import import_module

import pytest
from django.contrib.auth.models import Group, User

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.models import (
    Battle,
    Campaign,
    CampaignEvent,
    CampaignMembership,
    CampaignParticipant,
)
from n26.core.views.campaigns import LOG_ON_THE_PAGE
from n26.flags import CAMPAIGNS
from n26.library.authoring import create_wargear
from n26.tests.sandbox.actions import assign, found_campaign, found_gang, hire

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
def campaign(arbitrator, campaign_type):
    return found_campaign("Dust Falls", campaign_type, owner=arbitrator, budget=1000)


def founding(campaign_type, **fields):
    """A set-up form's POST, on the given type."""
    return {
        "name": "Dust Falls",
        "budget": "1000",
        "summary": "",
        "campaign_type": str(campaign_type.pk),
        **fields,
    }


def seat(campaign, user):
    """Put somebody at the campaign's table.

    The add-a-gang screen offers the gangs of people who have accepted a
    place, so a test wanting a gang addable has to seat its owner first.
    """
    from n26.core.campaigns import campaign_operation

    with campaign_operation(campaign, actor=campaign.owner) as act:
        act.invite(user)
    with campaign_operation(campaign, actor=user) as act:
        act.answer_invitation(user, accepted=True)


#: Every address this feature adds that opens on an empty campaign, so a new
#: one cannot skip the gate below. The screens for taking something out need
#: a row to name, and are gated in their own tests.
def addresses(campaign):
    return [
        "/n26/campaigns/",
        "/n26/campaigns/new/",
        f"/n26/campaigns/{campaign.pk}/",
        f"/n26/campaigns/{campaign.pk}/edit/",
        f"/n26/campaigns/{campaign.pk}/archive/",
        f"/n26/campaigns/{campaign.pk}/gangs/add/",
        f"/n26/campaigns/{campaign.pk}/participants/add/",
        f"/n26/campaigns/{campaign.pk}/battles/new/",
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
        self, client, arbitrator, campaign_type, shut
    ):
        found_campaign("Dust Falls", campaign_type, owner=arbitrator)
        body = client.get("/n26/").content.decode()

        assert "/n26/campaigns/new/" not in body
        assert "Dust Falls" not in body, "a campaign leaked into a shut tab"
        assert "working hard on it" in body

    def test_a_reader_with_it_gets_their_campaigns(
        self, client, arbitrator, campaign_type, open_to_everyone
    ):
        found_campaign("Dust Falls", campaign_type, owner=arbitrator)
        body = client.get("/n26/").content.decode()

        assert "Dust Falls" in body
        assert "/n26/campaigns/new/" in body

    def test_it_leaves_out_a_campaign_the_reader_has_no_place_in(
        self, client, arbitrator, campaign_type, open_to_everyone
    ):
        found_campaign(
            "Not Yours", campaign_type, owner=User.objects.create_user("someone-else")
        )
        assert "Not Yours" not in client.get("/n26/").content.decode()


class TestSearchingTheList:
    """The same box the gangs list has, answered the same way."""

    def test_it_narrows_to_what_was_asked_for(
        self, client, arbitrator, campaign_type, open_to_everyone
    ):
        found_campaign("Dust Falls", campaign_type, owner=arbitrator)
        found_campaign("Sump City Nights", campaign_type, owner=arbitrator)

        body = client.get("/n26/campaigns/?q=dust").content.decode()

        assert "Dust Falls" in body
        assert "Sump City Nights" not in body

    def test_a_query_that_matches_nothing_says_so(
        self, client, arbitrator, campaign_type, open_to_everyone
    ):
        found_campaign("Dust Falls", campaign_type, owner=arbitrator)
        assert "No campaigns match that" in (
            client.get("/n26/campaigns/?q=zzzz").content.decode()
        )


class TestALongList:
    """A paged list without a pager hides everything past the first page,
    and nothing on the page says so."""

    @pytest.fixture(autouse=True)
    def _type(self, campaign_type):
        self.campaign_type = campaign_type

    def _many(self, arbitrator, count):
        from n26.core.views.campaigns import CAMPAIGNS_PER_PAGE

        return [
            found_campaign(f"Campaign {n:03}", self.campaign_type, owner=arbitrator)
            for n in range(count)
        ], CAMPAIGNS_PER_PAGE

    def test_a_short_list_draws_no_pager(self, client, arbitrator, open_to_everyone):
        found_campaign("Only One", self.campaign_type, owner=arbitrator)
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
        self, client, arbitrator, campaign_type, open_to_everyone
    ):
        response = client.post("/n26/campaigns/new/", founding(campaign_type))
        made = Campaign.objects.get(name="Dust Falls")
        assert made.owner == arbitrator
        assert made.budget == 1000
        assert made.campaign_type == campaign_type
        assert response.status_code == 302
        assert response["Location"] == f"/n26/campaigns/{made.pk}/"

    def test_founding_gives_it_a_pack_and_an_additions_type(
        self, client, arbitrator, campaign_type, open_to_everyone
    ):
        """The pack is the arbitrator's own and the additions type sits
        in it, empty, named for the campaign."""
        client.post("/n26/campaigns/new/", founding(campaign_type))
        made = Campaign.objects.get(name="Dust Falls")
        assert made.pack.owner == arbitrator
        assert made.additions.pack == made.pack
        assert made.additions.name == "Dust Falls"
        assert made.additions.built_ins is None

    def test_the_form_offers_the_types_a_campaign_can_be_founded_on(
        self, client, arbitrator, campaign_type, campaign, open_to_everyone
    ):
        """The system pack's types, and never a campaign's own additions,
        which live in a pack somebody owns."""
        body = client.get("/n26/campaigns/new/").content.decode()
        assert f'value="{campaign_type.pk}"' in body
        assert f'value="{campaign.additions.pk}"' not in body

    def test_each_card_says_what_founding_on_the_type_gives(
        self, client, arbitrator, default_pack, open_to_everyone
    ):
        """The picker reads as choosing a rulebook: the type's description,
        how each kind of asset behaves, and what every gang starts with."""
        from django.apps import apps

        from n26.library.core_campaign import seed_core_campaign

        seed_core_campaign(apps)

        body = client.get("/n26/campaigns/new/").content.decode()
        assert "Territory campaign" in body
        assert "gangs fight for control of Territory" in body
        assert "Every gang gets one Settlement and keeps it." in body
        assert "Territories change hands." in body
        assert "Every gang starts with Reputation at 0 and one Settlement." in body

    def test_a_campaign_wide_rule_is_drawn_on_the_card(
        self, client, arbitrator, campaign_type, open_to_everyone
    ):
        """A modifier on the type reaches every member gang, so the card
        says what it does in the words the authoring pages use. A type
        with nothing built in says nothing about what a gang starts with."""
        from n26.library.authoring import (
            create_rule,
            ef_adds,
            modifier,
            targets_gang,
        )

        modifier(
            "Everyone is wanted",
            targets_gang(),
            ef_adds(create_rule("Wanted")),
            attach_to=campaign_type,
        )

        body = client.get("/n26/campaigns/new/").content.decode()
        assert "Wanted" in body
        assert "Every gang starts with" not in body

    def test_a_campaign_without_a_type_is_refused(
        self, client, arbitrator, campaign_type, open_to_everyone
    ):
        response = client.post(
            "/n26/campaigns/new/", {**founding(campaign_type), "campaign_type": ""}
        )
        assert response.status_code == 200
        assert "Select a campaign type." in response.content.decode()
        assert not Campaign.objects.exists()

    def test_the_page_names_the_type(self, client, campaign, open_to_everyone):
        body = client.get(f"/n26/campaigns/{campaign.pk}/").content.decode()
        assert "Campaign type" in body
        assert "Territory campaign" in body

    def test_the_form_opens_with_a_thousand_credit_budget(
        self, client, arbitrator, open_to_everyone
    ):
        response = client.get("/n26/campaigns/new/")
        assert response.context["form"]["budget"].value() == 1000
        body = response.content.decode()
        assert 'value="1000"' in body
        # The field still says what clearing it does, which is the one thing
        # a reader cannot see from a box that already holds a figure.
        assert "Leave blank to set no budget." in body

    def test_a_blank_budget_means_no_limit_rather_than_zero(
        self, client, arbitrator, campaign_type, open_to_everyone
    ):
        """Blank is not a zero, and a campaign that read it as zero would
        refuse everybody. Clearing the default is how a table that has
        not agreed a limit says so."""
        client.post(
            "/n26/campaigns/new/",
            founding(campaign_type, name="Open House", budget=""),
        )
        assert Campaign.objects.get(name="Open House").budget is None

    def test_a_nameless_campaign_is_refused(
        self, client, arbitrator, campaign_type, open_to_everyone
    ):
        response = client.post("/n26/campaigns/new/", founding(campaign_type, name=""))
        assert response.status_code == 200
        assert not Campaign.objects.exists()


class TestSomebodyElsesCampaign:
    """The page reads for anybody holding the address; the screens that
    change it are the arbitrator's, and answer a stranger with 404 rather
    than 403 — the same way every other page holding player data does."""

    @pytest.fixture
    def theirs(self, campaign_type):
        return found_campaign(
            "Not Yours", campaign_type, owner=User.objects.create_user("someone-else")
        )

    def test_it_is_readable(self, client, arbitrator, theirs, open_to_everyone):
        response = client.get(f"/n26/campaigns/{theirs.pk}/")
        assert response.status_code == 200
        assert "Not Yours" in response.content.decode()

    def test_it_offers_no_controls(self, client, arbitrator, theirs, open_to_everyone):
        """Not a disabled button but nothing at all, so every address that
        would refuse this reader is absent from what they are given."""
        drawn = client.get(f"/n26/campaigns/{theirs.pk}/").content.decode()
        for address in (
            f"/n26/campaigns/{theirs.pk}/edit/",
            f"/n26/campaigns/{theirs.pk}/archive/",
            f"/n26/campaigns/{theirs.pk}/participants/add/",
            f"/n26/campaigns/{theirs.pk}/gangs/add/",
            f"/n26/campaigns/{theirs.pk}/battles/new/",
        ):
            assert address not in drawn

    def test_an_archived_one_is_gone(
        self, client, arbitrator, theirs, open_to_everyone
    ):
        """A link does not keep alive what its arbitrator has put away."""
        theirs.archived = True
        theirs.save()
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
        """Readable at its own address, but not one of the reader's own."""
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
        self, client, arbitrator, campaign_type, open_to_everyone
    ):
        """The 1000 default is for a campaign being set up. Filling it in
        on edit would make a campaign that had no limit look as if it did."""
        campaign = found_campaign(
            "Open House", campaign_type, owner=arbitrator, budget=None
        )
        response = client.get(f"/n26/campaigns/{campaign.pk}/edit/")
        assert response.context["form"]["budget"].value() is None
        assert 'id="campaign-budget"' in response.content.decode()
        assert 'value="1000"' not in response.content.decode()

    def test_a_zero_budget_stays_zero_on_the_edit_form(
        self, client, arbitrator, campaign_type, open_to_everyone
    ):
        """Nought is a figure, not an absence: `default` would draw the
        box empty and a save would clear the limit."""
        campaign = found_campaign(
            "Broke House", campaign_type, owner=arbitrator, budget=0
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

    def test_a_fresh_campaign_opens_with_its_founding_line(
        self, client, arbitrator, campaign_type, open_to_everyone
    ):
        """No campaign has an empty log: founding writes the first line,
        and it names the type the campaign runs on."""
        made = found_campaign("Quiet Start", campaign_type, owner=arbitrator)
        drawn = self.page(client, made)
        assert "Log" in drawn
        assert "set the campaign up on Territory campaign" in drawn
        assert "Nothing yet." not in drawn

    def test_setting_one_up_writes_its_first_line(
        self, client, arbitrator, campaign_type, open_to_everyone
    ):
        client.post("/n26/campaigns/new/", founding(campaign_type))
        made = Campaign.objects.get(name="Dust Falls")
        assert [event.kind for event in made.events.all()] == [
            CampaignEvent.Kind.CREATED
        ]
        assert "set the campaign up on Territory campaign" in self.page(client, made)

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
        assert [event.kind for event in campaign.events.all()] == [
            CampaignEvent.Kind.CREATED
        ]

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
        # Fourteen renames and the founding line, ten of them drawn.
        assert "and 5 earlier acts" in drawn

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

    def test_log_timestamps_follow_the_reader_timezone(
        self, client, arbitrator, campaign, open_to_everyone
    ):
        """A 06:27 UTC act reads as 02:27 in Eastern Daylight Time."""
        from datetime import UTC, datetime

        from gyrinx.accounts.models import UserProfile

        UserProfile.objects.create(user=arbitrator, timezone="America/New_York")
        client.post(
            f"/n26/campaigns/{campaign.pk}/edit/",
            {"name": "Dust Falls II", "budget": "1000", "summary": ""},
        )
        CampaignEvent.objects.filter(campaign=campaign).update(
            created=datetime(2026, 8, 29, 6, 27, tzinfo=UTC)
        )
        drawn = self.page(client, campaign)
        assert "29 Aug 02:27" in drawn
        assert "29 Aug 06:27" not in drawn

    def test_archiving_is_recorded_even_though_the_page_shuts(
        self, client, campaign, open_to_everyone
    ):
        client.post(f"/n26/campaigns/{campaign.pk}/archive/")
        assert [event.kind for event in campaign.events.all()] == [
            CampaignEvent.Kind.CREATED,
            CampaignEvent.Kind.ARCHIVED,
        ]


class TestTheFullLog:
    """The campaign's page draws only its newest acts; the log page draws
    them all, newest first, a screenful at a time, for whoever the
    campaign's page opens for."""

    def rename(self, client, campaign, times):
        for number in range(1, times + 1):
            client.post(
                f"/n26/campaigns/{campaign.pk}/edit/",
                {"name": f"Dust Falls {number}", "budget": "1000", "summary": ""},
            )

    def test_every_act_is_drawn(self, client, campaign, open_to_everyone):
        self.rename(client, campaign, 14)
        drawn = client.get(f"/n26/campaigns/{campaign.pk}/log/").content.decode()
        assert drawn.count("renamed the campaign") == 14
        assert "set the campaign up on Territory campaign" in drawn
        assert "earlier act" not in drawn

    def test_the_newest_act_is_drawn_first(self, client, campaign, open_to_everyone):
        self.rename(client, campaign, 1)
        drawn = client.get(f"/n26/campaigns/{campaign.pk}/log/").content.decode()
        assert drawn.index("renamed the campaign") < drawn.index("set the campaign up")

    def test_a_long_log_is_paged(self, client, campaign, open_to_everyone, monkeypatch):
        """Every other parameter rides along, and the last page ends with
        the founding line."""
        # By module rather than by dotted path: the views package exports
        # a ``campaigns`` view under the submodule's own name.
        monkeypatch.setattr(
            import_module("n26.core.views.campaigns"), "LOG_PER_PAGE", 5
        )
        self.rename(client, campaign, 14)
        first = client.get(f"/n26/campaigns/{campaign.pk}/log/").content.decode()
        assert first.count("renamed the campaign") == 5
        assert "Page 1 of 3" in first
        assert "15 entries" in first
        last = client.get(f"/n26/campaigns/{campaign.pk}/log/?page=3").content.decode()
        assert "set the campaign up on Territory campaign" in last

    def test_it_opens_for_a_reader_who_does_not_arbitrate(
        self, client, campaign, open_to_everyone
    ):
        client.force_login(User.objects.create_user("reader"))
        assert client.get(f"/n26/campaigns/{campaign.pk}/log/").status_code == 200

    def test_it_is_shut_with_the_feature(self, client, campaign, shut):
        assert client.get(f"/n26/campaigns/{campaign.pk}/log/").status_code == 404


class TestTheRollOfGangs:
    """Who is playing, added from the gangs at the campaign's table."""

    @pytest.fixture
    def gang(self, gang_type, campaign):
        player = User.objects.create_user("player")
        seat(campaign, player)
        return found_gang("The Ashen Choir", gang_type, owner=player)

    def page(self, client, campaign):
        return client.get(f"/n26/campaigns/{campaign.pk}/").content.decode()

    def test_a_campaign_with_nobody_in_it_says_so(
        self, client, campaign, open_to_everyone
    ):
        drawn = self.page(client, campaign)
        assert "Gangs" in drawn
        assert "No gangs yet." in drawn

    def test_a_gang_is_added_by_its_key(self, client, campaign, gang, open_to_everyone):
        response = client.post(
            f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": str(gang.pk)}
        )
        assert response.status_code == 302
        assert CampaignMembership.objects.filter(
            campaign=campaign, gang=gang, left__isnull=True
        ).exists()

    def test_the_roll_draws_the_gang(self, client, campaign, gang, open_to_everyone):
        client.post(f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": str(gang.pk)})
        assert "The Ashen Choir" in self.page(client, campaign)

    def test_the_log_says_the_gang_joined(
        self, client, campaign, gang, open_to_everyone
    ):
        client.post(f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": str(gang.pk)})
        assert "added the gang to Dust Falls" in self.page(client, campaign)

    def test_a_key_naming_nothing_is_refused(self, client, campaign, open_to_everyone):
        response = client.post(
            f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": "not-a-gang"}
        )
        assert response.status_code == 200
        assert not CampaignMembership.objects.exists()

    def test_a_gang_belonging_to_nobody_at_the_table_is_refused(
        self, client, campaign, gang_type, open_to_everyone
    ):
        """The screen offers the gangs of people who have accepted a place,
        and the POST takes only what the screen would offer."""
        outsider = found_gang(
            "Not Invited", gang_type, owner=User.objects.create_user("outsider")
        )
        response = client.post(
            f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": str(outsider.pk)}
        )
        assert response.status_code == 200
        assert not CampaignMembership.objects.filter(gang=outsider).exists()

    def test_a_gang_already_playing_elsewhere_is_refused_in_words(
        self, client, campaign, gang, arbitrator, campaign_type, open_to_everyone
    ):
        elsewhere = found_campaign("Sump City", campaign_type, owner=arbitrator)
        # Seated there too: what is under test is the second join being
        # refused, not who the other campaign would have offered.
        seat(elsewhere, gang.owner)
        client.post(f"/n26/campaigns/{elsewhere.pk}/gangs/add/", {"gang": str(gang.pk)})

        response = client.post(
            f"/n26/campaigns/{campaign.pk}/gangs/add/",
            {"gang": str(gang.pk)},
            follow=True,
        )
        assert "already playing Sump City" in response.content.decode()
        assert CampaignMembership.objects.filter(gang=gang).count() == 1

    def test_joining_gives_the_gang_the_campaigns_types(
        self, client, campaign, gang, open_to_everyone
    ):
        """Both carriers, gang-hosted and granted, pointed at by the
        membership so what the campaign gave can be found again."""
        client.post(f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": str(gang.pk)})
        membership = CampaignMembership.objects.get(gang=gang)
        assert membership.type_carrier.assignable == campaign.campaign_type
        assert membership.additions_carrier.assignable == campaign.additions
        assert membership.type_carrier.gang == gang

    def test_the_page_offers_no_way_to_take_a_gang_out(
        self, client, campaign, gang, open_to_everyone
    ):
        """A gang that left would keep what the campaign gave it, so until
        leaving returns everything the control is not drawn."""
        client.post(f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": str(gang.pk)})
        assert f"/gangs/{gang.pk}/remove/" not in self.page(client, campaign)

    def test_the_remove_address_refuses_in_words_and_changes_nothing(
        self, client, campaign, gang, open_to_everyone
    ):
        client.post(f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": str(gang.pk)})
        address = f"/n26/campaigns/{campaign.pk}/gangs/{gang.pk}/remove/"
        for send in (client.get, client.post):
            response = send(address, follow=True)
            assert "cannot leave Dust Falls" in response.content.decode()
            assert CampaignMembership.objects.get(gang=gang).playing

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
        self, client, gang, campaign_type, open_to_everyone
    ):
        theirs = found_campaign(
            "Not Yours", campaign_type, owner=User.objects.create_user("someone-else")
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
    def gang(self, gang_type, campaign):
        player = User.objects.create_user("player")
        seat(campaign, player)
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
        self, client, campaign, gang, arbitrator, campaign_type, open_to_everyone
    ):
        """A picker over every gang there is would let an arbitrator record a
        battle between gangs that were never in the campaign."""
        elsewhere = found_campaign("Sump City", campaign_type, owner=arbitrator)
        # Seating the owner is only how the gang gets into the other
        # campaign; what is under test is which gangs the battle picker
        # offers afterwards.
        seat(elsewhere, gang.owner)
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
        self, client, campaign, arbitrator, campaign_type, open_to_everyone
    ):
        elsewhere = found_campaign("Sump City", campaign_type, owner=arbitrator)
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
    def gang(self, gang_type, campaign):
        player = User.objects.create_user("player")
        seat(campaign, player)
        return found_gang("The Ashen Choir", gang_type, owner=player)

    def screens(self, campaign, gang, battle):
        return [
            f"/n26/campaigns/{campaign.pk}/",
            f"/n26/campaigns/{campaign.pk}/edit/",
            f"/n26/campaigns/{campaign.pk}/archive/",
            f"/n26/campaigns/{campaign.pk}/gangs/add/",
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
        self, client, campaign, arbitrator, campaign_type, open_to_everyone
    ):
        found_campaign("Sump City", campaign_type, owner=arbitrator)
        drawn = client.get(f"/n26/campaigns/{campaign.pk}/").content.decode()
        assert "Sump City" in drawn

    def test_the_list_and_the_setup_screen_keep_the_places_switcher(
        self, client, arbitrator, open_to_everyone
    ):
        """Neither is one campaign, so neither names one in the bar."""
        for address in ("/n26/campaigns/", "/n26/campaigns/new/"):
            drawn = client.get(address).content.decode()
            assert "Switch to another campaign" not in drawn, address


class TestInvitingSomebody:
    @pytest.fixture
    def player(self):
        return User.objects.create_user("vex_ordo")

    def add_page(self, campaign, query=""):
        address = f"/n26/campaigns/{campaign.pk}/participants/add/"
        return f"{address}?q={query}" if query else address

    def test_the_search_finds_by_part_of_a_name(
        self, client, campaign, player, open_to_everyone
    ):
        drawn = client.get(self.add_page(campaign, "vex")).content.decode()
        assert "vex_ordo" in drawn

    def test_an_empty_search_offers_nobody(
        self, client, campaign, player, open_to_everyone
    ):
        """A page that listed every account by default would be a directory."""
        drawn = client.get(self.add_page(campaign)).content.decode()
        assert "vex_ordo" not in drawn
        assert "Type a username to search" in drawn

    def test_the_arbitrator_is_not_offered_themselves(
        self, client, campaign, arbitrator, open_to_everyone
    ):
        drawn = client.get(self.add_page(campaign, "arbitrator")).content.decode()
        assert "No users match that name" in drawn

    def test_the_message_box_opens_from_the_address(
        self, client, campaign, player, open_to_everyone
    ):
        drawn = client.get(
            f"{self.add_page(campaign, 'vex')}&invite={player.pk}"
        ).content.decode()
        assert "Invite vex_ordo" in drawn
        assert f'value="{player.pk}"' in drawn

    def test_inviting_records_it_and_says_so(
        self, client, campaign, player, arbitrator, open_to_everyone
    ):
        response = client.post(
            self.add_page(campaign),
            {"user": str(player.pk), "message": "Sunday."},
        )
        assert response.status_code == 302
        invitation = CampaignParticipant.objects.get()
        assert invitation.user == player
        assert invitation.message == "Sunday."
        assert (
            "invited vex_ordo"
            in client.get(f"/n26/campaigns/{campaign.pk}/").content.decode()
        )

    def test_somebody_already_asked_is_not_offered_again(
        self, client, campaign, player, open_to_everyone
    ):
        client.post(self.add_page(campaign), {"user": str(player.pk)})
        drawn = client.get(self.add_page(campaign, "vex")).content.decode()
        assert "Already asked" in drawn

    def test_an_account_that_has_gone_is_refused_in_words(
        self, client, campaign, open_to_everyone
    ):
        response = client.post(self.add_page(campaign), {"user": "999999"}, follow=True)
        assert "no longer exists" in response.content.decode()
        assert not CampaignParticipant.objects.exists()

    def test_somebody_elses_campaign_takes_no_participants(
        self, client, player, campaign_type, open_to_everyone
    ):
        theirs = found_campaign(
            "Not Yours", campaign_type, owner=User.objects.create_user("someone-else")
        )
        assert client.get(self.add_page(theirs)).status_code == 404
        assert (
            client.post(self.add_page(theirs), {"user": str(player.pk)}).status_code
            == 404
        )

    def test_the_routes_are_shut_when_the_feature_is(self, client, campaign, shut):
        assert client.get(self.add_page(campaign)).status_code == 404


class TestAnsweringAnInvitation:
    @pytest.fixture
    def theirs(self, arbitrator, campaign_type):
        """A campaign somebody else runs, so the reader is the one asked."""
        from n26.core.campaigns import campaign_operation

        owner = User.objects.create_user("kesh")
        campaign = found_campaign("Sump Wars", campaign_type, owner=owner)
        with campaign_operation(campaign, actor=owner) as act:
            act.invite(arbitrator, message="You in?")
        return campaign

    def test_it_shows_on_the_campaigns_list(self, client, theirs, open_to_everyone):
        drawn = client.get("/n26/campaigns/").content.decode()
        assert "Sump Wars" in drawn
        assert "You in?" in drawn

    def test_the_home_page_knows_an_invitation_is_waiting(
        self, client, theirs, open_to_everyone
    ):
        """The mark itself is drawn by the tab strip, which Alpine builds in
        the browser from a registered string — so what is checked here is the
        view's answer, which is the part that can quietly stop being right."""
        response = client.get("/n26/")
        assert response.context["waiting_invitations"] == 1
        assert "Sump Wars" in response.content.decode()

    def test_accepting_joins_and_stops_the_page_asking(
        self, client, theirs, arbitrator, open_to_everyone
    ):
        client.post(
            f"/n26/campaigns/{theirs.pk}/invitation/",
            {"answer": "accept", "next": "/n26/campaigns/"},
        )
        assert CampaignParticipant.objects.get(user=arbitrator).state == (
            CampaignParticipant.State.ACCEPTED
        )
        assert client.get("/n26/").context["waiting_invitations"] == 0

    def test_declining_is_recorded(self, client, theirs, arbitrator, open_to_everyone):
        client.post(f"/n26/campaigns/{theirs.pk}/invitation/", {"answer": "decline"})
        assert CampaignParticipant.objects.get(user=arbitrator).state == (
            CampaignParticipant.State.DECLINED
        )

    def test_answering_lands_back_where_the_reader_was(
        self, client, theirs, open_to_everyone
    ):
        response = client.post(
            f"/n26/campaigns/{theirs.pk}/invitation/",
            {"answer": "accept", "next": "/n26/"},
        )
        assert response["Location"] == "/n26/"

    def test_it_will_not_be_sent_somewhere_else(self, client, theirs, open_to_everyone):
        """The address to return to arrives in a form, so it is checked."""
        response = client.post(
            f"/n26/campaigns/{theirs.pk}/invitation/",
            {"answer": "accept", "next": "https://example.test/"},
        )
        assert response["Location"] == "/n26/campaigns/"

    def test_somebody_never_asked_gets_404(
        self, client, arbitrator, campaign_type, open_to_everyone
    ):
        uninvited = found_campaign(
            "Elsewhere", campaign_type, owner=User.objects.create_user("stranger")
        )
        assert (
            client.post(
                f"/n26/campaigns/{uninvited.pk}/invitation/", {"answer": "accept"}
            ).status_code
            == 404
        )


class TestWhatAParticipantSees:
    """Accepting puts the campaign among the reader's own, because the
    invitation it arrived on is answered and gone: without this a player
    who said yes has nothing left pointing at the campaign."""

    @pytest.fixture
    def theirs(self, arbitrator, campaign_type):
        from n26.core.campaigns import campaign_operation

        owner = User.objects.create_user("kesh")
        campaign = found_campaign("Sump Wars", campaign_type, owner=owner)
        with campaign_operation(campaign, actor=owner) as act:
            act.invite(arbitrator)
        return campaign

    def accept(self, client, campaign):
        client.post(f"/n26/campaigns/{campaign.pk}/invitation/", {"answer": "accept"})

    def test_the_list_holds_it_once_accepted(self, client, theirs, open_to_everyone):
        self.accept(client, theirs)
        response = client.get("/n26/campaigns/")
        assert [row.pk for row in response.context["campaigns"]] == [theirs.pk]

    def test_the_home_page_holds_it_too(self, client, theirs, open_to_everyone):
        self.accept(client, theirs)
        response = client.get("/n26/")
        assert [row.pk for row in response.context["campaigns"]] == [theirs.pk]

    def test_the_row_names_who_runs_it_and_offers_nothing(
        self, client, theirs, open_to_everyone
    ):
        self.accept(client, theirs)
        drawn = client.get("/n26/campaigns/").content.decode()
        assert "arbitrated by kesh" in drawn
        assert f"/n26/campaigns/{theirs.pk}/edit/" not in drawn

    def test_a_question_still_waiting_is_not_one_of_their_campaigns(
        self, client, theirs, open_to_everyone
    ):
        """It is drawn on the page as an invitation, which is a different
        thing from being in the campaign."""
        assert list(client.get("/n26/campaigns/").context["campaigns"]) == []

    def test_declining_leaves_it_out(self, client, theirs, open_to_everyone):
        client.post(f"/n26/campaigns/{theirs.pk}/invitation/", {"answer": "decline"})
        assert list(client.get("/n26/campaigns/").context["campaigns"]) == []

    def test_searching_finds_it(self, client, theirs, open_to_everyone):
        """The list is a join across participants and is deduplicated, so a
        search over it has to survive both."""
        self.accept(client, theirs)
        response = client.get("/n26/campaigns/", {"q": "Sump"})
        assert [row.pk for row in response.context["campaigns"]] == [theirs.pk]

    def test_searching_for_something_else_finds_nothing(
        self, client, theirs, open_to_everyone
    ):
        self.accept(client, theirs)
        assert (
            list(client.get("/n26/campaigns/", {"q": "Ashfall"}).context["campaigns"])
            == []
        )

    def test_the_bar_offers_it(self, client, theirs, open_to_everyone):
        """The chevron beside a campaign's name is how somebody reaches
        another of theirs, and a player has no other way through."""
        from n26.core.navigation import reader_campaigns

        self.accept(client, theirs)
        response = client.get(f"/n26/campaigns/{theirs.pk}/")
        assert [row.pk for row in reader_campaigns(response.wsgi_request)] == [
            theirs.pk
        ]

    def test_they_read_the_log(self, client, theirs, arbitrator, open_to_everyone):
        """Everybody who can open the page can read what has happened."""
        self.accept(client, theirs)
        response = client.get(f"/n26/campaigns/{theirs.pk}/")
        assert response.context["acts"]

    def test_the_arbitrator_still_gets_the_controls(
        self, client, campaign, open_to_everyone
    ):
        drawn = client.get(f"/n26/campaigns/{campaign.pk}/").content.decode()
        assert f"/n26/campaigns/{campaign.pk}/edit/" in drawn
        assert f"/n26/campaigns/{campaign.pk}/participants/add/" in drawn


class TestAPlayerBringingTheirOwnGang:
    """The add-a-gang screen read by somebody at the table rather than by
    the arbitrator: their own gangs, and the budget as the way in."""

    @pytest.fixture
    def theirs(self, arbitrator, campaign_type):
        """A campaign somebody else runs, which the reader has joined."""
        from n26.core.campaigns import campaign_operation

        owner = User.objects.create_user("kesh")
        campaign = found_campaign(
            "Sump Wars", campaign_type, owner=owner, budget=100_000
        )
        with campaign_operation(campaign, actor=owner) as act:
            act.invite(arbitrator)
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.answer_invitation(arbitrator, accepted=True)
        return campaign

    @pytest.fixture
    def mine(self, arbitrator, gang_type):
        return found_gang("My Own", gang_type, owner=arbitrator)

    def test_the_screen_opens_for_them(self, client, theirs, mine, open_to_everyone):
        response = client.get(f"/n26/campaigns/{theirs.pk}/gangs/add/")
        assert response.status_code == 200
        assert response.context["arbitrating"] is False
        assert [row["name"] for row in response.context["gangs"]] == ["My Own"]

    def test_they_are_offered_nobody_elses(
        self, client, theirs, mine, gang_type, open_to_everyone
    ):
        """The arbitrator draws on the whole table; a player draws on their
        own and is not shown what anybody else has."""
        found_gang("Not Mine", gang_type, owner=theirs.owner)
        response = client.get(f"/n26/campaigns/{theirs.pk}/gangs/add/")
        assert [row["name"] for row in response.context["gangs"]] == ["My Own"]

    def test_they_can_bring_it(self, client, theirs, mine, open_to_everyone):
        client.post(f"/n26/campaigns/{theirs.pk}/gangs/add/", {"gang": str(mine.pk)})
        assert CampaignMembership.objects.filter(
            campaign=theirs, gang=mine, left__isnull=True
        ).exists()

    def test_somebody_elses_gang_is_not_on_offer(
        self, client, theirs, mine, gang_type, open_to_everyone
    ):
        """The picker holds the reader's own and nothing else, so naming
        another is refused by the form rather than by a check after it."""
        not_theirs = found_gang(
            "Not Mine", gang_type, owner=User.objects.create_user("stranger")
        )
        client.post(
            f"/n26/campaigns/{theirs.pk}/gangs/add/", {"gang": str(not_theirs.pk)}
        )
        assert not CampaignMembership.objects.filter(gang=not_theirs).exists()

    def test_a_gang_already_playing_is_not_on_offer(
        self, client, theirs, mine, open_to_everyone
    ):
        """A gang plays one campaign at a time, so offering it would be
        offering something that gets refused."""
        client.post(f"/n26/campaigns/{theirs.pk}/gangs/add/", {"gang": str(mine.pk)})
        response = client.get(f"/n26/campaigns/{theirs.pk}/gangs/add/")
        # Still listed, because a reader who cannot find a gang is better
        # told where it went — and hidden to start with by the filter.
        assert [row["playing"] for row in response.context["gangs"]] == [True]
        assert not any(row["playing"] is False for row in response.context["gangs"])

    def test_a_reader_with_no_gangs_is_sent_to_make_one(
        self, client, theirs, open_to_everyone
    ):
        response = client.get(f"/n26/campaigns/{theirs.pk}/gangs/add/")
        assert response.context["nothing_to_offer"] is True
        drawn = response.content.decode()
        assert "No gangs yet" in drawn
        assert "/n26/gangs/new/" in drawn

    def test_a_gang_over_the_budget_joins_and_is_said_to_be_over(
        self,
        client,
        arbitrator,
        gang_type,
        make_profile,
        campaign_type,
        open_to_everyone,
    ):
        from n26.core.campaigns import campaign_operation

        owner = User.objects.create_user("kesh")
        tight = found_campaign("Shoestring", campaign_type, owner=owner, budget=0)
        with campaign_operation(tight, actor=owner) as act:
            act.invite(arbitrator)
        with campaign_operation(tight, actor=arbitrator) as act:
            act.answer_invitation(arbitrator, accepted=True)
        rich = found_gang("Too Rich", gang_type, owner=arbitrator)
        rich.credits = 0
        rich.save()
        # Worth nothing fits a budget of nothing, so put something in it.
        hire(rich, make_profile("Escher Ganger"), "Yolanda", paid=55)

        response = client.post(
            f"/n26/campaigns/{tight.pk}/gangs/add/",
            {"gang": str(rich.pk)},
            follow=True,
        )
        assert response.status_code == 200
        assert CampaignMembership.objects.filter(
            campaign=tight, gang=rich, left__isnull=True
        ).exists()

        said = [str(message) for message in response.context["messages"]]
        assert any("joined" in message for message in said), said
        # The sum is spelled out, so a reader can check it against the
        # figures their own gang sheet gives them.
        over = next(message for message in said if "over the budget" in message)
        assert "rating 55¢" in over, over
        assert "stash 0¢" in over, over
        assert "budget is 0¢" in over, over

    def test_somebody_with_no_place_at_the_table_gets_404(
        self, client, arbitrator, campaign_type, open_to_everyone
    ):
        elsewhere = found_campaign(
            "Elsewhere", campaign_type, owner=User.objects.create_user("stranger")
        )
        assert (
            client.get(f"/n26/campaigns/{elsewhere.pk}/gangs/add/").status_code == 404
        )

    def test_an_invitation_still_waiting_is_not_a_place(
        self, client, arbitrator, campaign_type, open_to_everyone
    ):
        from n26.core.campaigns import campaign_operation

        owner = User.objects.create_user("kesh")
        campaign = found_campaign("Sump Wars", campaign_type, owner=owner)
        with campaign_operation(campaign, actor=owner) as act:
            act.invite(arbitrator)
        assert client.get(f"/n26/campaigns/{campaign.pk}/gangs/add/").status_code == 404

    def test_the_campaign_page_offers_it_to_them(
        self, client, theirs, mine, open_to_everyone
    ):
        response = client.get(f"/n26/campaigns/{theirs.pk}/")
        assert response.context["may_add_gang"] is True
        assert f"/n26/campaigns/{theirs.pk}/gangs/add/" in response.content.decode()

    def test_adding_a_gang_is_the_only_thing_they_gain(
        self, client, theirs, mine, open_to_everyone
    ):
        """The page stopped offering its controls from one flag, so what a
        participant may do is worth stating rather than assuming."""
        self.accept_and_bring(client, theirs, mine)
        drawn = client.get(f"/n26/campaigns/{theirs.pk}/").content.decode()
        for address in (
            f"/n26/campaigns/{theirs.pk}/edit/",
            f"/n26/campaigns/{theirs.pk}/archive/",
            f"/n26/campaigns/{theirs.pk}/participants/add/",
            f"/n26/campaigns/{theirs.pk}/battles/new/",
        ):
            assert address not in drawn, address

    def test_the_screens_behind_those_controls_refuse_them(
        self, client, theirs, mine, open_to_everyone
    ):
        """Absent from the page is not the same as shut, so each is asked."""
        self.accept_and_bring(client, theirs, mine)
        for address in (
            f"/n26/campaigns/{theirs.pk}/edit/",
            f"/n26/campaigns/{theirs.pk}/archive/",
            f"/n26/campaigns/{theirs.pk}/participants/add/",
            f"/n26/campaigns/{theirs.pk}/battles/new/",
        ):
            assert client.get(address).status_code == 404, address

    def test_they_cannot_take_their_own_gang_back_out_yet(
        self, client, theirs, mine, open_to_everyone
    ):
        """Joining gave the gang the campaign's types and what they bring,
        and leaving is not offered until it can return all of it: no
        control is drawn, and the address refuses in words."""
        self.accept_and_bring(client, theirs, mine)
        drawn = client.get(f"/n26/campaigns/{theirs.pk}/").content.decode()
        remove = f"/n26/campaigns/{theirs.pk}/gangs/{mine.pk}/remove/"
        assert remove not in drawn

        response = client.post(remove, follow=True)
        assert "cannot leave" in response.content.decode()
        assert CampaignMembership.objects.filter(
            campaign=theirs, gang=mine, left__isnull=True
        ).exists()

    def test_they_cannot_take_out_somebody_elses(
        self, client, theirs, mine, gang_type, arbitrator, open_to_everyone
    ):
        from n26.core.operations import operation

        stranger = User.objects.create_user("stranger")
        not_theirs = found_gang("Not Mine", gang_type, owner=stranger)
        with operation(not_theirs, actor=stranger) as op:
            op.join_campaign(theirs)

        remove = f"/n26/campaigns/{theirs.pk}/gangs/{not_theirs.pk}/remove/"
        assert client.get(remove).status_code == 404
        client.post(remove)
        assert CampaignMembership.objects.filter(
            campaign=theirs, gang=not_theirs, left__isnull=True
        ).exists()

    def accept_and_bring(self, client, campaign, gang):
        """A participant with a gang of theirs already in the campaign."""
        client.post(f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": str(gang.pk)})


class TestTheRollsQueryCount:
    """One select_related is all that keeps the roll from asking after every
    gang's stash, and nothing else would notice it going."""

    def test_it_does_not_grow_with_the_gangs(
        self, client, arbitrator, campaign, gang_type, make_profile, open_to_everyone
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.core.operations import operation

        def seat(name, stashed):
            gang = found_gang(
                name, gang_type, owner=User.objects.create_user(f"owner-{name}")
            )
            hire(gang, make_profile(f"Fighter {name}"), "Yolanda", paid=55)
            if stashed:
                assign(
                    create_wargear(f"Crate {name}", price=25),
                    stash=gang.stash,
                    paid=25,
                )
            with operation(gang, actor=arbitrator) as op:
                op.join_campaign(campaign)

        seat("One", stashed=True)
        # Once first, so nothing one-off is counted as part of the page.
        client.get(f"/n26/campaigns/{campaign.pk}/")
        with CaptureQueriesContext(connection) as one_gang:
            client.get(f"/n26/campaigns/{campaign.pk}/")

        seat("Two", stashed=True)
        seat("Three", stashed=False)
        with CaptureQueriesContext(connection) as three_gangs:
            client.get(f"/n26/campaigns/{campaign.pk}/")

        assert len(three_gangs) == len(one_gang)


class TestTheAddGangScreensQueryCount:
    """Every row reads its owner and its stash, so two select_related terms
    are all that keep the list flat. Nothing else would notice them going."""

    def test_it_does_not_grow_with_the_gangs(
        self, client, arbitrator, campaign, gang_type, make_profile, open_to_everyone
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def seat_a_gang_owner(name):
            player = User.objects.create_user(name)
            seat(campaign, player)
            gang = found_gang(f"Gang of {name}", gang_type, owner=player)
            hire(gang, make_profile(f"Fighter {name}"), "Yolanda", paid=55)
            assign(
                create_wargear(f"Crate {name}", price=25),
                stash=gang.stash,
                paid=25,
            )

        address = f"/n26/campaigns/{campaign.pk}/gangs/add/"
        seat_a_gang_owner("one")
        client.get(address)
        with CaptureQueriesContext(connection) as few:
            client.get(address)

        seat_a_gang_owner("two")
        seat_a_gang_owner("three")
        with CaptureQueriesContext(connection) as many:
            client.get(address)

        assert len(many) == len(few)


class TestTheArbitratorsOwnAddGangScreen:
    """The same list a player sees, over everybody at the table."""

    @pytest.fixture
    def rich(self, campaign, gang_type, make_profile):
        player = User.objects.create_user("player")
        seat(campaign, player)
        gang = found_gang("Too Rich", gang_type, owner=player)
        hire(gang, make_profile("Escher Ganger"), "Yolanda", paid=55)
        return gang

    def test_it_offers_the_gangs_of_everybody_seated(
        self, client, campaign, rich, gang_type, arbitrator, open_to_everyone
    ):
        mine = found_gang("The Arbitrator's Own", gang_type, owner=arbitrator)
        outsider = found_gang(
            "Not Invited", gang_type, owner=User.objects.create_user("outsider")
        )

        response = client.get(f"/n26/campaigns/{campaign.pk}/gangs/add/")
        assert response.context["arbitrating"] is True
        offered = {row["name"] for row in response.context["gangs"]}
        assert offered == {"Too Rich", mine.name}
        assert outsider.name not in offered

    def test_the_newest_touched_gang_comes_first(
        self, client, campaign, rich, gang_type, make_profile, open_to_everyone
    ):
        """Ordered by the ledger, because the gang somebody is looking for
        is nearly always the one they were last working on."""
        older = found_gang("Long Untouched", gang_type, owner=rich.owner)
        hire(older, make_profile("Escher Juve"), "Nadia", paid=25)
        hire(rich, make_profile("Escher Champ"), "Vala", paid=80)

        response = client.get(f"/n26/campaigns/{campaign.pk}/gangs/add/")
        assert [row["name"] for row in response.context["gangs"]][:2] == [
            "Too Rich",
            "Long Untouched",
        ]

    def test_it_says_which_gangs_are_already_playing(
        self, client, campaign, rich, arbitrator, open_to_everyone
    ):
        """Hidden by the filter to start with, but listed — a reader who
        cannot find a gang should be told where it went."""
        client.post(f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": str(rich.pk)})
        response = client.get(f"/n26/campaigns/{campaign.pk}/gangs/add/")
        assert [row["playing"] for row in response.context["gangs"]] == [True]
        assert not any(row["playing"] is False for row in response.context["gangs"])

    def test_a_gang_over_the_budget_joins_and_is_marked(
        self, client, campaign, rich, arbitrator, open_to_everyone
    ):
        campaign.budget = 0
        campaign.save()
        client.post(f"/n26/campaigns/{campaign.pk}/gangs/add/", {"gang": str(rich.pk)})
        assert CampaignMembership.objects.filter(
            campaign=campaign, gang=rich, left__isnull=True
        ).exists()

        response = client.get(f"/n26/campaigns/{campaign.pk}/")
        assert [row.over_budget for row in response.context["playing"]] == [True]
        assert "Over budget" in response.content.decode()


class TestNothingTypedIntoAnAddressIsAServerError:
    """Ids reach these views from forms and addresses, where anything can be
    typed. A key column refuses what it cannot parse by raising, so every one
    of them has to be checked before it reaches a query."""

    @pytest.fixture
    def gone(self, campaign):
        return f"/n26/campaigns/{campaign.pk}/participants/add/"

    def test_a_post_with_no_account_says_so(
        self, client, campaign, gone, open_to_everyone
    ):
        response = client.post(gone, {"message": "hello"}, follow=True)
        assert response.status_code == 200
        assert "no longer exists" in response.content.decode()

    def test_a_post_naming_nonsense_says_so(
        self, client, campaign, gone, open_to_everyone
    ):
        response = client.post(gone, {"user": "not-a-number"}, follow=True)
        assert response.status_code == 200
        assert "no longer exists" in response.content.decode()

    def test_an_invite_parameter_of_nonsense_draws_the_page(
        self, client, campaign, gone, open_to_everyone
    ):
        assert client.get(f"{gone}?invite=not-a-number").status_code == 200

    def test_removing_a_participant_by_nonsense_is_a_404(
        self, client, campaign, open_to_everyone
    ):
        address = f"/n26/campaigns/{campaign.pk}/participants/not-a-number/remove/"
        assert client.get(address).status_code == 404

    def test_answering_at_a_malformed_campaign_is_a_404(
        self, client, arbitrator, open_to_everyone
    ):
        response = client.post(
            "/n26/campaigns/not-a-ulid/invitation/", {"answer": "accept"}
        )
        assert response.status_code == 404


class TestTheArbitratorIsNotAParticipant:
    """The model says so, so the write says so — the search screens them out,
    and a request that goes round the search must not get past this."""

    def test_inviting_the_owner_is_refused_in_words(
        self, client, campaign, arbitrator, open_to_everyone
    ):
        response = client.post(
            f"/n26/campaigns/{campaign.pk}/participants/add/",
            {"user": str(arbitrator.pk)},
            follow=True,
        )
        assert "an arbitrator cannot also be a participant" in response.content.decode()
        assert not CampaignParticipant.objects.exists()

    def test_an_account_switched_off_is_not_invited(
        self, client, campaign, open_to_everyone
    ):
        gone = User.objects.create_user("retired", is_active=False)
        response = client.post(
            f"/n26/campaigns/{campaign.pk}/participants/add/",
            {"user": str(gone.pk)},
            follow=True,
        )
        assert "no longer exists" in response.content.decode()
        assert not CampaignParticipant.objects.exists()
