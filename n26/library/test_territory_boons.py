"""The territory seed adds supported content without rewriting authored graphs."""

from types import SimpleNamespace

import pytest
from django.utils import timezone

from n26.core.models import BuiltInPropagationTask
from n26.library import authoring
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
    Hidden,
    Modifier,
    Pickable,
    Picklist,
    PicklistMember,
    Rule,
    Slot,
    TargetsGang,
)
from n26.library.territory_boons import (
    NOTHING_TO_DO,
    STANDING_BOONS,
    preview,
    seed_all,
)
from n26.tests.fixtures import library_setup
from n26.write_pause import SCOPE, WritesPaused, pause_scope

pytestmark = pytest.mark.django_db


EXPECTED_INCOME = {
    "Settlement": 15,
    "Bullet Den": 15,
    "Rogue Doc Shop": 15,
    "Mess Shack": 15,
    "Drinking Hole": 15,
    "Fence Hangout": 15,
    "Bounty Den": 25,
    "Generatorium": 15,
    "Corpse Farm": 25,
    "Tunnels": 20,
    "Tech Bazaar": 15,
    "Promethium Cache": 15,
    "Collapsed Dome": 20,
    "Bone Shrine": 25,
    "Mine Workings": 20,
    "Gambling Den": 15,
    "Synth Still": 20,
    "Old Ruins": 20,
    "Fighting Pit": 25,
    "Slug House": 20,
    "Flesh-makers Theatre": 15,
    "Fight Arena": 15,
    "Amneo-vats": 15,
    "Feasting Hall": 20,
    "Badzone Smelter": 20,
    "Phelynx Pen": 20,
    "Bio-lab": 15,
    "Wyld Den": 15,
    "Rogue Las Factoria": 20,
    "Chem Arena": 15,
    "Shivver Den": 15,
}


@pytest.fixture
@library_setup
def prepared(default_pack):
    campaign = authoring.create_campaign_type("Territory campaign", pack=default_pack)
    settlement = authoring.add_asset_type(campaign, "Settlement", "held-one-each")
    territory = authoring.add_asset_type(campaign, "Territory", "pooled")
    income = authoring.create_counter("Income", pack=default_pack)
    reputation = authoring.create_counter("Reputation", pack=default_pack)
    kind = authoring.create_slot_type("Gang supertype", pack=default_pack)
    picks = {
        house: authoring.create_pickable(
            house, kind, qualifier="Gang supertype", pack=default_pack
        )
        for house in ("Goliath", "Escher")
    }
    return SimpleNamespace(
        pack=default_pack,
        campaign=campaign,
        settlement=settlement,
        territory=territory,
        income=income,
        reputation=reputation,
        kind=kind,
        picks=picks,
    )


def snapshot():
    models = (
        Asset,
        AssetType,
        CampaignType,
        Counter,
        Modifier,
        AddsAssignable,
        Hidden,
        Hidden.modifiers.through,
        Slot,
        Pickable,
        Pickable.modifiers.through,
        Picklist,
        PicklistMember,
        TargetsGang,
        ContributesToCounter,
        GangHasPickable,
        GangHasPickable.pickables.through,
        Asset.modifiers.through,
        DefaultAssignment,
        DefaultAssignmentSet,
        BuiltInPropagationTask,
    )
    return {
        model._meta.label_lower: list(model.objects.order_by("pk").values())
        for model in models
    }


def baseline(asset):
    return asset.modifiers.get(
        contributes_to_counter__counter__name__iexact="Income",
        targets_gang__has_gang_pickable__isnull=True,
    )


def standing(name):
    return Modifier.objects.get(name=name)


class TestTheSupportedSeed:
    def test_all_source_figures_and_four_typed_effects_are_created_staged(
        self, prepared
    ):
        before_rules = Rule.objects.count()
        report = seed_all()
        assets = {asset.name: asset for asset in Asset.objects.all()}
        assert {name: asset.income for name, asset in assets.items()} == EXPECTED_INCOME
        assert sum(asset.income for asset in assets.values()) == 555
        assert all(asset.staged for asset in assets.values())
        assert all(row.staged for row in Modifier.objects.all())
        assert Modifier.objects.count() == 35
        assert Rule.objects.count() == before_rules
        assert assets["Settlement"].asset_type == prepared.settlement
        assert all(
            asset.asset_type == prepared.territory
            for name, asset in assets.items()
            if name != "Settlement"
        )
        assert "built the Settlement into Territory campaign" in report
        assert any(
            line.startswith("created the ") and line.endswith(" set") for line in report
        )
        assert DefaultAssignment.objects.filter(asset=assets["Settlement"]).count() == 1
        assert BuiltInPropagationTask.objects.count() == 1

        expected = (
            ("Generatorium: standing Reputation", "Reputation", 1, None),
            ("Gambling Den: standing Reputation", "Reputation", 1, None),
            ("Amneo-vats: Goliath standing Income", "Income", 10, "Goliath"),
            ("Shivver Den: Escher standing Reputation", "Reputation", 1, "Escher"),
        )
        for name, counter, amount, house in expected:
            row = standing(name)
            row.full_clean()
            assert row.targets_gang is not None and not row.targets_gang.echoes
            assert row.contributes_to_counter.counter.name == counter
            assert row.contributes_to_counter.amount == amount
            conditions = list(row.targets_gang.has_gang_pickable.all())
            if house is None:
                assert not conditions
            else:
                assert len(conditions) == 1 and not conditions[0].negate
                assert list(conditions[0].pickables.all()) == [prepared.picks[house]]

    def test_preview_rolls_back_assets_modifiers_built_ins_and_propagation(
        self, prepared
    ):
        before = snapshot()
        report = preview()
        assert snapshot() == before
        assert report == seed_all()
        assert BuiltInPropagationTask.objects.count() == 1

    def test_a_rerun_changes_neither_rows_nor_their_timestamps(self, prepared):
        seed_all()
        before = snapshot()
        assert seed_all() == [NOTHING_TO_DO]
        assert preview() == [NOTHING_TO_DO]
        assert snapshot() == before

    def test_an_interruption_rolls_back_the_complete_seed(self, prepared, monkeypatch):
        before = snapshot()
        real_set_income = authoring.set_income
        calls = 0

        def interrupted(asset, amount):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("Interrupted territory seed")
            return real_set_income(asset, amount)

        monkeypatch.setattr(authoring, "set_income", interrupted)
        with pytest.raises(RuntimeError, match="Interrupted territory seed"):
            seed_all()
        assert snapshot() == before


class TestExistingContent:
    def test_correct_live_income_and_asset_flags_stay_as_authored(self, prepared):
        asset = authoring.create_asset("Slug House", prepared.territory, income=20)
        row = baseline(asset)
        before = (asset.modified, row.modified, row.contributes_to_counter.pk)
        seed_all()
        asset.refresh_from_db()
        row.refresh_from_db()
        assert not asset.staged and not row.staged
        assert (asset.modified, row.modified, row.contributes_to_counter.pk) == before

    @pytest.mark.parametrize("amount", [1, 19, 30])
    def test_a_nonzero_authored_income_is_preserved_and_reported(
        self, prepared, amount
    ):
        asset = authoring.create_asset("Slug House", prepared.territory, income=amount)
        row = baseline(asset)
        before = row.contributes_to_counter.pk
        report = seed_all()
        assert asset.income == amount
        assert baseline(asset).contributes_to_counter.pk == before
        assert any("skipped baseline Income for Slug House" in line for line in report)

    def test_an_authored_zero_contribution_is_not_rewritten(self, prepared):
        asset = authoring.create_asset("Slug House", prepared.territory)
        row = authoring.modifier(
            "Authored zero",
            authoring.targets_gang_alone(),
            authoring.ef_contributes_to_counter(prepared.income, 0),
            attach_to=asset,
        )
        report = seed_all()
        assert asset.income == 0
        assert list(asset.modifiers.all()) == [row]
        assert any("skipped baseline Income for Slug House" in line for line in report)

    def test_a_missing_baseline_is_added_without_changing_the_existing_asset(
        self, prepared
    ):
        asset = authoring.create_asset("Slug House", prepared.territory)
        before = asset.modified
        report = seed_all()
        asset.refresh_from_db()
        assert not asset.staged and asset.modified == before
        assert baseline(asset).staged
        assert "added baseline Income 20 to Slug House, staged" in report

    def test_a_correct_contribution_with_another_name_does_not_get_a_duplicate(
        self, prepared
    ):
        asset = authoring.create_asset("Generatorium", prepared.territory, income=15)
        row = authoring.modifier(
            "Authored reputation",
            authoring.targets_gang_alone(),
            authoring.ef_contributes_to_counter(prepared.reputation, 1),
            attach_to=asset,
        )
        seed_all()
        assert (
            asset.modifiers.filter(
                contributes_to_counter__counter=prepared.reputation
            ).count()
            == 1
        )
        assert not Modifier.objects.filter(
            name="Generatorium: standing Reputation"
        ).exists()
        row.refresh_from_db()
        assert not row.staged

    @pytest.mark.parametrize("archived_at", [False, True])
    def test_an_archived_asset_is_not_modified(self, prepared, archived_at):
        asset = authoring.create_asset("Generatorium", prepared.territory)
        authoring.revise(
            asset,
            **({"archived_at": timezone.now()} if archived_at else {"archived": True}),
        )
        report = seed_all()
        assert not asset.modifiers.exists()
        assert "skipped Generatorium: its archive state or asset type differs" in report

    def test_a_wrong_type_asset_is_not_moved_or_given_benefits(self, prepared):
        other = authoring.create_campaign_type("Another campaign", pack=prepared.pack)
        kind = authoring.add_asset_type(other, "Territory", "pooled")
        asset = authoring.create_asset("Generatorium", kind)
        report = seed_all()
        asset.refresh_from_db()
        assert asset.asset_type == kind and not asset.modifiers.exists()
        assert "skipped Generatorium: its archive state or asset type differs" in report

    def test_an_asset_in_another_pack_remains_separate(self, prepared):
        other = authoring.create_pack("Another pack", slug="another-pack")
        outside = authoring.create_asset(
            "Slug House", prepared.territory, pack=other, income=77
        )
        seed_all()
        assert outside.income == 77
        assert (
            Asset.objects.get(
                pack=prepared.pack, name="Slug House", qualifier=""
            ).income
            == 20
        )

    def test_a_qualified_assets_occupied_income_name_is_preserved(self, prepared):
        qualified = authoring.create_asset(
            "Slug House", prepared.territory, qualifier="Authored", income=88
        )
        row = baseline(qualified)
        before = row.modified
        report = seed_all()
        row.refresh_from_db()
        assert qualified.income == 88
        assert baseline(qualified).pk == row.pk and row.modified == before
        canonical = Asset.objects.get(
            pack=prepared.pack, name="Slug House", qualifier=""
        )
        assert canonical.income == 0 and not canonical.modifiers.exists()
        assert (
            "skipped modifier Slug House: income: its name is already used by existing content"
            in report
        )

    def test_case_insensitive_natural_keys_reuse_the_existing_graph(self, prepared):
        authoring.revise(prepared.campaign, name="TERRITORY CAMPAIGN")
        authoring.revise(prepared.territory, label_singular="TERRITORY")
        authoring.revise(prepared.settlement, label_singular="SETTLEMENT")
        authoring.revise(prepared.income, name="INCOME")
        authoring.revise(prepared.reputation, name="REPUTATION")
        authoring.revise(prepared.kind, name="GANG SUPERTYPE")
        authoring.revise(
            prepared.picks["Goliath"], name="GOLIATH", qualifier="GANG SUPERTYPE"
        )
        asset = authoring.create_asset("slug house", prepared.territory, income=20)
        seed_all()
        assert (
            Asset.objects.filter(name__iexact="Slug House", qualifier="").count() == 1
        )
        assert Asset.objects.get(name__iexact="Slug House", qualifier="").pk == asset.pk
        row = standing("Amneo-vats: Goliath standing Income")
        assert list(row.targets_gang.has_gang_pickable.get().pickables.all()) == [
            prepared.picks["Goliath"]
        ]


class TestAuthoredGraphs:
    @pytest.mark.parametrize("graph", ["grant", "built-in", "cyclic grant"])
    def test_nested_hidden_effects_do_not_receive_direct_duplicates(
        self, prepared, graph
    ):
        seed_all()
        asset = Asset.objects.get(name="Generatorium")
        for row in list(asset.modifiers.all()):
            authoring.delete_content(row)
        payload = authoring.create_hidden(
            "Authored territory benefits",
            effects=[
                (
                    authoring.targets_gang_alone(),
                    authoring.ef_contributes_to_counter(prepared.income, 15),
                ),
                (
                    authoring.targets_gang_alone(),
                    authoring.ef_contributes_to_counter(prepared.reputation, 1),
                ),
            ],
            pack=prepared.pack,
        )
        wrapper = authoring.create_hidden(
            "Authored nested territory benefits",
            effects=[(authoring.targets_gang_alone(), authoring.ef_adds(payload))],
            pack=prepared.pack,
        )
        if graph == "cyclic grant":
            authoring.modifier(
                "Authored benefits return to their wrapper",
                authoring.targets_gang_alone(),
                authoring.ef_adds(wrapper),
                attach_to=payload,
                pack=prepared.pack,
            )
        if graph == "built-in":
            authoring.add_built_in(asset, wrapper, pack=prepared.pack)
        else:
            authoring.modifier(
                "Generatorium gives authored benefits",
                authoring.targets_gang_alone(),
                authoring.ef_adds(wrapper),
                attach_to=asset,
                pack=prepared.pack,
            )
        before = snapshot()
        report = preview()
        assert snapshot() == before
        assert seed_all() == report
        assert report[0] == NOTHING_TO_DO
        assert (
            "skipped baseline Income for Generatorium: its existing grants, choices or built-ins are authored"
            in report
        )
        assert (
            "skipped modifier Generatorium: standing Reputation: its existing grants, choices or built-ins are authored"
            in report
        )
        assert snapshot() == before
        assert not asset.modifiers.filter(contributes_to_counter__isnull=False).exists()

    def test_an_ordinary_slot_with_counter_benefits_is_not_given_direct_duplicates(
        self, prepared
    ):
        seed_all()
        asset = Asset.objects.get(name="Generatorium")
        for row in list(asset.modifiers.all()):
            authoring.delete_content(row)
        kind = authoring.create_slot_type(
            "Authored territory choice", pack=prepared.pack
        )
        picks = [
            authoring.create_pickable(
                f"Authored {counter.name}",
                kind,
                effects=[
                    (
                        authoring.targets_gang_alone(),
                        authoring.ef_contributes_to_counter(counter, amount),
                    )
                ],
                pack=prepared.pack,
            )
            for counter, amount in ((prepared.income, 15), (prepared.reputation, 1))
        ]
        picklist = authoring.create_picklist(
            "Authored territory benefits", kind, members=picks, pack=prepared.pack
        )
        slot = authoring.create_slot(
            "Authored territory benefit",
            kind,
            picklist,
            assigned_to="gang",
            pack=prepared.pack,
        )
        row = authoring.modifier(
            "Generatorium offers an authored benefit",
            authoring.targets_gang_alone(),
            authoring.ef_adds(slot),
            attach_to=asset,
            pack=prepared.pack,
        )
        before = snapshot()
        report = seed_all()
        assert report[0] == NOTHING_TO_DO
        assert sum("choices or built-ins are authored" in line for line in report) == 2
        assert list(asset.modifiers.all()) == [row]
        assert snapshot() == before

    def test_correct_direct_effects_stay_unchanged_beside_an_authored_graph(
        self, prepared
    ):
        seed_all()
        asset = Asset.objects.get(name="Generatorium")
        hidden = authoring.create_hidden(
            "Authored additional carrier", pack=prepared.pack
        )
        authoring.modifier(
            "Generatorium gives an authored carrier",
            authoring.targets_gang_alone(),
            authoring.ef_adds(hidden),
            attach_to=asset,
            pack=prepared.pack,
        )
        before = snapshot()
        assert seed_all() == [NOTHING_TO_DO]
        assert snapshot() == before


class TestConflictingModifiers:
    @pytest.mark.parametrize(
        "name", ["Slug House: income", "Generatorium: standing Reputation"]
    )
    def test_an_occupied_seed_name_is_neither_attached_nor_overwritten(
        self, prepared, name
    ):
        rule = authoring.create_rule("Authored rule", pack=prepared.pack)
        row = authoring.modifier(
            name,
            authoring.targets_gang_alone(),
            authoring.ef_adds(rule),
            pack=prepared.pack,
        )
        before = row.modified
        report = seed_all()
        row.refresh_from_db()
        assert row.modified == before and row.adds_assignable.rule == rule
        assert not Asset.objects.filter(modifiers=row).exists()
        assert (
            f"skipped modifier {name}: its name is already used by existing content"
            in report
        )

    @pytest.mark.parametrize(
        "change", ["amount", "echoes", "archived", "archive_timestamp", "counter"]
    )
    def test_an_edited_standing_effect_is_preserved_without_a_duplicate(
        self, prepared, change
    ):
        seed_all()
        row = standing("Generatorium: standing Reputation")
        if change == "amount":
            authoring.revise(row.contributes_to_counter, amount=4)
        elif change == "echoes":
            authoring.revise(row.targets_gang, echoes=True)
        elif change == "counter":
            other = authoring.create_counter("Renown", pack=prepared.pack)
            authoring.revise(row.contributes_to_counter, counter=other)
        else:
            authoring.revise(
                row,
                **(
                    {"archived_at": timezone.now()}
                    if change == "archive_timestamp"
                    else {"archived": True}
                ),
            )
        before = snapshot()
        report = seed_all()
        assert report[0] == NOTHING_TO_DO
        assert any(
            "skipped modifier Generatorium: standing Reputation" in line
            for line in report
        )
        assert snapshot() == before

    @pytest.mark.parametrize("change", ["negate", "empty", "additional", "different"])
    def test_a_changed_house_condition_does_not_get_a_second_effect(
        self, prepared, change
    ):
        seed_all()
        row = standing("Amneo-vats: Goliath standing Income")
        condition = row.targets_gang.has_gang_pickable.get()
        if change == "negate":
            authoring.revise(condition, negate=True)
        elif change == "empty":
            condition.pickables.clear()
        elif change == "additional":
            condition.pickables.add(prepared.picks["Escher"])
        else:
            condition.pickables.set([prepared.picks["Escher"]])
        before = snapshot()
        report = seed_all()
        assert report[0] == NOTHING_TO_DO
        assert any(
            "skipped modifier Amneo-vats: Goliath standing Income" in line
            for line in report
        )
        assert snapshot() == before

    def test_an_equivalent_renamed_house_effect_is_preserved_without_a_duplicate(
        self, prepared
    ):
        seed_all()
        row = standing("Amneo-vats: Goliath standing Income")
        authoring.revise(row, name="Authored Goliath income", staged=False)
        before = snapshot()
        assert seed_all() == [NOTHING_TO_DO]
        assert snapshot() == before

    def test_empty_condition_rows_on_a_baseline_are_preserved_as_authored(
        self, prepared
    ):
        asset = authoring.create_asset("Slug House", prepared.territory, income=20)
        row = baseline(asset)
        GangHasPickable.objects.create(scope=row.targets_gang)
        report = seed_all()
        assert list(asset.modifiers.all()) == [row]
        assert any("skipped baseline Income for Slug House" in line for line in report)

    def test_an_income_counter_from_another_pack_is_not_treated_as_the_system_counter(
        self, prepared
    ):
        other = authoring.create_pack("Other income", slug="other-income")
        counter = authoring.create_counter("Income", pack=other)
        asset = authoring.create_asset("Slug House", prepared.territory)
        row = authoring.modifier(
            "Other pack income",
            authoring.targets_gang_alone(),
            authoring.ef_contributes_to_counter(counter, 20),
            attach_to=asset,
            pack=prepared.pack,
        )
        report = seed_all()
        assert list(asset.modifiers.all()) == [row]
        assert any("skipped baseline Income for Slug House" in line for line in report)


class TestPrerequisitesAndAdmission:
    @pytest.mark.parametrize(
        "missing", ["campaign", "territory", "settlement", "income", "reputation"]
    )
    def test_missing_prerequisites_are_reported_without_creating_content(
        self, prepared, missing
    ):
        authoring.delete_content(getattr(prepared, missing))
        before = snapshot()
        report = seed_all()
        assert report[0] == NOTHING_TO_DO
        assert any("missing" in line for line in report[1:])
        assert snapshot() == before

    def test_a_missing_default_pack_is_not_provisioned(self, prepared, settings):
        settings.DEFAULT_CONTENT_PACK_SLUG = "missing-default-pack"
        before = snapshot()
        assert seed_all() == [
            NOTHING_TO_DO,
            "skipped territory boons: missing default content pack",
        ]
        assert snapshot() == before

    @pytest.mark.parametrize(
        "which", ["pack", "campaign", "territory", "settlement", "income", "reputation"]
    )
    def test_archived_prerequisites_are_reported_without_creating_content(
        self, prepared, which
    ):
        authoring.revise(getattr(prepared, which), archived=True)
        before = snapshot()
        report = seed_all()
        assert report[0] == NOTHING_TO_DO
        assert any("archived" in line for line in report[1:])
        assert snapshot() == before

    def test_an_archived_built_in_set_is_not_extended_for_a_missing_settlement(
        self, prepared
    ):
        authoring.add_built_in(prepared.campaign, prepared.income, pack=prepared.pack)
        prepared.campaign.refresh_from_db()
        default_set = prepared.campaign.built_ins
        authoring.revise(default_set, archived=True)
        before_members = list(default_set.members.values_list("pk", flat=True))
        report = seed_all()
        assert not Asset.objects.filter(name="Settlement").exists()
        assert list(default_set.members.values_list("pk", flat=True)) == before_members
        assert "skipped Settlement: the campaign built-ins are archived" in report

    def test_a_wrong_asset_type_ownership_is_not_changed(self, prepared):
        authoring.revise(prepared.territory, ownership="held-one-each")
        before = snapshot()
        report = seed_all()
        assert report[0] == NOTHING_TO_DO
        assert (
            "skipped territory boons: Territory asset type has a different pack or ownership"
            in report
        )
        assert snapshot() == before

    def test_a_missing_house_pick_skips_only_its_conditional_boon(self, prepared):
        authoring.delete_content(prepared.picks["Goliath"])
        report = seed_all()
        assert Asset.objects.get(name="Amneo-vats").income == 15
        assert not Modifier.objects.filter(
            name="Amneo-vats: Goliath standing Income"
        ).exists()
        assert (
            "skipped Goliath standing boon: missing or archived Gang supertype pick"
            in report
        )
        assert len(STANDING_BOONS) == 4

    def test_preview_and_apply_refuse_a_write_pause_before_any_content_write(
        self, prepared
    ):
        pause_scope(SCOPE, actor=None, reason="Territory maintenance")
        before = snapshot()
        for run in (preview, seed_all):
            with pytest.raises(WritesPaused, match="Territory maintenance"):
                run()
        assert snapshot() == before
