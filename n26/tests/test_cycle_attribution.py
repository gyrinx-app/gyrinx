"""Battle and action attribution preserves selected historical cycle identities."""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models.deletion import RestrictedError
from django.http import QueryDict

from gyrinx.site.models import Availability, FeatureFlag
from n26.core import cycles
from n26.core import schedule as s
from n26.core.battle_workflow import perform
from n26.core.campaigns import campaign_operation
from n26.core.cycle_context import CycleContext
from n26.core.cycle_data import ref_data, template_data
from n26.core.models import (
    Battle,
    BattleCommand,
    CampaignCycle,
    CampaignScheduleTemplate,
    LedgerEvent,
)
from n26.core.operations import Refusal, operation
from n26.core.reconcile import assert_reconciled
from n26.flags import CYCLE_TRACKING
from n26.library import authoring as a
from n26.tests.sandbox.actions import found_campaign, found_gang, hire, join_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def table(campaign_type, gang_type, make_profile, counter_tracking):
    owner = User.objects.create_user("cycle-context-owner")
    flag = FeatureFlag.objects.create(
        slug=CYCLE_TRACKING, name="Campaign cycles", availability=Availability.EVERYONE
    )
    campaign = found_campaign("Ash Road", campaign_type, owner=owner)
    gang = found_gang("Ash Walkers", gang_type, owner=owner, budget=1000)
    join_campaign(gang, campaign)
    fighter = hire(gang, make_profile("Walker", price=100), "Ada")
    template = CampaignScheduleTemplate.objects.create(
        name=s.DEFAULT_TEMPLATE.name, definition=template_data(s.DEFAULT_TEMPLATE)
    )
    cycles.configure(
        campaign,
        actor=owner,
        template_id=template.pk,
        current_position=0,
        mode="fixed",
        request_key=uuid4(),
    )
    state = cycles.load(campaign)
    return SimpleNamespace(
        owner=owner,
        flag=flag,
        campaign=campaign,
        gang=gang,
        fighter=fighter,
        state=state,
        context=CycleContext(
            campaign_id=str(campaign.pk), cycle_id=state.current_cycle_id
        ),
    )


def record_battle(table, **kwargs):
    with campaign_operation(table.campaign, actor=table.owner) as act:
        return act.record_battle(
            date=date(2026, 11, 7),
            scenario="Street fight",
            gangs=[table.gang],
            **kwargs,
        )


def battle_data(**fields):
    data = QueryDict(mutable=True)
    data.update(
        {
            "request_key": str(uuid4()),
            "scenario": "Street fight",
            "date": "2026-11-07",
            **fields,
        }
    )
    return data


class TestBattleCycles:
    def test_default_recording_uses_the_current_cycle_and_closed_flags_keep_legacy_behaviour(
        self, table
    ):
        battle = record_battle(table)
        assert str(battle.cycle_id) == table.state.current_cycle_id
        table.flag.availability = Availability.OFF
        table.flag.save()
        assert record_battle(table).cycle_id is None
        with pytest.raises(Refusal, match="not available"):
            record_battle(table, cycle=s.SavedCycleRef(table.state.current_cycle_id))

    def test_projected_selection_saves_the_prefix_once_without_starting_it(self, table):
        selected = s.project(table.state)[3]
        first = record_battle(table, cycle=selected.ref)
        second = record_battle(table, cycle=selected.ref)
        assert first.cycle_id == second.cycle_id
        after = cycles.load(table.campaign)
        assert len(after.cycles) == 5
        assert after.current_cycle_id == table.state.current_cycle_id
        assert not table.campaign.cycle_transitions.exists()
        assert_reconciled(table.gang)

    def test_outer_rollback_removes_battle_and_projected_prefix_together(self, table):
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                record_battle(table, cycle=s.project(table.state)[3].ref)
                raise RuntimeError("Rollback")
        assert not Battle.objects.exists()
        assert CampaignCycle.objects.count() == 1

    def test_foreign_cycle_selection_is_refused(self, table, campaign_type):
        other = found_campaign("Elsewhere", campaign_type, owner=table.owner)
        with campaign_operation(other, actor=table.owner) as act:
            with pytest.raises(Refusal, match="campaign"):
                act.record_battle(
                    date=date(2026, 11, 7),
                    scenario="Wrong cycle",
                    cycle=s.SavedCycleRef(table.state.current_cycle_id),
                )

    def test_new_workflow_retries_replay_before_a_battle_is_created_twice(self, table):
        data = battle_data()
        for _ in range(2):
            saved = perform(
                table.campaign,
                table.owner,
                type(table.gang).objects.filter(pk=table.gang.pk),
                data,
            )
            assert saved.battle is not None, saved.form.errors
        assert saved.replayed
        assert Battle.objects.count() == BattleCommand.objects.count() == 1
        data["scenario"] = "Different fight"
        refused = perform(
            table.campaign,
            table.owner,
            type(table.gang).objects.filter(pk=table.gang.pk),
            data,
        )
        assert not refused.battle and refused.form.non_field_errors()

    def test_linked_cycles_cannot_be_deleted(self, table):
        battle = record_battle(table)
        with pytest.raises(RestrictedError):
            battle.cycle.delete()


class TestActionCycles:
    def test_application_after_a_campaign_move_keeps_the_original_cycle_on_all_effects(
        self, table, campaign_type
    ):
        counter = a.create_counter("Marks")
        outcome = a.create_outcome(
            "Clear marks", a.apply_changes(a.counter_change(counter, "set", 0))
        )
        action = a.create_action(
            "Cycle maintenance",
            "post_cycle",
            outcomes=[outcome],
            use_price=[{"resource": "credits", "payer": "gang", "amount": 10}],
        )
        with operation(table.gang, actor=table.owner) as op:
            balance = op.assign(counter, miniature=table.fighter)
            op.tally(balance, 4)
            op.assign(action, miniature=table.fighter)
        with operation(
            table.gang, actor=table.owner, cycle_context=table.context
        ) as op:
            record = op.start_action(table.fighter, action, uuid4())
        # Saving and starting a later cycle does not alter the recorded selection.
        for _ in range(4):
            current = cycles.load(table.campaign)
            if current.status == "pre_campaign":
                cycles.start(
                    table.campaign,
                    actor=table.owner,
                    expected_current=current.current_cycle_id,
                    expected_revision=current.revision,
                    request_key=uuid4(),
                )
                current = cycles.load(table.campaign)
            cycles.advance(
                table.campaign,
                actor=table.owner,
                expected_current=current.current_cycle_id,
                expected_revision=current.revision,
                request_key=uuid4(),
            )
        assert (
            cycles.load(table.campaign).current_phase.details.name == "Takeover Phase"
        )
        with operation(table.gang, actor=table.owner) as op:
            op.leave_campaign()
        other = found_campaign("Another campaign", campaign_type, owner=table.owner)
        join_campaign(table.gang, other)
        with operation(table.gang, actor=table.owner) as op:
            record = op.review_action(record, outcome=outcome)
            record = op.complete_action(
                record, revision=record.revision, review=record.review, outcome=outcome
            )
            op.append_note(table.fighter, "Unrelated note", note="Unrelated note")
        events = LedgerEvent.objects.filter(action_record=record)
        assert events.count() >= 3
        assert set(events.values_list("cycle_id", flat=True)) == {record.cycle_id}
        assert set(events.values_list("campaign_id", flat=True)) == {table.campaign.pk}
        assert record.cycle.phase.name == "Occupation Phase"
        unrelated = LedgerEvent.objects.filter(note="Unrelated note").get()
        assert unrelated.cycle_id is None and unrelated.campaign_id == other.pk
        assert_reconciled(table.gang)

    def test_flag_off_and_foreign_context_are_refused_before_action_writes(
        self, table, campaign_type
    ):
        table.flag.availability = Availability.OFF
        table.flag.save()
        with pytest.raises(Refusal, match="not available"):
            with operation(table.gang, actor=table.owner, cycle_context=table.context):
                pass
        table.flag.availability = Availability.EVERYONE
        table.flag.save()
        other = found_campaign("Other", campaign_type, owner=table.owner)
        foreign = CycleContext(str(other.pk), table.state.current_cycle_id)
        with pytest.raises(Refusal, match="campaign"):
            with operation(table.gang, actor=table.owner, cycle_context=foreign):
                pass


class TestBattleWorkflowAdapters:
    @pytest.mark.parametrize("native", [False, True])
    def test_battle_forms_default_to_current_and_replay_future_selection_once(
        self, client, table, native
    ):
        import json

        from django.urls import reverse

        client.force_login(table.owner)
        page = client.get(reverse("n26-campaign-add-battle", args=[table.campaign.pk]))
        props = page.context["battle_editor"]
        assert json.loads(props["values"]["cycle"]) == {
            "cycle_id": table.state.current_cycle_id
        }
        assert props["cycles"]["choices"][0]["isCurrent"]
        selected = s.project(table.state)[3]
        data = {
            **props["values"],
            "date": "2026-11-07",
            "gangs": json.dumps([str(table.gang.pk)]),
            "cycle": json.dumps(ref_data(selected.ref)),
        }
        target = props["action"] if native else props["commandHref"]
        first, second = client.post(target, data), client.post(target, data)
        assert first.status_code == second.status_code == (302 if native else 200)
        battle = Battle.objects.get(campaign=table.campaign)
        assert battle.cycle.order == 5
        assert table.campaign.cycle_commands.count() == 1
        assert BattleCommand.objects.count() == 1
        assert (
            cycles.load(table.campaign).current_cycle_id == table.state.current_cycle_id
        )

    def test_closed_flag_hides_selection_and_refuses_direct_attribution_writes(
        self, client, table
    ):
        import json

        from django.urls import reverse

        client.force_login(table.owner)
        table.flag.availability = Availability.OFF
        table.flag.save()
        page = client.get(reverse("n26-campaign-add-battle", args=[table.campaign.pk]))
        props = page.context["battle_editor"]
        assert props["cycles"] is None and "cycle" not in props["values"]
        assert (
            client.get(
                reverse("n26-battle-cycle-options", args=[table.campaign.pk])
            ).status_code
            == 404
        )
        data = {
            **props["values"],
            "date": "2026-11-07",
            "cycle": json.dumps(
                ref_data(s.SavedCycleRef(table.state.current_cycle_id))
            ),
        }
        refused = client.post(props["commandHref"], data)
        assert refused.status_code == 422
        assert not Battle.objects.exists()
        data.pop("cycle")
        assert client.post(props["commandHref"], data).status_code == 200
        assert Battle.objects.get().cycle_id is None

    def test_stale_edit_preserves_the_draft_and_requires_review(self, client, table):
        from django.urls import reverse

        client.force_login(table.owner)
        battle = record_battle(table)
        page = client.get(
            reverse("n26-campaign-edit-battle", args=[table.campaign.pk, battle.pk])
        )
        props = page.context["battle_editor"]
        data = {**props["values"], "scenario": "Server name"}
        assert client.post(props["commandHref"], data).status_code == 200
        response = client.post(
            props["commandHref"],
            {**data, "request_key": str(uuid4()), "scenario": "Stale name"},
        )
        assert response.status_code == 409
        assert response.json()["current"]["scenario"] == "Server name"
        assert response.json()["code"] == "revision_conflict"
        battle.refresh_from_db()
        assert battle.scenario == "Server name"

    def test_closed_flag_edit_preserves_existing_cycle_and_removes_its_link(
        self, client, table
    ):
        from django.urls import reverse

        client.force_login(table.owner)
        battle = record_battle(table)
        original = battle.cycle_id
        table.flag.availability = Availability.OFF
        table.flag.save()
        page = client.get(
            reverse("n26-campaign-edit-battle", args=[table.campaign.pk, battle.pk])
        )
        props = page.context["battle_editor"]
        assert (
            client.post(
                props["commandHref"],
                {**props["values"], "scenario": "Edited with flag off"},
            ).status_code
            == 200
        )
        battle.refresh_from_db()
        assert battle.cycle_id == original
        detail = client.get(reverse("n26-battle", args=[table.campaign.pk, battle.pk]))
        assert detail.context["cycle_attribution"] is None
        table.flag.availability = Availability.EVERYONE
        table.flag.save()
        detail = client.get(reverse("n26-battle", args=[table.campaign.pk, battle.pk]))
        assert detail.context["cycle_attribution"]["name"] == "Cycle 1"


@pytest.mark.parametrize("reuse_key", [False, True])
def test_projected_action_selection_and_its_prefix_share_one_transaction(
    table, reuse_key
):
    action = a.create_action("Cycle preparation", "post_cycle")
    with operation(table.gang, actor=table.owner) as op:
        op.assign(action, miniature=table.fighter)
    selected, key = s.project(table.state)[3], uuid4()
    for _ in range(2):
        with cycles.action_operation(
            table.campaign, table.gang, actor=table.owner, target=selected.ref
        ) as op:
            record = op.start_action(table.fighter, action, key)
    assert record.cycle.order == 5
    assert record.action.records.count() == 1
    assert CampaignCycle.objects.count() == 5
    before = cycles.load(table.campaign)
    with pytest.raises(Refusal, match="another action use|different cycle"):
        with cycles.action_operation(
            table.campaign,
            table.gang,
            actor=table.owner,
            target=s.project(before)[0].ref,
        ) as op:
            op.start_action(table.fighter, action, key if reuse_key else uuid4())
    assert CampaignCycle.objects.count() == 5
    assert cycles.load(table.campaign) == before
    assert before.current_cycle_id == table.state.current_cycle_id
    assert_reconciled(table.gang)


@pytest.mark.django_db(transaction=True)
def test_concurrent_battle_retries_commit_one_battle_and_one_projected_prefix(table):
    import json
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections, connections

    selected = s.project(table.state)[3]
    data = battle_data(cycle=json.dumps(ref_data(selected.ref)))
    barrier = Barrier(2)

    def submit():
        close_old_connections()
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
            barrier.wait(timeout=10)
            saved = perform(
                table.campaign,
                table.owner,
                type(table.gang).objects.filter(pk=table.gang.pk),
                data,
            )
            assert saved.battle is not None, saved.form.errors
            return saved.battle.pk, saved.replayed
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = [
            future.result(timeout=20)
            for future in [pool.submit(submit), pool.submit(submit)]
        ]
    assert first[0] == second[0]
    assert {first[1], second[1]} == {False, True}
    assert Battle.objects.count() == BattleCommand.objects.count() == 1
    assert CampaignCycle.objects.count() == 5
    assert cycles.load(table.campaign).current_cycle_id == table.state.current_cycle_id


def test_cycle_choice_reads_remain_bounded_as_saved_history_grows(table):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from n26.core.cycle_selection import options

    with CaptureQueriesContext(connection) as initial:
        small = options(table.campaign)
    cycles.replace_plan(
        table.campaign,
        actor=table.owner,
        steps=table.state.plan.steps,
        mode="repeating",
        expected_revision=table.state.revision,
        request_key=uuid4(),
    )
    state = cycles.load(table.campaign)
    record_battle(table, cycle=s.project(state, limit=60)[-1].ref)
    with CaptureQueriesContext(connection) as expanded:
        large = options(table.campaign)
    assert len(initial) == len(expanded)
    assert len(small["choices"]) == 7
    assert len(large["choices"]) == 62
    assert large["next"] == 2
    selected = {"cycle_id": table.state.current_cycle_id}
    second = options(table.campaign, page=2, selected=selected)
    assert second["choices"][0]["value"] == selected
    assert len(second["choices"]) == 24


@pytest.mark.parametrize("value", ["false", "[]", "{}", "0"])
def test_malformed_optional_cycle_values_are_refused_instead_of_clearing_attribution(
    client, table, value
):
    from django.urls import reverse

    client.force_login(table.owner)
    page = client.get(reverse("n26-campaign-add-battle", args=[table.campaign.pk]))
    props = page.context["battle_editor"]
    response = client.post(
        props["commandHref"], {**props["values"], "date": "2026-11-07", "cycle": value}
    )
    assert response.status_code == 422
    assert "cycle" in response.json()["errors"]
    assert not Battle.objects.exists()


def test_uuid_contexts_are_canonical_for_exact_retries_and_legacy_resume(table):
    from n26.core.fields import to_ulid

    action = a.create_action("Cycle preparation", "post_cycle")
    with operation(table.gang, actor=table.owner) as op:
        op.assign(action, miniature=table.fighter)
    context = CycleContext(
        str(table.campaign.pk.to_uuid()), str(to_ulid(table.context.cycle_id).to_uuid())
    )
    key = uuid4()
    identities = []
    for _ in range(2):
        with operation(table.gang, actor=table.owner, cycle_context=context) as op:
            assert op.cycle_context == table.context
            record = op.start_action(table.fighter, action, key)
            identities.append(record.pk)
    with operation(table.gang, actor=table.owner) as op:
        assert op.start_action(table.fighter, action, key).pk == identities[0]
        assert op.start_action(table.fighter, action, uuid4()).pk == identities[0]
    assert len(set(identities)) == 1
    assert action.records.count() == 1
    assert_reconciled(table.gang)


def test_enabling_the_flag_after_a_lost_creation_response_replays_the_original_unattributed_battle(
    client, table
):
    from django.urls import reverse

    client.force_login(table.owner)
    table.flag.availability = Availability.OFF
    table.flag.save()
    props = client.get(
        reverse("n26-campaign-add-battle", args=[table.campaign.pk])
    ).context["battle_editor"]
    data = {**props["values"], "date": "2026-11-08"}
    assert "cycle" not in data
    assert client.post(props["commandHref"], data).status_code == 200
    table.flag.availability = Availability.EVERYONE
    table.flag.save()
    fresh = client.get(props["action"]).context["battle_editor"]
    assert "cycle" in fresh["values"]
    assert client.post(fresh["commandHref"], data).status_code == 200
    assert Battle.objects.count() == BattleCommand.objects.count() == 1
    assert Battle.objects.get().cycle_id is None
