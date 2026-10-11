"""The boon conversion preserves baseline content and reports authored conflicts."""

from types import SimpleNamespace

import pytest

from n26.core.models import Assignment, BuiltInPropagationTask, LedgerEntry, LedgerEvent
from n26.library import authoring as a
from n26.library.models import (
    AddsAssignable,
    Asset,
    AssetType,
    CampaignType,
    ContributesToCounter,
    Counter,
    DefaultAssignment,
    DefaultAssignmentSet,
    GangHasPickable,
    Modifier,
    Pickable,
    Picklist,
    PicklistMember,
    Rule,
    Slot,
    SlotType,
    TargetsGang,
)
from n26.library.territory_boon_choices import (
    ALTERNATIVES,
    NOTHING_TO_DO,
    preview,
    seed_all,
)
from n26.library.territory_boons import seed_all as seed_baselines
from n26.tests.fixtures import library_setup

pytestmark = pytest.mark.django_db


EXPECTED = {
    "Settlement": (15, "Ganger recruitment"),
    "Bullet Den": (15, "Ammo-Jack recruitment"),
    "Rogue Doc Shop": (15, "Rogue Doc recruitment"),
    "Mess Shack": (15, "Slopper recruitment"),
    "Drinking Hole": (15, "Hive Watcher recruitment"),
    "Fence Hangout": (15, "Dome Runner recruitment"),
    "Promethium Cache": (15, "Hazard suits"),
    "Mine Workings": (20, "Respirators"),
    "Flesh-makers Theatre": (15, "Forge Patcher recruitment"),
    "Wyld Den": (15, "Wyld Runner recruitment"),
    "Rogue Las Factoria": (20, "Lasguns"),
    "Chem Arena": (15, "Chem-alchemy Elixir"),
}


@library_setup
def prerequisites(default_pack):
    campaign = a.create_campaign_type("Territory campaign", pack=default_pack)
    settlement = a.add_asset_type(campaign, "Settlement", "held-one-each")
    territory = a.add_asset_type(campaign, "Territory", "pooled")
    income = a.create_counter("Income", pack=default_pack)
    a.create_counter("Reputation", pack=default_pack)
    supertype = a.create_slot_type("Gang supertype", pack=default_pack)
    houses = {
        name: a.create_pickable(
            name, supertype, qualifier="Gang supertype", pack=default_pack
        )
        for name in ("Goliath", "Escher")
    }
    return SimpleNamespace(
        pack=default_pack,
        campaign=campaign,
        settlement=settlement,
        territory=territory,
        income=income,
        houses=houses,
    )


@pytest.fixture
def prepared(default_pack):
    content = prerequisites(default_pack)
    seed_baselines()
    return content


def snapshot():
    models = (
        Asset,
        AssetType,
        CampaignType,
        Counter,
        Modifier,
        Rule,
        AddsAssignable,
        SlotType,
        Slot,
        Pickable,
        Picklist,
        PicklistMember,
        TargetsGang,
        ContributesToCounter,
        GangHasPickable,
        GangHasPickable.pickables.through,
        Asset.modifiers.through,
        Pickable.modifiers.through,
        DefaultAssignment,
        DefaultAssignmentSet,
        BuiltInPropagationTask,
        Assignment,
        LedgerEntry,
        LedgerEvent,
    )
    return {
        model._meta.label_lower: list(model.objects.order_by("pk").values())
        for model in models
    }


def baseline(asset):
    return asset.modifiers.get(
        contributes_to_counter__counter__name="Income",
        targets_gang__has_gang_pickable__isnull=True,
    )


def content_state(asset):
    return (
        Asset.objects.values().get(pk=asset.pk),
        set(asset.modifiers.values_list("pk", flat=True)),
    )


class TestTheConversion:
    def test_twelve_alternatives_move_the_same_baselines_and_keep_catalogue_income(
        self, prepared
    ):
        original_assets = list(Asset.objects.all())
        original = {
            asset.pk: list(asset.modifiers.values_list("pk", flat=True))
            for asset in original_assets
        }
        baselines = {
            asset.name: baseline(asset)
            for asset in original_assets
            if asset.name in EXPECTED
        }
        modifier_records = {
            row.pk: Modifier.objects.values().get(pk=row.pk)
            for row in baselines.values()
        }
        report = seed_all()
        assert len([line for line in report if line.startswith("converted ")]) == 12
        assert {
            entry.asset: (entry.income, entry.name) for entry in ALTERNATIVES
        } == EXPECTED
        assert Asset.objects.count() == 31
        assert Modifier.objects.count() == 47
        assert sum(asset.income for asset in Asset.objects.all()) == 555
        assert (
            Assignment.objects.count()
            == LedgerEntry.objects.count()
            == LedgerEvent.objects.count()
            == 0
        )
        for asset in original_assets:
            asset.refresh_from_db()
            if asset.name not in EXPECTED:
                assert asset.base_income_modifier is None
                assert set(asset.modifiers.values_list("pk", flat=True)) == set(
                    original[asset.pk]
                )
                continue
            income, name = EXPECTED[asset.name]
            assert asset.base_income_modifier_id == baselines[asset.name].pk
            assert (
                Modifier.objects.values().get(pk=asset.base_income_modifier_id)
                == modifier_records[asset.base_income_modifier_id]
            )
            pick = Pickable.objects.get(name="Income", qualifier=asset.name)
            alternative = Pickable.objects.get(name=name, qualifier=asset.name)
            slot = Slot.objects.get(name="Boon", qualifier=asset.name)
            assert pick.modifiers.get() == asset.base_income_modifier
            assert not alternative.modifiers.exists()
            assert not alternative.record_only
            assert (
                "cycle end" in alternative.summary and "manually" in alternative.summary
            )
            assert slot.min_picks == slot.max_picks == 1
            assert slot.assigned_to == "gang" and not slot.hidden
            assert list(
                slot.picklist.members.values_list("pickable__name", flat=True)
            ) == ["Income", name]
            assert asset.income == income
            assert asset.staged and slot.staged and pick.staged and alternative.staged

    def test_new_choices_inherit_each_assets_discovery_stage(self, prepared):
        asset = Asset.objects.get(name="Bullet Den")
        a.put_live(asset)
        seed_all()
        asset.refresh_from_db()
        slot = Slot.objects.get(name="Boon", qualifier=asset.name)
        assert not asset.staged
        assert (
            not slot.staged and not slot.picklist.staged and not slot.slot_type.staged
        )
        assert not slot.picklist.members.filter(staged=True).exists()
        assert not slot.picklist.members.filter(pickable__staged=True).exists()
        assert not asset.modifiers.get(adds_assignable__isnull=False).staged

    def test_independent_standing_contributions_keep_their_complete_graph(
        self, prepared
    ):
        asset = Asset.objects.get(name="Settlement")
        standing = a.modifier(
            "Settlement: Goliath addition",
            a.targets_gang_alone(a.has_gang_pickable(prepared.houses["Goliath"])),
            a.ef_contributes_to_counter(prepared.income, 7),
            attach_to=asset,
            pack=prepared.pack,
        )
        before = (
            Modifier.objects.values().get(pk=standing.pk),
            TargetsGang.objects.values().get(pk=standing.targets_gang_id),
            ContributesToCounter.objects.values().get(
                pk=standing.contributes_to_counter_id
            ),
            list(standing.targets_gang.has_gang_pickable.values()),
        )
        seed_all()
        assert asset.modifiers.filter(pk=standing.pk).exists()
        assert before == (
            Modifier.objects.values().get(pk=standing.pk),
            TargetsGang.objects.values().get(pk=standing.targets_gang_id),
            ContributesToCounter.objects.values().get(
                pk=standing.contributes_to_counter_id
            ),
            list(standing.targets_gang.has_gang_pickable.values()),
        )
        asset.refresh_from_db()
        assert asset.income == 15

    def test_rerunning_changes_no_content_or_player_records(self, prepared):
        seed_all()
        before = snapshot()
        assert seed_all() == [NOTHING_TO_DO]
        assert snapshot() == before

    def test_preview_executes_the_same_conversion_and_rolls_back_every_write(
        self, prepared
    ):
        before = snapshot()
        planned = preview()
        assert snapshot() == before
        assert seed_all() == planned


class TestConflictingContent:
    @pytest.mark.parametrize(
        "change", ("archive", "amount", "shared", "grant", "built-ins", "second-income")
    )
    def test_an_edited_or_shared_baseline_is_preserved_and_reported(
        self, prepared, change
    ):
        asset = Asset.objects.get(name="Bullet Den")
        income = baseline(asset)
        if change == "archive":
            a.revise(income, archived=True)
        elif change == "amount":
            a.revise(income.contributes_to_counter, amount=42)
        elif change == "shared":
            other = a.create_rule("Shared contribution", pack=prepared.pack)
            a.attach_modifiers_to(other, [income])
        elif change == "grant":
            rule = a.create_rule("Authored reward", pack=prepared.pack)
            a.modifier(
                "Authored grant",
                a.targets_gang_alone(),
                a.ef_adds(rule),
                attach_to=asset,
                pack=prepared.pack,
            )
        elif change == "built-ins":
            kit = a.create_default_set("Authored kit", pack=prepared.pack)
            a.revise(asset, built_ins=kit)
        elif change == "second-income":
            a.modifier(
                "More Income",
                a.targets_gang_alone(),
                a.ef_contributes_to_counter(prepared.income, 1),
                attach_to=asset,
                pack=prepared.pack,
            )
        before = content_state(asset)
        report = seed_all()
        assert any(line.startswith("skipped Bullet Den:") for line in report)
        assert content_state(asset) == before
        assert income.pk in set(asset.modifiers.values_list("pk", flat=True))
        assert not Slot.objects.filter(qualifier=asset.name).exists()

    def test_an_incoming_asset_grant_is_preserved_and_reported(self, prepared):
        asset = Asset.objects.get(name="Settlement")
        carrier = a.create_rule("Authored possession", pack=prepared.pack)
        grant = a.modifier(
            "Authored Settlement grant",
            a.targets_gang_alone(),
            a.ef_adds(asset),
            attach_to=carrier,
            pack=prepared.pack,
        )
        before_asset = content_state(asset)
        before_grant = Modifier.objects.values().get(pk=grant.pk)
        report = seed_all()
        assert "skipped Settlement: an existing modifier grants this asset" in report
        assert content_state(asset) == before_asset
        assert Modifier.objects.values().get(pk=grant.pk) == before_grant
        assert carrier.modifiers.get() == grant
        assert not Slot.objects.filter(qualifier=asset.name).exists()

    def test_an_existing_graph_name_is_preserved_including_archived_content(
        self, prepared
    ):
        existing = a.create_slot_type(
            "Bullet Den boon", pack=prepared.pack, archived=True
        )
        before = SlotType.objects.values().get(pk=existing.pk)
        asset = Asset.objects.get(name="Bullet Den")
        before_asset = content_state(asset)
        report = seed_all()
        assert any("skipped Bullet Den: a boon graph name" in line for line in report)
        assert SlotType.objects.values().get(pk=existing.pk) == before
        assert content_state(asset) == before_asset

    def test_an_edited_converted_policy_is_preserved_without_rebuilding_it(
        self, prepared
    ):
        seed_all()
        alternative = Pickable.objects.get(name="Ammo-Jack recruitment")
        a.revise(alternative, summary="An authored manual policy.")
        before = snapshot()
        report = seed_all()
        assert report[0] == NOTHING_TO_DO
        assert any(
            "skipped Bullet Den: its declared boon graph" in line for line in report
        )
        assert snapshot() == before

    def test_sharing_a_converted_income_option_preserves_the_graph_and_reports_it(
        self, prepared
    ):
        seed_all()
        asset = Asset.objects.get(name="Bullet Den")
        extra = a.create_rule("Shared declared baseline", pack=prepared.pack)
        extra.modifiers.add(asset.base_income_modifier)
        before = snapshot()
        report = seed_all()
        assert any(
            "skipped Bullet Den: its declared boon graph" in line for line in report
        )
        assert snapshot() == before

    def test_missing_baseline_content_is_reported_without_provisioning_it(
        self, prepared
    ):
        asset = Asset.objects.get(name="Bullet Den")
        income = baseline(asset)
        a.detach_modifier(asset, income)
        report = seed_all()
        assert any(line.startswith("skipped Bullet Den:") for line in report)
        assert not Asset.objects.get(pk=asset.pk).base_income_modifier_id
        assert Modifier.objects.filter(pk=income.pk).exists()

    def test_missing_prerequisites_are_reported_without_creating_a_default_pack(
        self, prepared, settings
    ):
        settings.DEFAULT_CONTENT_PACK_SLUG = "unprovisioned"
        before = snapshot()
        report = seed_all()
        assert report[0] == NOTHING_TO_DO
        assert "missing default content pack" in report[1]
        assert snapshot() == before
