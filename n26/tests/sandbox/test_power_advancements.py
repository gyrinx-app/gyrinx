"""Power families placed as skill sets use the same advancement flow."""

from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.advancements import preview_advancement, skill_options
from n26.core.models import ActionRecord, Assignment, LedgerEvent
from n26.core.operations import Refusal, operation
from n26.core.reconcile import assert_reconciled
from n26.library import authoring as a
from n26.library.models import Power, Skill
from n26.tests.sandbox import test_advancement_action_flows as skill_flows
from n26.tests.sandbox.test_advancement_action_flows import (
    _choose_result,
    _load_rolls,
    _post_roll,
    _start,
)

pytestmark = pytest.mark.django_db
advancement = skill_flows.advancement


@pytest.fixture(
    params=[("Psi-Gheist", "Psychoteric Whispers"), ("Outcast Leader", "Wyrd Powers")]
)
def wyrd(advancement, request):
    model_name, family_name = request.param
    profile = advancement.fighter.membership.profile
    a.revise(profile, name=model_name)
    collection = a.create_collection("Skills & Powers", contains=[Skill, Power])
    primary = a.section_of(collection, "Primary", 0)
    secondary = a.section_of(collection, "Secondary", 1)
    a.section_of(collection, "Other", 2, is_default=True)
    family = a.create_category("Powers", family_name)
    second_family = a.create_category("Powers", "Secondary powers")
    unrelated = a.create_category("Powers", "Unavailable powers")
    powers = {
        "owned": a.create_power("First power", category=family, position=1),
        "primary": a.create_power("Second power", category=family, position=2),
        "secondary": a.create_power("Third power", category=second_family, position=1),
        "unrelated": a.create_power(
            "Unavailable power", category=unrelated, position=1
        ),
    }
    placements = []
    for category, section in (
        (advancement.skills["primary"].category, primary),
        (advancement.skills["secondary"].category, secondary),
        (family, primary),
        (second_family, secondary),
    ):
        placements.append(
            a.modifier(
                f"{model_name}: {category} is {section}",
                a.targets_model(),
                a.ef_places(category, section),
                attach_to=profile,
            )
        )
    for key, result in advancement.results.items():
        offer = result.modifiers.get().effect
        a.revise(
            offer,
            from_section=primary
            if key in ("primary", "random")
            else secondary
            if key == "secondary"
            else None,
            power_access_collection=collection,
        )
    with operation(advancement.gang, actor=advancement.owner) as op:
        op.assign(powers["owned"], miniature=advancement.fighter)
    return SimpleNamespace(
        advancement=advancement,
        powers=powers,
        family=family,
        secondary=secondary,
        collection=collection,
        placements=placements,
    )


def _confirm(client, response):
    assert response.status_code == 302, response.content.decode()
    page = client.get(response.url)
    token = page.context["form"]["review"].value()
    completed = client.post(response.url, {"review": token})
    assert completed.status_code == 302
    return response.url, token


def test_a_stale_power_selection_uses_power_aware_wording(client, monkeypatch, wyrd):
    data = wyrd.advancement
    _load_rolls(monkeypatch, 12)
    record = _start(client, data)
    _post_roll(client, data, record)
    _choose_result(client, data, record, data.results["primary"])
    record.refresh_from_db()
    power = wyrd.powers["primary"]
    power.archive()
    with pytest.raises(Refusal, match="Choose an available skill or power"):
        preview_advancement(
            record,
            data.outcome.resolve_advancement,
            {"pickable_id": str(data.results["primary"].pk), "skill_id": str(power.pk)},
        )


def test_a_saved_roll_from_before_power_support_can_offer_powers(
    client, monkeypatch, wyrd
):
    data = wyrd.advancement
    _load_rolls(monkeypatch, 12)
    record = _start(client, data)
    _post_roll(client, data, record)
    record.refresh_from_db()
    # Historical roll snapshots predate the new nullable offer field.
    for member in record.terms["advancement_table"]["members"]:
        for modifier in member["modifiers"]:
            effect = modifier[3]
            if effect[0] == "library.offerschoice":
                effect[1] = [
                    field
                    for field in effect[1]
                    if field[0] != "power_access_collection_id"
                ]
    record.save(update_fields=["terms"])
    choice_url = _choose_result(client, data, record, data.results["primary"])
    assert str(wyrd.powers["primary"].pk) in client.get(choice_url).content.decode()
    _confirm(
        client, client.post(choice_url, {"skill_id": str(wyrd.powers["primary"].pk)})
    )
    record.refresh_from_db()
    assert record.skill_selection.selected_power == wyrd.powers["primary"]


@pytest.mark.parametrize(
    ("result_key", "power_key"),
    [("primary", "primary"), ("secondary", "secondary"), ("any", "primary")],
)
def test_a_placed_power_can_replace_a_skill_and_correct_back_to_a_skill(
    client,
    monkeypatch,
    wyrd,
    result_key,
    power_key,
):
    data = wyrd.advancement
    _load_rolls(monkeypatch, 12)
    record = _start(client, data)
    _post_roll(client, data, record)
    choice_url = _choose_result(client, data, record, data.results[result_key])
    page = client.get(choice_url)
    offered_ids = {
        skill["key"]
        for group in page.context["skill_groups"]
        for skill in group["skills"]
    }
    assert str(wyrd.powers[power_key].pk) in offered_ids
    assert str(wyrd.powers["owned"].pk) not in offered_ids
    assert str(wyrd.powers["unrelated"].pk) not in offered_ids
    assert "Select a skill or power" in page.content.decode()
    review = client.post(choice_url, {"skill_id": str(wyrd.powers[power_key].pk)})
    review_url, token = _confirm(client, review)
    assert client.post(review_url, {"review": token}).status_code == 302
    record.refresh_from_db()
    selection = record.skill_selection
    assert selection.selected_power == wyrd.powers[power_key]
    assert selection.selected_skill is None
    assert selection.skill_assignment.power == wyrd.powers[power_key]
    assert selection.skill_assignment.rating == 0
    assert record.terms["skill_kind"] == "power"
    assert record.state == ActionRecord.State.COMPLETED
    assert (
        Assignment.objects.filter(power=wyrd.powers[power_key], archived=False).count()
        == 1
    )
    history = client.get(reverse("n26-edit-fighter", args=[data.fighter.pk]))
    panel = next(
        panel
        for panel in history.context["action_history_panels"]
        if panel.action_id == str(data.action.pk)
    )
    assert str(wyrd.powers[power_key]) in panel.completed[0].detail
    assert str(wyrd.powers[power_key]) in history.content.decode()
    old_assignment = selection.skill_assignment
    old_payment = record.payment_id
    corrected_url = _choose_result(
        client, data, record, data.results["primary"], stage="correct"
    )
    _confirm(
        client, client.post(corrected_url, {"skill_id": str(data.skills["primary"].pk)})
    )
    record.refresh_from_db()
    old_assignment.refresh_from_db()
    assert old_assignment.archived
    assert record.skill_selection.selected_skill == data.skills["primary"]
    assert record.skill_selection.selected_power is None
    assert record.payment_id == old_payment
    assert (
        LedgerEvent.objects.filter(
            action_record=record, kind=LedgerEvent.Kind.ROLLED
        ).count()
        == 1
    )
    data.gang.refresh_from_db()
    assert_reconciled(data.gang)


@pytest.mark.parametrize("secondary", [False, True])
def test_random_powers_keep_their_roll_when_resumed_or_submitted_twice(
    client,
    monkeypatch,
    wyrd,
    secondary,
):
    data = wyrd.advancement
    result = data.results["random"]
    if secondary:
        a.revise(result.modifiers.get().effect, from_section=wyrd.secondary)
    category = wyrd.powers["secondary"].category if secondary else wyrd.family
    power = wyrd.powers["secondary" if secondary else "primary"]
    archived = a.create_power(
        "Superseded power", category=category, position=power.position
    )
    archived.archive()
    _load_rolls(monkeypatch, 12, *([1] if secondary else [1, 2]))
    record = _start(client, data)
    _post_roll(client, data, record)
    choice_url = _choose_result(client, data, record, result)
    page = client.get(choice_url)
    payload = {
        "request_key": page.context["form"]["request_key"].value(),
        "skill_set_id": str(category.pk),
    }
    client.post(choice_url, payload)
    client.post(choice_url, payload)
    resumed = client.get(
        reverse("n26-action-flow", args=[data.fighter.pk, record.pk, "resume"]),
        follow=True,
    )
    if not secondary:
        assert "No available skill or power was rolled." in resumed.content.decode()
        client.post(
            choice_url,
            {
                "request_key": resumed.context["form"]["request_key"].value(),
                "skill_set_id": str(category.pk),
            },
        )
    record.refresh_from_db()
    assert record.skill_selection.selected_power == power
    assert record.skill_selection.random_attempts[-1]["skill_kind"] == "power"
    _confirm(client, client.post(choice_url, {"continue": "1"}))
    record.refresh_from_db()
    assert record.skill_selection.skill_assignment.power == power
    corrected_url = _choose_result(client, data, record, result, stage="correct")
    _confirm(client, client.post(corrected_url, {"continue": "1"}))
    assert Assignment.objects.filter(power=power, archived=False).count() == 1
    assert LedgerEvent.objects.filter(
        action_record=record, kind=LedgerEvent.Kind.ROLLED
    ).count() == (2 if secondary else 3)
    data.gang.refresh_from_db()
    assert_reconciled(data.gang)


def test_an_ordinary_model_cannot_gain_a_power_through_select_any(
    client, monkeypatch, wyrd
):
    data = wyrd.advancement
    profile = data.fighter.membership.profile
    profile.modifiers.remove(*wyrd.placements)
    _load_rolls(monkeypatch, 12)
    record = _start(client, data)
    _post_roll(client, data, record)
    choice_url = _choose_result(client, data, record, data.results["any"])
    page = client.get(choice_url)
    assert not any(
        skill["key"] == str(wyrd.powers["primary"].pk)
        for group in page.context["skill_groups"]
        for skill in group["skills"]
    )
    forged = client.post(choice_url, {"skill_id": str(wyrd.powers["primary"].pk)})
    assert forged.status_code == 200
    assert "skill_id" in forged.context["form"].errors


def test_skill_only_offers_keep_powers_out_of_the_picker(client, monkeypatch, wyrd):
    data = wyrd.advancement
    a.revise(
        data.results["primary"].modifiers.get().effect, power_access_collection=None
    )
    _load_rolls(monkeypatch, 12)
    record = _start(client, data)
    _post_roll(client, data, record)
    choice_url = _choose_result(client, data, record, data.results["primary"])
    page = client.get(choice_url)
    offered_ids = {
        skill["key"]
        for group in page.context["skill_groups"]
        for skill in group["skills"]
    }
    assert str(data.skills["primary"].pk) in offered_ids
    assert str(wyrd.powers["primary"].pk) not in offered_ids


def test_more_powers_do_not_add_a_query_for_each_choice(client, monkeypatch, wyrd):
    data = wyrd.advancement
    _load_rolls(monkeypatch, 12)
    record = _start(client, data)
    _post_roll(client, data, record)
    choice_url = _choose_result(client, data, record, data.results["primary"])
    client.get(choice_url)
    with CaptureQueriesContext(connection) as small:
        assert client.get(choice_url).status_code == 200
    for index in range(12):
        a.create_power(f"Extra power {index}", category=wyrd.family, position=index + 3)
    with CaptureQueriesContext(connection) as large:
        assert client.get(choice_url).status_code == 200
    assert len(large) == len(small)


def test_power_access_uses_the_resolved_grade_and_usability(
    client, monkeypatch, wyrd, make_profile
):
    data = wyrd.advancement
    a.modifier(
        "Secondary placement",
        a.targets_model(),
        a.ef_places(wyrd.family, wyrd.secondary),
        attach_to=data.fighter.membership.profile,
    )
    other_profile = make_profile("Other Wyrd")
    restricted = a.create_power(
        "Restricted power", category=wyrd.family, usable_by_profiles=[other_profile]
    )
    _load_rolls(monkeypatch, 12)
    record = _start(client, data)
    _post_roll(client, data, record)
    configured = data.outcome.resolve_advancement
    record.refresh_from_db()
    primary = skill_options(record, configured, data.results["primary"].pk)
    secondary = skill_options(record, configured, data.results["secondary"].pk)
    assert wyrd.powers["primary"] in primary[wyrd.family]
    assert wyrd.family not in secondary
    assert restricted not in primary[wyrd.family]
