"""Campaign feeds: who may make them, and what their public addresses serve."""

import datetime

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import campaign_operation
from n26.core.models import Battle, CampaignFeed
from n26.flags import CAMPAIGN_FEEDS
from n26.tests.sandbox.actions import found_campaign, found_gang

pytestmark = pytest.mark.django_db


def open_flags(*slugs):
    for slug in slugs:
        FeatureFlag.objects.create(
            slug=slug, name=slug, availability=Availability.EVERYONE
        )


@pytest.fixture
def campaign(campaign_type):
    open_flags(CAMPAIGN_FEEDS)
    owner = User.objects.create_user("arbitrator")
    return found_campaign("Dust Falls", campaign_type, owner=owner)


def feeds_tab(campaign):
    return reverse("n26-edit-campaign", args=[campaign.pk]) + "?tab=feeds"


def make_feed(client, campaign, section, target):
    return client.post(
        reverse("n26-campaign-add-feed", args=[campaign.pk]),
        {"section": section, "target": target},
    )


class TestTheFeedsTab:
    def test_the_arbitrator_sees_the_tab(self, client, campaign):
        client.force_login(campaign.owner)

        response = client.get(feeds_tab(campaign))

        assert response.status_code == 200
        assert "Make a feed" in response.text

    def test_the_tab_is_hidden_while_the_flag_is_shut(self, client, campaign):
        FeatureFlag.objects.filter(slug=CAMPAIGN_FEEDS).delete()
        client.force_login(campaign.owner)

        response = client.get(feeds_tab(campaign))

        assert "Make a feed" not in response.text

    def test_nobody_else_may_make_a_feed(self, client, campaign):
        client.force_login(User.objects.create_user("player"))

        response = make_feed(client, campaign, "gangs", "google_sites")

        assert response.status_code == 404
        assert not CampaignFeed.objects.exists()

    def test_the_arbitrator_makes_and_turns_off_a_feed(self, client, campaign):
        client.force_login(campaign.owner)

        make_feed(client, campaign, "gangs", "google_sites")
        feed = CampaignFeed.objects.get()
        page = client.get(feeds_tab(campaign)).text
        client.post(reverse("n26-campaign-turn-off-feed", args=[campaign.pk, feed.pk]))

        assert f"/n26/feeds/{feed.token}/" in page
        assert "&lt;iframe" in page
        feed.refresh_from_db()
        assert feed.archived

    def test_rss_is_refused_for_anything_but_battles(self, client, campaign):
        client.force_login(campaign.owner)

        make_feed(client, campaign, "gangs", "rss")

        assert not CampaignFeed.objects.exists()


class TestThePublicPage:
    def test_it_opens_without_signing_in_and_may_be_framed(self, client, campaign):
        feed = CampaignFeed.objects.create(
            campaign=campaign, section="gangs", target="google_sites"
        )

        response = client.get(reverse("n26-campaign-feed", args=[feed.token]))

        assert response.status_code == 200
        assert "X-Frame-Options" not in response.headers
        assert response.headers["Content-Security-Policy"] == "frame-ancestors *"
        assert not response.cookies

    def test_it_carries_a_link_card(self, client, campaign, gang_type):
        gang = found_gang("Venom Sisters", gang_type, owner=campaign.owner)
        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.add_gang(gang)
        feed = CampaignFeed.objects.create(
            campaign=campaign, section="gangs", target="link_card"
        )

        page = BeautifulSoup(
            client.get(reverse("n26-campaign-feed", args=[feed.token])).text,
            "html.parser",
        )

        def tag(name):
            return page.find("meta", property=name)["content"]

        assert tag("og:title") == "Gangs – Dust Falls"
        assert tag("og:description") == "1 gang: Venom Sisters."

    def test_a_turned_off_feed_is_gone(self, client, campaign):
        feed = CampaignFeed.objects.create(
            campaign=campaign, section="gangs", target="google_sites"
        )
        feed.archive()

        response = client.get(reverse("n26-campaign-feed", args=[feed.token]))

        assert response.status_code == 404

    def test_every_feed_is_gone_while_the_flag_is_shut(self, client, campaign):
        feed = CampaignFeed.objects.create(
            campaign=campaign, section="gangs", target="google_sites"
        )
        FeatureFlag.objects.filter(slug=CAMPAIGN_FEEDS).delete()

        response = client.get(reverse("n26-campaign-feed", args=[feed.token]))

        assert response.status_code == 404


class TestTheRssFeed:
    def test_it_lists_the_battles(self, client, campaign, gang_type):
        gang = found_gang("Venom Sisters", gang_type, owner=campaign.owner)
        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.add_gang(gang)
            act.record_battle(
                datetime.date(2026, 10, 14),
                [gang],
                scenario="Sabotage",
                result="winners",
                winners=[gang],
            )
        feed = CampaignFeed.objects.create(
            campaign=campaign, section="battles", target="rss"
        )

        response = client.get(reverse("n26-campaign-feed-rss", args=[feed.token]))

        assert response.status_code == 200
        assert response["Content-Type"].startswith("application/rss+xml")
        assert "<title>Sabotage</title>" in response.text
        assert "Won by Venom Sisters." in response.text

    def test_only_an_rss_feed_answers_as_rss(self, client, campaign):
        feed = CampaignFeed.objects.create(
            campaign=campaign, section="battles", target="wordpress"
        )

        response = client.get(reverse("n26-campaign-feed-rss", args=[feed.token]))

        assert response.status_code == 404


@pytest.fixture
def two_battles(campaign, gang_type):
    player = User.objects.create_user("ganger-gertie")
    gang = found_gang("Venom Sisters", gang_type, owner=player)
    with campaign_operation(campaign, actor=campaign.owner) as act:
        act.add_gang(gang)
        kept = act.record_battle(
            datetime.date(2026, 10, 14),
            [gang],
            scenario="Sabotage",
            result="winners",
            winners=[gang],
        )
        archived = act.record_battle(
            datetime.date(2026, 10, 15), [gang], scenario="Ambush"
        )
    Battle.objects.filter(pk=archived.pk).update(archived=True)
    return kept, archived


class TestTheBattlesFeedRows:
    def test_the_page_shows_gang_types_but_no_players(
        self, client, campaign, gang_type, two_battles
    ):
        feed = CampaignFeed.objects.create(
            campaign=campaign, section="battles", target="google_sites"
        )

        page = client.get(reverse("n26-campaign-feed", args=[feed.token])).text

        assert "Sabotage" in page
        assert gang_type.name in page
        assert "ganger-gertie" not in page

    def test_archived_battles_are_left_out(self, client, campaign, two_battles):
        feed = CampaignFeed.objects.create(
            campaign=campaign, section="battles", target="rss"
        )

        rss = client.get(reverse("n26-campaign-feed-rss", args=[feed.token])).text

        assert "<title>Sabotage</title>" in rss
        assert "Ambush" not in rss
        assert "ganger-gertie" not in rss
