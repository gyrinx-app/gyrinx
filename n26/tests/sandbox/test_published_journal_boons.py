"""Published journal placeholders have a separate, bounded maintenance repair.

The repair removes the eleven empty Controlled rules and their exact grants.
Publication is the only difference from the seeded placeholders. Authored
behaviour and references remain protected; no territory, Income contribution,
House table, holding or ledger record is changed.
"""

from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from gyrinx.maintenance.models import Backfill
from gyrinx.site.models import WritePause
from gyrinx.tasks.worker import Outcome as TaskOutcome
from n26.core.campaigns import campaign_operation, tables_held_by
from n26.core.history import build, campaign_history
from n26.core.models import CampaignAsset, LedgerEntry, LedgerEvent
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_gang
from n26.library import authoring
from n26.library.authoring import (
    add_built_in,
    attach_modifiers_to,
    create_asset,
    create_category,
    create_gang_type,
    create_rule,
    detach_modifier,
    ef_adds,
    ef_contributes_to_counter,
    has_gang_pickable,
    modifier,
    put_live,
    recompose_modifier,
    revise,
    targets_gang_alone,
)
from n26.library.core_campaign import CAMPAIGN_TYPE
from n26.library.gang_supertypes import HOUSES, supertype_pick
from n26.library.income import ensure_income_counter, income_of
from n26.library.journal_content import (
    JOURNALS,
    seed_all,
)
from n26.library.journal_content import (
    NOTHING_TO_DO as JOURNAL_UP_TO_DATE,
)
from n26.library.models import Asset, AssetTable, CampaignType, Counter, Modifier, Rule
from n26.library.published_journal_boons import (
    NOTHING_TO_DO,
    preview,
    remove_published_journal_boons,
)
from n26.maintenance import (
    Operation,
    task_routes,
)
from n26.maintenance import (
    remove_published_journal_boons as cleanup_task,
)
from n26.tests.fixtures import library_setup
from n26.tests.sandbox.actions import (
    add_asset,
    assign,
    assign_asset,
    found_campaign,
    found_gang,
    join_campaign,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
@library_setup
def houses(default_pack):
    return {house: create_gang_type(house) for house in HOUSES}


@pytest.fixture
def catalogue(houses, default_pack):
    seed_all()
    for gang_type in houses.values():
        gang_type.refresh_from_db()
    return CampaignType.objects.get(pack=default_pack, name=CAMPAIGN_TYPE)


@pytest.fixture
@library_setup
def published_boons(catalogue, default_pack):
    """The journal grants after an author publishes all eleven placeholder rules."""
    made = {}
    for house, _table, territories in JOURNALS:
        for entry in territories:
            asset = Asset.objects.get(pack=default_pack, name=entry.name)
            if entry.name == "Amneo-vats":
                rule = None
                effect = ef_contributes_to_counter(ensure_income_counter(), 10)
            else:
                rule = create_rule(
                    f"{house} Controlled",
                    annotation=entry.name,
                    pack=default_pack,
                    staged=True,
                )
                put_live(rule)
                effect = ef_adds(rule)
            boon = modifier(
                f"{entry.name}: {house} Controlled",
                targets_gang_alone(has_gang_pickable(supertype_pick(house))),
                effect,
                attach_to=asset,
                pack=default_pack,
            )
            made[entry.name] = (boon, rule)
    return made


def placeholder_ids(boons):
    return [rule.pk for _boon, rule in boons.values() if rule is not None]


def grant_ids(boons):
    return [boon.pk for boon, rule in boons.values() if rule is not None]


def parts(boons):
    return [
        (type(boon.scope), boon.scope.pk, type(boon.effect), boon.effect.pk)
        for boon, rule in boons.values()
        if rule is not None
    ]


def interrupt_after_one(monkeypatch):
    delete = authoring.delete_modifier

    def interrupt(boon):
        delete(boon)
        raise RuntimeError("Interrupted published boon cleanup")

    monkeypatch.setattr(authoring, "delete_modifier", interrupt)


class TestPublishedPlaceholders:
    """The preview and apply reports agree on exactly eleven published grants and rules."""

    def test_the_preview_rolls_back_every_removal_and_a_repeated_run_changes_nothing(
        self, published_boons
    ):
        rule_ids = placeholder_ids(published_boons)
        boon_ids = grant_ids(published_boons)
        component_ids = parts(published_boons)
        before = {
            model: list(model.objects.order_by("pk").values())
            for model in (Asset, Rule, Modifier)
        }
        assert len(rule_ids) == 11
        assert not Rule.objects.filter(pk__in=rule_ids, staged=True).exists()

        report = preview()

        assert (
            len([line for line in report if line.startswith("removed modifier")]) == 11
        )
        assert len([line for line in report if line.startswith("removed rule")]) == 11
        assert not [
            line
            for line in report
            if "Amneo-vats" in line or line.startswith("skipped")
        ]
        assert before == {
            model: list(model.objects.order_by("pk").values()) for model in before
        }
        assert all(
            scope.objects.filter(pk=scope_pk).exists()
            and effect.objects.filter(pk=effect_pk).exists()
            for scope, scope_pk, effect, effect_pk in component_ids
        )

        assert remove_published_journal_boons() == report
        assert not Rule.objects.filter(pk__in=rule_ids).exists()
        assert not Modifier.objects.filter(pk__in=boon_ids).exists()
        assert all(
            not scope.objects.filter(pk=scope_pk).exists()
            and not effect.objects.filter(pk=effect_pk).exists()
            for scope, scope_pk, effect, effect_pk in component_ids
        )
        vats, _rule = published_boons["Amneo-vats"]
        assert Modifier.objects.filter(pk=vats.pk).exists()
        assert remove_published_journal_boons() == [NOTHING_TO_DO]
        assert preview() == [NOTHING_TO_DO]

    def test_the_repair_creates_no_missing_catalogue_content(self, default_pack):
        before = {
            model: model.objects.count()
            for model in (Asset, AssetTable, CampaignType, Counter, Rule, Modifier)
        }
        assert preview() == [NOTHING_TO_DO]
        assert remove_published_journal_boons() == [NOTHING_TO_DO]
        assert before == {model: model.objects.count() for model in before}

    def test_an_unused_published_rule_can_be_removed_after_its_modifier_was_removed(
        self, published_boons
    ):
        boon, rule = published_boons["Slug House"]
        authoring.delete_modifier(boon)
        report = preview()
        assert f"removed rule {rule}" in report
        assert f"removed modifier {boon.name}" not in report
        assert Rule.objects.filter(pk=rule.pk).exists()
        assert remove_published_journal_boons() == report
        assert not Rule.objects.filter(pk=rule.pk).exists()
        assert remove_published_journal_boons() == [NOTHING_TO_DO]

    def test_an_unused_published_rule_can_be_removed_without_a_territory_catalogue(
        self, default_pack
    ):
        rule = create_rule(
            "Goliath Controlled",
            annotation="Slug House",
            pack=default_pack,
            staged=True,
        )
        put_live(rule)
        before = {
            model: list(model.objects.order_by("pk").values())
            for model in (Asset, AssetTable, CampaignType, Counter, Modifier)
        }
        assert not CampaignType.objects.filter(
            pack=default_pack, name=CAMPAIGN_TYPE
        ).exists()

        report = preview()

        assert report == [f"removed rule {rule}"]
        assert Rule.objects.filter(pk=rule.pk).exists()
        assert remove_published_journal_boons() == report
        assert not Rule.objects.filter(pk=rule.pk).exists()
        assert before == {
            model: list(model.objects.order_by("pk").values()) for model in before
        }
        assert remove_published_journal_boons() == [NOTHING_TO_DO]

    def test_the_original_journal_update_precedes_the_separate_published_cleanup(
        self, published_boons
    ):
        vats, _rule = published_boons["Amneo-vats"]
        original_report = seed_all()
        assert "removed modifier Amneo-vats: Goliath Controlled" in original_report
        assert any(
            line.startswith("skipped rule Goliath Controlled (Slug House)")
            for line in original_report
        )
        assert not Modifier.objects.filter(pk=vats.pk).exists()
        assert Modifier.objects.filter(pk__in=grant_ids(published_boons)).count() == 11
        assert (
            Rule.objects.filter(pk__in=placeholder_ids(published_boons)).count() == 11
        )

        report = preview()
        assert (
            len([line for line in report if line.startswith("removed modifier")]) == 11
        )
        assert len([line for line in report if line.startswith("removed rule")]) == 11
        assert remove_published_journal_boons() == report
        assert remove_published_journal_boons() == [NOTHING_TO_DO]
        assert seed_all()[0] == JOURNAL_UP_TO_DATE

    @pytest.mark.parametrize(
        "change",
        [
            "staged",
            "archived",
            "archive_timestamp",
            "help",
            "price",
            "trade_points",
            "exclusive",
            "position",
            "category",
            "built_ins",
            "payload",
        ],
    )
    def test_changed_rules_and_staged_rules_keep_their_grants(
        self, published_boons, change
    ):
        boon, rule = published_boons["Slug House"]
        updates = {
            "staged": {"staged": True},
            "archived": {"archived": True},
            "archive_timestamp": {"archived_at": timezone.now()},
            "help": {"library_author_help": "Authored recruitment setup."},
            "price": {"price": 1},
            "trade_points": {"trade_point_price": 0},
            "exclusive": {"is_exclusive": True},
            "position": {"position": 1},
        }
        if change == "category":
            revise(rule, category=create_category("Rules", "Territory rules"))
        elif change == "built_ins":
            add_built_in(rule, create_rule("Authored workshop rule"))
        elif change == "payload":
            modifier(
                "Authored reputation",
                targets_gang_alone(),
                ef_contributes_to_counter(ensure_income_counter(), 3),
                attach_to=rule,
            )
        else:
            revise(rule, **updates[change])
        report = preview()
        assert any(
            line.startswith(f"skipped rule {rule} and its modifier:") for line in report
        )
        assert remove_published_journal_boons() == report
        assert Rule.objects.filter(pk=rule.pk).exists()
        assert Modifier.objects.filter(pk=boon.pk).exists()
        assert (
            not Rule.objects.filter(pk__in=placeholder_ids(published_boons))
            .exclude(pk=rule.pk)
            .exists()
        )
        assert remove_published_journal_boons()[0] == NOTHING_TO_DO

    @pytest.mark.parametrize(
        "change",
        [
            "staged",
            "archived",
            "echoes",
            "wrong_house",
            "wrong_rule",
            "shared",
            "wrong_carrier",
            "wrong_catalogue",
        ],
    )
    def test_changed_or_shared_modifiers_keep_their_rules(
        self, published_boons, change
    ):
        boon, rule = published_boons["Slug House"]
        slug = Asset.objects.get(name="Slug House")
        if change in ("staged", "archived"):
            revise(boon, **{change: True})
        elif change == "echoes":
            revise(boon.targets_gang, echoes=True)
        elif change == "wrong_house":
            recompose_modifier(
                boon,
                boon.name,
                targets_gang_alone(has_gang_pickable(supertype_pick("Escher"))),
                ef_adds(rule),
            )
        elif change == "wrong_rule":
            revise(boon.adds_assignable, rule=create_rule("Authored rule"))
        elif change == "wrong_catalogue":
            revise(slug.asset_type, label_singular="Relic")
        else:
            other = create_asset("Authored territory", slug.asset_type)
            attach_modifiers_to(other, [boon])
            if change == "wrong_carrier":
                detach_modifier(slug, boon)
        report = preview()
        assert any(line.startswith(f"skipped modifier {boon.name}:") for line in report)
        assert remove_published_journal_boons() == report
        assert Modifier.objects.filter(pk=boon.pk).exists()
        assert Rule.objects.filter(pk=rule.pk).exists()

    def test_other_packs_and_same_named_authored_variants_are_untouched(
        self, published_boons, other_pack
    ):
        slug = Asset.objects.get(name="Slug House")
        other_asset = create_asset("Slug House", slug.asset_type, pack=other_pack)
        other_rule = create_rule(
            "Goliath Controlled", annotation="Slug House", pack=other_pack
        )
        other_boon = modifier(
            "Slug House: Goliath Controlled",
            targets_gang_alone(has_gang_pickable(supertype_pick("Goliath"))),
            ef_adds(other_rule),
            attach_to=other_asset,
            pack=other_pack,
        )
        variant = create_rule(
            "Goliath Controlled", annotation="Slug House", qualifier="Authored"
        )
        authored = modifier(
            "Slug House: authored rule",
            targets_gang_alone(),
            ef_adds(variant),
            attach_to=slug,
        )
        remove_published_journal_boons()
        assert Rule.objects.filter(pk__in=[other_rule.pk, variant.pk]).count() == 2
        assert Modifier.objects.filter(pk__in=[other_boon.pk, authored.pk]).count() == 2
        assert not Rule.objects.filter(pk__in=placeholder_ids(published_boons)).exists()

    def test_a_referenced_rule_is_kept_after_its_exact_generated_grant_is_removed(
        self, published_boons
    ):
        boon, rule = published_boons["Slug House"]
        other_asset = Asset.objects.get(name="Fight Arena")
        reused = modifier(
            "Authored rule grant",
            targets_gang_alone(),
            ef_adds(rule),
            attach_to=other_asset,
        )
        report = remove_published_journal_boons()
        assert f"removed modifier {boon.name}" in report
        assert (
            f"skipped rule {rule}: it is still referenced by content or player history"
            in report
        )
        assert Rule.objects.filter(pk=rule.pk).exists()
        assert Modifier.objects.filter(pk=reused.pk).exists()
        assert remove_published_journal_boons()[0] == NOTHING_TO_DO

    def test_a_directly_assigned_rule_and_its_history_are_preserved(
        self, published_boons, houses, owner
    ):
        boon, rule = published_boons["Slug House"]
        gang = found_gang("Irontooth", houses["Goliath"], owner=owner)
        assignment = assign(rule, gang=gang)
        before = build(gang)
        entries = list(
            LedgerEntry.objects.filter(assignment__gang_root=gang)
            .order_by("pk")
            .values()
        )
        events = list(LedgerEvent.objects.filter(gang=gang).order_by("pk").values())
        report = remove_published_journal_boons()
        assert f"removed modifier {boon.name}" in report
        assert (
            f"skipped rule {rule}: it is still referenced by content or player history"
            in report
        )
        assignment.refresh_from_db()
        assert assignment.rule_id == rule.pk and not assignment.archived
        assert Rule.objects.filter(pk=rule.pk).exists()
        assert build(gang) == before
        assert (
            list(
                LedgerEntry.objects.filter(assignment__gang_root=gang)
                .order_by("pk")
                .values()
            )
            == entries
        )
        assert (
            list(LedgerEvent.objects.filter(gang=gang).order_by("pk").values())
            == events
        )
        assert_reconciled(gang)

    def test_holdings_ledger_catalogue_income_and_house_tables_are_unchanged(
        self, published_boons, catalogue, houses, owner
    ):
        gang = found_gang("Irontooth", houses["Goliath"], owner=owner)
        arbitrator = User.objects.create_user("arbitrator")
        campaign = found_campaign("Dust Falls", catalogue, owner=arbitrator)
        join_campaign(gang, campaign)
        vats = Asset.objects.get(name="Amneo-vats")
        assign_asset(add_asset(campaign, vats), gang)
        slug = Asset.objects.get(name="Slug House")
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.add_assets([slug], income=7, request_key=uuid4())
        overridden = campaign.campaign_assets.get(asset=slug)
        assign_asset(overridden, gang)
        table = AssetTable.objects.get(name=JOURNALS[0][1])
        assets = list(Asset.objects.filter(asset_type=vats.asset_type))
        baseline = {asset.pk: income_of(asset) for asset in assets}
        holdings = list(
            CampaignAsset.objects.filter(campaign=campaign).order_by("pk").values()
        )
        entries = list(
            LedgerEntry.objects.filter(assignment__gang_root=gang)
            .order_by("pk")
            .values()
        )
        events = list(LedgerEvent.objects.filter(gang=gang).order_by("pk").values())
        campaign_events = campaign_history(campaign)
        before = next(
            line.value
            for line in render_gang(gang).campaign.counters
            if line.name == "Income"
        )
        report = preview()
        assert (
            Rule.objects.filter(pk__in=placeholder_ids(published_boons)).count() == 11
        )
        assert remove_published_journal_boons() == report
        assert {asset.pk: income_of(asset) for asset in assets} == baseline
        assert (
            next(
                line.value
                for line in render_gang(gang).campaign.counters
                if line.name == "Income"
            )
            == before
            == 42
        )
        assert (
            list(
                CampaignAsset.objects.filter(campaign=campaign).order_by("pk").values()
            )
            == holdings
        )
        assert (
            list(
                LedgerEntry.objects.filter(assignment__gang_root=gang)
                .order_by("pk")
                .values()
            )
            == entries
        )
        assert (
            list(LedgerEvent.objects.filter(gang=gang).order_by("pk").values())
            == events
        )
        assert campaign_history(campaign) == campaign_events
        assert Modifier.objects.filter(pk=overridden.income_override_id).exists()
        assert table in tables_held_by(gang, campaign, include_staged=True)
        assert Modifier.objects.filter(pk=published_boons["Amneo-vats"][0].pk).exists()
        assert_reconciled(gang)

    def test_an_interrupted_cleanup_rolls_back_all_removals(
        self, published_boons, monkeypatch
    ):
        interrupt_after_one(monkeypatch)
        with pytest.raises(RuntimeError, match="Interrupted published boon cleanup"):
            remove_published_journal_boons()
        assert (
            Rule.objects.filter(pk__in=placeholder_ids(published_boons)).count() == 11
        )
        assert Modifier.objects.filter(pk__in=grant_ids(published_boons)).count() == 11


class TestTheSeparateMaintenanceOperation:
    """The new console operation previews, records and delivers this repair independently."""

    @pytest.fixture
    def address(self):
        return reverse(
            f"admin:maintenance_{Operation.REMOVE_PUBLISHED_JOURNAL_BOONS.value}"
        )

    @pytest.fixture
    def superuser(self):
        return User.objects.create_superuser("boss", "boss@example.com", "password")

    def test_the_console_preview_writes_nothing(
        self, client, superuser, published_boons, address
    ):
        client.force_login(superuser)
        response = client.get(address)
        assert response.status_code == 200
        assert (
            "removed modifier Slug House: Goliath Controlled"
            in response.content.decode()
        )
        assert not Backfill.objects.exists()
        assert (
            Rule.objects.filter(pk__in=placeholder_ids(published_boons)).count() == 11
        )
        assert Modifier.objects.filter(pk__in=grant_ids(published_boons)).count() == 11

    def test_a_paused_console_preview_refuses_before_removing_content(
        self, client, superuser, published_boons, address
    ):
        client.force_login(superuser)
        WritePause.objects.filter(scope="n26").update(
            state=WritePause.State.PAUSED, reason="Library maintenance is in progress."
        )
        response = client.get(address)
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "30"
        assert "Library maintenance is in progress." in response.content.decode()
        assert not Backfill.objects.exists()
        assert (
            Rule.objects.filter(pk__in=placeholder_ids(published_boons)).count() == 11
        )
        assert Modifier.objects.filter(pk__in=grant_ids(published_boons)).count() == 11

    def test_post_records_the_preview_and_delivery_records_the_same_report_once(
        self, client, superuser, published_boons, address, task_queue
    ):
        client.force_login(superuser)
        expected = preview()
        with task_queue.capture():
            response = client.post(address)
        record = Backfill.objects.get(
            operation=Operation.REMOVE_PUBLISHED_JOURNAL_BOONS
        )
        assert response.status_code == 302
        assert str(record.pk) in response["Location"]
        assert record.triggered_by == superuser
        assert record.status == Backfill.Status.RUNNING
        assert record.summary["preview"] == expected
        assert record.summary["attempts"] == 0
        assert (
            Rule.objects.filter(pk__in=placeholder_ids(published_boons)).count() == 11
        )
        task_queue.deliver_all()
        task_queue.redeliver_last()
        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE
        assert record.summary["attempts"] == 1
        assert record.summary["report"] == expected
        assert not Rule.objects.filter(pk__in=placeholder_ids(published_boons)).exists()
        assert not Modifier.objects.filter(pk__in=grant_ids(published_boons)).exists()
        detail = client.get(
            reverse("admin:maintenance_backfill_detail", args=[record.pk])
        ).content.decode()
        assert "removed modifier Slug House: Goliath Controlled" in detail
        assert not Backfill.objects.filter(
            operation=Operation.SEED_JOURNAL_CONTENT
        ).exists()

    def test_post_with_nothing_to_remove_records_no_run(
        self, client, superuser, published_boons, address
    ):
        remove_published_journal_boons()
        client.force_login(superuser)
        response = client.post(address, follow=True)
        assert response.status_code == 200
        assert NOTHING_TO_DO in response.content.decode()
        assert not Backfill.objects.exists()

    @pytest.mark.django_db(transaction=True)
    def test_simultaneous_submissions_share_one_committed_run(
        self, client, superuser, published_boons, address, task_queue, monkeypatch
    ):
        import importlib
        import threading

        from django.db import close_old_connections, connection
        from django.test import Client

        from gyrinx.tasks.local_backend import DatabaseBackend

        library = importlib.import_module("n26.library.published_journal_boons")
        admission = importlib.import_module("gyrinx.site.write_pause")
        original_preview = library.preview
        original_advisory = admission._advisory
        original_enqueue = DatabaseBackend.enqueue
        first_preview_started = threading.Event()
        second_admission_started = threading.Event()
        responses = []
        errors = []
        enqueued = []

        def preview_after_second_submission_starts():
            if threading.current_thread() is first:
                first_preview_started.set()
                assert second_admission_started.wait(10)
            return original_preview()

        def observed_advisory(function, scope):
            if (
                threading.current_thread() is second
                and scope == "n26"
                and function == "pg_advisory_xact_lock"
            ):
                second_admission_started.set()
            return original_advisory(function, scope)

        def enqueue_after_commit(backend, task, args, kwargs):
            if task.func is cleanup_task.func:
                assert not connection.in_atomic_block
                enqueued.append(kwargs["backfill_id"])
            return original_enqueue(backend, task, args, kwargs)

        def post():
            close_old_connections()
            try:
                request_client = Client()
                request_client.force_login(User.objects.get(pk=superuser.pk))
                responses.append(request_client.post(address))
            except Exception as exc:
                errors.append(exc)
            finally:
                close_old_connections()

        first = threading.Thread(target=post)
        second = threading.Thread(target=post)
        monkeypatch.setattr(library, "preview", preview_after_second_submission_starts)
        monkeypatch.setattr(admission, "_advisory", observed_advisory)
        monkeypatch.setattr(DatabaseBackend, "enqueue", enqueue_after_commit)
        try:
            first.start()
            assert first_preview_started.wait(10)
            second.start()
        finally:
            first.join(15)
            if second.ident is not None:
                second.join(15)

        assert not first.is_alive()
        assert not second.is_alive()
        assert errors == []
        assert len(responses) == 2
        assert all(response.status_code == 302 for response in responses)
        record = Backfill.objects.get(
            operation=Operation.REMOVE_PUBLISHED_JOURNAL_BOONS
        )
        assert enqueued == [str(record.pk)]
        assert task_queue.pending() == 1
        assert responses[0]["Location"] == responses[1]["Location"]
        assert str(record.pk) in responses[0]["Location"]

        client.force_login(superuser)
        repeated = client.post(address)
        assert repeated["Location"] == responses[0]["Location"]
        assert task_queue.pending() == 1
        assert task_queue.deliver_all() == 1
        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE

    def test_only_a_superuser_can_preview_or_enqueue_it(self, client, address):
        staff = User.objects.create_user("staff", is_staff=True)
        client.force_login(staff)
        assert client.get(address).status_code in (302, 403)
        assert client.post(address).status_code in (302, 403)
        assert not Backfill.objects.exists()

    def test_a_failed_delivery_records_the_failure_and_rolls_back_the_cleanup(
        self, published_boons, monkeypatch, task_queue
    ):
        record = Backfill.objects.create(
            operation=Operation.REMOVE_PUBLISHED_JOURNAL_BOONS,
            status=Backfill.Status.RUNNING,
            summary={"attempts": 0},
        )
        interrupt_after_one(monkeypatch)
        with task_queue.capture():
            cleanup_task.enqueue(backfill_id=str(record.pk))
        task_queue.deliver_all()
        record.refresh_from_db()
        assert record.status == Backfill.Status.FAILED
        assert record.summary["attempts"] == 1
        assert "Interrupted published boon cleanup" in record.error
        assert (
            Rule.objects.filter(pk__in=placeholder_ids(published_boons)).count() == 11
        )
        assert Modifier.objects.filter(pk__in=grant_ids(published_boons)).count() == 11

    def test_a_paused_exclusive_delivery_preserves_content_and_its_attempt_count(
        self, published_boons, task_queue
    ):
        route = next(route for route in task_routes if route.func == cleanup_task)
        assert route.exclusive_write and route.write_scope == "n26"
        record = Backfill.objects.create(
            operation=Operation.REMOVE_PUBLISHED_JOURNAL_BOONS,
            status=Backfill.Status.RUNNING,
            summary={"attempts": 0},
        )
        with task_queue.capture():
            cleanup_task.enqueue(backfill_id=str(record.pk))
        WritePause.objects.filter(scope="n26").update(state=WritePause.State.PAUSED)
        assert task_queue.deliver_next() == TaskOutcome.DEFERRED
        record.refresh_from_db()
        assert record.summary["attempts"] == 0
        assert (
            Rule.objects.filter(pk__in=placeholder_ids(published_boons)).count() == 11
        )
        assert Modifier.objects.filter(pk__in=grant_ids(published_boons)).count() == 11
        WritePause.objects.filter(scope="n26").update(state=WritePause.State.OPEN)
        task_queue.deliver_all()
        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE
        assert record.summary["attempts"] == 1
