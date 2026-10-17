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
from n26.core import history
from n26.core.campaigns import BattleStake, battle_stake, campaign_operation
from n26.core.forms import BattleForm
from n26.core.history import build, latest
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
        "stake_versions": BattleForm(
            playing=Gang.objects.all(), battle=table.battle
        ).initial.get("stake_versions", ""),
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
    def test_unclaimed_assets_and_assets_participants_hold_are_offered(
        self, table, default_pack
    ):
        territory = table.ruins.asset.asset_type
        held_elsewhere = add_asset(
            table.campaign, create_asset("Sump Market", territory)
        )
        assign_asset(held_elsewhere, table.bystanders)
        unclaimed = add_asset(table.campaign, create_asset("Bone Shrine", territory))

        form = BattleForm(playing=Gang.objects.all(), battle=table.battle)

        assert set(form.fields["stake"].queryset) == {table.ruins, unclaimed}
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
        with campaign_operation(table.campaign, actor=table.arbitrator) as act:
            act.remove_asset(table.ruins)

        form = BattleForm(playing=Gang.objects.all(), battle=table.battle)

        assert "stake" not in form.fields
        assert "stake_awarded_to" not in form.fields

    def test_a_gang_added_in_the_same_save_can_win_it(self, client, table):
        response = client.post(
            edit_url(table),
            form_fields(
                table,
                gangs=[str(g.pk) for g in (table.choir, table.kings, table.bystanders)],
                winners=[str(table.bystanders.pk)],
                stake_awarded_to=str(table.bystanders.pk),
            ),
        )

        assert response.status_code == 302
        assert holder(table) == table.bystanders

    def test_another_campaigns_asset_is_refused(self, client, table, gang_type):
        other = found_campaign(
            "Elsewhere", table.campaign.campaign_type, owner=table.arbitrator
        )
        outsiders = found_gang("Outsiders", gang_type, owner=table.arbitrator)
        join_campaign(outsiders, other)
        foreign = add_asset(
            other, create_asset("Far Ruins", table.ruins.asset.asset_type)
        )
        assign_asset(foreign, outsiders)

        response = client.post(
            edit_url(table), form_fields(table, stake=str(foreign.pk))
        )

        assert response.status_code == 200
        assert (
            "Select a territory that is unclaimed or held by a participant."
            in response.content.decode()
        )
        foreign.refresh_from_db()
        assert foreign.holder.gang == outsiders
        assert Battle.objects.get(pk=table.battle.pk).stake is None
        assert holder(table) == table.choir


class TestWhereItCanGo:
    def options(self, table):
        table.battle.refresh_from_db()
        form = BattleForm(playing=Gang.objects.all(), battle=table.battle)
        return [label for _, label in form.fields["stake_awarded_to"].choices]

    def test_before_a_stake_is_set_the_empty_choice_says_what_it_does(self, table):
        assert self.options(table) == [
            "Not awarded",
            "Ashen Choir",
            "Rust Kings",
        ]

    def test_the_gang_that_held_it_is_offered_once(self, table):
        stake_as(table, None)

        assert self.options(table) == ["Not awarded", "Ashen Choir", "Rust Kings"]

    def test_clearing_the_award_returns_it_to_the_first_holder(self, client, table):
        client.post(edit_url(table), form_fields(table))

        assert self.options(table) == ["Not awarded", "Ashen Choir", "Rust Kings"]
        client.post(edit_url(table), form_fields(table, stake_awarded_to=""))
        assert holder(table) == table.choir

    def test_an_explicit_award_to_the_first_holder_stays_selected(self, table):
        stake_as(table, table.choir)
        table.battle.refresh_from_db()

        form = BattleForm(playing=Gang.objects.all(), battle=table.battle)

        assert form.initial["stake_awarded_to"] == table.choir.pk

    def test_editing_the_scenario_preserves_an_award_to_the_first_holder(
        self, client, table
    ):
        stake_as(table, table.choir)
        response = client.get(edit_url(table))
        document = BeautifulSoup(response.content, "html.parser")
        assert document.select_one("#battle-stake-awarded-to option[selected]")[
            "value"
        ] == str(table.choir.pk)
        data = html_fields(response, scenario="Stand-off at dusk")
        assert client.post(edit_url(table), data).status_code == 302
        table.battle.refresh_from_db()
        assert table.battle.scenario == "Stand-off at dusk"
        assert table.battle.stake_awarded_to_id == table.choir.pk
        assert holder(table) == table.choir
        assert not moves(table)


class TestRemovingTheBattle:
    def test_a_battle_that_moved_its_stake_cannot_be_removed(self, client, table):
        client.post(edit_url(table), form_fields(table))
        table.battle.refresh_from_db()

        response = client.post(
            reverse(
                "n26-campaign-remove-battle",
                args=[table.campaign.pk, table.battle.pk],
            ),
            {"revision": table.battle.revision},
            follow=True,
        )

        assert (
            "cannot remove a battle with recorded gang history"
            in response.content.decode()
        )
        assert Battle.objects.filter(pk=table.battle.pk).exists()
        assert holder(table) == table.kings


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
        text = " ".join(stake.get_text().split())
        assert "Territory staked" in text
        assert f"Old Ruins [{str(table.ruins.pk)[-6:]}] · Goes to Rust Kings" in text
        # It is where it went, so the holder is not named twice.
        assert "Held by" not in text
        assert "Only the campaign's arbitrator can change this on Edit battle." in text
        assert stake.select("select, input, button") == []

    def test_the_arbitrator_is_not_told_to_ask_themselves(self, client, table):
        stake_as(table, table.kings)

        page = client.get(
            reverse("n26-battle", args=[table.campaign.pk, table.battle.pk])
        )

        text = stake_text(page)
        assert f"Old Ruins [{str(table.ruins.pk)[-6:]}] · Goes to Rust Kings" in text
        assert "arbitrator" not in text


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
            assert "Old Ruins" in text
            assert "Moved from Ashen Choir to Rust Kings" in text
            assert "Already applied" in text
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

    def test_a_stake_not_given_away_stays_with_its_holder(self):
        def outcome(holder):
            return BattleStake(
                label="Territory staked", name="Old Ruins", awarded_to="", holder=holder
            ).outcome

        assert outcome("Rust Kings") == "Stays with Rust Kings"
        assert outcome("") == "Not given to any gang"

    def test_the_note_names_a_holder_the_outcome_does_not(self):
        def note(awarded_to, holder, arbitrator=False):
            return BattleStake(
                label="Territory staked",
                name="Old Ruins",
                awarded_to=awarded_to,
                holder=holder,
                arbitrator=arbitrator,
            ).note

        assert note("Rust Kings", "Rust Kings", arbitrator=True) == ""
        assert note("", "Rust Kings", arbitrator=True) == ""
        assert note("Rust Kings", "Bystanders", arbitrator=True) == (
            "Held by Bystanders."
        )
        assert note("Rust Kings", "Bystanders") == (
            "Held by Bystanders. Only the campaign's arbitrator can change "
            "this on Edit battle."
        )


def stake_text(response):
    stake = BeautifulSoup(response.content, "html.parser").select_one(
        "[data-battle-stake]"
    )
    assert stake is not None
    return " ".join(stake.get_text().split())


class TestGangHistory:
    """Each gang's history says the stake moved in the battle, from the
    gang's own side, and names nobody as the one who lost it."""

    def told(self, gang, viewer=None):
        return [
            (act.actor, "".join(span.text for span in act.spans))
            for act in build(gang, viewer=viewer)
            if "Old Ruins" in "".join(span.text for span in act.spans)
        ]

    def test_the_award_is_won_and_lost_in_the_battle(self, table):
        stake_as(table, table.kings)

        assert self.told(table.choir)[-1] == ("", "Lost Old Ruins in Stand-off")
        assert self.told(table.kings) == [("", "Won Old Ruins in Stand-off")]

    def test_a_correction_says_the_battle_was_corrected(self, table):
        stake_as(table, table.kings)
        stake_as(table, None)
        stake_as(table, table.kings)

        assert self.told(table.kings) == [
            ("", "Won Old Ruins in Stand-off"),
            ("", "Returned Old Ruins after Stand-off was corrected"),
            ("", "Won Old Ruins in Stand-off"),
        ]
        assert self.told(table.choir)[-3:] == [
            ("", "Lost Old Ruins in Stand-off"),
            ("", "Got Old Ruins back after Stand-off was corrected"),
            ("", "Lost Old Ruins in Stand-off"),
        ]

    def test_the_correction_is_recorded_on_the_moves_it_undoes(self, table):
        stake_as(table, table.kings)
        stake_as(table, None)

        undo = LedgerEvent.objects.filter(
            campaign_asset=table.ruins, reversal_of__isnull=False
        ).select_related("reversal_of")
        assert {(e.gang, e.kind, e.reversal_of.kind) for e in undo} == {
            (table.kings, LedgerEvent.Kind.LOST, LedgerEvent.Kind.GAINED),
            (table.choir, LedgerEvent.Kind.GAINED, LedgerEvent.Kind.LOST),
        }

    def test_the_snapshot_and_the_full_history_agree(self, table, monkeypatch):
        stake_as(table, table.kings)
        stake_as(table, None)
        # A snapshot too short to see the award still reads the
        # correction as one.
        monkeypatch.setattr(history, "SNAPSHOT_WINDOW", 1)

        for gang in (table.kings, table.choir):
            full = ["".join(span.text for span in act.spans) for act in build(gang)][-1]
            snapshot = [
                "".join(span.text for span in act.spans)
                for act in latest(gang, limit=1)
            ]
            assert snapshot == [full]
            assert full.endswith("after Stand-off was corrected")

    def test_a_transfer_on_the_campaign_page_reads_as_before(self, table):
        transfer_asset(table.ruins, table.kings)

        assert self.told(table.kings) == [
            ("arbitrator", "gained the territory Old Ruins")
        ]


class TestUnclaimedStakes:
    def test_recording_a_stake_before_the_battle_awards_nothing(self, client, table):
        unassign_asset(table.ruins)
        before = LedgerEvent.objects.count()
        response = client.post(
            edit_url(table),
            form_fields(
                table,
                result="not_recorded",
                winners=[],
                stake_awarded_to="",
            ),
        )
        assert response.status_code == 302
        table.battle.refresh_from_db()
        assert table.battle.stake == table.ruins
        assert table.battle.stake_awarded_to is None
        assert table.battle.stake_transfer_mark is None
        assert holder(table) is None
        assert LedgerEvent.objects.count() == before
        assert "Old Ruins" in stake_text(
            client.get(
                reverse(
                    "n26-battle",
                    args=[table.campaign.pk, table.battle.pk],
                )
            )
        )

    def test_equal_named_unclaimed_copies_can_be_selected_independently(
        self, client, table
    ):
        unassign_asset(table.ruins)
        other = add_asset(table.campaign, table.ruins.asset)
        form = BattleForm(playing=Gang.objects.all(), battle=table.battle)
        labels = {str(value): label for value, label in form.fields["stake"].choices}
        assert labels[str(table.ruins.pk)] != labels[str(other.pk)]
        response = client.post(
            edit_url(table),
            form_fields(
                table,
                stake=str(other.pk),
                stake_awarded_to="",
            ),
        )
        assert response.status_code == 302
        table.battle.refresh_from_db()
        assert table.battle.stake_id == other.pk
        assert holder(table) is None
        other.refresh_from_db()
        assert other.holder is None

    def test_explicitly_awarding_an_unclaimed_stake_is_journalled_once(
        self, client, table
    ):
        unassign_asset(table.ruins)
        data = form_fields(table)
        assert client.post(edit_url(table), data).status_code == 302
        assert holder(table) == table.kings
        assert len(moves(table)) == 1
        table.battle.refresh_from_db()
        gained = LedgerEvent.objects.get(
            battle=table.battle,
            campaign_asset=table.ruins,
        )
        assert gained.kind == LedgerEvent.Kind.GAINED
        assert gained.batch == table.battle.stake_transfer_mark
        assert client.post(edit_url(table), data).status_code == 200
        assert len(moves(table)) == 1
        assert (
            client.post(
                edit_url(table), form_fields(table, scenario="Renamed")
            ).status_code
            == 302
        )
        assert len(moves(table)) == 1

    def test_clearing_an_award_returns_the_stake_to_the_unclaimed_pool(self, table):
        unassign_asset(table.ruins)
        stake_as(table, table.kings)
        gained = LedgerEvent.objects.get(
            battle=table.battle,
            kind=LedgerEvent.Kind.GAINED,
        )
        stake_as(table, None)
        assert holder(table) is None
        returned = LedgerEvent.objects.get(reversal_of=gained)
        assert returned.kind == LedgerEvent.Kind.LOST
        assert returned.battle_id == table.battle.pk
        table.battle.refresh_from_db()
        assert table.battle.stake_transfer_mark is None

    def test_correcting_the_winner_reverses_the_unclaimed_award(self, table):
        unassign_asset(table.ruins)
        stake_as(table, table.kings)
        stake_as(table, table.choir)
        assert holder(table) == table.choir
        assert [kind for _, kind, _ in moves(table)] == [
            LedgerEvent.Kind.GAINED,
            LedgerEvent.Kind.LOST,
            LedgerEvent.Kind.GAINED,
        ]

    def test_a_stale_unclaimed_choice_cannot_take_a_participants_new_holding(
        self, client, table
    ):
        unassign_asset(table.ruins)
        data = form_fields(table)
        assign_asset(table.ruins, table.choir)
        response = client.post(edit_url(table), data)
        assert response.status_code == 200
        assert "This stake changed hands" in response.content.decode()
        assert holder(table) == table.choir
        assert not moves(table)

    def test_moving_an_awarded_stake_away_and_back_blocks_a_correction(self, table):
        unassign_asset(table.ruins)
        stake_as(table, table.kings)
        transfer_asset(table.ruins, table.choir)
        transfer_asset(table.ruins, table.kings)
        with pytest.raises(Refusal, match="cannot move back"):
            stake_as(table, None)
        assert holder(table) == table.kings

    def test_another_campaigns_unclaimed_stake_is_refused(self, client, table):
        other = found_campaign(
            "Elsewhere", table.campaign.campaign_type, owner=table.arbitrator
        )
        foreign = add_asset(other, table.ruins.asset)
        response = client.post(
            edit_url(table), form_fields(table, stake=str(foreign.pk))
        )
        assert response.status_code == 200
        foreign.refresh_from_db()
        assert foreign.holder is None
        assert not moves(table)

    def test_a_stale_choice_claimed_by_a_bystander_is_not_silently_ignored(
        self, client, table
    ):
        unassign_asset(table.ruins)
        data = form_fields(table)
        assign_asset(table.ruins, table.bystanders)
        response = client.post(edit_url(table), data)
        assert response.status_code == 200
        assert "The available stakes changed" in response.content.decode()
        assert holder(table) == table.bystanders
        assert not moves(table)

    def test_more_unclaimed_stakes_do_not_add_per_choice_queries(self, client, table):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def count():
            client.get(edit_url(table))
            with CaptureQueriesContext(connection) as queries:
                response = client.get(edit_url(table))
                assert response.status_code == 200
            return len(queries)

        before = count()
        for _ in range(5):
            add_asset(table.campaign, table.ruins.asset)
        assert count() <= before

    def test_a_tampered_ownership_snapshot_cannot_award_a_stake(self, client, table):
        unassign_asset(table.ruins)
        data = form_fields(table, stake_versions="tampered")
        response = client.post(edit_url(table), data)
        assert response.status_code == 200
        assert "The available stakes changed" in response.content.decode()
        assert holder(table) is None
        assert not moves(table)

    @pytest.mark.parametrize("select_stake", [False, True])
    def test_a_missing_ownership_snapshot_shows_a_reload_message(
        self, client, table, select_stake
    ):
        data = form_fields(table)
        del data["stake_versions"]
        if not select_stake:
            data.update(stake="", stake_awarded_to="")
        response = client.post(edit_url(table), data)
        assert response.status_code == 200
        message = "The available stakes changed. Reload the battle before saving."
        assert message in response.context["form"].non_field_errors()
        assert message in BeautifulSoup(response.content, "html.parser").get_text()
        assert holder(table) == table.choir
        assert not moves(table)

    def test_a_newly_available_stake_requires_a_visible_reload_before_saving(
        self, client, table
    ):
        transfer_asset(table.ruins, table.bystanders)
        response = client.get(edit_url(table))
        assert "stake_versions" not in response.context["form"].fields
        data = html_fields(response, scenario="Stand-off at dusk")
        assert "stake_versions" not in data
        unassign_asset(table.ruins)
        response = client.post(edit_url(table), data)
        message = "The available stakes changed. Reload the battle before saving."
        assert response.status_code == 200
        assert message in response.context["form"].non_field_errors()
        assert message in BeautifulSoup(response.content, "html.parser").get_text()
        table.battle.refresh_from_db()
        assert table.battle.scenario == "Stand-off"
        assert holder(table) is None
        assert not moves(table)
        refreshed = client.get(edit_url(table))
        assert (
            client.post(
                edit_url(table), html_fields(refreshed, scenario="Stand-off at dusk")
            ).status_code
            == 302
        )
        table.battle.refresh_from_db()
        assert table.battle.scenario == "Stand-off at dusk"
        assert table.battle.stake_id is None
        assert holder(table) is None
        assert not moves(table)

    def test_an_unclaimed_award_and_correction_remain_in_gang_history(self, table):
        unassign_asset(table.ruins)
        stake_as(table, table.kings)
        stake_as(table, None)
        lines = [
            text
            for act in build(table.kings)
            if "Old Ruins" in (text := "".join(span.text for span in act.spans))
        ]
        assert lines == [
            "Won Old Ruins in Stand-off",
            "Returned Old Ruins after Stand-off was corrected",
        ]

    def test_changing_from_a_held_stake_can_award_an_unclaimed_copy_to_that_holder(
        self, client, table
    ):
        stake_as(table, None)
        other = add_asset(table.campaign, table.ruins.asset)
        response = client.post(
            edit_url(table),
            form_fields(
                table,
                stake=str(other.pk),
                stake_awarded_to=str(table.choir.pk),
            ),
        )
        assert response.status_code == 302
        table.battle.refresh_from_db()
        other.refresh_from_db()
        assert table.battle.stake_id == other.pk
        assert other.holder.gang_id == table.choir.pk
        assert holder(table) == table.choir


@pytest.mark.django_db(transaction=True)
def test_correcting_an_unclaimed_award_can_finish_beside_a_ransom_payment(
    table, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from queue import Queue
    from threading import Event, local
    from time import monotonic, sleep

    from django.db import close_old_connections, connection

    from n26.core import operations
    from n26.core.reconcile import assert_reconciled

    earlier, later = sorted([table.choir, table.kings], key=lambda gang: gang.pk)
    for gang in (earlier, later):
        with operations.operation(gang, actor=table.arbitrator) as op:
            op.set_budget(100)
    unassign_asset(table.ruins)
    stake_as(table, later)
    held = Event()
    proceed = Event()
    payment_pid = Queue()
    worker = local()
    original_hold = operations._hold

    def pause_after_first_correction_lock(*gangs):
        original_hold(*gangs)
        if getattr(worker, "correcting", False) and not getattr(
            worker, "paused", False
        ):
            worker.paused = True
            held.set()
            assert proceed.wait(10), "The payment did not reach its gang locks."

    monkeypatch.setattr(operations, "_hold", pause_after_first_correction_lock)

    def correct():
        close_old_connections()
        worker.correcting = True
        try:
            stake_as(table, earlier)
        finally:
            close_old_connections()

    def pay():
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                payment_pid.put(cursor.fetchone()[0])
            with operations.operation(
                earlier, actor=table.arbitrator, also=[later]
            ) as op:
                op.transfer(later, 10, note="ransom")
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        correction = pool.submit(correct)
        try:
            assert held.wait(10), "The correction did not reach its gang locks."
            payment = pool.submit(pay)
            pid = payment_pid.get(timeout=10)
            deadline = monotonic() + 10
            while monotonic() < deadline:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT cardinality(pg_blocking_pids(%s))", [pid])
                    if cursor.fetchone()[0]:
                        break
                sleep(0.01)
            else:
                pytest.fail("The payment did not wait for the correction's gang lock.")
        finally:
            proceed.set()
        correction.result(timeout=10)
        payment.result(timeout=10)

    table.battle.refresh_from_db()
    assert table.battle.stake_awarded_to_id == earlier.pk
    assert holder(table) == earlier
    earlier.refresh_from_db()
    later.refresh_from_db()
    assert earlier.credits == 90
    assert later.credits == 110
    assert LedgerEvent.objects.filter(kind=LedgerEvent.Kind.TRANSFERRED).count() == 2
    assert_reconciled(earlier)
    assert_reconciled(later)
