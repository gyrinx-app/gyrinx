"""A gang can replace campaign settlements with its own inherent asset."""

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.card import build_gang_card, build_modifier_index, carriers
from n26.core.effects import compute, counter_readings
from n26.core.render import render_campaign, render_gang
from n26.library.authoring import (
    add_asset_type,
    add_built_in,
    create_asset,
    create_gang_type,
    create_pickable,
    create_picklist,
    create_rule,
    create_slot,
    create_slot_type,
    ef_adds,
    ef_excludes_campaign_assets,
    ef_removes,
    has_gang_pickable,
    modifier,
    set_given_to_every_gang,
    set_income,
    targets_gang_alone,
)
from n26.library.core_campaign import seed_core_campaign
from n26.library.forms import ModifierComposerForm, generate_form
from n26.library.models import CampaignType, DefaultAssignment, Modifier
from n26.library.possessions import build_in_missing
from n26.library.specs import specs
from n26.tests.sandbox.actions import (
    add_asset,
    assign,
    create_campaign_asset,
    found_campaign,
    found_gang,
    join_campaign,
    remove,
    remove_from_campaign,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(default_pack):
    seed_core_campaign(apps)
    core = CampaignType.objects.get(name="Territory campaign")
    settlement_type = core.asset_types.get(label_singular="Settlement")
    settlement = core.assets.get(name="Settlement")
    set_income(settlement, 10)
    camp = create_asset(
        "Test base camp", settlement_type, income=25, given_to_every_gang=False
    )
    camp_type = create_gang_type("Camp party")
    replacement = create_rule("Replacement base")
    exclude = modifier(
        "Exclude campaign settlements",
        targets_gang_alone(),
        ef_excludes_campaign_assets(settlement_type),
        attach_to=replacement,
    )
    modifier(
        "Give base camp", targets_gang_alone(), ef_adds(camp), attach_to=replacement
    )
    add_built_in(camp_type, replacement)
    ordinary_type = create_gang_type("Ordinary party")
    player = User.objects.create_user("player")
    arbitrator = User.objects.create_user("arbitrator")
    campaign = found_campaign("Test campaign", core, owner=arbitrator, budget=1000)
    gang = found_gang("Camp gang", camp_type, owner=player)
    ordinary = found_gang("Ordinary gang", ordinary_type, owner=player)
    return dict(
        core=core,
        settlement_type=settlement_type,
        settlement=settlement,
        camp=camp,
        gang=gang,
        ordinary=ordinary,
        campaign=campaign,
        replacement=replacement,
        exclude=exclude,
        player=player,
    )


def join_both(setup):
    for gang in (setup["gang"], setup["ordinary"]):
        join_campaign(gang, setup["campaign"])


def names(gang):
    return [line.name for line in render_gang(gang).campaign.lines]


def income(gang):
    return next(
        line.value
        for line in render_gang(gang).campaign.counters
        if line.name == "Income"
    )


def test_the_replacement_is_an_inherent_settlement_for_only_its_gang(setup):
    join_both(setup)
    assert setup["camp"].is_possession
    assert not DefaultAssignment.objects.filter(asset=setup["camp"]).exists()
    assert names(setup["gang"]) == ["Test base camp"]
    assert names(setup["ordinary"]) == ["Settlement"]
    assert [income(gang) for gang in (setup["gang"], setup["ordinary"])] == [25, 10]
    assert (
        setup["gang"]
        .assignments.filter(asset=setup["settlement"], archived=False)
        .exists()
    )
    assert not setup["gang"].assignments.filter(asset=setup["camp"]).exists()
    line = render_gang(setup["gang"]).campaign.lines[0]
    assert line.type_label == "Settlement"
    assert line.income == 25
    assert line.provenance.computed
    assert line.provenance.source == "Replacement base"


def test_campaign_gang_columns_show_the_replacement_and_its_income(setup):
    join_both(setup)
    sheet = render_campaign(setup["campaign"])
    pos = next(
        i for i, column in enumerate(sheet.asset_types) if column.label == "Settlement"
    )
    incomes = sheet.counter_columns.index("Income")
    by_name = {line.name: line for line in sheet.gangs}
    assert by_name["Camp gang"].assets[pos] == ["Test base camp"]
    assert by_name["Ordinary gang"].assets[pos] == ["Settlement"]
    assert by_name["Camp gang"].counters[incomes].value == 25


def test_custom_settlements_of_the_shared_type_are_excluded(setup):
    create_campaign_asset(
        setup["campaign"], setup["settlement_type"], "Custom settlement", income=7
    )
    join_both(setup)
    assert names(setup["gang"]) == ["Test base camp"]
    assert names(setup["ordinary"]) == ["Settlement", "Custom settlement"]
    assert income(setup["gang"]) == 25
    assert income(setup["ordinary"]) == 17


def test_another_inherent_asset_type_is_still_received(setup):
    other_type = add_asset_type(
        setup["campaign"].additions,
        "Hideout",
        "held-one-each",
        pack=setup["campaign"].pack,
    )
    create_campaign_asset(setup["campaign"], other_type, "Bolthole", income=3)
    join_both(setup)
    assert names(setup["gang"]) == ["Bolthole", "Test base camp"]
    assert income(setup["gang"]) == 28


def test_removing_the_rule_restores_the_campaign_settlement(setup):
    join_both(setup)
    replacement = setup["gang"].assignments.get(
        rule=setup["replacement"], archived=False
    )
    remove(replacement)
    assert names(setup["gang"]) == ["Settlement"]
    assert income(setup["gang"]) == 10


def test_a_named_asset_removal_also_cancels_its_boons(setup):
    cancellation = create_rule("Remove named settlement")
    modifier(
        "Remove settlement",
        targets_gang_alone(),
        ef_removes(setup["settlement"]),
        attach_to=cancellation,
    )
    join_both(setup)
    assignment = assign(cancellation, gang=setup["ordinary"])
    assert names(setup["ordinary"]) == []
    assert income(setup["ordinary"]) == 0
    remove(assignment)
    assert names(setup["ordinary"]) == ["Settlement"]


def test_explicitly_granting_the_same_default_asset_survives_exclusion(setup):
    modifier(
        "Explicit settlement",
        targets_gang_alone(),
        ef_adds(setup["settlement"]),
        attach_to=setup["replacement"],
    )
    join_both(setup)
    assert set(names(setup["gang"])) == {"Settlement", "Test base camp"}
    assert income(setup["gang"]) == 35


def test_the_grant_is_inactive_outside_its_campaign_type(setup):
    card = build_gang_card(setup["gang"], with_statlines=False)
    computed = compute(card, build_modifier_index(carriers(card)))
    assert card.granted == []
    assert counter_readings(card, computed) == []
    join_both(setup)
    assert names(setup["gang"]) == ["Test base camp"]
    remove_from_campaign(setup["gang"], setup["campaign"])
    assert render_gang(setup["gang"]).campaign is None
    card = build_gang_card(setup["gang"], with_statlines=False)
    compute(card, build_modifier_index(carriers(card)))
    assert card.granted == []


def test_grants_and_exclusions_compute_without_database_queries(setup):
    join_both(setup)
    card = build_gang_card(setup["gang"], with_statlines=False)
    index = build_modifier_index(carriers(card))
    with CaptureQueriesContext(connection) as queries:
        computed = compute(card, index)
        assert [
            (r.name, r.value)
            for r in counter_readings(card, computed)
            if r.name == "Income"
        ] == [("Income", 25)]
    assert len(queries) == 0


def test_archive_restore_and_seed_do_not_distribute_modifier_only_assets(setup):
    camp = setup["camp"]
    camp.archive()
    camp.unarchive()
    build_in_missing(apps)
    assert not DefaultAssignment.objects.filter(asset=camp, archived=False).exists()
    join_both(setup)
    assert names(setup["ordinary"]) == ["Settlement"]


def test_distribution_can_be_changed_through_the_authoring_verb(setup):
    camp = setup["camp"]
    set_given_to_every_gang(camp, True)
    assert DefaultAssignment.objects.filter(asset=camp, archived=False).exists()
    set_given_to_every_gang(camp, False)
    assert not DefaultAssignment.objects.filter(asset=camp, archived=False).exists()
    join_both(setup)
    assert names(setup["ordinary"]) == ["Settlement"]


def test_transferable_assets_cannot_be_granted_or_excluded(setup):
    territory = setup["core"].asset_types.get(label_singular="Territory")
    asset = create_asset("Transferable example", territory)
    for verb in (ef_adds, ef_removes):
        with pytest.raises(ValidationError, match="inherent asset"):
            verb(asset)
    with pytest.raises(ValidationError, match="inherent asset type"):
        ef_excludes_campaign_assets(territory)
    join_both(setup)
    with pytest.raises(ValueError):
        add_asset(setup["campaign"], setup["camp"])


def test_authoring_forms_expose_and_save_the_distribution_control(setup):
    form = generate_form(specs()["create_asset"])(
        data={
            "name": "Another camp",
            "asset_type": str(setup["settlement_type"].pk),
            "income": "4",
            "given_to_every_gang": "",
        },
        carrier=setup["settlement_type"],
    )
    assert form.is_valid(), form.errors
    asset = form.compile()
    assert not asset.given_to_every_gang
    edit = generate_form(specs()["create_asset"]).opened_on(
        asset,
        data={"name": asset.name, "income": "4", "given_to_every_gang": "on"},
        prefix="",
    )
    assert edit.is_valid(), edit.errors
    edit.apply_to(asset)
    assert DefaultAssignment.objects.filter(asset=asset, archived=False).exists()


def test_modifier_forms_can_author_asset_grants_and_type_exclusion(setup):
    for effect, payload in (
        (
            "ef_adds",
            {"what-thing_kind": "asset", "what-thing_asset": str(setup["camp"].pk)},
        ),
        (
            "ef_excludes_campaign_assets",
            {"what-asset_type": str(setup["settlement_type"].pk)},
        ),
    ):
        form = ModifierComposerForm(
            data={
                "name": "Authored " + effect,
                "scope_kind": "targets_gang_alone",
                "effect_kind": effect,
                "conditions-TOTAL_FORMS": "0",
                "conditions-INITIAL_FORMS": "0",
                **payload,
            }
        )
        assert form.is_valid(), form.errors
        form.save()
        assert Modifier.objects.filter(name="Authored " + effect).exists()


def test_excluded_boons_stop_reaching_fighters_and_camp_boons_reach_them(
    setup, make_profile
):
    from n26.core.card import build_modifier_index
    from n26.core.effects import compute
    from n26.library.authoring import targets_every_model
    from n26.tests.sandbox.actions import hire

    settlement_rule = create_rule("Settlement fighter boon")
    camp_rule = create_rule("Camp fighter boon")
    for asset, rule in (
        (setup["settlement"], settlement_rule),
        (setup["camp"], camp_rule),
    ):
        modifier(
            "Give " + rule.name, targets_every_model(), ef_adds(rule), attach_to=asset
        )
    join_both(setup)
    profile = make_profile("Test fighter", price=0)
    fighter = hire(setup["gang"], profile, "Test fighter")
    card = build_gang_card(setup["gang"])
    index = build_modifier_index(carriers(card))
    member_card = card.members[fighter.pk]
    with CaptureQueriesContext(connection) as queries:
        computed = compute(member_card, index)
    assert len(queries) == 0
    assert [entry.name for entry in computed.rules] == ["Camp fighter boon"]


def test_settlements_created_after_joining_are_excluded_on_catch_up(setup, task_queue):
    from gyrinx.site.models import Availability, FeatureFlag
    from n26.flags import BUILT_IN_PROPAGATION

    FeatureFlag.objects.create(
        slug=BUILT_IN_PROPAGATION,
        name="Built-in propagation",
        availability=Availability.EVERYONE,
    )
    join_both(setup)
    with task_queue.capture():
        create_campaign_asset(
            setup["campaign"], setup["settlement_type"], "Later settlement", income=9
        )
    task_queue.deliver_all()
    assert names(setup["gang"]) == ["Test base camp"]
    assert names(setup["ordinary"]) == ["Settlement", "Later settlement"]
    assert (
        setup["gang"]
        .assignments.filter(asset__name="Later settlement", archived=False)
        .exists()
    )
    assert income(setup["gang"]) == 25


def test_a_second_granter_keeps_the_asset_when_the_first_is_removed(setup):
    backup = create_rule("Second base camp source")
    modifier(
        "Second camp grant",
        targets_gang_alone(),
        ef_adds(setup["camp"]),
        attach_to=backup,
    )
    join_both(setup)
    assignment = assign(backup, gang=setup["gang"])
    remove(setup["gang"].assignments.get(rule=setup["replacement"], archived=False))
    assert set(names(setup["gang"])) == {"Settlement", "Test base camp"}
    assert income(setup["gang"]) == 35
    remove(assignment)
    assert names(setup["gang"]) == ["Settlement"]


def test_authoring_pickers_offer_only_inherent_assets_and_types(setup):
    territory_type = setup["core"].asset_types.get(label_singular="Territory")
    territory = create_asset("Picker territory", territory_type)
    for verb in ("ef_adds", "ef_removes"):
        form = generate_form(specs()[verb])()
        assert form.fields["thing_asset"].queryset.filter(pk=setup["camp"].pk).exists()
        assert not form.fields["thing_asset"].queryset.filter(pk=territory.pk).exists()
        submitted = generate_form(specs()[verb])(
            data={"thing_kind": "asset", "thing_asset": str(territory.pk)}
        )
        assert not submitted.is_valid()
    form = generate_form(specs()["ef_excludes_campaign_assets"])()
    assert not form.fields["asset_type"].queryset.filter(pk=territory_type.pk).exists()


def test_campaign_page_queries_stay_flat_with_more_gangs_holding_granted_assets(
    setup, client
):
    from gyrinx.site.models import Availability, FeatureFlag
    from n26.flags import CAMPAIGNS

    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
    join_both(setup)
    client.force_login(setup["campaign"].owner)
    url = reverse("n26-campaign", args=[setup["campaign"].pk])

    def count():
        client.get(url)
        with CaptureQueriesContext(connection) as queries:
            response = client.get(url)
        assert response.status_code == 200
        assert "Test base camp" in response.content.decode()
        return len(queries)

    small = count()
    gang_type = (
        setup["gang"].assignments.get(gang_type__isnull=False, archived=False).gang_type
    )
    for number in range(4):
        gang = found_gang(f"Repeated camp {number}", gang_type, owner=setup["player"])
        join_campaign(gang, setup["campaign"])
    assert count() <= small


def test_authoring_pages_describe_the_replacement(setup, client):
    player = setup["player"]
    player.is_staff = True
    player.save(update_fields=["is_staff"])
    client.force_login(player)
    carrier = setup["replacement"]
    response = client.get(reverse("authoring-detail", args=["rule", carrier.pk]))
    assert response.status_code == 200
    assert "campaign-provided Settlements are hidden" in response.content.decode()
    response = client.get(reverse("authoring-modifier", args=[setup["exclude"].pk]))
    assert response.status_code == 200
    assert "Assets given by a modifier remain" in response.content.decode()


@pytest.mark.parametrize("also_grant_default", [False, True])
def test_cancelling_the_replacement_source_restores_default_assets(
    setup, also_grant_default
):
    if also_grant_default:
        modifier(
            "Explicit settlement",
            targets_gang_alone(),
            ef_adds(setup["settlement"]),
            attach_to=setup["replacement"],
        )
    cancellation = create_rule("Cancel replacement")
    modifier(
        "Cancel replacement rule",
        targets_gang_alone(),
        ef_removes(setup["replacement"]),
        attach_to=cancellation,
    )
    join_both(setup)
    assignment = assign(cancellation, gang=setup["gang"])
    assert names(setup["gang"]) == ["Settlement"]
    assert income(setup["gang"]) == 10
    remove(assignment)
    expected = (
        {"Test base camp", "Settlement"} if also_grant_default else {"Test base camp"}
    )
    assert set(names(setup["gang"])) == expected
    assert income(setup["gang"]) == (35 if also_grant_default else 25)


def test_exclusion_preserves_a_default_with_money_behind_it(setup):
    join_both(setup)
    card = build_gang_card(setup["gang"], with_statlines=False)
    settlement = next(
        node for node in card.all_nodes() if node.assignable == setup["settlement"]
    )
    settlement.assignment = None
    settlement.rating = 10
    computed = compute(card, build_modifier_index(carriers(card)))
    assert not settlement.suppressed
    assert (
        next(
            line.value
            for line in counter_readings(card, computed)
            if line.name == "Income"
        )
        == 35
    )
    assert any("Settlement" in step.refused for step in computed.plan)


@pytest.mark.parametrize(
    "independent_name", ["Independent exclusion", "Zulu exclusion"]
)
def test_cancelling_one_exclusion_leaves_another_exclusion_in_force(
    setup, independent_name
):
    independent = create_rule(independent_name)
    modifier(
        "Independent exclusion",
        targets_gang_alone(),
        ef_excludes_campaign_assets(setup["settlement_type"]),
        attach_to=independent,
    )
    cancellation = create_rule("Cancel replacement")
    modifier(
        "Cancel replacement rule",
        targets_gang_alone(),
        ef_removes(setup["replacement"]),
        attach_to=cancellation,
    )
    join_both(setup)
    assign(independent, gang=setup["gang"])
    cancelled = assign(cancellation, gang=setup["gang"])
    assert names(setup["gang"]) == []
    assert income(setup["gang"]) == 0
    remove(cancelled)
    assert names(setup["gang"]) == ["Test base camp"]
    assert income(setup["gang"]) == 25


def test_a_later_round_cancellation_restores_campaign_defaults(setup):
    marker_type = create_slot_type("Cancellation marker")
    marker = create_pickable("Cancel replacement", marker_type)
    choices = create_picklist("Cancellation markers", marker_type, members=[marker])
    slot = create_slot(
        "Cancellation marker", marker_type, choices, assigned_to="gang", hidden=True
    )
    cancellation = create_rule("Conditional cancellation")
    modifier(
        "Give cancellation marker",
        targets_gang_alone(),
        ef_adds(slot, with_pick=marker),
        attach_to=cancellation,
    )
    cancel = modifier(
        "Cancel replacement in a later round",
        targets_gang_alone(has_gang_pickable(marker)),
        ef_removes(setup["replacement"]),
        attach_to=cancellation,
    )
    join_both(setup)
    assign(cancellation, gang=setup["gang"])
    card = build_gang_card(setup["gang"], with_statlines=False)
    computed = compute(card, build_modifier_index(carriers(card)))
    exclusion_step = next(
        step for step in computed.plan if step.modifier == setup["exclude"]
    )
    cancellation_step = next(step for step in computed.plan if step.modifier == cancel)
    assert cancellation_step.ran_in > exclusion_step.ran_in
    assert exclusion_step.outcome == "retracted"
    assert names(setup["gang"]) == ["Settlement"]
    assert income(setup["gang"]) == 10
