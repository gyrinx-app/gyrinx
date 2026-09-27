"""The asset a battle staked: the arbitrator records it and where it went,
on Edit battle, and saving moves it once.

A gang's report never moves it. Both participants' reports show the same
holder, read from the asset.
"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.apps import apps
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import battle_stake, campaign_operation
from n26.core.forms import BattleForm
from n26.core.models import Battle, Gang, LedgerEvent, PostBattleReport
from n26.core.operations import Refusal
from n26.core.post_battle import start_report
from n26.flags import CAMPAIGNS
from n26.library.authoring import create_asset
from n26.library.core_campaign import seed_core_campaign
from n26.library.models import CampaignType
from n26.tests.sandbox.actions import (
    add_asset,
    assign_asset,
    found_campaign,
    found_gang,
    join_campaign,
    transfer_asset,
    unassign_asset,
)
from n26.tests.test_views_post_battle import html_fields

pytestmark = pytest.mark.django_db


@pytest.fixture
def table(client, default_pack, gang_type):
    """A campaign with two gangs in one battle and a third that did not
    play; the Choir holds the Old Ruins."""
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
    seed_core_campaign(apps)
    core = CampaignType.objects.get(name="Territory campaign")
    arbitrator = User.objects.create_user("arbitrator")
    player = User.objects.create_user("player")
    rival = User.objects.create_user("rival")
    campaign = found_campaign("Dust Falls", core, owner=arbitrator)
    choir = found_gang("Ashen Choir", gang_type, owner=player)
    kings = found_gang("Rust Kings", gang_type, owner=rival)
    bystanders = found_gang("Bystanders", gang_type, owner=rival)
    for gang in (choir, kings, bystanders):
        join_campaign(gang, campaign)
    territory = core.asset_types.get(label_singular="Territory")
    ruins = add_asset(campaign, create_asset("Old Ruins", territory))
    assign_asset(ruins, choir)
    with campaign_operation(campaign, actor=arbitrator) as act:
        battle = act.record_battle(
            date(2026, 9, 20), [choir, kings], scenario="Stand-off"
        )
    client.force_login(arbitrator)
    return SimpleNamespace(
        arbitrator=arbitrator,
        player=player,
        campaign=campaign,
        choir=choir,
        kings=kings,
        bystanders=bystanders,
        ruins=ruins,
        battle=battle,
    )


def edit_url(table):
    return reverse(
        "n26-campaign-edit-battle", args=[table.campaign.pk, table.battle.pk]
    )


def form_fields(table, **changes):
    table.battle.refresh_from_db()
    return {
        "scenario": "Stand-off",
        "date": "2026-09-20",
        "result": "winners",
        "gangs": [str(table.choir.pk), str(table.kings.pk)],
        "winners": [str(table.kings.pk)],
        "revision": table.battle.revision,
        "stake": str(table.ruins.pk),
        "stake_awarded_to": str(table.kings.pk),
    } | changes


def holder(table):
    table.ruins.refresh_from_db()
    return table.ruins.holder.gang if table.ruins.holder else None


def moves(table):
    return list(
        LedgerEvent.objects.filter(
            campaign_asset=table.ruins, battle=table.battle
        ).values_list("gang__name", "kind", "batch")
    )


def stake_as(table, awarded_to, *, revision=None):
    table.battle.refresh_from_db()
    with campaign_operation(table.campaign, actor=table.arbitrator) as act:
        return act.edit_battle(
            table.battle,
            scenario="Stand-off",
            date=date(2026, 9, 20),
            gangs=[table.choir, table.kings],
            result="not_recorded",
            winners=[],
            revision=table.battle.revision if revision is None else revision,
            stake=table.ruins,
            stake_awarded_to=awarded_to,
        )


class TestSavingTheStake:
    def test_saving_moves_the_stake_to_the_gang_it_goes_to(self, client, table):
        response = client.post(edit_url(table), form_fields(table))

        assert response.status_code == 302
        assert holder(table) == table.kings
        table.battle.refresh_from_db()
        mark = table.battle.stake_transfer_mark
        assert mark is not None
        assert sorted(moves(table)) == [
            ("Ashen Choir", LedgerEvent.Kind.LOST, mark),
            ("Rust Kings", LedgerEvent.Kind.GAINED, mark),
        ]

    def test_saving_twice_moves_it_once(self, client, table):
        client.post(edit_url(table), form_fields(table))
        response = client.post(
            edit_url(table), form_fields(table, scenario="Stand-off at dusk")
        )

        assert response.status_code == 302
        assert holder(table) == table.kings
        assert len(moves(table)) == 2

    def test_a_repeated_submit_is_refused_and_moves_nothing(self, client, table):
        data = form_fields(table)
        client.post(edit_url(table), data)
        response = client.post(edit_url(table), data)

        assert response.status_code == 200
        assert "This battle changed" in response.content.decode()
        assert len(moves(table)) == 2

    def test_staying_with_its_holder_moves_nothing(self, client, table):
        client.post(edit_url(table), form_fields(table, stake_awarded_to=""))

        table.battle.refresh_from_db()
        assert table.battle.stake == table.ruins
        assert table.battle.stake_transfer_mark is None
        assert holder(table) == table.choir
        assert moves(table) == []

    def test_going_to_its_holder_moves_nothing(self, table):
        battle = stake_as(table, table.choir)

        assert battle.stake_transfer_mark is None
        assert holder(table) == table.choir
        assert moves(table) == []

    def test_a_winner_without_a_stake_is_refused(self, table):
        with pytest.raises(Refusal, match="Select what was staked"):
            with campaign_operation(table.campaign, actor=table.arbitrator) as act:
                act.edit_battle(
                    table.battle,
                    scenario="Stand-off",
                    date=date(2026, 9, 20),
                    gangs=[table.choir, table.kings],
                    result="not_recorded",
                    winners=[],
                    revision=table.battle.revision,
                    stake=None,
                    stake_awarded_to=table.kings,
                )

    def test_editing_without_naming_the_stake_keeps_it(self, table):
        stake_as(table, table.kings)
        table.battle.refresh_from_db()
        with campaign_operation(table.campaign, actor=table.arbitrator) as act:
            act.edit_battle(
                table.battle,
                scenario="Renamed",
                date=date(2026, 9, 20),
                gangs=[table.choir, table.kings],
                result="not_recorded",
                winners=[],
                revision=table.battle.revision,
            )

        table.battle.refresh_from_db()
        assert table.battle.stake == table.ruins
        assert table.battle.stake_awarded_to == table.kings
        assert len(moves(table)) == 2


class TestWhatCanBeStaked:
    def test_only_assets_participants_hold_are_offered(self, table, default_pack):
        territory = table.ruins.asset.asset_type
        held_elsewhere = add_asset(
            table.campaign, create_asset("Sump Market", territory)
        )
        assign_asset(held_elsewhere, table.bystanders)
        add_asset(table.campaign, create_asset("Bone Shrine", territory))

        form = BattleForm(playing=Gang.objects.all(), battle=table.battle)

        assert list(form.fields["stake"].queryset) == [table.ruins]
        assert form.fields["stake"].label == "Territory staked"
        assert set(form.fields["stake_awarded_to"].queryset) == {
            table.choir,
            table.kings,
        }

    def test_an_asset_a_bystander_holds_is_refused(self, table):
        transfer_asset(table.ruins, table.bystanders)

        with pytest.raises(Refusal, match="No participant holds Old Ruins"):
            stake_as(table, table.kings)
        assert holder(table) == table.bystanders

    def test_nothing_to_stake_leaves_the_fields_out(self, table):
        unassign_asset(table.ruins)

        form = BattleForm(playing=Gang.objects.all(), battle=table.battle)

        assert "stake" not in form.fields
        assert "stake_awarded_to" not in form.fields


class TestCorrectingTheStake:
    def test_a_different_recipient_reverses_the_transfer_first(self, table):
        stake_as(table, table.kings)
        battle = stake_as(table, None)

        assert battle.stake_transfer_mark is None
        assert holder(table) == table.choir
        assert len(moves(table)) == 4

    def test_a_correction_after_it_changed_hands_is_refused(self, client, table):
        client.post(edit_url(table), form_fields(table))
        transfer_asset(table.ruins, table.bystanders)

        response = client.post(edit_url(table), form_fields(table, stake_awarded_to=""))

        assert response.status_code == 200
        assert (
            "Old Ruins cannot move back: the gang it went to no longer holds it. "
            "Transfer it on the campaign page." in response.content.decode()
        )
        assert holder(table) == table.bystanders
        table.battle.refresh_from_db()
        assert table.battle.stake_awarded_to == table.kings
        assert table.battle.stake_transfer_mark is not None


class TestWhoMovesTheStake:
    def test_a_gang_owner_cannot_open_or_save_edit_battle(self, client, table):
        client.force_login(table.player)

        assert client.get(edit_url(table)).status_code == 404
        response = client.post(edit_url(table), form_fields(table))

        assert response.status_code == 404
        assert holder(table) == table.choir
        assert Battle.objects.get(pk=table.battle.pk).stake is None

    def test_the_gang_owner_sees_the_stake_read_only(self, client, table):
        stake_as(table, table.kings)
        client.force_login(table.player)

        page = client.get(
            reverse("n26-battle", args=[table.campaign.pk, table.battle.pk])
        )

        stake = BeautifulSoup(page.content, "html.parser").select_one(
            "[data-battle-stake]"
        )
        assert "Territory staked" in stake.get_text()
        assert "Held by Rust Kings" in stake.get_text()
        assert stake.select("select, input, button") == []


class TestBothReportsAgree:
    def test_both_editors_and_receipts_name_the_holder_now(self, client, table):
        stake_as(table, table.kings)
        reports = {}
        for gang in (table.choir, table.kings):
            reports[gang.pk] = start_report(
                gang, actor=gang.owner, battle=table.battle, request_key=uuid4()
            )
        transfer_asset(table.ruins, table.bystanders)

        for gang in (table.choir, table.kings):
            client.force_login(gang.owner)
            report = reports[gang.pk]
            url = reverse("n26-post-battle-editor", args=[report.pk])
            editor = client.get(url)
            text = stake_text(editor)
            assert "Old Ruins · Goes to Rust Kings" in text
            assert "Held by Bystanders" in text
            applied = client.post(
                url,
                html_fields(editor, intent="apply", participation_confirmed="on"),
            )
            assert applied.status_code == 302, applied.content.decode()[:2000]
            receipt = client.get(applied.url)
            assert "Held by Bystanders" in stake_text(receipt)
        assert (
            PostBattleReport.objects.filter(
                battle=table.battle, state=PostBattleReport.State.APPLIED
            ).count()
            == 2
        )
        assert holder(table) == table.bystanders

    def test_no_stake_shows_nothing(self, table):
        assert battle_stake(table.battle) is None


def stake_text(response):
    stake = BeautifulSoup(response.content, "html.parser").select_one(
        "[data-battle-stake]"
    )
    assert stake is not None
    return " ".join(stake.get_text().split())
