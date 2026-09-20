"""A crew remembers models and their cards; participation is recorded later."""

from datetime import date
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext

from n26.core.campaigns import campaign_operation
from n26.core.crews import (
    CrewSelection,
    build_crew_sheet,
    crew_roster,
    save_crew,
    saved_card_key,
)
from n26.core.models import AssignmentSet, BattleCrew, CrewMember, LedgerEvent
from n26.core.operations import Refusal, operation
from n26.core.reconcile import assert_reconciled
from n26.core.status import Status
from n26.tests.sandbox.actions import (
    create_assignment_set,
    create_weapon,
    found_campaign,
    found_gang,
    give_weapon,
    hire,
    join_campaign,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def table(default_pack, gang_type, campaign_type, make_profile):
    owner = User.objects.create_user("crew-owner")
    arbitrator = User.objects.create_user("crew-arbitrator")
    campaign = found_campaign("Sump Road", campaign_type, owner=arbitrator)
    gang = found_gang("Iron Hounds", gang_type, owner=owner, budget=1000)
    join_campaign(gang, campaign)
    profile = make_profile("Gunner")
    models = [
        hire(gang, profile, name, paid=20) for name in ["Mara", "Nell", "Cal", "Vega"]
    ]
    gun = give_weapon(models[0], create_weapon("Autogun"), paid=15)
    knife = give_weapon(models[0], create_weapon("Knife"), paid=5)
    ranged = create_assignment_set(models[0], "Long range", [gun])
    close = create_assignment_set(models[0], "Close quarters", [knife])
    with campaign_operation(campaign, actor=arbitrator) as act:
        battle = act.record_battle(date(2026, 9, 20), [gang], scenario="Toll bridge")
    return SimpleNamespace(
        owner=owner,
        arbitrator=arbitrator,
        campaign=campaign,
        gang=gang,
        battle=battle,
        models=models,
        gun=gun,
        knife=knife,
        ranged=ranged,
        close=close,
        profile=profile,
    )


def save(table, selections=(), revision=0, **kwargs):
    return save_crew(
        battle=table.battle,
        gang=table.gang,
        actor=table.owner,
        revision=revision,
        selections=selections,
        **kwargs,
    ).crew


def select(model, role="starting", card="full", override=False):
    return CrewSelection(str(model.pk), role, str(card), override)


class TestSavedCrews:
    def test_card_selection_changes_no_gang_data_and_is_one_model_once(self, table):
        before = LedgerEvent.objects.filter(gang=table.gang).count()
        crew = save(
            table,
            [
                select(table.models[0], card=table.ranged.pk),
                select(table.models[1], role="reserve"),
            ],
            confirm=True,
        )
        assert crew.confirmed
        assert crew.revision == 1
        assert crew.members.count() == 2
        member = crew.members.get(miniature=table.models[0])
        assert member.card_name == "Long range"
        assert member.equipment_ids == [str(table.gun.pk)]
        assert member.rating == 40
        assert LedgerEvent.objects.filter(gang=table.gang).count() == before
        assert_reconciled(table.gang)

    def test_empty_draft_is_not_an_all_roster_crew(self, table):
        crew = save(table)
        assert not crew.confirmed
        assert not crew.members.exists()
        with pytest.raises(Refusal, match="at least one model"):
            save(table, revision=1, confirm=True)

    def test_duplicate_models_and_foreign_cards_are_refused(self, table):
        model = table.models[1]
        with pytest.raises(Refusal, match="only be selected once"):
            save(table, [select(model), select(model, role="reserve")])
        with pytest.raises(Refusal, match="no longer available"):
            save(table, [select(model, card=table.ranged.pk)])
        assert not BattleCrew.objects.exists()

    def test_named_cards_never_add_an_implicit_full_equipment_choice(self, table):
        roster = crew_roster(table.gang)
        mara = next(item for item in roster if item.miniature.pk == table.models[0].pk)
        assert {card.key for card in mara.cards} == {
            str(table.ranged.pk),
            str(table.close.pk),
        }
        with pytest.raises(Refusal, match="no longer available"):
            save(table, [select(table.models[0])])

    def test_saved_card_survives_rename_edit_and_deletion(self, table):
        crew = save(table, [select(table.models[0], card=table.ranged.pk)])
        member = crew.members.get()
        table.ranged.name = "Renamed"
        table.ranged.save()
        table.ranged.assignments.set([table.knife])
        crew = save(
            table,
            [select(table.models[0], card=saved_card_key(member))],
            revision=crew.revision,
        )
        assert crew.members.get().equipment_ids == [str(table.gun.pk)]
        assert crew.members.get().card_name == "Long range"
        table.ranged.delete()
        member.refresh_from_db()
        assert member.assignment_set_id is None
        crew = save(
            table,
            [select(table.models[0], card=saved_card_key(member))],
            revision=crew.revision,
        )
        sheet = build_crew_sheet(crew)
        assert [w.name for w in sheet.starting[0].card.weapons] == ["Autogun"]
        assert sheet.starting[0].card.rating == 40
        assert sheet.starting[0].member.card_name == "Long range"

    def test_removed_equipment_is_reported_without_replacing_the_card(self, table):
        crew = save(table, [select(table.models[0], card=table.ranged.pk)])
        with operation(table.gang, actor=table.owner) as act:
            act.remove(table.gun)
        sheet = build_crew_sheet(crew)
        assert sheet.starting[0].missing_equipment
        assert not sheet.starting[0].card.weapons
        assert sheet.starting[0].member.equipment_ids == [str(table.gun.pk)]
        assert_reconciled(table.gang)

    def test_stale_save_does_not_replace_newer_crew(self, table):
        crew = save(table, [select(table.models[1])])
        with pytest.raises(Refusal, match="changed while"):
            save(table, [select(table.models[2])], revision=0)
        assert list(crew.members.values_list("miniature_id", flat=True)) == [
            table.models[1].pk
        ]

    def test_moved_equipment_does_not_appear_on_another_saved_card(self, table):
        crew = save(
            table,
            [select(table.models[0], card=table.ranged.pk), select(table.models[1])],
        )
        with operation(table.gang, actor=table.owner) as act:
            act.move(table.gun, to=table.models[1])
        sheet = build_crew_sheet(crew)
        assert all(not line.card.weapons for line in sheet.starting)
        assert next(
            line
            for line in sheet.starting
            if line.member.miniature_id == table.models[0].pk
        ).missing_equipment
        assert_reconciled(table.gang)


class TestDraws:
    def test_cards_are_drawn_for_the_whole_pool_before_models(self, table):
        crew = save(table, [select(table.models[1])], random_count=1)
        assert set(crew.last_draw["cards"]) == {
            str(m.pk) for m in [table.models[0], table.models[2], table.models[3]]
        }
        assert crew.last_draw["cards"][str(table.models[0].pk)]["key"] in {
            str(table.ranged.pk),
            str(table.close.pk),
        }
        assert len(crew.last_draw["models"]) == 1
        assert crew.members.filter(source=CrewMember.Source.RANDOM).count() == 1
        assert crew.members.filter(
            miniature=table.models[1], source=CrewMember.Source.MANUAL
        ).exists()
        assert not crew.confirmed

    def test_replayed_draw_is_refused_without_another_draw(self, table):
        crew = save(table, random_count=2)
        snapshot = crew.last_draw.copy()
        with pytest.raises(Refusal, match="changed while"):
            save(table, random_count=2)
        crew.refresh_from_db()
        assert crew.draw_number == 1
        assert crew.last_draw == snapshot

    def test_reinforcement_draw_keeps_its_distinct_role(self, table):
        crew = save(table, random_count=2, random_role="reserve")
        assert crew.members.filter(role="reserve").count() == 2
        assert not crew.members.filter(role="starting").exists()

    def test_random_card_override_is_explicit_and_rating_is_shared(self, table):
        crew = save(table, random_count=4)
        member = crew.members.get(miniature=table.models[0])
        alternative = (
            table.close if member.assignment_set_id == table.ranged.pk else table.ranged
        )
        selections = [
            select(
                m.miniature,
                role=m.role,
                card=alternative.pk if m.pk == member.pk else saved_card_key(m),
            )
            for m in crew.members.select_related("miniature")
        ]
        crew = save(table, selections, revision=crew.revision)
        changed = crew.members.get(pk=member.pk)
        assert changed.card_source == CrewMember.Source.OVERRIDE
        assert changed.rating == member.rating == 40
        assert changed.source == CrewMember.Source.RANDOM

    def test_ineligible_models_stay_out_of_the_random_pool(self, table):
        with operation(table.gang, actor=table.owner) as act:
            act.set_status(table.models[1], Status.RECOVERY)
            act.set_status(table.models[2], Status.DEAD)
            act.remove(table.models[3].membership)
        crew = save(table, random_count=1)
        assert list(crew.last_draw["cards"]) == [str(table.models[0].pk)]
        assert crew.members.get().miniature_id == table.models[0].pk
        assert_reconciled(table.gang)

    def test_recovery_needs_an_explicit_manual_override(self, table):
        model = table.models[1]
        with operation(table.gang, actor=table.owner) as act:
            act.set_status(model, Status.RECOVERY)
        with pytest.raises(Refusal, match="Allow this model"):
            save(table, [select(model)])
        crew = save(table, [select(model, override=True)])
        assert crew.members.get().eligibility_override


class TestCrewPermissions:
    def test_current_arbitrator_can_save_but_a_stranger_cannot(self, table):
        stranger = User.objects.create_user("outsider")
        with pytest.raises(Refusal, match="cannot edit"):
            save_crew(
                battle=table.battle,
                gang=table.gang,
                actor=stranger,
                revision=0,
                selections=[],
            )
        result = save_crew(
            battle=table.battle,
            gang=table.gang,
            actor=table.arbitrator,
            revision=0,
            selections=[select(table.models[1])],
        )
        assert result.crew.updated_by == table.arbitrator

    def test_former_arbitrator_cannot_edit_a_gang_that_left(self, table):
        with operation(table.gang, actor=table.owner) as act:
            act.leave_campaign()
        with pytest.raises(Refusal, match="cannot edit"):
            save_crew(
                battle=table.battle,
                gang=table.gang,
                actor=table.arbitrator,
                revision=0,
                selections=[],
            )
        assert save(table).gang == table.gang

    def test_nonparticipant_is_refused(self, table):
        table.battle.gangs.remove(table.gang)
        with pytest.raises(Refusal, match="not a participant"):
            save(table)


class TestCrewQueryGrowth:
    def test_more_cards_do_not_add_a_query_per_model(self, table):
        crew = save(table, [select(table.models[0], card=table.ranged.pk)])
        with CaptureQueriesContext(connection) as one:
            build_crew_sheet(crew)
        crew = save(
            table,
            [
                select(table.models[0], card=saved_card_key(crew.members.get())),
                *[select(m) for m in table.models[1:]],
            ],
            revision=crew.revision,
        )
        with CaptureQueriesContext(connection) as many:
            build_crew_sheet(crew)
        assert len(many) == len(one)
        assert AssignmentSet.objects.count() == 2
