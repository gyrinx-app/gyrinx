"""Selectable Income keeps one ordinary modifier and an unambiguous choice."""

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from n26.library import authoring
from n26.library.income import boons_of, income_modifiers, income_of, with_income
from n26.library.income_choices import declared_income_choice
from n26.library.models import Asset, AssetType

pytestmark = pytest.mark.django_db


@pytest.fixture
def income_choice_graph(default_pack):
    campaign_type = authoring.create_campaign_type("Territory campaign")
    asset_type = authoring.add_asset_type(
        campaign_type, "Territory", AssetType.Ownership.HOLDING
    )
    asset = authoring.create_asset("Workshop", asset_type, income=15)
    (baseline,) = income_modifiers(asset)
    slot_type = authoring.create_slot_type("Workshop boon")
    income = authoring.create_pickable("Income", slot_type)
    alternative = authoring.create_pickable("Recruitment", slot_type)
    picklist = authoring.create_picklist(
        "Workshop boons", slot_type, [income, alternative]
    )
    slot = authoring.create_slot(
        "Workshop boon", slot_type, picklist, assigned_to="gang"
    )
    grant = authoring.modifier(
        "Workshop: boon choice",
        authoring.targets_gang_alone(),
        authoring.ef_adds(slot),
        attach_to=asset,
    )
    authoring.detach_modifier(asset, baseline)
    authoring.attach_modifiers_to(income, [baseline])
    return asset, baseline, income, alternative, slot, grant


@pytest.fixture
def income_choice(income_choice_graph):
    asset, baseline, *_ = income_choice_graph
    authoring.set_base_income_modifier(asset, baseline)
    return income_choice_graph


def test_the_declaration_points_to_the_existing_income_option(income_choice):
    asset, baseline, income, _, slot, _ = income_choice
    choice = declared_income_choice(asset)
    assert (choice.modifier, choice.pickable, choice.slot) == (baseline, income, slot)
    assert income_of(asset) == 15
    assert not asset.modifiers.filter(pk=baseline.pk).exists()


def test_an_echoing_grant_cannot_be_declared_as_the_assets_income_choice(
    income_choice_graph,
):
    asset, baseline, *_, grant = income_choice_graph
    authoring.revise(grant.targets_gang, echoes=True)
    with pytest.raises(ValidationError, match="standard gang choice"):
        authoring.set_base_income_modifier(asset, baseline)
    asset.refresh_from_db()
    assert asset.base_income_modifier_id is None
    assert grant.targets_gang.echoes


def test_an_existing_income_choices_grant_must_remain_the_gangs_alone(
    income_choice,
):
    asset, baseline, _, _, slot, grant = income_choice
    scope = grant.targets_gang
    with pytest.raises(ValidationError, match="standard gang choice"):
        authoring.revise(scope, echoes=True)
    scope.refresh_from_db()
    asset.refresh_from_db()
    assert not scope.echoes
    assert asset.base_income_modifier_id == baseline.pk
    assert declared_income_choice(asset).slot == slot


@pytest.mark.parametrize("carrier_kind", ["asset", "income"])
def test_a_slot_that_the_asset_or_income_option_removes_cannot_be_declared(
    income_choice_graph, carrier_kind
):
    asset, baseline, income, _, slot, _ = income_choice_graph
    carrier = asset if carrier_kind == "asset" else income
    removal = authoring.modifier(
        "Workshop: removed benefit",
        authoring.targets_gang_alone(),
        authoring.ef_removes(slot),
        attach_to=carrier,
    )
    with pytest.raises(ValidationError, match="cannot remove their declared choice"):
        authoring.set_base_income_modifier(asset, baseline)
    asset.refresh_from_db()
    assert asset.base_income_modifier_id is None
    assert carrier.modifiers.filter(pk=removal.pk).exists()


@pytest.mark.parametrize("carrier_kind", ["asset", "income"])
def test_attached_removals_cannot_cancel_the_declared_choice(
    income_choice, carrier_kind
):
    from n26.library.models import Modifier

    asset, baseline, income, _, slot, _ = income_choice
    carrier = asset if carrier_kind == "asset" else income
    before = set(carrier.modifiers.values_list("pk", flat=True))
    with pytest.raises(ValidationError, match="cannot remove their declared choice"):
        authoring.modifier(
            "Workshop: cancelled benefit",
            authoring.targets_gang_alone(),
            authoring.ef_removes(slot),
            attach_to=carrier,
        )
    assert set(carrier.modifiers.values_list("pk", flat=True)) == before
    assert not Modifier.objects.filter(name="Workshop: cancelled benefit").exists()
    assert declared_income_choice(asset).modifier == baseline


@pytest.mark.parametrize("carrier_kind", ["asset", "income"])
def test_editing_an_attached_removal_by_slot_id_preserves_declared_income(
    income_choice, carrier_kind
):
    asset, baseline, income, _, slot, _ = income_choice
    carrier = asset if carrier_kind == "asset" else income
    unrelated = authoring.create_rule("Unrelated benefit")
    removal = authoring.modifier(
        "Workshop: removes another benefit",
        authoring.targets_gang_alone(),
        authoring.ef_removes(unrelated),
        attach_to=carrier,
    )
    effect = removal.removes_assignable
    with pytest.raises(ValidationError, match="cannot remove their declared choice"):
        authoring.revise(effect, rule=None, slot_id=str(slot.pk))
    effect.refresh_from_db()
    assert effect.rule_id == unrelated.pk
    assert effect.slot_id is None
    assert carrier.modifiers.filter(pk=removal.pk).exists()
    assert declared_income_choice(asset).modifier == baseline


def test_a_declared_asset_can_still_remove_unrelated_benefits(income_choice):
    asset, baseline, *_ = income_choice
    unrelated_rule = authoring.create_rule("Unrelated benefit")
    unrelated_type = authoring.create_slot_type("Unrelated choice")
    unrelated_list = authoring.create_picklist("Unrelated choices", unrelated_type)
    unrelated_slot = authoring.create_slot(
        "Unrelated choice", unrelated_type, unrelated_list, assigned_to="gang"
    )
    for target in [unrelated_slot, unrelated_rule]:
        removal = authoring.modifier(
            f"Workshop: removes {target.name}",
            authoring.targets_gang_alone(),
            authoring.ef_removes(target),
            attach_to=asset,
        )
        assert asset.modifiers.filter(pk=removal.pk).exists()
    assert declared_income_choice(asset).modifier == baseline


def test_setting_zero_preserves_the_option_and_its_modifier(income_choice):
    asset, baseline, income, _, _, _ = income_choice
    authoring.set_income(asset, 42)
    assert income_of(asset) == 42
    assert authoring.set_income(asset, 0) == baseline
    asset.refresh_from_db()
    assert asset.base_income_modifier_id == baseline.pk
    assert income.modifiers.filter(pk=baseline.pk).exists()
    assert income_of(asset) == 0
    authoring.set_income(asset, 23)
    assert income_of(asset) == 23


def test_catalogue_reads_are_query_free_after_batch_loading(income_choice):
    asset, *_ = income_choice
    loaded = with_income(Asset.objects.filter(pk=asset.pk)).get()
    with CaptureQueriesContext(connection) as queries:
        assert income_of(loaded) == 15
    assert len(queries) == 0


@pytest.mark.parametrize(
    "fields",
    [
        {"hidden": True},
        {"max_picks": 2},
        {"assigned_to": "bearer"},
        {"follows_status": True},
        {"mode": "tier_ladder"},
    ],
)
def test_later_slot_edits_cannot_make_the_declaration_ambiguous(income_choice, fields):
    *_, slot, _ = income_choice
    before = {name: getattr(slot, name) for name in fields}
    with pytest.raises(ValidationError):
        authoring.revise(slot, **fields)
    slot.refresh_from_db()
    assert {name: getattr(slot, name) for name in fields} == before


def test_the_income_modifier_cannot_be_shared_with_the_alternative(income_choice):
    _, baseline, _, alternative, _, _ = income_choice
    with pytest.raises(ValidationError, match="exactly one Income pickable"):
        authoring.attach_modifiers_to(alternative, [baseline])
    assert not alternative.modifiers.filter(pk=baseline.pk).exists()


@pytest.mark.parametrize("iterable", ["queryset", "generator"])
def test_iterable_attachments_cannot_share_declared_income(income_choice, iterable):
    from n26.library.models import Modifier

    _, baseline, *_ = income_choice
    carrier = authoring.create_rule("Unrelated carrier")
    modifiers = Modifier.objects.filter(pk=baseline.pk)
    if iterable == "generator":
        modifiers = (row for row in modifiers)
    with pytest.raises(ValidationError, match="exactly one Income pickable"):
        authoring.attach_modifiers_to(carrier, modifiers)
    assert not carrier.modifiers.exists()


def test_a_private_income_choice_cannot_be_added_to_another_built_in_set(income_choice):
    _, _, _, _, slot, _ = income_choice
    carrier = authoring.create_gang_type("Another gang type")
    with pytest.raises(ValidationError, match="belong only to this asset"):
        authoring.add_built_in(carrier, slot)
    carrier.refresh_from_db()
    assert carrier.built_ins_id is None


def test_direct_default_members_cannot_share_the_declared_choice(income_choice):
    _, _, _, _, slot, _ = income_choice
    defaults = authoring.create_default_set("Another default set")
    with pytest.raises(ValidationError, match="belong only to this asset"):
        authoring.add_default_member(defaults, slot)
    assert not defaults.members.exists()


def test_the_income_option_cannot_be_a_computed_default(income_choice):
    _, _, income, alternative, slot, _ = income_choice
    picklist = authoring.create_picklist("Another list", slot.slot_type, [alternative])
    nested = authoring.create_slot(
        "Another choice", slot.slot_type, picklist, hidden=True
    )
    with pytest.raises(ValidationError, match="belong only to this asset"):
        authoring.modifier(
            "Another default",
            authoring.targets_gang_alone(),
            authoring.ef_adds(nested, with_pick=income),
            attach_to=alternative,
        )
    assert not alternative.modifiers.exists()


def test_the_income_option_cannot_be_a_built_in_default_elsewhere(income_choice):
    _, _, income, _, slot, _ = income_choice
    picklist = authoring.create_picklist("Another list", slot.slot_type)
    nested = authoring.create_slot("Another choice", slot.slot_type, picklist)
    defaults = authoring.create_default_set("Another default set")
    with pytest.raises(ValidationError, match="belong only to this asset"):
        authoring.add_default_member(defaults, nested, default_pickable=income)
    assert not defaults.members.exists()


def test_creating_another_slot_cannot_share_the_declared_picklist(income_choice):
    _, _, _, _, slot, _ = income_choice
    with pytest.raises(ValidationError, match="belong only to this asset"):
        authoring.create_slot("Another choice", slot.slot_type, slot.picklist)
    assert not slot.picklist.slots.filter(name="Another choice").exists()


def test_a_new_grant_cannot_share_the_declared_slot(income_choice):
    _, _, _, _, slot, _ = income_choice
    carrier = authoring.create_rule("Another carrier")
    with pytest.raises(ValidationError, match="belong only to this asset"):
        authoring.modifier(
            "Another grant",
            authoring.targets_gang_alone(),
            authoring.ef_adds(slot),
            attach_to=carrier,
        )
    assert not carrier.modifiers.exists()


def test_creating_an_asset_cannot_bypass_declaration_validation(income_choice):
    asset, baseline, *_ = income_choice
    with pytest.raises(ValidationError):
        authoring.create_asset(
            "Unwired asset", asset.asset_type, base_income_modifier=baseline
        )
    assert not Asset.objects.filter(name="Unwired asset").exists()


def test_the_income_modifier_cannot_be_detached_from_its_option(income_choice):
    _, baseline, income, _, _, _ = income_choice
    with pytest.raises(ValidationError, match="exactly one Income pickable"):
        authoring.detach_modifier(income, baseline)
    assert income.modifiers.filter(pk=baseline.pk).exists()


def test_the_income_option_cannot_be_removed_from_its_choice(income_choice):
    _, _, income, _, slot, _ = income_choice
    member = slot.picklist.members.get(pickable=income)
    member_id = member.pk
    with pytest.raises(ValidationError, match="belong only to this asset"):
        authoring.remove_picklist_member(member)
    assert slot.picklist.members.filter(pk=member_id).exists()


def test_the_granted_slot_cannot_be_detached_from_the_asset(income_choice):
    asset, *_, grant = income_choice
    with pytest.raises(ValidationError, match="exactly one boon choice"):
        authoring.detach_modifier(asset, grant)
    assert asset.modifiers.filter(pk=grant.pk).exists()


def test_other_direct_income_stays_independent_of_the_declared_base(
    income_choice,
):
    asset, baseline, *_ = income_choice
    extra = authoring.modifier(
        "Workshop: standing income",
        authoring.targets_gang_alone(),
        authoring.ef_contributes_to_counter(baseline.effect.counter, 10),
        attach_to=asset,
    )
    authoring.set_income(asset, 23)
    assert income_of(asset) == 23
    assert asset.modifiers.filter(pk=extra.pk).exists()
    assert extra.effect.amount == 10
    assert extra in boons_of(asset)


def test_a_declaration_cannot_be_cleared_by_a_generic_edit(income_choice):
    asset, baseline, *_ = income_choice
    with pytest.raises(ValidationError, match="must keep"):
        authoring.revise(asset, base_income_modifier=None)
    asset.refresh_from_db()
    assert asset.base_income_modifier_id == baseline.pk


def test_the_income_pick_must_apply_its_modifiers(income_choice):
    _, _, income, *_ = income_choice
    with pytest.raises(ValidationError, match="apply its modifiers"):
        authoring.revise(income, record_only=True)
    income.refresh_from_db()
    assert not income.record_only


def test_an_ordinary_direct_income_modifier_still_disappears_at_zero(default_pack):
    campaign_type = authoring.create_campaign_type("Direct income campaign")
    asset_type = authoring.add_asset_type(
        campaign_type, "Territory", AssetType.Ownership.HOLDING
    )
    asset = authoring.create_asset("Old Ruins", asset_type, income=20)
    authoring.set_income(asset, 0)
    assert income_of(asset) == 0
    assert income_modifiers(asset) == []
