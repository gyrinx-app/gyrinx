"""Players record dice on campaign pages without changing their gangs."""

from datetime import date
from unittest.mock import Mock
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import campaign_operation
from n26.core.models import Battle, CampaignEvent, CampaignRoll, LedgerEvent
from n26.core.operations import Refusal
from n26.flags import CAMPAIGNS
from n26.library.models import Dice
from n26.tests.sandbox.actions import found_campaign, found_gang

pytestmark = pytest.mark.django_db


@pytest.fixture
def campaign(client, campaign_type):
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
    owner = User.objects.create_user("arb")
    client.force_login(owner)
    return found_campaign("Dust Falls", campaign_type, owner=owner)


@pytest.fixture
def player(client, campaign):
    player = User.objects.create_user("player")
    with campaign_operation(campaign, actor=campaign.owner) as act:
        act.invite(player)
    with campaign_operation(campaign, actor=player) as act:
        act.answer_invitation(player, accepted=True)
    client.force_login(player)
    return player


def payload(**changes):
    return {
        "request_key": str(uuid4()),
        "reason": "Rare trade",
        "dice": "d6",
        "source": "generated",
        "modifier": "",
        **changes,
    }


def record_url(campaign):
    return reverse("n26-campaign-record-roll", args=[campaign.pk])


def roll_url(roll):
    return reverse("n26-campaign-roll", args=[roll.campaign_id, roll.pk])


class TestRecordingPages:
    def test_players_get_header_actions_and_dedicated_pages(
        self, client, campaign, player
    ):
        body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
        assert "Record a battle" in body
        assert 'aria-label="Log a dice roll"' in body
        assert "View log" in body
        assert f"/n26/campaigns/{campaign.pk}/edit/" not in body
        assert "Archive campaign" not in body
        response = client.get(record_url(campaign))
        assert response.status_code == 200
        assert "Log a dice roll" in response.content.decode()
        assert 'name="request_key"' in response.content.decode()
        assert response.context["roll_source"]["source"] == "generated"
        assert response.context["roll_source"]["rolled"] == ""
        assert response.context["roll_source"]["sourceErrors"] == []
        assert "<dialog" not in response.content.decode()
        assert (
            "Log a dice roll"
            in client.get(
                reverse("n26-campaign-log", args=[campaign.pk])
            ).content.decode()
        )

    def test_players_can_create_battles_but_cannot_edit_or_remove_them(
        self, client, campaign, player
    ):
        url = reverse("n26-campaign-add-battle", args=[campaign.pk])
        assert client.get(url).status_code == 200
        response = client.post(url, {"scenario": "Stand-off", "date": "2026-10-02"})
        assert response.status_code == 302
        battle = Battle.objects.get(campaign=campaign)
        assert (
            campaign.events.get(kind=CampaignEvent.Kind.BATTLE_RECORDED).actor == player
        )
        for route in ["n26-campaign-edit-battle", "n26-campaign-remove-battle"]:
            assert (
                client.post(
                    reverse(route, args=[campaign.pk, battle.pk]), {}
                ).status_code
                == 404
            )

    @pytest.mark.parametrize("state", [None, "invited", "declined"])
    def test_outsiders_and_unaccepted_players_cannot_record(
        self, client, campaign, state
    ):
        outsider = User.objects.create_user("outsider")
        if state:
            with campaign_operation(campaign, actor=campaign.owner) as act:
                act.invite(outsider)
            if state == "declined":
                with campaign_operation(campaign, actor=outsider) as act:
                    act.answer_invitation(outsider, accepted=False)
        client.force_login(outsider)
        for route in ["n26-campaign-record-roll", "n26-campaign-add-battle"]:
            url = reverse(route, args=[campaign.pk])
            assert client.get(url).status_code == 404
            assert client.post(url, payload()).status_code == 404
        body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
        assert record_url(campaign) not in body
        assert not CampaignRoll.objects.exists()

    @pytest.mark.parametrize("dice,rolled", [("d3", 3), ("d6", 6), ("d66", 61)])
    def test_physical_results_and_modifiers_are_kept_separately(
        self, client, campaign, player, dice, rolled
    ):
        response = client.post(
            record_url(campaign),
            payload(dice=dice, source="manual", rolled=str(rolled), modifier="-2"),
        )
        roll = CampaignRoll.objects.get()
        assert response.url == roll_url(roll)
        assert (roll.rolled, roll.modifier, roll.total) == (rolled, -2, rolled - 2)
        assert roll.actor == player
        assert roll.source == "manual"
        assert "Physical dice" in client.get(response.url).content.decode()
        assert LedgerEvent.objects.count() == 0

    @pytest.mark.parametrize(
        "fields",
        [
            {"dice": "d3", "rolled": "4"},
            {"dice": "d6", "rolled": "7"},
            {"dice": "d66", "rolled": "17"},
            {"dice": "d66", "rolled": "20"},
            {"dice": "d66", "rolled": "70"},
            {"rolled": ""},
            {"rolled": "2.5"},
            {"dice": "2d6", "rolled": "8"},
            {"source": "generated", "rolled": "3"},
            {"modifier": "2147483648", "rolled": "3"},
            {"request_key": "", "rolled": "3"},
        ],
    )
    def test_invalid_results_are_redrawn_without_recording(
        self, client, campaign, fields
    ):
        response = client.post(
            record_url(campaign), payload(**{"source": "manual", **fields})
        )
        assert response.status_code == 200
        assert response.context["form"].errors
        assert response.context["roll_source"]["source"] == fields.get(
            "source", "manual"
        )
        assert response.context["roll_source"]["rolled"] == fields.get("rolled", "")
        assert response.context["roll_source"]["rolledErrors"] == list(
            response.context["form"]["rolled"].errors
        )
        assert not CampaignRoll.objects.exists()
        assert not campaign.events.filter(kind=CampaignEvent.Kind.DICE_ROLLED).exists()

    @pytest.mark.parametrize("key", ["", "not-a-uuid"])
    def test_invalid_request_keys_offer_reload_guidance(self, client, campaign, key):
        response = client.post(record_url(campaign), payload(request_key=key))
        assert response.status_code == 200
        assert "Reload this page" in response.content.decode()
        assert not CampaignRoll.objects.exists()
        fresh = client.get(record_url(campaign))
        response = client.post(
            record_url(campaign),
            payload(request_key=str(fresh.context["form"]["request_key"].value())),
        )
        assert response.status_code == 302
        assert CampaignRoll.objects.count() == 1

    def test_retrying_generated_rolls_returns_the_saved_result(
        self, client, campaign, monkeypatch
    ):
        roller = Mock(return_value=4)
        monkeypatch.setattr(Dice, "roll", roller)
        data = payload(modifier="2")
        first = client.post(record_url(campaign), data)
        second = client.post(record_url(campaign), data)
        assert first.url == second.url
        roller.assert_called_once_with("d6", rng=None)
        roll = CampaignRoll.objects.get()
        assert (roll.rolled, roll.modifier, roll.total) == (4, 2, 6)
        assert campaign.events.filter(kind=CampaignEvent.Kind.DICE_ROLLED).count() == 1
        before = CampaignRoll.objects.count()
        assert client.get(roll_url(roll)).status_code == 200
        assert CampaignRoll.objects.count() == before
        assert roller.call_count == 1

    def test_notes_are_saved_without_rerolling_and_retries_add_no_events(
        self, client, campaign, player
    ):
        client.post(
            record_url(campaign), payload(source="manual", rolled="4", modifier="2")
        )
        roll = CampaignRoll.objects.get()
        response = client.post(roll_url(roll), {"outcome": "Rare item available."})
        assert response.status_code == 302
        client.post(roll_url(roll), {"outcome": "Rare item available."})
        roll.refresh_from_db()
        assert (roll.rolled, roll.total, roll.outcome) == (4, 6, "Rare item available.")
        assert (
            campaign.events.filter(kind=CampaignEvent.Kind.DICE_ROLL_NOTED).count() == 1
        )
        for route in ["n26-campaign", "n26-campaign-log"]:
            body = client.get(reverse(route, args=[campaign.pk])).content.decode()
            assert "D6: 4 + 2 = 6" in body
            assert "Rare trade" in body
            assert "Rare item available." in body
        client.force_login(campaign.owner)
        assert client.get(roll_url(roll)).status_code == 200
        assert (
            client.post(
                roll_url(roll), {"outcome": "Changed by someone else"}
            ).status_code
            == 404
        )

    def test_changing_and_clearing_notes_preserves_each_change_in_the_log(
        self, client, campaign, player
    ):
        client.post(
            record_url(campaign), payload(source="manual", rolled="4", modifier="2")
        )
        roll = CampaignRoll.objects.get()
        notes = ["Rare item available.", "Rare item bought.", ""]
        for note in notes:
            assert client.post(roll_url(roll), {"outcome": note}).status_code == 302
        assert client.post(roll_url(roll), {"outcome": ""}).status_code == 302
        roll.refresh_from_db()
        assert (roll.rolled, roll.modifier, roll.total, roll.outcome) == (4, 2, 6, "")
        assert (
            list(
                campaign.events.filter(kind=CampaignEvent.Kind.DICE_ROLL_NOTED)
                .order_by("created", "pk")
                .values_list("note", flat=True)
            )
            == notes
        )
        assert campaign.events.filter(kind=CampaignEvent.Kind.DICE_ROLLED).count() == 1
        body = client.get(
            reverse("n26-campaign-log", args=[campaign.pk])
        ).content.decode()
        assert "Rare item available." in body
        assert "Rare item bought." in body
        assert "cleared the outcome note for Rare trade" in body

    def test_roll_attribution_prevents_battle_removal_after_confirmation(
        self, client, campaign, player
    ):
        with campaign_operation(campaign, actor=campaign.owner) as act:
            battle = act.record_battle(date(2026, 10, 2), scenario="Stand-off")
        remove = reverse("n26-campaign-remove-battle", args=[campaign.pk, battle.pk])
        detail = reverse("n26-battle", args=[campaign.pk, battle.pk])
        client.force_login(campaign.owner)
        assert not client.get(remove).context["has_history"]
        with campaign_operation(campaign, actor=player) as act:
            roll = act.record_roll(
                request_key=uuid4(),
                reason="Trade",
                dice="d6",
                source="generated",
                battle=battle,
            )
        assert client.get(remove).context["has_history"]
        assert remove not in client.get(detail).content.decode()
        response = client.post(remove, {"revision": battle.revision}, follow=True)
        assert (
            "You cannot remove a battle with recorded dice rolls."
            in response.content.decode()
        )
        with pytest.raises(Refusal, match="recorded dice rolls"):
            with campaign_operation(campaign, actor=campaign.owner) as act:
                act.remove_battle(battle, revision=battle.revision)
        roll.refresh_from_db()
        assert roll.battle_id == battle.pk
        assert Battle.objects.filter(pk=battle.pk).exists()
        assert not campaign.events.filter(
            kind=CampaignEvent.Kind.BATTLE_REMOVED
        ).exists()
        assert (
            str(battle.pk)
            in client.get(
                reverse("n26-campaign-log", args=[campaign.pk])
            ).content.decode()
        )

    def test_related_choices_are_scoped_and_preserved(
        self, client, campaign, player, gang_type, campaign_type
    ):
        gang = found_gang("Ashen Choir", gang_type, owner=player)
        client.force_login(campaign.owner)
        client.post(
            reverse("n26-campaign-add-gang", args=[campaign.pk]), {"gang": gang.pk}
        )
        with campaign_operation(campaign, actor=campaign.owner) as act:
            battle = act.record_battle(date(2026, 10, 2), [gang], scenario="Stand-off")
        elsewhere = found_campaign("Elsewhere", campaign_type, owner=campaign.owner)
        with campaign_operation(elsewhere, actor=campaign.owner) as act:
            foreign = act.record_battle(date(2026, 10, 2), scenario="Ambush")
        client.force_login(player)
        body = client.get(record_url(campaign)).content.decode()
        assert "Ashen Choir" in body and "Stand-off" in body
        assert "Ambush" not in body
        assert (
            client.post(record_url(campaign), payload(battle=foreign.pk)).status_code
            == 200
        )
        assert not CampaignRoll.objects.exists()
        client.post(record_url(campaign), payload(gang=gang.pk, battle=battle.pk))
        roll = CampaignRoll.objects.get()
        assert roll.gang == gang and roll.battle == battle
        assert (
            client.get(
                reverse("n26-campaign-roll", args=[elsewhere.pk, roll.pk])
            ).status_code
            == 404
        )
        assert (
            client.get(
                reverse("n26-campaign-roll", args=[campaign.pk, "bad-id"])
            ).status_code
            == 404
        )

    def test_the_flag_and_archive_gate_both_roll_pages(self, client, campaign):
        client.post(record_url(campaign), payload())
        roll = CampaignRoll.objects.get()
        urls = [record_url(campaign), roll_url(roll)]
        flag = FeatureFlag.objects.get(slug=CAMPAIGNS)
        flag.availability = Availability.OFF
        flag.save()
        for url in urls:
            assert client.get(url).status_code == 404
            assert client.post(url, payload()).status_code == 404
        flag.availability = Availability.EVERYONE
        flag.save()
        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.archive()
        for url in urls:
            assert client.get(url).status_code == 404


class TestOperationGuards:
    def test_removal_after_a_form_opens_is_rechecked_at_write_time(
        self, campaign, player
    ):
        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.remove_player(campaign.participants.get(user=player))
        with pytest.raises(Refusal), campaign_operation(campaign, actor=player) as act:
            act.record_roll(
                request_key=uuid4(), reason="Trade", dice="d6", source="generated"
            )
        with pytest.raises(Refusal), campaign_operation(campaign, actor=player) as act:
            act.record_battle(date(2026, 10, 2), scenario="Stand-off")

    def test_operations_refuse_foreign_attribution_and_invalid_physical_rolls(
        self, campaign, campaign_type, gang_type
    ):
        foreign_gang = found_gang("Elsewhere", gang_type, owner=campaign.owner)
        foreign_campaign = found_campaign(
            "Elsewhere", campaign_type, owner=campaign.owner
        )
        with campaign_operation(foreign_campaign, actor=campaign.owner) as act:
            foreign_battle = act.record_battle(date(2026, 10, 2), scenario="Ambush")
        for fields in [
            {"gang": foreign_gang},
            {"battle": foreign_battle},
            {"source": "manual", "rolled": 17, "dice": "d66"},
        ]:
            args = {
                "request_key": uuid4(),
                "reason": "Trade",
                "dice": "d6",
                "source": "generated",
                **fields,
            }
            with (
                pytest.raises(Refusal),
                campaign_operation(campaign, actor=campaign.owner) as act,
            ):
                act.record_roll(**args)
        assert not CampaignRoll.objects.exists()

    def test_a_request_key_cannot_be_reused_by_another_player(self, campaign, player):
        key = uuid4()
        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.record_roll(
                request_key=key, reason="Trade", dice="d6", source="generated"
            )
        with pytest.raises(Refusal), campaign_operation(campaign, actor=player) as act:
            act.record_roll(
                request_key=key, reason="Trade", dice="d6", source="generated"
            )

    @pytest.mark.django_db(transaction=True)
    def test_simultaneous_submissions_generate_one_roll(self, campaign, monkeypatch):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        from django.db import close_old_connections

        from n26.core.models import Campaign

        key = uuid4()
        ready = Barrier(2)
        roller = Mock(return_value=4)
        monkeypatch.setattr(Dice, "roll", roller)

        def record():
            close_old_connections()
            try:
                found = Campaign.objects.get(pk=campaign.pk)
                ready.wait(timeout=10)
                with campaign_operation(found, actor=found.owner) as act:
                    roll = act.record_roll(
                        request_key=key, reason="Trade", dice="d6", source="generated"
                    )
                return roll.pk
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: record(), range(2)))
        assert results[0] == results[1]
        assert CampaignRoll.objects.count() == 1
        assert campaign.events.filter(kind=CampaignEvent.Kind.DICE_ROLLED).count() == 1
        assert roller.call_count == 1


class TestCampaignLogQueries:
    @pytest.mark.parametrize(
        "route",
        [
            "n26-campaign",
            "n26-campaign-log",
            "n26-battle",
            "n26-campaign-remove-battle",
        ],
    )
    def test_more_attributed_rolls_add_no_queries(
        self, client, campaign, player, gang_type, route
    ):
        gang = found_gang("Ashen Choir", gang_type, owner=player)
        client.force_login(campaign.owner)
        client.post(
            reverse("n26-campaign-add-gang", args=[campaign.pk]), {"gang": gang.pk}
        )
        with campaign_operation(campaign, actor=campaign.owner) as act:
            battle = act.record_battle(date(2026, 10, 2), [gang], scenario="Stand-off")

        def add_roll():
            with campaign_operation(campaign, actor=player) as act:
                act.record_roll(
                    request_key=uuid4(),
                    reason="Trade",
                    dice="d6",
                    source="generated",
                    gang=gang,
                    battle=battle,
                )

        args = (
            [campaign.pk, battle.pk]
            if route in ("n26-battle", "n26-campaign-remove-battle")
            else [campaign.pk]
        )
        url = reverse(route, args=args)
        add_roll()
        client.get(url)
        with CaptureQueriesContext(connection) as before:
            client.get(url)
        for _ in range(6):
            add_roll()
        with CaptureQueriesContext(connection) as after:
            response = client.get(url)
        assert response.status_code == 200
        assert len(after) <= len(before)
