"""Authored status conditions offer a separate choice for each status transition."""

from copy import deepcopy
from uuid import uuid4

import pytest
from django.db import connection
from django.http import Http404
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.card import build_card, build_modifier_index, carriers
from n26.core.effects import compute
from n26.core.models import Assignment, LedgerEvent, Miniature
from n26.core.operations import Refusal, clone_gang, operation
from n26.core.post_battle import preview_report, start_correction
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card, slot_key
from n26.core.result_history import result_history
from n26.core.status import Status
from n26.core.views.choose import find_slot
from n26.library.authoring import (
    add_picklist_member,
    create_pickable,
    create_picklist,
    create_profile,
    create_slot,
    create_slot_type,
    create_wargear,
    ef_adds,
    has_status,
    modifier,
    op_adds_model,
    op_sets_status,
    targets_every_model,
    targets_model,
)
from n26.tests.fixtures import admit_to_founding
from n26.tests.sandbox import test_post_battle as report_tests
from n26.tests.sandbox.actions import hire

owner = report_tests.owner
content = report_tests.content
gang = report_tests.gang
model = report_tests.model
report = report_tests.report
payload_for = report_tests.payload_for
save = report_tests.save
apply = report_tests.apply
effect_for = report_tests.effect_for


pytestmark = pytest.mark.django_db


@pytest.fixture
def follow_up(content, gang_type):
    kind = create_slot_type("Release result")
    released = create_pickable(
        "Back to the gang",
        kind,
        record_only=True,
        effects=[(targets_model(), op_sets_status(Status.RECOVERY))],
    )
    ransom = create_pickable(
        "Held for payment",
        kind,
        record_only=True,
        effects=[(targets_model(), op_sets_status(Status.RANSOMED))],
    )
    table = create_picklist(
        "Release table",
        kind,
        members=[released, ransom],
        dice="d6",
        roll_selects="band",
    )
    slot = create_slot(
        "Release", kind, table, min_picks=0, max_picks=1, follows_status=True
    )
    modifier(
        "Prisoners may resolve Release",
        targets_every_model(has_status(Status.CAPTURED)),
        ef_adds(slot),
        attach_to=gang_type,
    )
    captured = create_pickable(
        "Taken prisoner",
        content["kind"],
        record_only=True,
        effects=[(targets_model(), op_sets_status(Status.CAPTURED))],
    )
    add_picklist_member(content["table"], captured)
    return captured, slot, released, ransom


def computed(model):
    card = build_card(model)
    return compute(card, build_modifier_index(carriers(card)))


def choose(model, slot, pick):
    question = next(q for q in computed(model).choices if q.slot.pk == slot.pk)
    with operation(model.gang, actor=model.gang.owner) as op:
        return op.choose(question.anchor.assignment, pick, slot=slot, miniature=model)


def mark(model, status):
    with operation(model.gang, actor=model.gang.owner) as op:
        op.set_status(model, status)


def test_manual_status_offers_a_choice_without_an_injury(model, follow_up):
    _, slot, _, _ = follow_up
    assert all(q.slot.pk != slot.pk for q in computed(model).choices)
    mark(model, Status.CAPTURED)
    question = next(q for q in computed(model).choices if q.slot.pk == slot.pk)
    assert not question.picks
    assert question.status_revision == 1
    assert not Assignment.objects.filter(
        miniature=model, pickable__isnull=False
    ).exists()


def test_results_leave_current_choices_but_keep_history(model, content, follow_up):
    captured, slot, released, _ = follow_up
    choose(model, content["slot"], content["wound"])
    capture = choose(model, content["slot"], captured)
    card = build_model_card(model, computed=computed(model))
    assert [q.chosen for q in card.row_questions if q.is_lasting_effect] == [
        "Grievous Wound"
    ]
    picked = choose(model, slot, released)
    assert model.status == Status.RECOVERY
    assert all(q.slot.pk != slot.pk for q in computed(model).choices)
    assert (
        Assignment.objects.filter(
            pk__in=[capture.pk, picked.pk], archived=False
        ).count()
        == 2
    )
    assert LedgerEvent.objects.filter(assignment=capture).exists()
    with operation(model.gang, actor=model.gang.owner) as op:
        op.clean_house()
    model.refresh_from_db()
    assert model.status == Status.ACTIVE
    assert all(q.slot.pk != slot.pk for q in computed(model).choices)


def test_a_later_capture_has_a_new_address_and_no_old_pick(model, follow_up):
    _, slot, released, _ = follow_up
    mark(model, Status.CAPTURED)
    first = next(q for q in computed(model).choices if q.slot.pk == slot.pk)
    old_key = slot_key(first, str(model.pk))
    choose(model, slot, released)
    mark(model, Status.CAPTURED)
    fresh = next(q for q in computed(model).choices if q.slot.pk == slot.pk)
    assert not fresh.picks
    assert slot_key(fresh, str(model.pk)) != old_key
    with pytest.raises(Http404):
        find_slot(model.gang, old_key)
    events = LedgerEvent.objects.count()
    mark(model, Status.CAPTURED)
    assert LedgerEvent.objects.count() == events
    assert model.status_revision == fresh.status_revision


def test_post_battle_can_resolve_the_status_choice_in_the_same_report(
    report, owner, model, follow_up
):
    captured, _, released, _ = follow_up
    effect = effect_for(report, owner, captured)
    payload = payload_for(model, effects=[effect])
    before = (
        LedgerEvent.objects.count(),
        Assignment.objects.count(),
        model.status_revision,
    )
    plan = preview_report(report, actor=owner, payload=payload)
    assert plan.valid, plan.errors
    question = plan.models[0].effects[0].questions[0]
    effect["choices"][question.key] = [
        next(o.value for o in question.options if o.label == released.name)
    ]
    plan = preview_report(report, actor=owner, payload=payload)
    assert plan.valid, plan.errors
    assert plan.models[0].final_status == Status.RECOVERY
    assert not plan.models[0].status_conflict
    assert plan.models[0].effects[0].display_name == "Taken prisoner → Back to the gang"
    from n26.core.post_battle_forms import editor_models, preview_display

    display = preview_display(plan, editor_models(plan, payload))
    assert "Taken prisoner → Back to the gang" in display["models"][0]["lines"]
    model.refresh_from_db()
    assert (
        LedgerEvent.objects.count(),
        Assignment.objects.count(),
        model.status_revision,
    ) == before
    report = save(report, owner, payload)
    key = uuid4()
    apply(report, owner, key=key)
    events = LedgerEvent.objects.count()
    apply(report, owner, key=key)
    assert LedgerEvent.objects.count() == events
    model.refresh_from_db()
    assert model.status == Status.RECOVERY
    assert Assignment.objects.filter(miniature=model, pickable=released).exists()


def test_deferred_choice_is_available_to_a_later_report(
    report, owner, model, follow_up
):
    captured, slot, released, _ = follow_up
    effect = effect_for(report, owner, captured)
    report = save(report, owner, payload_for(model, effects=[effect]))
    apply(report, owner)
    model.refresh_from_db()
    assert model.status == Status.CAPTURED
    report = start_correction(report, actor=owner)
    release = effect_for(report, owner, released)
    payload = deepcopy(report.draft)
    payload["models"][0]["effects"].append(release)
    payload["models"][0]["status"] = ""
    report = save(report, owner, payload)
    apply(report, owner)
    model.refresh_from_db()
    assert model.status == Status.RECOVERY
    picked = Assignment.objects.get(miniature=model, pickable=released, archived=False)
    assert picked.chosen_for_slot_id == slot.pk


@pytest.mark.parametrize("legacy_receipt", [False, True])
def test_a_carried_choice_can_be_corrected_and_removed(
    report, owner, model, follow_up, legacy_receipt
):
    _, slot, released, ransom = follow_up
    mark(model, Status.CAPTURED)
    effect = effect_for(report, owner, released)
    report = save(report, owner, payload_for(model, effects=[effect]))
    revision = apply(report, owner)
    if legacy_receipt:
        from n26.core.models import PostBattleRevision

        receipt = deepcopy(revision.receipt)
        for recorded in receipt["models"]:
            recorded.pop("status_revision_after", None)
        PostBattleRevision.objects.filter(pk=revision.pk).update(receipt=receipt)
    report = start_correction(report, actor=owner)
    payload = deepcopy(report.draft)
    payload["models"][0]["effects"][0]["pick"] = str(ransom.pk)
    payload["models"][0]["status"] = ""
    report = save(report, owner, payload)
    apply(report, owner)
    model.refresh_from_db()
    assert model.status == Status.RANSOMED
    assert not Assignment.objects.filter(
        miniature=model, pickable=released, archived=False
    ).exists()
    report = start_correction(report, actor=owner)
    payload = deepcopy(report.draft)
    payload["models"][0]["effects"] = []
    report = save(report, owner, payload)
    apply(report, owner)
    model.refresh_from_db()
    assert model.status == Status.CAPTURED
    assert not next(q for q in computed(model).choices if q.slot.pk == slot.pk).picks
    reopened = LedgerEvent.objects.filter(
        miniature=model,
        kind=LedgerEvent.Kind.STATUS_SET,
        note__endswith=": Post-battle correction",
    ).latest("created")
    assert reopened.note == "ransomed → captured: Post-battle correction"
    assert reopened.post_battle_occurrence is None


def test_roster_queries_do_not_grow_with_status_choices(
    client, owner, model, gang, content, follow_up
):
    admit_to_founding(owner)
    client.force_login(owner)
    mark(model, Status.CAPTURED)
    url = reverse("n26-gang", args=[gang.pk])
    client.get(url)
    with CaptureQueriesContext(connection) as small:
        response = client.get(url)
    assert response.status_code == 200
    assert "Resolve" in response.content.decode()
    for n in range(4):
        another = hire(gang, content["profile"], f"Prisoner {n}")
        mark(another, Status.CAPTURED)
    with CaptureQueriesContext(connection) as large:
        assert client.get(url).status_code == 200
    assert len(large) == len(small)


def test_inline_follow_up_is_removed_with_its_report_result(
    report, owner, model, follow_up
):
    captured, _, released, ransom = follow_up
    effect = effect_for(report, owner, captured)
    payload = payload_for(model, effects=[effect])
    question = (
        preview_report(report, actor=owner, payload=payload)
        .models[0]
        .effects[0]
        .questions[0]
    )
    effect["choices"][question.key] = [
        next(o.value for o in question.options if o.label == released.name)
    ]
    report = save(report, owner, payload)
    revision = apply(report, owner)
    record = revision.receipt["occurrences"][effect["id"]]
    assert len(record["assignment_ids"]) == 2
    report = start_correction(report, actor=owner)
    payload = deepcopy(report.draft)
    payload["models"][0]["effects"][0]["choices"][question.key] = [
        f"library.pickable:{ransom.pk}"
    ]
    payload["models"][0]["status"] = ""
    report = save(report, owner, payload)
    apply(report, owner)
    model.refresh_from_db()
    assert model.status == Status.RANSOMED
    assert not Assignment.objects.filter(
        miniature=model, pickable=released, archived=False
    ).exists()
    assert (
        Assignment.objects.filter(
            miniature=model, pickable=captured, archived=False
        ).count()
        == 1
    )


def test_model_edit_keeps_result_history_and_persistent_injuries(
    client, owner, model, content, follow_up
):
    captured, slot, released, _ = follow_up
    admit_to_founding(owner)
    client.force_login(owner)
    choose(model, content["slot"], content["wound"])
    choose(model, content["slot"], captured)
    choose(model, slot, released)
    response = client.get(reverse("n26-edit-fighter", args=[model.pk]))
    assert response.status_code == 200
    assert [r.name for r in response.context["result_history"]] == [
        released.name,
        captured.name,
    ]
    assert "Result history" in response.content.decode()
    assert "Grievous Wound" in response.content.decode()


def test_stale_status_choice_post_does_not_change_a_later_capture(
    client, owner, model, follow_up
):
    _, slot, released, _ = follow_up
    admit_to_founding(owner)
    client.force_login(owner)
    mark(model, Status.CAPTURED)
    question = next(q for q in computed(model).choices if q.slot.pk == slot.pk)
    old_url = reverse(
        "n26-choose", args=[model.gang.pk, slot_key(question, str(model.pk))]
    )
    choose(model, slot, released)
    mark(model, Status.CAPTURED)
    count = LedgerEvent.objects.count()
    response = client.post(old_url, {"thing": f"library.pickable:{released.pk}"})
    assert response.status_code == 404
    model.refresh_from_db()
    assert model.status == Status.CAPTURED
    assert LedgerEvent.objects.count() == count


def test_follow_up_controls_are_only_available_to_the_owner(
    client, owner, model, follow_up
):
    from django.contrib.auth.models import User

    _, slot, _, _ = follow_up
    mark(model, Status.CAPTURED)
    question = next(q for q in computed(model).choices if q.slot.pk == slot.pk)
    url = reverse("n26-choose", args=[model.gang.pk, slot_key(question, str(model.pk))])
    visitor = User.objects.create_user("other-player")
    admit_to_founding(visitor)
    client.force_login(visitor)
    assert client.get(url).status_code == 404
    roster = client.get(reverse("n26-gang", args=[model.gang.pk]))
    assert "Resolve" not in roster.content.decode()


def test_an_unrelated_result_does_not_attach_an_existing_status_choice(
    report, owner, model, content, follow_up, counter_tracking
):
    mark(model, Status.CAPTURED)
    effect = effect_for(report, owner, content["lesson"])
    plan = preview_report(
        report, actor=owner, payload=payload_for(model, effects=[effect])
    )
    assert plan.valid, plan.errors
    assert not plan.models[0].effects[0].questions
    assert plan.models[0].final_status == Status.CAPTURED


def test_batched_and_selected_cards_keep_status_facts(model, follow_up):
    from n26.core.card import build_gang_card
    from n26.core.models import AssignmentSet

    _, slot, _, _ = follow_up
    mark(model, Status.CAPTURED)
    gang_card = build_gang_card(model.gang)
    selection = AssignmentSet.objects.create(miniature=model, name="Empty equipment")
    for card in (
        gang_card.members[model.pk],
        gang_card.members_under(selection)[model.pk],
    ):
        assert card.miniature is None
        index = build_modifier_index(carriers(card))
        with CaptureQueriesContext(connection) as queries:
            done = compute(card, index)
        assert len(queries) == 0
        question = next(q for q in done.choices if q.slot.pk == slot.pk)
        assert question.status_revision == model.status_revision


def test_a_status_choice_is_never_offered_as_a_gang_status(gang, follow_up):
    from n26.core.card import build_gang_card
    from n26.core.effects import compute_gang

    _, slot, _, _ = follow_up
    with operation(gang, actor=gang.owner) as op:
        op.assign(slot, gang=gang)
    card = build_gang_card(gang)
    done = compute_gang(card, build_modifier_index(carriers(card)))
    assert all(q.slot.pk != slot.pk for q in done.choices)


def test_a_roll_from_an_earlier_capture_cannot_settle_the_current_choice(
    client, owner, model, follow_up
):
    _, slot, released, _ = follow_up
    admit_to_founding(owner)
    client.force_login(owner)
    mark(model, Status.CAPTURED)
    with operation(model.gang, actor=owner) as op:
        old_roll = op.roll(slot, miniature=model, rolled=6)
    mark(model, Status.ACTIVE)
    mark(model, Status.CAPTURED)
    question = next(q for q in computed(model).choices if q.slot.pk == slot.pk)
    url = reverse("n26-choose", args=[model.gang.pk, slot_key(question, str(model.pk))])
    before = (LedgerEvent.objects.count(), Assignment.objects.count())
    assert client.get(f"{url}?roll={old_roll.pk}").status_code == 404
    assert (
        client.post(
            url, {"thing": f"library.pickable:{released.pk}", "roll": str(old_roll.pk)}
        ).status_code
        == 404
    )
    with pytest.raises(Refusal, match="status change"):
        with operation(model.gang, actor=owner) as op:
            op.choose(
                question.anchor.assignment,
                released,
                slot=slot,
                miniature=model,
                roll=old_roll,
            )
    assert (LedgerEvent.objects.count(), Assignment.objects.count()) == before
    model.refresh_from_db()
    assert model.status == Status.CAPTURED
    with operation(model.gang, actor=owner) as op:
        current_roll = op.roll(slot, miniature=model, rolled=6)
        picked = op.choose(
            question.anchor.assignment,
            released,
            slot=slot,
            miniature=model,
            roll=current_roll,
        )
    assert picked.roll_id == current_roll.pk
    assert current_roll.status_revision == question.status_revision
    assert picked.chosen_for_status_revision == current_roll.status_revision
    model.refresh_from_db()
    assert model.status == Status.RECOVERY


@pytest.mark.parametrize("keep_capture", [True, False])
def test_a_deferred_follow_up_can_be_replaced_and_removed_on_later_corrections(
    report, owner, model, follow_up, keep_capture
):
    captured, slot, released, ransom = follow_up
    capture = effect_for(report, owner, captured)
    report = save(report, owner, payload_for(model, effects=[capture]))
    apply(report, owner)
    report = start_correction(report, actor=owner)
    release = effect_for(report, owner, released)
    payload = deepcopy(report.draft)
    payload["models"][0]["effects"].append(release)
    payload["models"][0]["status"] = ""
    report = save(report, owner, payload)
    apply(report, owner)
    report = start_correction(report, actor=owner)
    payload = deepcopy(report.draft)
    payload["models"][0]["effects"][1]["pick"] = str(ransom.pk)
    payload["models"][0]["status"] = ""
    plan = preview_report(report, actor=owner, payload=payload)
    assert plan.valid, plan.errors
    assert plan.models[0].final_status == Status.RANSOMED
    report = save(report, owner, payload)
    apply(report, owner)
    model.refresh_from_db()
    assert model.status == Status.RANSOMED
    report = start_correction(report, actor=owner)
    payload = deepcopy(report.draft)
    payload["models"][0]["effects"] = [capture] if keep_capture else []
    expected = Status.CAPTURED if keep_capture else Status.ACTIVE
    payload["models"][0]["status"] = ""
    plan = preview_report(report, actor=owner, payload=payload)
    assert plan.valid, plan.errors
    assert plan.models[0].final_status == expected
    report = save(report, owner, payload)
    apply(report, owner)
    model.refresh_from_db()
    assert model.status == expected
    if keep_capture:
        assert not next(
            q for q in computed(model).choices if q.slot.pk == slot.pk
        ).picks
    else:
        assert all(q.slot.pk != slot.pk for q in computed(model).choices)
    assert Assignment.objects.filter(
        miniature=model, pickable=captured, archived=False
    ).count() == int(keep_capture)


def test_repeated_status_choices_have_distinct_keys_and_replay_on_correction(
    report, owner, model, follow_up, gang_type
):
    from django.http import QueryDict

    from n26.core.post_battle_forms import posted_payload

    captured, slot, released, ransom = follow_up
    modifier(
        "Payment may be resolved separately",
        targets_every_model(has_status(Status.RANSOMED)),
        ef_adds(slot),
        attach_to=gang_type,
    )
    effect = effect_for(report, owner, captured)
    payload = payload_for(model, effects=[effect])
    first = (
        preview_report(report, actor=owner, payload=payload)
        .models[0]
        .effects[0]
        .questions[0]
    )
    ransom_value = next(o.value for o in first.options if o.label == ransom.name)
    effect["choices"][first.key] = [ransom_value]
    plan = preview_report(report, actor=owner, payload=payload)
    assert plan.valid, plan.errors
    questions = plan.models[0].effects[0].questions
    assert len(questions) == 2
    first, second = questions
    assert first.key != second.key
    assert first.selected == [ransom_value]
    assert second.selected == []
    legacy_payload = deepcopy(payload)
    legacy_payload["models"][0]["effects"][0]["choices"] = {
        first.key.removeprefix(f"post-battle:{effect['id']}:").rsplit(":status-", 1)[
            0
        ]: [ransom_value]
    }
    legacy_plan = preview_report(report, actor=owner, payload=legacy_payload)
    assert legacy_plan.valid, legacy_plan.errors
    assert [q.selected for q in legacy_plan.models[0].effects[0].questions] == [
        [ransom_value],
        [],
    ]
    release_value = next(o.value for o in second.options if o.label == released.name)
    data = QueryDict(mutable=True)
    data.setlist("model_id", [str(model.pk)])
    data.setlist(f"model-{model.pk}-effect", [effect["id"]])
    data[f"effect-{effect['id']}-pick"] = f"{effect['slot']}|{effect['pick']}"
    data.setlist(f"effect-{effect['id']}-question", [first.key, second.key])
    data.setlist(f"effect-{effect['id']}-choice-{first.key}", [ransom_value])
    data.setlist(f"effect-{effect['id']}-choice-{second.key}", [release_value])
    choices = posted_payload(data)["models"][0]["effects"][0]["choices"]
    assert choices == {first.key: [ransom_value], second.key: [release_value]}
    effect["choices"] = choices
    plan = preview_report(report, actor=owner, payload=payload)
    assert plan.valid, plan.errors
    assert plan.models[0].final_status == Status.RECOVERY
    report = save(report, owner, payload)
    apply(report, owner)
    model.refresh_from_db()
    assert model.status == Status.RECOVERY
    picks = Assignment.objects.filter(
        miniature=model, chosen_for_slot=slot, archived=False
    )
    assert picks.count() == 2
    assert picks.values("chosen_for_status_revision").distinct().count() == 2
    report = start_correction(report, actor=owner)
    payload = deepcopy(report.draft)
    payload["models"][0]["effects"][0]["choices"][second.key] = []
    payload["models"][0]["status"] = ""
    plan = preview_report(report, actor=owner, payload=payload)
    assert plan.valid, plan.errors
    assert [q.key for q in plan.models[0].effects[0].questions] == [
        first.key,
        second.key,
    ]
    assert plan.models[0].final_status == Status.RANSOMED
    report = save(report, owner, payload)
    apply(report, owner)
    model.refresh_from_db()
    assert model.status == Status.RANSOMED


def test_legacy_status_choice_keys_remain_readable_in_drafts_and_corrections(
    report, owner, model, follow_up
):
    captured, _, released, ransom = follow_up
    effect = effect_for(report, owner, captured)
    payload = payload_for(model, effects=[effect])
    question = (
        preview_report(report, actor=owner, payload=payload)
        .models[0]
        .effects[0]
        .questions[0]
    )
    legacy_key = question.key.removeprefix(f"post-battle:{effect['id']}:").rsplit(
        ":status-", 1
    )[0]
    effect["choices"][legacy_key] = [f"library.pickable:{released.pk}"]
    plan = preview_report(report, actor=owner, payload=payload)
    assert plan.valid, plan.errors
    assert plan.models[0].final_status == Status.RECOVERY
    assert plan.models[0].effects[0].questions[0].selected == [
        f"library.pickable:{released.pk}"
    ]
    from n26.core.post_battle_forms import editor_models

    assert editor_models(plan, payload)[0].effects[0].retained_choices == []
    report = save(report, owner, payload)
    apply(report, owner)
    report = start_correction(report, actor=owner)
    payload = deepcopy(report.draft)
    payload["models"][0]["effects"][0]["choices"][legacy_key] = [
        f"library.pickable:{ransom.pk}"
    ]
    payload["models"][0]["status"] = ""
    plan = preview_report(report, actor=owner, payload=payload)
    assert plan.valid, plan.errors
    assert plan.models[0].final_status == Status.RANSOMED
    report = save(report, owner, payload)
    apply(report, owner)
    model.refresh_from_db()
    assert model.status == Status.RANSOMED


@pytest.mark.parametrize("starting_status", [Status.CRITICAL, Status.RANSOMED])
def test_selected_nested_status_choice_resolves_an_existing_status(
    report, owner, model, follow_up, starting_status
):
    captured, _, released, _ = follow_up
    mark(model, starting_status)
    effect = effect_for(report, owner, captured)
    payload = payload_for(model, effects=[effect])
    preview = preview_report(report, actor=owner, payload=payload)
    assert preview.models[0].status_conflict
    question = preview.models[0].effects[0].questions[0]
    effect["choices"][question.key] = [
        next(o.value for o in question.options if o.label == released.name)
    ]
    preview = preview_report(report, actor=owner, payload=payload)
    assert preview.valid, preview.errors
    assert not preview.models[0].status_conflict
    assert preview.models[0].final_status == Status.RECOVERY
    report = save(report, owner, payload)
    apply(report, owner)
    model.refresh_from_db()
    assert model.status == Status.RECOVERY
    assert_reconciled(report.gang)


@pytest.mark.parametrize("whole_gang", [False, True], ids=["model", "gang"])
def test_clones_keep_permanent_results_without_copying_capture_history(
    owner, model, content, follow_up, whole_gang
):
    captured, slot, released, _ = follow_up
    choose(model, content["slot"], content["wound"])
    choose(model, content["slot"], captured)
    choose(model, slot, released)
    assert len(result_history(model)) == 2
    if whole_gang:
        destination = clone_gang(
            model.gang, name="Copied gang", owner=owner, actor=owner
        )
        clone = Miniature.objects.get(membership__gang=destination, name=model.name)
    else:
        destination = model.gang
        with operation(destination, actor=owner) as op:
            clone = op.clone_miniature(model)
    assert result_history(clone) == []
    assert Assignment.objects.filter(
        miniature=clone, pickable=content["wound"], archived=False
    ).exists()
    assert not Assignment.objects.filter(
        miniature=clone, pickable__record_only=True
    ).exists()
    assert len(result_history(model)) == 2
    assert_reconciled(model.gang)
    assert_reconciled(destination)


@pytest.mark.parametrize("whole_gang", [False, True], ids=["model", "gang"])
def test_a_cloned_standing_status_result_does_not_settle_a_fresh_capture(
    owner, model, follow_up, whole_gang
):
    _, slot, released, _ = follow_up
    released.record_only = False
    released.save(update_fields=["record_only"])
    mark(model, Status.CAPTURED)
    choose(model, slot, released)
    if whole_gang:
        destination = clone_gang(model.gang, name="New gang", owner=owner, actor=owner)
        clone = Miniature.objects.get(membership__gang=destination, name=model.name)
    else:
        destination = model.gang
        with operation(destination, actor=owner) as op:
            clone = op.clone_miniature(model)
    result = Assignment.objects.get(miniature=clone, pickable=released, archived=False)
    assert result.chosen_for_slot_id is None
    assert result.chosen_for_id is None
    assert result.chosen_for_status_revision is None
    assert clone.status == Status.ACTIVE
    mark(clone, Status.CAPTURED)
    assert not next(q for q in computed(clone).choices if q.slot.pk == slot.pk).picks
    assert_reconciled(destination)


@pytest.mark.parametrize("whole_gang", [False, True], ids=["model", "gang"])
def test_cloning_keeps_live_models_and_nested_gear_brought_by_a_historical_result(
    owner, model, content, follow_up, whole_gang
):
    captured, _, _, _ = follow_up
    profile = content["profile"]
    pet_profile = create_profile(
        "Rescued companion", profile.profile_type, profile.gang_type
    )
    modifier(
        "A capture brings a companion",
        targets_model(),
        op_adds_model(pet_profile),
        attach_to=captured,
    )
    result = choose(model, content["slot"], captured)
    pet = Miniature.objects.get(membership__caused_by=result)
    gear = create_wargear("Retained equipment")
    with operation(model.gang, actor=owner) as op:
        source_gear = op.assign(gear, parent=result, caused_by=result)
    if whole_gang:
        destination = clone_gang(model.gang, name="New gang", owner=owner, actor=owner)
        clone = Miniature.objects.get(membership__gang=destination, name=model.name)
    else:
        destination = model.gang
        with operation(destination, actor=owner) as op:
            clone = op.clone_miniature(model)
    companion = Miniature.objects.get(
        membership__gang=destination,
        membership__caused_by=clone.membership,
        name=pet.name,
    )
    copied_gear = Assignment.objects.get(miniature=clone, wargear=gear, archived=False)
    assert copied_gear.caused_by_id == clone.membership_id
    assert copied_gear.parent_id is None
    assert companion.membership.caused_by_id == clone.membership_id
    assert result_history(clone) == []
    source_gear.refresh_from_db()
    assert source_gear.parent_id == result.pk
    assert source_gear.caused_by_id == result.pk
    assert_reconciled(model.gang)
    assert_reconciled(destination)


@pytest.mark.parametrize("legacy_receipt", [False, True], ids=["revision", "legacy"])
@pytest.mark.parametrize(
    "intervening_correction", [False, True], ids=["direct", "credits-correction"]
)
@pytest.mark.parametrize("immediate", [False, True], ids=["deferred", "immediate"])
def test_correcting_an_old_escape_does_not_overwrite_a_later_escape_to_the_same_status(
    report, owner, model, follow_up, legacy_receipt, intervening_correction, immediate
):
    from n26.core.models import PostBattleRevision

    captured, slot, released, _ = follow_up
    if immediate:
        effect = effect_for(report, owner, captured)
        payload = payload_for(model, effects=[effect])
        question = (
            preview_report(report, actor=owner, payload=payload)
            .models[0]
            .effects[0]
            .questions[0]
        )
        effect["choices"][question.key] = [f"library.pickable:{released.pk}"]
    else:
        mark(model, Status.CAPTURED)
        effect = effect_for(report, owner, released)
        payload = payload_for(model, effects=[effect])
    report = save(report, owner, payload)
    revision = apply(report, owner)
    if legacy_receipt:
        receipt = deepcopy(revision.receipt)
        for recorded in receipt["models"]:
            recorded.pop("status_revision_after", None)
        PostBattleRevision.objects.filter(pk=revision.pk).update(receipt=receipt)
    mark(model, Status.CAPTURED)
    choose(model, slot, released)
    model.refresh_from_db()
    later_revision = model.status_revision
    if intervening_correction:
        report = start_correction(report, actor=owner)
        payload = deepcopy(report.draft)
        payload["credit_lines"] = [
            {"id": str(uuid4()), "amount": 3, "reason": "Extra income"}
        ]
        report = save(report, owner, payload)
        apply(report, owner)
    report = start_correction(report, actor=owner)
    payload = deepcopy(report.draft)
    payload["models"][0]["effects"] = []
    payload["models"][0]["status"] = ""
    plan = preview_report(report, actor=owner, payload=payload)
    assert not plan.valid
    assert any("status has changed" in error for error in plan.errors)
    model.refresh_from_db()
    assert model.status == Status.RECOVERY
    assert model.status_revision == later_revision


@pytest.mark.parametrize("nested", [False, True], ids=["separate", "nested"])
def test_a_status_choice_without_a_status_effect_does_not_hide_a_conflict(
    report, owner, model, follow_up, gang_type, nested
):
    captured, _, _, _ = follow_up
    kind = create_slot_type("Treatment result")
    waiting = create_pickable("Wait for treatment", kind, record_only=True)
    table = create_picklist("Treatment table", kind, members=[waiting])
    treatment = create_slot(
        "Treatment", kind, table, min_picks=0, max_picks=1, follows_status=True
    )
    modifier(
        "Critical models may choose treatment",
        targets_every_model(has_status(Status.CAPTURED if nested else Status.CRITICAL)),
        ef_adds(treatment),
        attach_to=gang_type,
    )
    mark(model, Status.CRITICAL)
    effect = effect_for(report, owner, captured)
    if nested:
        payload = payload_for(model, effects=[effect])
        plan = preview_report(report, actor=owner, payload=payload)
        question = next(
            q
            for q in plan.models[0].effects[0].questions
            if any(option.label == waiting.name for option in q.options)
        )
        effect["choices"][question.key] = [question.options[0].value]
    else:
        wait = effect_for(report, owner, waiting)
        payload = payload_for(model, effects=[wait, effect])
    plan = preview_report(report, actor=owner, payload=payload)
    assert not plan.valid
    assert plan.models[0].status_conflict
    assert "Critically Injured" in plan.models[0].status_conflict
    assert plan.models[0].final_status == Status.CAPTURED
    model.refresh_from_db()
    assert model.status == Status.CRITICAL


@pytest.mark.parametrize("model_count", [1, 4])
def test_legacy_status_ownership_uses_one_ledger_query_for_all_models(
    report, owner, model, content, follow_up, model_count
):
    from n26.core.models import PostBattleRevision

    captured, _, _, _ = follow_up
    models = [
        model,
        *[
            hire(model.gang, content["profile"], f"Prisoner {i}")
            for i in range(1, model_count)
        ],
    ]
    payload = report_tests.payload_for_all(models)
    initial = preview_report(report, actor=owner, payload=payload)
    for entered in payload["models"]:
        result = next(m for m in initial.models if m.id == entered["id"])
        slot = next(
            s
            for s in result.effect_slots
            if any(o.value == str(captured.pk) for o in s.options)
        )
        entered["effects"] = [
            {
                "id": str(uuid4()),
                "slot": slot.key,
                "pick": str(captured.pk),
                "choices": {},
            }
        ]
    report = save(report, owner, payload)
    revision = apply(report, owner)
    receipt = deepcopy(revision.receipt)
    for recorded in receipt["models"]:
        recorded.pop("status_revision_after", None)
    PostBattleRevision.objects.filter(pk=revision.pk).update(receipt=receipt)
    report = start_correction(report, actor=owner)
    payload = deepcopy(report.draft)
    for entered in payload["models"]:
        entered["effects"] = []
    with CaptureQueriesContext(connection) as queries:
        plan = preview_report(report, actor=owner, payload=payload)
    assert plan.valid, plan.errors
    status_queries = [
        q["sql"]
        for q in queries
        if LedgerEvent._meta.db_table in q["sql"]
        and str(LedgerEvent.Kind.STATUS_SET) in q["sql"]
        and "post_battle_revision" in q["sql"]
    ]
    assert len(status_queries) == 1, status_queries
    assert_reconciled(report.gang)


@pytest.mark.parametrize("max_picks", [1, 2])
def test_a_history_only_status_result_settles_without_appearing_on_the_current_card(
    model, follow_up, max_picks
):
    from n26.core.render import choice_lines
    from n26.library.authoring import revise

    _, slot, _, _ = follow_up
    revise(slot, max_picks=max_picks)
    waiting = create_pickable("Awaiting rescue", slot.slot_type, record_only=True)
    add_picklist_member(slot.picklist, waiting)
    mark(model, Status.CAPTURED)
    result = choose(model, slot, waiting)
    reading = computed(model)
    settled = next(
        q for q in reading.choices if q.slot is not None and q.slot.pk == slot.pk
    )
    assert settled.is_full == (max_picks == 1)
    assert settled.is_resolved
    assert [node.assignment.pk for node in settled.picks] == [result.pk]
    card = build_model_card(model, computed=reading)
    for lines in [card.row_questions, choice_lines(reading, str(model.pk))]:
        shown = [q for q in lines if q.follows_status]
        if max_picks == 1:
            assert not shown
        else:
            assert len(shown) == 1
            assert not shown[0].chosen and not shown[0].is_full
    assert any(entry.name == waiting.name for entry in result_history(model))


@pytest.mark.parametrize("max_picks", [1, 2])
def test_post_battle_offers_only_status_choices_with_remaining_capacity(
    report, owner, model, follow_up, max_picks
):
    from n26.library.authoring import revise

    _, slot, _, _ = follow_up
    revise(slot, max_picks=max_picks)
    waiting = create_pickable("Awaiting rescue", slot.slot_type, record_only=True)
    add_picklist_member(slot.picklist, waiting)
    mark(model, Status.CAPTURED)
    choose(model, slot, waiting)
    plan = preview_report(report, actor=owner, payload=payload_for(model))
    assert any(
        s.key.endswith(f":{slot.pk}") and s.options for s in plan.models[0].effect_slots
    ) == (max_picks == 2)


@pytest.mark.parametrize("outcome", ["waiting", "released", "ransom", "escape"])
def test_a_correction_retains_a_settled_status_result_without_offering_it_again(
    report, owner, model, follow_up, gang_type, outcome
):
    _, slot, released, ransom = follow_up
    if outcome == "waiting":
        result = create_pickable("Awaiting rescue", slot.slot_type, record_only=True)
        add_picklist_member(slot.picklist, result)
    elif outcome == "escape":
        from n26.library.models import Pickable, Slot
        from n26.library.standard_content import STANDARD_CONTENT

        STANDARD_CONTENT["lasting-effect-tables"].create()
        slot = Slot.objects.get(name="Escape", qualifier="")
        result = Pickable.objects.get(name="Daring Escape", slot_type=slot.slot_type)
        modifier(
            "Prisoners may resolve Escape",
            targets_every_model(has_status(Status.CAPTURED)),
            ef_adds(slot),
            attach_to=gang_type,
        )
    else:
        result = released if outcome == "released" else ransom
    mark(model, Status.CAPTURED)
    payload = payload_for(model, effects=[effect_for(report, owner, result)])
    report = save(report, owner, payload)
    apply(report, owner)
    report = start_correction(report, actor=owner)
    plan = preview_report(report, actor=owner)
    assert plan.valid, plan.errors
    assert plan.models[0].effects[0].display_name == result.name
    from n26.core.post_battle_forms import editor_models

    shown = editor_models(plan, report.draft)[0]
    assert shown.effects[0].retained_option
    assert shown.effects[0].name == result.name
    assert shown.effects[0].label == f"{slot.slot_type.name} 1"
    assert not any(value.endswith(f"|{result.pk}") for value, _ in shown.effect_options)
    assert not any(
        s.key.endswith(f":{slot.pk}") and s.options for s in plan.models[0].effect_slots
    )

    from django.template.loader import render_to_string

    html = render_to_string("n26/includes/post_battle_model.html", {"model": shown})
    assert f'aria-label="Remove {slot.slot_type.name} 1"' in html
    assert_reconciled(report.gang)
