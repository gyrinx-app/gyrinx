"""An asset's income is a contribution to the system Income counter.

Income is not a figure on the asset. It is a counter every gang in a
Territory campaign has at 0, like Reputation, and each asset adds its
figure to it through a gang-scoped modifier for as long as the gang
holds the asset. A gang's Income reading is therefore the sum of what it
holds — its Settlement and every Territory — and it shows wherever
counters show: the gang sheet's campaign block and the campaign page's
gangs table. Nothing collects it yet.

The forms keep a plain Income box. ``set_income`` writes the modifier
behind it, and the readers take the figure back off the modifiers so a
page prints what the author typed. See ``n26/library/income.py``.
"""

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.render import render_campaign, render_gang
from n26.flags import CAMPAIGNS
from n26.library.authoring import (
    create_asset,
    create_rule,
    ef_adds,
    ef_contributes_to_counter,
    modifier,
    set_income,
    targets_gang,
)
from n26.library.core_campaign import seed_core_campaign
from n26.library.income import (
    INCOME,
    boons_of,
    ensure_income_counter,
    income_counter,
    income_modifiers,
    income_of,
    is_income_contribution,
)
from n26.library.models import Asset, CampaignType, Counter, Modifier
from n26.tests.sandbox.actions import (
    add_asset,
    assign_asset,
    create_campaign_asset,
    found_campaign,
    found_gang,
    join_campaign,
    unassign_asset,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def core(default_pack):
    seed_core_campaign(apps)
    return CampaignType.objects.get(name="Territory campaign")


@pytest.fixture
def territory(core):
    return core.asset_types.get(label_singular="Territory")


@pytest.fixture
def campaign(core):
    arbitrator = User.objects.create_user("arbitrator")
    return found_campaign("Dust Falls", core, owner=arbitrator, budget=1000)


@pytest.fixture
def gangs(gang_type, campaign):
    """Two gangs at the table, so one's Income can be read against the
    other's."""
    made = []
    for name, owner in (("The Ashen Choir", "ash"), ("The Rust Kings", "rust")):
        gang = found_gang(name, gang_type, owner=User.objects.create_user(owner))
        join_campaign(gang, campaign)
        made.append(gang)
    return made


def reading(gang, name=INCOME):
    """A campaign counter's reading off the gang sheet."""
    block = render_gang(gang).campaign
    return next(line.value for line in block.counters if line.name == name)


def column(sheet, gang_name, counter_name):
    line = next(line for line in sheet.gangs if line.name == gang_name)
    position = sheet.counter_columns.index(counter_name)
    counter = line.counters[position]
    return counter.value if counter is not None else None


class TestTheSeed:
    def test_income_is_a_system_counter_built_into_the_territory_campaign(
        self, core, default_pack
    ):
        income = Counter.objects.get(name=INCOME)
        assert income.pack == default_pack
        assert income_counter() == income
        members = core.built_ins.members.filter(counter=income)
        assert [(member.amount, member.position) for member in members] == [(0, 2)]

    def test_running_it_again_changes_nothing(self, core):
        assert seed_core_campaign(apps) == []
        assert Counter.objects.filter(name__iexact=INCOME).count() == 1

    def test_a_differently_cased_counter_is_taken_as_the_one(self, default_pack):
        Counter.objects.create(pack=default_pack, name="income")
        seed_core_campaign(apps)
        assert Counter.objects.filter(name__iexact=INCOME).count() == 1

    def test_every_gang_that_joins_reads_income_at_nought(self, gangs):
        assert [reading(gang) for gang in gangs] == [0, 0]

    def test_the_migration_files_a_propagation_pass_only_when_it_builds_income_in(
        self, default_pack
    ):
        """A built-in written by the seed reaches only gangs that join
        afterwards; the migration files the pass an authoring edit would,
        and only on the run that built Income in — a re-run owes none."""
        from importlib import import_module

        from n26.core.models import BuiltInPropagationTask

        migration = import_module(
            "n26.library.migrations.0086_income_is_a_counter_that_assets_contribute_to"
        )
        lines = seed_core_campaign(apps)
        migration._file_propagation(apps, lines)
        core = CampaignType.objects.get(name="Territory campaign")
        filed = BuiltInPropagationTask.objects.filter(default_set=core.built_ins)
        assert [task.status for task in filed] == ["PENDING"]

        migration._file_propagation(apps, seed_core_campaign(apps))
        assert filed.count() == 1


class TestWritingIncome:
    """The Income box on a form writes one modifier, and edits it in place."""

    def test_creating_with_income_writes_the_contribution(self, territory, core):
        ruins = create_asset("Old Ruins", territory, income=30)
        (row,) = income_modifiers(ruins)
        assert row.name == "Old Ruins: income"
        assert row.pack == ruins.pack
        assert str(row.scope) == "the gang alone"
        assert str(row.effect) == f"adds 30 to {INCOME}"
        assert row.contributes_to_counter.counter == income_counter()
        assert income_of(ruins) == 30
        assert ruins.income == 30

    def test_no_income_writes_nothing(self, territory):
        plain = create_asset("Sludge Sea", territory)
        assert not plain.modifiers.exists()
        assert income_of(plain) == 0

    def test_setting_it_again_changes_the_amount_in_place(self, territory):
        ruins = create_asset("Old Ruins", territory, income=30)
        (before,) = income_modifiers(ruins)
        set_income(ruins, 45)
        (after,) = income_modifiers(ruins)
        assert after.pk == before.pk
        assert income_of(ruins) == 45

    def test_setting_it_to_nought_takes_the_modifier_away(self, territory):
        ruins = create_asset("Old Ruins", territory, income=30)
        (row,) = income_modifiers(ruins)
        scope, effect = row.scope, row.effect
        set_income(ruins, 0)
        assert income_of(ruins) == 0
        assert not Modifier.objects.filter(pk=row.pk).exists()
        # The parts go with it, so nothing unreachable is left behind.
        assert not type(scope).objects.filter(pk=scope.pk).exists()
        assert not type(effect).objects.filter(pk=effect.pk).exists()

    def test_several_contributions_fold_into_one_when_set(self, territory):
        ruins = create_asset("Old Ruins", territory, income=30)
        modifier(
            "Old Ruins: more income",
            targets_gang(),
            ef_contributes_to_counter(income_counter(), 5),
            attach_to=ruins,
        )
        assert income_of(ruins) == 35
        set_income(ruins, 40)
        assert [
            row.contributes_to_counter.amount for row in income_modifiers(ruins)
        ] == [40]

    def test_the_counter_is_created_where_no_seed_has_run(self, default_pack):
        from n26.library.authoring import add_asset_type, create_campaign_type

        assert income_counter() is None
        racket = add_asset_type(create_campaign_type("Dominion"), "Racket", "pooled")
        protection = create_asset("Protection", racket, income=10)
        assert income_counter() is not None
        assert income_of(protection) == 10
        assert ensure_income_counter() == income_counter()

    def test_two_same_named_assets_get_names_apart(self, territory, default_pack):
        create_asset("Old Ruins", territory, income=30)
        other = create_asset("Old Ruins", territory, qualifier="book two", income=15)
        (row,) = income_modifiers(other)
        assert row.name == "Old Ruins (book two): income"

    def test_a_boon_is_not_income_and_income_is_not_a_boon(self, territory):
        ruins = create_asset("Old Ruins", territory, income=30)
        salvage = modifier(
            "Old Ruins: Salvage",
            targets_gang(),
            ef_adds(create_rule("Salvage")),
            attach_to=ruins,
        )
        (income,) = income_modifiers(ruins)
        assert is_income_contribution(income)
        assert not is_income_contribution(salvage)
        assert boons_of(ruins) == [salvage]


class TestWhatAGangReads:
    """A gang's Income is the sum of what it holds, read as any counter."""

    def test_a_held_territory_gives_its_holder_the_figure(
        self, campaign, territory, gangs
    ):
        ruins = create_asset("Old Ruins", territory, income=30)
        held = add_asset(campaign, ruins)
        assign_asset(held, gangs[0])

        assert reading(gangs[0]) == 30
        assert reading(gangs[1]) == 0

        unassign_asset(held)
        assert reading(gangs[0]) == 0

    def test_two_territories_add_up(self, campaign, territory, gangs):
        ruins = create_asset("Old Ruins", territory, income=30)
        toll = create_asset("Toll Crossing", territory, income=20)
        assign_asset(add_asset(campaign, ruins), gangs[0])
        assign_asset(add_asset(campaign, toll), gangs[0])
        assert reading(gangs[0]) == 50

    def test_the_stored_value_stays_at_nought(self, campaign, territory, gangs):
        ruins = create_asset("Old Ruins", territory, income=30)
        assign_asset(add_asset(campaign, ruins), gangs[0])
        income = gangs[0].assignments.get(counter__name=INCOME)
        assert income.counter_value.value == 0

    def test_a_settlement_with_income_gives_every_gang_its_figure(self, core, gangs):
        """A possession is every gang's own, built into the type, so its
        income reaches every gang through the gang's own assignment of it."""
        settlement = Asset.objects.get(name="Settlement")
        set_income(settlement, 10)
        assert [reading(gang) for gang in gangs] == [10, 10]
        block = render_gang(gangs[0]).campaign
        assert [(line.type_label, line.name, line.income) for line in block.lines] == [
            ("Settlement", "Settlement", 10)
        ]

    def test_the_holding_line_prints_the_figure(self, campaign, territory, gangs):
        ruins = create_asset("Old Ruins", territory, income=30)
        assign_asset(add_asset(campaign, ruins), gangs[0])
        block = render_gang(gangs[0]).campaign
        assert [(h.type_label, h.name, h.income) for h in block.holdings] == [
            ("Territory", "Old Ruins", 30)
        ]

    def test_a_captured_gang_state_carries_the_figure(self, campaign, territory, gangs):
        """The before/after capture a conversion checks itself against reads
        the campaign block too, so a holding's figure is part of what it
        proves unchanged."""
        from n26.core.capture import gang_state

        ruins = create_asset("Old Ruins", territory, income=30)
        assign_asset(add_asset(campaign, ruins), gangs[0])
        state = gang_state(gangs[0])
        assert state["campaign"]["holdings"] == [("Territory", "Old Ruins", "30")]
        assert ("Income", "30") in state["campaign"]["counters"]

    def test_the_figure_is_read_without_effects_too(self, campaign, territory, gangs):
        ruins = create_asset("Old Ruins", territory, income=30)
        assign_asset(add_asset(campaign, ruins), gangs[0])
        block = render_gang(gangs[0], with_effects=False).campaign
        assert [h.income for h in block.holdings] == [30]


class TestTheCampaignPage:
    @pytest.fixture(autouse=True)
    def open_to_everyone(self):
        return FeatureFlag.objects.create(
            slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
        )

    def test_the_gangs_table_has_an_income_column(self, campaign, territory, gangs):
        ruins = create_asset("Old Ruins", territory, income=30)
        assign_asset(add_asset(campaign, ruins), gangs[0])

        sheet = render_campaign(campaign)

        assert sheet.counter_columns == ["Reputation", INCOME]
        assert column(sheet, "The Ashen Choir", INCOME) == 30
        assert column(sheet, "The Rust Kings", INCOME) == 0

    def test_the_assets_table_prints_income_and_lists_the_other_boons(
        self, campaign, territory, gangs
    ):
        ruins = create_asset("Old Ruins", territory, income=30)
        modifier(
            "Old Ruins: Salvage",
            targets_gang(),
            ef_adds(create_rule("Salvage")),
            attach_to=ruins,
        )
        add_asset(campaign, ruins)

        (territories,) = render_campaign(campaign).assets
        (entry,) = territories.entries
        assert entry.income == 30
        assert len(entry.boons) == 1
        assert "Salvage" in entry.boons[0]
        assert not any(INCOME in boon for boon in entry.boons)

    def test_the_arbitrator_creates_an_asset_with_income(self, campaign, territory):
        made = create_campaign_asset(campaign, territory, "Sump Hole", income=15)
        assert made.pack == campaign.pack
        (row,) = income_modifiers(made)
        assert row.pack == campaign.pack
        assert income_of(made) == 15

    def test_the_arbitrators_form_writes_it(self, client, campaign, territory):
        client.force_login(campaign.owner)
        response = client.post(
            reverse("n26-campaign-new-asset", args=[campaign.pk]),
            {
                "asset_type": str(territory.pk),
                "name": "Sump Hole",
                "annotation": "",
                "income": "15",
            },
        )
        assert response.status_code == 302
        made = Asset.objects.get(name="Sump Hole")
        assert income_of(made) == 15

    def test_the_add_asset_page_says_the_income(self, client, campaign, territory):
        create_asset("Old Ruins", territory, income=30)
        client.force_login(campaign.owner)
        body = client.get(
            reverse("n26-campaign-add-asset", args=[campaign.pk])
        ).content.decode()
        assert "income 30¢" in body

    def test_income_cannot_be_added_again_as_the_arbitrators_counter(self, campaign):
        from n26.core.operations import Refusal
        from n26.tests.sandbox.actions import add_campaign_counter

        with pytest.raises(Refusal):
            add_campaign_counter(campaign, "Income")


class TestTheAuthoringPages:
    @pytest.fixture
    def author(self, client):
        user = User.objects.create_user("author", is_staff=True)
        client.force_login(user)
        return user

    def test_the_type_page_adds_an_asset_with_income(
        self, author, client, core, territory
    ):
        page = f"/n26/authoring/campaign-type/{core.pk}/"
        response = client.post(
            page,
            {
                "act": "add-asset",
                "part": str(territory.pk),
                f"add-asset-{territory.pk}-name": "Old Ruins",
                f"add-asset-{territory.pk}-income": "10",
            },
        )
        assert response.status_code == 302
        ruins = Asset.objects.get(name="Old Ruins")
        assert income_of(ruins) == 10
        body = client.get(page).content.decode()
        assert "income 10cr · no other modifiers" in body

    def test_editing_the_figure_edits_the_modifier(
        self, author, client, core, territory
    ):
        ruins = create_asset("Old Ruins", territory, income=10)
        (before,) = income_modifiers(ruins)

        page = client.get(f"/n26/authoring/asset/{ruins.pk}/").content.decode()
        assert 'name="edit-income"' in page
        assert 'value="10"' in page

        response = client.post(
            f"/n26/authoring/asset/{ruins.pk}/",
            {"act": "edit", "edit-name": "Older Ruins", "edit-income": "20"},
        )
        assert response.status_code == 302
        ruins.refresh_from_db()
        (after,) = income_modifiers(ruins)
        assert (ruins.name, income_of(ruins), after.pk) == (
            "Older Ruins",
            20,
            before.pk,
        )

    def test_a_blank_box_leaves_the_figure_standing(
        self, author, client, core, territory
    ):
        ruins = create_asset("Old Ruins", territory, income=10)
        client.post(
            f"/n26/authoring/asset/{ruins.pk}/",
            {"act": "edit", "edit-name": "Old Ruins", "edit-income": ""},
        )
        assert income_of(ruins) == 10

    def test_nought_takes_it_away(self, author, client, core, territory):
        ruins = create_asset("Old Ruins", territory, income=10)
        client.post(
            f"/n26/authoring/asset/{ruins.pk}/",
            {"act": "edit", "edit-name": "Old Ruins", "edit-income": "0"},
        )
        assert income_of(ruins) == 0
        assert not ruins.modifiers.exists()

    def test_a_built_in_settlement_with_income_reads_on_the_type_page(
        self, author, client, core
    ):
        settlement = Asset.objects.get(name="Settlement")
        set_income(settlement, 10)
        body = client.get(f"/n26/authoring/campaign-type/{core.pk}/").content.decode()
        assert "income 10cr · no other modifiers" in body
