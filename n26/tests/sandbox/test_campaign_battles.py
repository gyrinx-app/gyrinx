"""Battle identity and outcomes are separate from the gangs' own records."""

from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from n26.core.campaigns import campaign_operation
from n26.core.history import campaign_history
from n26.core.models import Battle, CampaignEvent, LedgerEvent
from n26.core.operations import Refusal, operation
from n26.tests.sandbox.actions import found_campaign, found_gang, join_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def arbitrator():
    return User.objects.create_user("arbitrator")


@pytest.fixture
def campaign(arbitrator, campaign_type):
    return found_campaign("Dust Falls", campaign_type, owner=arbitrator, budget=1000)


@pytest.fixture
def gang(gang_type, arbitrator, campaign):
    gang = found_gang("The Ashen Choir", gang_type, owner=arbitrator)
    join_campaign(gang, campaign)
    return gang


@pytest.fixture
def battle(campaign, arbitrator, gang):
    with campaign_operation(campaign, actor=arbitrator) as act:
        return act.record_battle(date(2026, 8, 3), [gang], scenario="Stand-off")


def told(campaign):
    return [
        "".join(span.text for span in act.spans) for act in campaign_history(campaign)
    ]


def edit(act, battle, **changes):
    fields = {
        "scenario": battle.scenario,
        "date": battle.date,
        "gangs": list(battle.gangs.all()),
        "result": battle.result,
        "winners": list(battle.winners.all()),
        "revision": battle.revision,
    }
    return act.edit_battle(battle, **(fields | changes))


class TestRecordingABattle:
    def test_identity_and_unrecorded_result(self, battle, campaign, gang):
        battle.refresh_from_db()
        assert battle.scenario == "Stand-off"
        assert battle.date == date(2026, 8, 3)
        assert list(battle.gangs.all()) == [gang]
        assert battle.campaign == campaign
        assert battle.result == Battle.Result.NOT_RECORDED
        assert not battle.winners.exists()

    def test_nobody_need_be_named(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            battle = act.record_battle(date(2026, 8, 3), scenario="Stand-off")
        assert not battle.gangs.exists()
        assert told(campaign)[-1] == "recorded Stand-off on 2026-08-03"

    def test_no_gang_is_touched(self, campaign, arbitrator, gang):
        before = list(gang.ledger_events.values_list("pk", flat=True))
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.record_battle(
                date(2026, 8, 3),
                [gang],
                scenario="Stand-off",
                result=Battle.Result.WINNERS,
                winners=[gang],
            )
        assert list(gang.ledger_events.values_list("pk", flat=True)) == before

    def test_battles_read_newest_first(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            for day in (1, 9, 5):
                act.record_battle(date(2026, 8, day), scenario="Stand-off")
        assert [b.date.day for b in campaign.battles.all()] == [9, 5, 1]

    @pytest.mark.parametrize("scenario", ["", "  ", "x" * 201])
    def test_scenario_required(self, campaign, arbitrator, scenario):
        with pytest.raises(Refusal, match="scenario"):
            with campaign_operation(campaign, actor=arbitrator) as act:
                act.record_battle(date(2026, 8, 3), scenario=scenario)
        assert not Battle.objects.exists()

    def test_foreign_gangs_refused(self, campaign, arbitrator, gang_type):
        foreign = found_gang("Elsewhere", gang_type, owner=arbitrator)
        with pytest.raises(Refusal, match="this campaign"):
            with campaign_operation(campaign, actor=arbitrator) as act:
                act.record_battle(date(2026, 8, 3), [foreign], scenario="Stand-off")
        assert not Battle.objects.exists()

    @pytest.mark.parametrize(
        "result,with_winner",
        [("bogus", False), ("winners", False), ("draw", True), ("not_recorded", True)],
    )
    def test_invalid_outcomes_refused(
        self, campaign, arbitrator, gang, result, with_winner
    ):
        with pytest.raises(Refusal):
            with campaign_operation(campaign, actor=arbitrator) as act:
                act.record_battle(
                    date(2026, 8, 3),
                    [gang],
                    scenario="Stand-off",
                    result=result,
                    winners=[gang] if with_winner else [],
                )
        assert not Battle.objects.exists()

    def test_winner_must_participate(self, campaign, arbitrator, gang):
        with pytest.raises(Refusal, match="participant"):
            with campaign_operation(campaign, actor=arbitrator) as act:
                act.record_battle(
                    date(2026, 8, 3),
                    scenario="Stand-off",
                    result="winners",
                    winners=[gang],
                )

    def test_multiple_winners(self, campaign, arbitrator, gang, gang_type):
        ally = found_gang("Allies", gang_type, owner=arbitrator)
        join_campaign(ally, campaign)
        with campaign_operation(campaign, actor=arbitrator) as act:
            battle = act.record_battle(
                date(2026, 8, 3),
                [gang, ally],
                scenario="Stand-off",
                result="winners",
                winners=[gang, ally],
            )
        assert set(battle.winners.all()) == {gang, ally}


class TestBattleModel:
    def test_legacy_record_has_no_invented_scenario_or_result(self, campaign):
        battle = Battle.objects.create(campaign=campaign, date=date(2026, 8, 3))
        assert battle.title == "Battle on 2026-08-03"
        assert battle.result_label == "Not recorded"
        assert not battle.scenario

    def test_known_result_constraint(self, campaign):
        with pytest.raises(IntegrityError), transaction.atomic():
            Battle.objects.create(
                campaign=campaign, date=date(2026, 8, 3), result="bogus"
            )

    def test_outcome_validation_has_field_errors(self):
        with pytest.raises(ValidationError) as exc:
            Battle.validate_outcome(result="winners", gangs=[], winners=[])
        assert "winners" in exc.value.message_dict


class TestEditingABattle:
    def test_edits_result_without_rewards(self, battle, campaign, arbitrator, gang):
        before = list(gang.ledger_events.values_list("pk", flat=True))
        with campaign_operation(campaign, actor=arbitrator) as act:
            saved = edit(
                act, battle, scenario="Ambush", result="winners", winners=[gang]
            )
        assert saved.revision == 1
        assert saved.result_label == "Won by The Ashen Choir"
        assert list(gang.ledger_events.values_list("pk", flat=True)) == before
        assert (
            campaign.events.filter(kind=CampaignEvent.Kind.BATTLE_EDITED).count() == 1
        )
        with campaign_operation(campaign, actor=arbitrator) as act:
            saved = edit(act, saved, result="draw", winners=[])
        assert saved.result_label == "Draw"
        assert not saved.winners.exists()
        assert told(campaign)[-1] == "edited the battle: Ambush on 2026-08-03"

    def test_unchanged_save_is_noop(self, battle, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            saved = edit(act, battle)
        assert saved.revision == 0
        assert not campaign.events.filter(
            kind=CampaignEvent.Kind.BATTLE_EDITED
        ).exists()

    def test_stale_edit_does_not_overwrite(self, battle, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            edit(act, battle, scenario="Ambush")
        with pytest.raises(Refusal, match="changed"):
            with campaign_operation(campaign, actor=arbitrator) as act:
                edit(act, battle, scenario="Old edit")
        battle.refresh_from_db()
        assert battle.scenario == "Ambush"
        assert battle.revision == 1

    def test_participant_with_history_cannot_be_removed(
        self, battle, campaign, arbitrator, gang
    ):
        event = LedgerEvent.objects.create(
            gang=gang, campaign=campaign, battle=battle, kind=LedgerEvent.Kind.ADDED
        )
        with pytest.raises(Refusal, match="participant"):
            with campaign_operation(campaign, actor=arbitrator) as act:
                edit(act, battle, gangs=[])
        assert list(battle.gangs.all()) == [gang]
        event.refresh_from_db()
        assert event.battle_id == battle.pk

    def test_departed_participant_is_retained(self, battle, campaign, arbitrator, gang):
        with operation(gang, actor=arbitrator) as op:
            op.leave_campaign()
        with campaign_operation(campaign, actor=arbitrator) as act:
            saved = edit(act, battle, result="winners", winners=[gang])
        assert list(saved.gangs.all()) == [gang]
        assert list(saved.winners.all()) == [gang]

    def test_foreign_battle_refused(self, battle, arbitrator, campaign_type):
        foreign = found_campaign("Elsewhere", campaign_type, owner=arbitrator)
        with pytest.raises(Refusal, match="no longer available"):
            with campaign_operation(foreign, actor=arbitrator) as act:
                edit(act, battle, scenario="Wrong campaign")
        battle.refresh_from_db()
        assert battle.scenario == "Stand-off"

    def test_invalid_edit_rolls_back(self, battle, campaign, arbitrator):
        with pytest.raises(Refusal):
            with campaign_operation(campaign, actor=arbitrator) as act:
                edit(act, battle, scenario="Ambush", result="winners")
        battle.refresh_from_db()
        assert battle.scenario == "Stand-off"
        assert battle.revision == 0


class TestRemovingABattle:
    @pytest.mark.parametrize(
        "changes",
        [
            {"scenario": "Ambush"},
            {"date": date(2026, 8, 4)},
            {"result": "draw"},
            {"gangs": []},
        ],
    )
    def test_metadata_changes_invalidate_an_earlier_removal_confirmation(
        self, battle, campaign, arbitrator, changes
    ):
        revision = battle.revision
        with campaign_operation(campaign, actor=arbitrator) as act:
            updated = edit(act, battle, **changes)
        assert updated.revision == revision + 1
        with pytest.raises(Refusal, match="changed.*before removing"):
            with campaign_operation(campaign, actor=arbitrator) as act:
                act.remove_battle(battle, revision=revision)
        assert Battle.objects.filter(pk=battle.pk, revision=revision + 1).exists()
        assert not campaign.events.filter(
            kind=CampaignEvent.Kind.BATTLE_REMOVED
        ).exists()

    def test_log_retains_scenario_when_removed(self, campaign, arbitrator):
        with campaign_operation(campaign, actor=arbitrator) as act:
            battle = act.record_battle(date(2026, 8, 3), scenario="Stand-off")
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.remove_battle(battle, revision=battle.revision)
        assert told(campaign)[-2:] == [
            "recorded Stand-off on 2026-08-03",
            "removed the battle of 2026-08-03",
        ]
        assert not campaign.battles.exists()

    def test_recorded_gang_history_keeps_its_battle(
        self, battle, campaign, arbitrator, gang
    ):
        event = LedgerEvent.objects.create(
            gang=gang, campaign=campaign, battle=battle, kind=LedgerEvent.Kind.ADDED
        )
        with pytest.raises(Refusal, match="recorded gang history"):
            with campaign_operation(campaign, actor=arbitrator) as act:
                act.remove_battle(battle, revision=battle.revision)
        event.refresh_from_db()
        assert event.battle_id == battle.pk
        assert Battle.objects.filter(pk=battle.pk).exists()
        assert not campaign.events.filter(
            kind=CampaignEvent.Kind.BATTLE_REMOVED
        ).exists()

    def test_foreign_battle_refused(self, battle, arbitrator, campaign_type):
        foreign = found_campaign("Elsewhere", campaign_type, owner=arbitrator)
        with pytest.raises(Refusal):
            with campaign_operation(foreign, actor=arbitrator) as act:
                act.remove_battle(battle, revision=battle.revision)
        assert Battle.objects.filter(pk=battle.pk).exists()
