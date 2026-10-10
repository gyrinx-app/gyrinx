"""The core Territory content seed: the eighteen Territories on the core
Territory Selection Table get their income and boons, once, as a
maintenance operation.

What this file holds: every Territory gets the book's income; a figure an
author already entered is kept and the line says so; Generatorium and
Gambling Den add Reputation; the recruit, equipment and special boons are
named rules on the holder; a rerun writes nothing and says so; the preview
writes nothing; a gang that holds a seeded Territory reads its income,
Reputation and rule; and the console previews, enqueues, records and stands
down on a redelivery.
"""

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.maintenance.models import Backfill
from gyrinx.site.models import Availability, FeatureFlag
from n26.core.card import build_gang_card, build_modifier_index, carriers
from n26.core.effects import compute_gang
from n26.core.render import render_gang
from n26.flags import CAMPAIGNS
from n26.library.authoring import set_income
from n26.library.core_campaign import CAMPAIGN_TYPE, REPUTATION, seed_core_campaign
from n26.library.core_territory_content import (
    NOTHING_TO_DO,
    TERRITORIES,
    preview,
    seed_all,
)
from n26.library.income import INCOME, income_of
from n26.library.models import Asset, CampaignType, Modifier, Rule
from n26.library.territory_table import seed_territory_table
from n26.maintenance import Operation, seed_core_territory_content
from n26.tests.sandbox.actions import (
    add_asset,
    assign_asset,
    found_campaign,
    found_gang,
    join_campaign,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def core(default_pack):
    """The Territory campaign type as it ships: the eighteen Territories
    on its table, with no income and no boons."""
    seed_core_campaign(apps)
    seed_territory_table(apps)
    return CampaignType.objects.get(name=CAMPAIGN_TYPE)


@pytest.fixture
def seeded(core):
    return seed_all()


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser("boss", "boss@example.com", "password")


def territory(name):
    return Asset.objects.get(name=name)


def counter_reading(gang, name):
    block = render_gang(gang).campaign
    return next(line.value for line in block.counters if line.name == name)


def gang_rules(gang):
    card = build_gang_card(gang)
    index = build_modifier_index(carriers(card))
    return [str(c.thing) for c in compute_gang(card, index).rules]


class TestTheSeed:
    """Each Territory gets the book's income and its boon, once; a figure
    already entered stays; a rerun writes nothing and says so."""

    def test_the_territories_start_with_no_income(self, core):
        assert {income_of(territory(t.name)) for t in TERRITORIES} == {0}

    def test_every_territory_gets_the_books_income(self, seeded):
        assert {t.name: income_of(territory(t.name)) for t in TERRITORIES} == {
            t.name: t.income for t in TERRITORIES
        }
        assert "Bullet Den: income 15" in seeded
        assert "Fighting Pit: income 25" in seeded

    def test_generatorium_and_gambling_den_add_reputation(self, seeded):
        for name in ("Generatorium", "Gambling Den"):
            boon = Modifier.objects.get(name=f"{name}: {REPUTATION}")
            assert boon.contributes_to_counter.counter.name == REPUTATION
            assert boon.contributes_to_counter.amount == 1
            assert territory(name).modifiers.filter(pk=boon.pk).exists()

    def test_the_other_boons_are_named_rules(self, seeded):
        named = {
            (rule.name, rule.annotation)
            for rule in Rule.objects.filter(
                annotation__in=[t.name for t in TERRITORIES]
            )
        }
        assert named == {
            ("Recruit", "Bullet Den"),
            ("Recruit", "Rogue Doc Shop"),
            ("Recruit", "Mess Shack"),
            ("Recruit", "Drinking Hole"),
            ("Recruit", "Fence Hangout"),
            ("Special", "Tech Bazaar"),
            ("Equipment", "Promethium Cache"),
            ("Equipment", "Mine Workings"),
        }
        assert (
            "Promethium Cache: the Equipment (Promethium Cache) rule for the gang "
            "that holds it (the book offers it instead of the income)"
        ) in seeded
        assert (
            "Tech Bazaar: the Special (Tech Bazaar) rule for the gang that holds it"
        ) in seeded

    def test_an_income_already_entered_is_kept(self, core):
        set_income(territory("Old Ruins"), 30)

        lines = seed_all()

        assert income_of(territory("Old Ruins")) == 30
        assert "skipped the income of Old Ruins: it already has 30" in lines
        assert "Old Ruins: income 20" not in lines

    def test_running_it_again_writes_nothing_and_says_so(self, seeded):
        modifiers = Modifier.objects.count()
        rules = Rule.objects.count()

        again = seed_all()

        assert again[0] == NOTHING_TO_DO
        assert all(line.startswith("skipped") for line in again[1:])
        assert len(again) == 1 + len(TERRITORIES)
        assert (Modifier.objects.count(), Rule.objects.count()) == (modifiers, rules)

    def test_the_preview_says_the_same_and_writes_nothing(self, core):
        modifiers = Modifier.objects.count()

        lines = preview()

        assert "Bullet Den: income 15" in lines
        assert Modifier.objects.count() == modifiers
        assert income_of(territory("Bullet Den")) == 0

    def test_a_missing_territory_is_skipped_and_said(self, core):
        Asset.objects.filter(name="Tunnels").update(name="Tunnel Rats")

        lines = seed_all()

        assert "skipped Tunnels: the system pack has no territory of that name" in (
            lines
        )
        assert "Bullet Den: income 15" in lines


class TestASeededTerritoryInPlay:
    """A gang holding a seeded Territory reads its income, its Reputation
    and its rule, whether it took the Territory before the seed ran or
    after."""

    @pytest.fixture(autouse=True)
    def campaigns_open(self, db):
        return FeatureFlag.objects.create(
            slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
        )

    @pytest.fixture
    def gang(self, core, gang_type):
        campaign = found_campaign(
            "Dust Falls", core, owner=User.objects.create_user("arbitrator")
        )
        gang = found_gang(
            "The Ashen Choir", gang_type, owner=User.objects.create_user("player")
        )
        join_campaign(gang, campaign)
        gang.test_campaign = campaign
        return gang

    def test_bullet_den_brings_its_income_and_the_recruit_rule(self, seeded, gang):
        assign_asset(add_asset(gang.test_campaign, territory("Bullet Den")), gang)

        assert counter_reading(gang, INCOME) == 15
        assert "Recruit (Bullet Den)" in gang_rules(gang)

    def test_generatorium_brings_one_reputation(self, seeded, gang):
        before = counter_reading(gang, REPUTATION)

        assign_asset(add_asset(gang.test_campaign, territory("Generatorium")), gang)

        assert counter_reading(gang, REPUTATION) == before + 1
        assert counter_reading(gang, INCOME) == 15

    def test_a_gang_already_holding_territories_reads_the_seed_at_once(self, gang):
        assign_asset(add_asset(gang.test_campaign, territory("Bullet Den")), gang)
        assign_asset(add_asset(gang.test_campaign, territory("Gambling Den")), gang)
        before = counter_reading(gang, REPUTATION)

        seed_all()

        assert counter_reading(gang, INCOME) == 30
        assert counter_reading(gang, REPUTATION) == before + 1
        assert "Recruit (Bullet Den)" in gang_rules(gang)


class TestTheMaintenanceOperation:
    """The seed runs from the maintenance console: GET previews without
    writing, POST records a run and enqueues it, the task writes its
    outcome onto the record, and a redelivered message changes nothing."""

    @pytest.fixture
    def address(self):
        return reverse(
            f"admin:maintenance_{Operation.SEED_CORE_TERRITORY_CONTENT.value}"
        )

    def test_the_preview_lists_the_rows_and_writes_nothing(
        self, client, superuser, core, address
    ):
        client.force_login(superuser)

        page = client.get(address).content.decode()

        assert "Bullet Den: income 15" in page
        assert "Write the missing income and boons" in page
        assert not Backfill.objects.exists()
        assert income_of(territory("Bullet Den")) == 0

    def test_posting_records_a_run_and_the_task_writes_its_outcome(
        self, client, superuser, core, address
    ):
        client.force_login(superuser)

        response = client.post(address)

        assert response.status_code == 302
        record = Backfill.objects.get(operation=Operation.SEED_CORE_TERRITORY_CONTENT)
        assert str(record.pk) in response["Location"]
        assert record.status == Backfill.Status.DONE
        assert record.triggered_by == superuser
        assert "Bullet Den: income 15" in record.summary["report"]
        assert income_of(territory("Bullet Den")) == 15

        detail = client.get(
            reverse("admin:maintenance_backfill_detail", args=[record.pk])
        ).content.decode()
        assert "What it did" in detail

    def test_a_run_with_nothing_to_do_records_nothing(
        self, client, superuser, seeded, address
    ):
        client.force_login(superuser)

        response = client.post(address, follow=True)

        assert NOTHING_TO_DO in response.content.decode()
        assert not Backfill.objects.exists()
        assert "Nothing to write" in client.get(address).content.decode()

    def test_a_redelivered_message_writes_nothing_more(self, core, task_queue):
        record = Backfill.objects.create(
            operation=Operation.SEED_CORE_TERRITORY_CONTENT,
            status=Backfill.Status.RUNNING,
            summary={"attempts": 0},
        )

        with task_queue.capture():
            seed_core_territory_content.enqueue(backfill_id=str(record.pk))
        task_queue.deliver_all()
        task_queue.redeliver_last()

        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE
        assert record.summary["attempts"] == 1
        assert Rule.objects.filter(name="Recruit").count() == 5
        assert income_of(territory("Bullet Den")) == 15

    def test_only_a_superuser_reaches_it(self, client, address):
        client.force_login(User.objects.create_user("author", is_staff=True))
        assert client.get(address).status_code in (302, 403)
