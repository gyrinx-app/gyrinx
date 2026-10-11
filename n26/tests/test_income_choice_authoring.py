"""Authoring refusals preserve a declared Income graph and explain the edit."""

from html import unescape

import pytest
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.urls import reverse

from n26.library import authoring
from n26.library.income import income_modifiers, income_of
from n26.library.income_choices import validate_income_choice
from n26.library.models import (
    AddsAssignable,
    AssetType,
    ContributesToCounter,
    GangHasPickable,
    Modifier,
    TargetsGang,
)
from n26.tests.fixtures import library_setup

pytestmark = pytest.mark.django_db


@pytest.fixture
@library_setup
def declared_asset(default_pack):
    campaign_type = authoring.create_campaign_type("Territory campaign")
    asset_type = authoring.add_asset_type(
        campaign_type, "Territory", AssetType.Ownership.HOLDING
    )
    asset = authoring.create_asset("Workshop", asset_type, income=15)
    (baseline,) = income_modifiers(asset)
    kind = authoring.create_slot_type("Workshop boon")
    income = authoring.create_pickable("Income", kind)
    alternative = authoring.create_pickable("Recruitment", kind)
    picks = authoring.create_picklist("Workshop boons", kind, [income, alternative])
    slot = authoring.create_slot("Workshop boon", kind, picks, assigned_to="gang")
    grant = authoring.modifier(
        "Workshop: boon choice",
        authoring.targets_gang_alone(),
        authoring.ef_adds(slot),
        attach_to=asset,
    )
    authoring.detach_modifier(asset, baseline)
    authoring.attach_modifiers_to(income, [baseline])
    authoring.set_base_income_modifier(asset, baseline)
    return asset, baseline, income, alternative, slot, grant


@pytest.fixture
def author(client):
    client.force_login(User.objects.create_user("author", is_staff=True))


def graph_counts():
    return tuple(
        model.objects.count()
        for model in (
            Modifier,
            TargetsGang,
            GangHasPickable,
            ContributesToCounter,
            AddsAssignable,
        )
    )


@pytest.mark.parametrize("edited", ["baseline", "grant"])
def test_adding_a_condition_reports_a_form_error_and_preserves_income(
    client, author, declared_asset, edited
):
    asset, baseline, _, alternative, slot, grant = declared_asset
    modifier = baseline if edited == "baseline" else grant
    before = graph_counts()
    scope_id, effect_id = modifier.targets_gang_id, modifier.effect.pk
    effect = (
        {"what-counter": str(baseline.effect.counter_id), "what-amount": "15"}
        if edited == "baseline"
        else {"what-thing_kind": "slot", "what-thing_slot": str(slot.pk)}
    )
    response = client.post(
        reverse("authoring-modifier", args=[modifier.pk]),
        {
            "name": modifier.name,
            "scope_kind": "targets_gang_alone",
            "effect_kind": "ef_contributes_to_counter"
            if edited == "baseline"
            else "ef_adds",
            **effect,
            "conditions-TOTAL_FORMS": "1",
            "conditions-INITIAL_FORMS": "0",
            "conditions-MIN_NUM_FORMS": "0",
            "conditions-MAX_NUM_FORMS": "1000",
            "conditions-0-kind": "has_gang_pickable",
            "conditions-0-pickables": [str(alternative.pk)],
        },
    )
    assert response.status_code == 200
    errors = response.context["composer"].non_field_errors()
    assert len(errors) == 1
    assert str(errors[0]) in unescape(response.content.decode())
    assert graph_counts() == before
    modifier.refresh_from_db()
    assert (modifier.targets_gang_id, modifier.effect.pk) == (scope_id, effect_id)
    assert not modifier.targets_gang.is_conditional
    assert income_of(asset) == 15
    validate_income_choice(asset)


@pytest.mark.parametrize("inline", [False, True])
def test_composing_a_shared_choice_reports_a_form_error_without_new_parts(
    client, author, declared_asset, inline
):
    asset, _, _, _, slot, _ = declared_asset
    rule = authoring.create_rule("Unrelated rule")
    before = graph_counts()
    address = (
        reverse("authoring-detail", args=["rule", rule.pk])
        if inline
        else reverse("authoring-modifier-create")
    )
    response = client.post(
        address,
        {
            "act": "compose",
            "for_kind": "rule",
            "for": str(rule.pk),
            "scope_kind": "targets_gang_alone",
            "effect_kind": "ef_adds",
            "what-thing_kind": "slot",
            "what-thing_slot": str(slot.pk),
            "conditions-TOTAL_FORMS": "0",
            "conditions-INITIAL_FORMS": "0",
            "conditions-MIN_NUM_FORMS": "0",
            "conditions-MAX_NUM_FORMS": "1000",
        },
    )
    assert response.status_code == 200
    assert "belong only to this asset" in response.content.decode()
    assert graph_counts() == before
    assert not rule.modifiers.exists()
    validate_income_choice(asset)


def test_attaching_declared_income_reports_a_refusal_and_keeps_its_carrier(
    client, author, declared_asset
):
    _, baseline, income, alternative, _, _ = declared_asset
    response = client.post(
        reverse("authoring-detail", args=["pickable", alternative.pk]),
        {"act": "attach", "modifier": str(baseline.pk)},
    )
    assert response.status_code == 302
    assert "exactly one Income pickable" in " ".join(
        str(message) for message in get_messages(response.wsgi_request)
    )
    assert income.modifiers.filter(pk=baseline.pk).exists()
    assert not alternative.modifiers.filter(pk=baseline.pk).exists()


def test_detaching_the_declared_choice_reports_a_refusal_and_keeps_the_grant(
    client, author, declared_asset
):
    asset, *_, grant = declared_asset
    response = client.post(
        reverse("authoring-detail", args=["asset", asset.pk]),
        {"act": "detach", "modifier": str(grant.pk)},
    )
    assert response.status_code == 302
    assert "exactly one boon choice" in " ".join(
        str(message) for message in get_messages(response.wsgi_request)
    )
    assert asset.modifiers.filter(pk=grant.pk).exists()
    validate_income_choice(asset)


def test_bulk_attachment_refusal_rolls_back_earlier_carriers(
    client, author, declared_asset
):
    asset, _, _, _, slot, _ = declared_asset
    plain = authoring.create_asset("Plain territory", asset.asset_type)
    other_kind = authoring.create_slot_type("Another boon")
    other_pick = authoring.create_pickable("Another option", other_kind)
    other_list = authoring.create_picklist("Another list", other_kind, [other_pick])
    other_slot = authoring.create_slot("Another choice", other_kind, other_list)
    extra = authoring.modifier(
        "Another grant", authoring.targets_gang_alone(), authoring.ef_adds(other_slot)
    )
    response = client.post(
        reverse("authoring-attach-modifier", args=["asset"]),
        {"pk": [str(plain.pk), str(asset.pk)], "modifier": str(extra.pk)},
    )
    assert response.status_code == 302
    assert "exactly one boon choice" in " ".join(
        str(message) for message in get_messages(response.wsgi_request)
    )
    assert not plain.modifiers.filter(pk=extra.pk).exists()
    assert not asset.modifiers.filter(pk=extra.pk).exists()
    assert validate_income_choice(asset).slot == slot


def test_an_invalid_slot_edit_reports_a_form_error_and_keeps_the_choice_visible(
    client, author, declared_asset
):
    asset, _, _, _, slot, _ = declared_asset
    response = client.post(
        reverse("authoring-detail", args=["slot", slot.pk]),
        {
            "act": "edit",
            "edit-name": slot.name,
            "edit-picklist": str(slot.picklist_id),
            "edit-min_picks": "1",
            "edit-max_picks": "1",
            "edit-assigned_to": "gang",
            "edit-hidden": "on",
            "edit-mode": "standard",
            "edit-position": "0",
        },
    )
    assert response.status_code == 200
    refusal = "Use one visible, standard gang choice with exactly one pick."
    assert list(response.context["edit_form"].non_field_errors()) == [refusal]
    assert refusal in response.content.decode()
    slot.refresh_from_db()
    assert not slot.hidden
    assert validate_income_choice(asset).slot == slot


def declared_graph_rows(content):
    asset, baseline, income, alternative, slot, grant = content
    return (
        asset,
        baseline,
        income,
        alternative,
        slot,
        grant,
        slot.slot_type,
        slot.picklist,
        *slot.picklist.members.all(),
        baseline.effect.counter,
        baseline.scope,
        baseline.effect,
        grant.scope,
        grant.effect,
    )


def stored_addresses(rows):
    return tuple((type(row), row.pk) for row in rows)


def assert_still_present(addresses):
    for model, pk in addresses:
        assert model.objects.filter(pk=pk).exists(), (
            f"{model.__name__} {pk} disappeared"
        )


@pytest.mark.parametrize("deleted", ["baseline", "grant"])
def test_deleting_a_declared_modifier_reports_a_refusal_and_rolls_back_all_parts(
    client, author, declared_asset, deleted
):
    asset, baseline, _, _, _, grant = declared_asset
    modifier = baseline if deleted == "baseline" else grant
    addresses = stored_addresses(declared_graph_rows(declared_asset))
    before = graph_counts()
    address = reverse("authoring-modifier-delete", args=[modifier.pk])
    response = client.post(address)
    assert response.status_code == 302
    assert response["Location"] == address
    expected = "still in use" if deleted == "baseline" else "exactly one boon choice"
    assert expected in " ".join(
        str(message) for message in get_messages(response.wsgi_request)
    )
    assert_still_present(addresses)
    assert graph_counts() == before
    assert income_of(asset) == 15
    validate_income_choice(asset)


def test_removing_the_income_listing_reports_a_refusal_and_preserves_the_graph(
    client, author, declared_asset
):
    asset, _, income, _, slot, _ = declared_asset
    member = slot.picklist.members.get(pickable=income)
    addresses = stored_addresses(declared_graph_rows(declared_asset))
    before = graph_counts()
    address = reverse("authoring-picklist-member-remove", args=[member.pk])
    response = client.post(address)
    assert response.status_code == 302
    assert response["Location"] == address
    assert "belong only to this asset" in " ".join(
        str(message) for message in get_messages(response.wsgi_request)
    )
    assert_still_present(addresses)
    assert graph_counts() == before
    assert validate_income_choice(asset).pickable == income


def test_deleting_only_the_staged_income_listing_rolls_back_earlier_roots(
    client, author, declared_asset
):
    asset, _, income, _, slot, _ = declared_asset
    member = slot.picklist.members.get(pickable=income)
    authoring.stage(member)
    unrelated = authoring.create_asset(
        "Disposable territory", asset.asset_type, staged=True
    )
    addresses = stored_addresses((*declared_graph_rows(declared_asset), unrelated))
    before = graph_counts()
    address = reverse("authoring-staged-delete")
    response = client.post(address)
    assert response.status_code == 302
    assert response["Location"] == address
    assert "belong only to this asset" in " ".join(
        str(message) for message in get_messages(response.wsgi_request)
    )
    assert_still_present(addresses)
    assert graph_counts() == before
    assert validate_income_choice(asset).pickable == income


def test_a_complete_staged_declared_graph_refuses_without_losing_any_parts(
    client, author, declared_asset
):
    from n26.library.deletion import plan_deletion
    from n26.library.models import Content

    asset, baseline, _, _, _, grant = declared_asset
    rows = declared_graph_rows(declared_asset)
    staged = [row for row in rows if isinstance(row, Content)]
    authoring.stage_all(staged)
    plan = plan_deletion(staged)
    assert plan.ok, plan.refusals
    assert str(baseline.pk) in plan.modifier_ids
    assert str(grant.pk) in plan.modifier_ids
    addresses = stored_addresses(rows)
    before = graph_counts()
    address = reverse("authoring-staged-delete")
    response = client.post(address)
    assert response.status_code == 302
    assert response["Location"] == address
    assert "still in use" in " ".join(
        str(message) for message in get_messages(response.wsgi_request)
    )
    assert_still_present(addresses)
    assert graph_counts() == before
    assert income_of(asset) == 15
    validate_income_choice(asset)
