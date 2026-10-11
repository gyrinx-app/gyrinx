"""Standing territory readings follow ownership and the holder's House."""

from uuid import uuid4

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.test import RequestFactory

from n26.core.campaigns import campaign_operation
from n26.core.models import LedgerEvent, Miniature
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_campaign, render_gang
from n26.core.views.campaign_assets import _asset_context
from n26.library.authoring import (
    add_built_in,
    create_gang_type,
    create_hidden,
    create_pickable,
    create_picklist,
    create_slot,
    create_slot_type,
    ef_adds,
    ef_contributes_to_counter,
    modifier,
    targets_gang_alone,
)
from n26.library.core_campaign import CAMPAIGN_TYPE, seed_core_campaign
from n26.library.gang_supertypes import seed_gang_supertypes
from n26.library.models import Asset, CampaignType, Counter, Modifier, Slot
from n26.library.territory_boons import NOTHING_TO_DO, preview, seed_all
from n26.library.territory_table import seed_territory_table
from n26.tests.fixtures import library_setup
from n26.tests.sandbox.actions import (
    add_asset,
    assign_asset,
    choose,
    found_campaign,
    found_gang,
    join_campaign,
    remove,
    transfer_asset,
    unassign_asset,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
@library_setup
def content(default_pack):
    seed_core_campaign(apps)
    seed_territory_table(apps)
    kinds = {name: create_gang_type(name) for name in ("Goliath", "Escher", "Outcast")}
    clan_type = create_slot_type("Clan House")
    picks = [
        create_pickable(f"House {name}", clan_type) for name in ("Goliath", "Escher")
    ]
    clan_list = create_picklist("Clan Houses", clan_type, members=picks)
    clan_slot = create_slot("Clan House", clan_type, clan_list, assigned_to="gang")
    add_built_in(kinds["Outcast"], clan_slot)
    seed_gang_supertypes()
    for kind in kinds.values():
        kind.refresh_from_db()
    return {
        "campaign_type": CampaignType.objects.get(name=CAMPAIGN_TYPE),
        "kinds": kinds,
        "clan_picks": picks,
        "clan_slot": clan_slot,
    }


@pytest.fixture
def campaign(content):
    return found_campaign(
        "Standing boon checks",
        content["campaign_type"],
        owner=User.objects.create_user("arbitrator"),
        budget=1000,
    )


def member(campaign, content, house, name):
    gang = found_gang(
        name, content["kinds"][house], owner=User.objects.create_user(name)
    )
    join_campaign(gang, campaign)
    return gang


def readings(gang):
    return {line.name: line.value for line in render_gang(gang).campaign.counters}


def holding_readings(campaign):
    return {
        entry.campaign_asset_id: entry.income
        for group in render_campaign(campaign, viewer=campaign.owner).assets
        for entry in group.entries
    }


def clan_choice(gang):
    return next(row for row in gang.assignments.filter(archived=False) if row.slot_id)


class TestStandingReadings:
    def test_the_seed_changes_already_held_assets_without_moving_money(
        self, campaign, content
    ):
        gang = member(campaign, content, "Goliath", "Irontooth")
        generator = assign_asset(
            add_asset(campaign, Asset.objects.get(name="Generatorium")), gang
        )
        before = (
            gang.credits,
            gang.rating,
            gang.wealth,
            LedgerEvent.objects.count(),
            Miniature.objects.count(),
        )
        assert readings(gang) == {"Reputation": 0, "Income": 0}
        assert preview() != [NOTHING_TO_DO]
        assert readings(gang) == {"Reputation": 0, "Income": 0}

        seed_all()

        assert readings(gang) == {"Reputation": 1, "Income": 30}
        assert holding_readings(campaign)[str(generator.pk)] == 15
        request = RequestFactory().get("/")
        request.user = campaign.owner
        assert (
            _asset_context(request, campaign.pk, generator.pk)["details"].income == 15
        )
        gang.refresh_from_db()
        assert (
            gang.credits,
            gang.rating,
            gang.wealth,
            LedgerEvent.objects.count(),
            Miniature.objects.count(),
        ) == before
        assert_reconciled(gang)

    def test_two_copies_stack_and_transfer_rechecks_the_new_holders_house(
        self, campaign, content
    ):
        seed_all()
        goliath = member(campaign, content, "Goliath", "Irontooth")
        escher = member(campaign, content, "Escher", "Wild Roses")
        vats = Asset.objects.get(name="Amneo-vats")
        first = assign_asset(add_asset(campaign, vats), goliath)
        second = assign_asset(add_asset(campaign, vats), goliath)
        assert readings(goliath)["Income"] == 65
        assert holding_readings(campaign)[str(first.pk)] == 25
        assert holding_readings(campaign)[str(second.pk)] == 25

        transfer_asset(first, escher)
        assert readings(goliath)["Income"] == 40
        assert readings(escher)["Income"] == 30
        assert holding_readings(campaign)[str(first.pk)] == 15
        unassign_asset(second)
        assert readings(goliath)["Income"] == 15
        assert holding_readings(campaign)[str(second.pk)] == 15
        assign_asset(second, goliath)
        assert readings(goliath)["Income"] == 40
        for gang in (goliath, escher):
            gang.refresh_from_db()
            assert_reconciled(gang)

    def test_a_campaign_override_replaces_baseline_and_keeps_house_income(
        self, campaign, content
    ):
        seed_all()
        gang = member(campaign, content, "Goliath", "Irontooth")
        vats = Asset.objects.get(name="Amneo-vats")
        with campaign_operation(campaign, actor=campaign.owner) as op:
            op.add_assets([vats], income=42, request_key=uuid4())
        holding = campaign.campaign_assets.get(asset=vats)
        assert holding_readings(campaign)[str(holding.pk)] == 42
        assign_asset(holding, gang)
        assert holding_readings(campaign)[str(holding.pk)] == 52
        assert readings(gang)["Income"] == 67
        assert Asset.objects.get(pk=vats.pk).income == 15

    @pytest.mark.parametrize(
        "house,territory,expected_income,expected_rep",
        [
            ("Goliath", "Amneo-vats", 40, 0),
            ("Escher", "Amneo-vats", 30, 0),
            ("Escher", "Shivver Den", 30, 1),
            ("Goliath", "Shivver Den", 30, 0),
            ("Goliath", "Gambling Den", 30, 1),
        ],
    )
    def test_only_the_matching_house_gets_its_standing_boon(
        self, campaign, content, house, territory, expected_income, expected_rep
    ):
        seed_all()
        gang = member(campaign, content, house, "House check")
        assign_asset(add_asset(campaign, Asset.objects.get(name=territory)), gang)
        assert readings(gang) == {"Income": expected_income, "Reputation": expected_rep}

    def test_an_outcast_house_change_recomputes_boons_and_removal_retracts_them(
        self, campaign, content
    ):
        seed_all()
        gang = member(campaign, content, "Outcast", "The Cast Out")
        for name in ("Amneo-vats", "Shivver Den"):
            assign_asset(add_asset(campaign, Asset.objects.get(name=name)), gang)
        assert readings(gang) == {"Income": 45, "Reputation": 0}
        anchor = clan_choice(gang)
        goliath_pick = choose(anchor, content["clan_picks"][0])
        assert readings(gang) == {"Income": 55, "Reputation": 0}
        with operation(gang, actor=gang.owner) as op:
            op.remove(goliath_pick)
            op.choose(anchor, content["clan_picks"][1])
        assert readings(gang) == {"Income": 45, "Reputation": 1}
        selected = gang.assignments.get(
            pickable=content["clan_picks"][1], archived=False
        )
        remove(selected)
        assert readings(gang) == {"Income": 45, "Reputation": 0}

    def test_a_house_variant_uses_its_supertype_without_name_dispatch(
        self, campaign, content
    ):
        seed_all()
        variant = create_gang_type("Furnace descendants")
        supertype = Slot.objects.get(name="Gang supertype")
        from n26.library.gang_supertypes import supertype_pick

        add_built_in(variant, supertype, default_pickable=supertype_pick("Goliath"))
        variant.refresh_from_db()
        content["kinds"]["variant"] = variant
        gang = member(campaign, content, "variant", "Furnace gang")
        assign_asset(add_asset(campaign, Asset.objects.get(name="Amneo-vats")), gang)
        assert readings(gang)["Income"] == 40

    def test_existing_journal_maintenance_keeps_the_new_standing_effects(
        self, campaign, content
    ):
        from n26.library.journal_content import seed_all as seed_journals
        from n26.library.published_journal_boons import remove_published_journal_boons

        seed_all()
        identifiers = set(
            Modifier.objects.filter(name__contains="standing").values_list(
                "pk", flat=True
            )
        )
        assert len(identifiers) == 4
        seed_journals()
        remove_published_journal_boons()
        assert (
            set(
                Modifier.objects.filter(pk__in=identifiers).values_list("pk", flat=True)
            )
            == identifiers
        )
        gang = member(campaign, content, "Goliath", "After journal maintenance")
        assign_asset(add_asset(campaign, Asset.objects.get(name="Amneo-vats")), gang)
        assert readings(gang)["Income"] == 40

    def test_authored_nested_income_and_reputation_are_not_doubled_by_the_seed(
        self, campaign, content
    ):
        asset = Asset.objects.get(name="Generatorium")
        bundle = create_hidden(
            "Authored Generatorium effects",
            effects=[
                (
                    targets_gang_alone(),
                    ef_contributes_to_counter(Counter.objects.get(name="Income"), 15),
                ),
                (
                    targets_gang_alone(),
                    ef_contributes_to_counter(
                        Counter.objects.get(name="Reputation"), 1
                    ),
                ),
            ],
        )
        authored = modifier(
            "Generatorium grants authored effects",
            targets_gang_alone(),
            ef_adds(bundle),
            attach_to=asset,
        )
        gang = member(campaign, content, "Goliath", "Authored effects check")
        assign_asset(add_asset(campaign, asset), gang)
        assert readings(gang) == {"Income": 15, "Reputation": 1}

        report = seed_all()

        assert any("skipped" in line and "Generatorium" in line for line in report)
        assert list(asset.modifiers.all()) == [authored]
        assert readings(gang) == {"Income": 30, "Reputation": 1}
