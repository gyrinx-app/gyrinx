"""Battles: the occasion a campaign's records hang from.

A battle carries only when it was fought and who was in it. What it did to a
gang is written against that gang, in its own ledger, naming the battle.
"""

from datetime import date

import pytest
from django.contrib.auth.models import User

from n26.core.campaigns import campaign_operation
from n26.core.history import campaign_history
from n26.core.models import LedgerEvent
from n26.tests.sandbox.actions import found_campaign, found_gang

pytestmark = pytest.mark.django_db


@pytest.fixture
def arbitrator():
    return User.objects.create_user("arbitrator")


@pytest.fixture
def campaign(arbitrator, campaign_type):
    return found_campaign("Dust Falls", campaign_type, owner=arbitrator, budget=1000)


#: The log's first line, which founding writes before any test here acts.
FOUNDED = "set the campaign up on Territory campaign"


@pytest.fixture
def gang(gang_type, arbitrator):
    return found_gang("The Ashen Choir", gang_type, owner=arbitrator)


def told(campaign):
    """Each act as one plain sentence, the way a page draws it."""
    return [
        "".join(span.text for span in act.spans) for act in campaign_history(campaign)
    ]


class TestRecordingABattle:
    def test_it_keeps_the_date_and_who_fought(self, campaign, arbitrator, gang):
        with campaign_operation(campaign, actor=arbitrator) as act:
            battle = act.record_battle(date(2026, 8, 3), [gang])

        battle.refresh_from_db()
        assert battle.date == date(2026, 8, 3)
        assert list(battle.gangs.all()) == [gang]
        assert battle.campaign == campaign

    def test_nobody_need_be_named(self, campaign, arbitrator):
        """A battle written down before the players are settled is still a
        date worth keeping."""
        with campaign_operation(campaign, actor=arbitrator) as act:
            battle = act.record_battle(date(2026, 8, 3))

        assert not battle.gangs.exists()

    def test_the_campaigns_log_says_so(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.record_battle(date(2026, 8, 3))

        assert told(campaign) == [FOUNDED, "recorded a battle fought on 3 August"]

    def test_no_gang_is_touched(self, campaign, arbitrator, gang):
        """Recording one says a thing happened. What it did to anybody is
        written against that gang afterwards."""
        before = gang.ledger_events.count()
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.record_battle(date(2026, 8, 3), [gang])

        assert gang.ledger_events.count() == before

    def test_battles_read_newest_first(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.record_battle(date(2026, 8, 1))
            act.record_battle(date(2026, 8, 9))
            act.record_battle(date(2026, 8, 5))

        assert [b.date.day for b in campaign.battles.all()] == [9, 5, 1]


class TestRemovingABattle:
    def test_the_log_keeps_both_lines(self, campaign, arbitrator):
        """The battle happened and was then removed. Both are true, and an
        append-only log says so rather than losing the first."""
        with campaign_operation(campaign, actor=arbitrator) as act:
            battle = act.record_battle(date(2026, 8, 3))
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.remove_battle(battle)

        assert told(campaign) == [
            FOUNDED,
            "recorded a battle",
            "removed the battle of 2026-08-03",
        ]
        assert not campaign.battles.exists()

    def test_a_gangs_own_records_survive_it(self, campaign, arbitrator, gang):
        """What a gang did in a battle keeps its record and simply stops
        naming one."""
        with campaign_operation(campaign, actor=arbitrator) as act:
            battle = act.record_battle(date(2026, 8, 3), [gang])

        event = LedgerEvent.objects.create(
            gang=gang, campaign=campaign, battle=battle, kind=LedgerEvent.Kind.ADDED
        )

        with campaign_operation(campaign, actor=arbitrator) as act:
            act.remove_battle(battle)

        event.refresh_from_db()
        assert event.battle_id is None
        assert event.gang == gang
