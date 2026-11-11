"""React display and retry contracts for post-battle commands."""

import json
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import PostBattleReport
from n26.tests.test_views_post_battle import (
    _prepared_report_catalogue as _prepared_report_catalogue,
)
from n26.tests.test_views_post_battle import (
    editor_url,
    html_fields,
    start_url,
)
from n26.tests.test_views_post_battle import (
    gang_type as gang_type,
)
from n26.tests.test_views_post_battle import (
    person_statline_type as person_statline_type,
)
from n26.tests.test_views_post_battle import (
    person_type as person_type,
)
from n26.tests.test_views_post_battle import (
    table as table,
)

pytestmark = pytest.mark.django_db


def react_props(response):
    document = BeautifulSoup(response.content, "html.parser")
    host = document.select_one('[data-react-name="post-battle"]')
    assert host is not None
    return json.loads(document.find(id=host["data-react-props"]).string)


def command_page(client, table):
    client.post(start_url(table), {"request_key": uuid4()})
    report = PostBattleReport.objects.get(gang=table.gang)
    response = client.get(editor_url(report))
    data = html_fields(response)
    data["command_key"] = str(uuid4())
    data["intent"] = "autosave"
    return report, data


def command_url(report):
    return reverse("n26-post-battle-command", args=[report.pk])


class TestReactDraftCommands:
    def test_one_root_owns_the_editor_without_partial_update_bridges(
        self, client, table
    ):
        report, _ = command_page(client, table)
        response = client.get(editor_url(report))
        props = react_props(response)
        document = BeautifulSoup(response.content, "html.parser")
        assert len(document.select('[data-react-name="post-battle"]')) == 1
        assert not document.select(
            '[data-react-name="post-battle-preview"], [data-react-name="post-battle-toolbar"]'
        )
        assert "post-battle.js" not in response.content.decode()
        assert props["commandHref"] == command_url(report)
        assert len(props["models"]) == 2
        assert "no-store" in response["Cache-Control"]

    def test_a_lost_autosave_response_replays_without_another_revision(
        self, client, table
    ):
        from n26.core.models.post_battle import PostBattleCommandReceipt

        report, data = command_page(client, table)
        first = client.post(command_url(report), data).json()
        second = client.post(command_url(report), data).json()
        report.refresh_from_db()
        assert first["acknowledged"] == second["acknowledged"]
        assert report.draft_revision == 1
        assert PostBattleCommandReceipt.objects.filter(report=report).count() == 1
        assert not second["newer"]

    def test_acknowledgement_is_separate_from_a_later_saved_draft(self, client, table):
        report, data = command_page(client, table)
        first = client.post(command_url(report), data).json()
        later = dict(data)
        later["command_key"] = str(uuid4())
        later["revision"] = first["display"]["revision"]
        later["intent"] = "check"
        client.post(command_url(report), later)
        replay = client.post(command_url(report), data)
        assert replay.status_code == 200
        result = replay.json()
        assert result["acknowledged"]["revision"] == 1
        assert result["currentDisplay"]["revision"] == 2
        assert result["newer"]

    def test_a_key_cannot_be_reused_for_different_business_input(self, client, table):
        report, data = command_page(client, table)
        client.post(command_url(report), data)
        changed = dict(data)
        changed[f"model-{table.models[0].pk}-xp"] = "7"
        response = client.post(command_url(report), changed)
        assert response.status_code == 409
        assert response.json()["acknowledged"] is None
        report.refresh_from_db()
        assert report.draft_revision == 1

    def test_cached_native_requests_derive_stable_distinct_command_identities(
        self, client, table
    ):
        from n26.core.models.post_battle import PostBattleCommandReceipt

        report, data = command_page(client, table)
        data.pop("command_key")
        first = client.post(editor_url(report), data)
        assert first.status_code == 200
        second = client.post(editor_url(report), data)
        assert second.status_code == 200
        assert first.json()["revision"] == second.json()["revision"] == 1
        changed = dict(data, intent="check")
        refused = client.post(command_url(report), changed)
        assert refused.status_code == 409
        assert PostBattleCommandReceipt.objects.filter(report=report).count() == 1

    def test_stale_tabs_keep_their_entries_and_require_explicit_review(
        self, client, table
    ):
        report, data = command_page(client, table)
        client.post(command_url(report), data)
        stale = dict(data, command_key=str(uuid4()))
        stale[f"model-{table.models[0].pk}-xp"] = "9"
        response = client.post(command_url(report), stale)
        assert response.status_code == 409
        assert response.json()["conflict"]
        assert response.json()["display"]["payload"]["models"][0]["xp"] == "9"
        assert response.json()["currentDisplay"]["revision"] == 1

    def test_the_participation_check_survives_save_and_reload(self, client, table):
        report, data = command_page(client, table)
        response = client.post(
            command_url(report), dict(data, participation_confirmed="on")
        )
        assert response.status_code == 200
        assert response.json()["display"]["participationConfirmed"]
        assert react_props(client.get(editor_url(report)))["participationConfirmed"]

    def test_the_command_requires_current_access_before_replaying(self, client, table):
        report, data = command_page(client, table)
        client.post(command_url(report), data)
        outsider = User.objects.create_user("unrelated-report-reader")
        client.force_login(outsider)
        response = client.post(command_url(report), data)
        assert response.status_code == 404

    def test_expired_sessions_return_json_without_redirecting_the_write(
        self, client, table
    ):
        report, data = command_page(client, table)
        client.logout()
        response = client.post(command_url(report), data)
        assert response.status_code == 401
        assert response.headers["Content-Type"].startswith("application/json")

    def test_changing_the_intent_with_the_same_key_cannot_apply_a_saved_draft(
        self, client, table
    ):
        report, data = command_page(client, table)
        client.post(command_url(report), data)
        response = client.post(command_url(report), dict(data, intent="apply"))
        assert response.status_code == 409
        report.refresh_from_db()
        assert report.state == PostBattleReport.State.DRAFT
        assert not report.revisions.exists()


class TestReactApplicationRecovery:
    def test_apply_replay_returns_its_receipt_without_reapplying_credits(
        self, client, table
    ):
        from n26.core.reconcile import assert_reconciled

        report, data = command_page(client, table)
        data["participation_confirmed"] = "on"
        line = data["credit_line"][0]
        data[f"credit-{line}-amount"] = "35"
        data[f"credit-{line}-reason"] = "Scenario reward"
        client.post(command_url(report), data)
        apply_data = html_fields(client.get(editor_url(report)))
        apply_data.update(intent="apply", command_key=str(uuid4()))
        first = client.post(command_url(report), apply_data)
        assert first.status_code == 200, first.content
        assert first.json()["nextUrl"]
        table.gang.refresh_from_db()
        balance = table.gang.credits
        replay = client.post(command_url(report), apply_data)
        assert replay.status_code == 200
        assert replay.json()["nextUrl"] == first.json()["nextUrl"]
        table.gang.refresh_from_db()
        assert table.gang.credits == balance
        assert report.revisions.count() == 1
        assert_reconciled(table.gang)

    def test_receipts_from_before_the_migration_still_settle_a_lost_apply(
        self, client, table
    ):
        from django.http import QueryDict

        from n26.core.post_battle import apply_report, preview_report, save_draft
        from n26.core.post_battle_forms import posted_payload

        report, data = command_page(client, table)
        data["participation_confirmed"] = "on"
        posted = QueryDict(mutable=True)
        for name, values in data.items():
            posted.setlist(name, values if isinstance(values, list) else [str(values)])
        payload = posted_payload(posted)
        report = save_draft(
            report,
            actor=table.owner,
            generation=report.generation,
            revision=report.draft_revision,
            payload=payload,
        )
        plan = preview_report(report, actor=table.owner)
        data.update(intent="apply", revision=report.draft_revision, review=plan.review)
        previous = apply_report(
            report,
            actor=table.owner,
            generation=report.generation,
            revision=report.draft_revision,
            submission_key=data["submission_key"][0],
            review=plan.review,
        )
        replay = client.post(command_url(report), data)
        assert replay.status_code == 200, replay.content
        assert replay.json()["nextUrl"] == reverse(
            "n26-post-battle-revision", args=[report.pk, previous.sequence]
        )
        assert report.revisions.count() == 1

    def test_an_old_save_cannot_modify_a_new_correction_generation(self, client, table):
        from n26.core.post_battle import start_correction

        report, data = command_page(client, table)
        data["participation_confirmed"] = "on"
        saved = client.post(command_url(report), data).json()
        apply_data = html_fields(client.get(editor_url(report)))
        apply_data.update(intent="apply", command_key=str(uuid4()))
        assert client.post(command_url(report), apply_data).status_code == 200
        report.refresh_from_db()
        correction = start_correction(report, actor=table.owner)
        generation = correction.generation
        replay = client.post(command_url(report), data)
        assert replay.status_code == 200
        assert (
            replay.json()["acknowledged"]["generation"]
            == saved["acknowledged"]["generation"]
        )
        assert replay.json()["newer"]
        report.refresh_from_db()
        assert report.generation == generation
        assert report.draft_revision == 0

    def test_Apply_without_checked_participation_writes_no_results_or_receipt(
        self, client, table
    ):
        from n26.core.models.post_battle import PostBattleCommandReceipt

        report, data = command_page(client, table)
        response = client.post(command_url(report), dict(data, intent="apply"))
        assert response.status_code == 409
        assert response.json()["acknowledged"] is None
        assert not report.revisions.exists()
        assert not PostBattleCommandReceipt.objects.filter(report=report).exists()
        report.refresh_from_db()
        assert report.draft_revision == 0


def test_cached_native_add_result_replays_its_original_generated_identity(
    client, table
):
    report, data = command_page(client, table)
    data.pop("command_key")
    data["intent"] = f"add-effect:{table.models[0].pk}"
    first = client.post(editor_url(report), data)
    assert first.status_code == 200
    original = react_props(first)["models"][0]["effects"]
    assert len(original) == 1
    replay = client.post(editor_url(report), data)
    assert replay.status_code == 200
    assert react_props(replay)["models"][0]["effects"] == original
    report.refresh_from_db()
    assert report.draft_revision == 1


def test_real_csrf_rejection_writes_no_command_receipt(client, table):
    from django.test import Client

    from n26.core.models.post_battle import PostBattleCommandReceipt

    report, data = command_page(client, table)
    guarded = Client(enforce_csrf_checks=True)
    guarded.force_login(table.owner)
    response = guarded.post(
        command_url(report), data, headers={"Accept": "application/json"}
    )
    assert response.status_code == 403
    report.refresh_from_db()
    assert report.draft_revision == 0
    assert not PostBattleCommandReceipt.objects.filter(report=report).exists()


def test_json_autosave_query_growth_is_bounded_with_more_models(client, table):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from n26.tests.sandbox.actions import hire

    report, _ = command_page(client, table)

    def count():
        data = html_fields(client.get(editor_url(report)))
        data.update(intent="autosave", command_key=str(uuid4()))
        with CaptureQueriesContext(connection) as queries:
            response = client.post(command_url(report), data)
        assert response.status_code == 200
        return len(queries), response.json()

    count()
    small, _ = count()
    for name in ("Ash", "Flare", "Coal"):
        hire(table.gang, table.models[0].membership.profile, name)
    large, display = count()
    assert len(display["display"]["models"]) == 5
    assert large <= small


@pytest.mark.parametrize("adapter", ["native", "json"])
def test_access_lost_under_the_command_lock_returns_no_editor_display(
    client, table, monkeypatch, adapter
):
    import n26.core.post_battle as domain
    from n26.core.models.post_battle import PostBattleCommandReceipt

    report, data = command_page(client, table)
    checks = []

    def current_access(report, actor):
        checks.append(actor.pk)
        return len(checks) == 1

    monkeypatch.setattr(domain, "can_edit_report", current_access)
    url = command_url(report) if adapter == "json" else editor_url(report)
    response = client.post(url, data)
    assert response.status_code == 404
    assert len(checks) >= 3
    report.refresh_from_db()
    assert report.draft_revision == 0
    assert not report.revisions.exists()
    assert not PostBattleCommandReceipt.objects.filter(report=report).exists()


@pytest.mark.parametrize("adapter", ["native", "json"])
def test_both_adapters_apply_and_correct_the_same_awards_without_replaying_events(
    client, table, adapter
):
    from n26.core.models import Assignment, LedgerEvent
    from n26.core.operations import operation
    from n26.tests.test_views_post_battle import assert_books, awards, xp_value

    report, _ = command_page(client, table)
    url = command_url(report) if adapter == "json" else editor_url(report)

    def submit(data, sequence):
        if adapter == "json":
            data["command_key"] = str(uuid4())
        response = client.post(url, data)
        destination = reverse("n26-post-battle-revision", args=[report.pk, sequence])
        if adapter == "json":
            assert response.status_code == 200, response.content
            assert response.json()["nextUrl"] == destination
        else:
            assert response.status_code == 302, response.content
            assert response.url == destination
        count = LedgerEvent.objects.count()
        replay = client.post(url, data)
        assert replay.status_code == response.status_code
        assert LedgerEvent.objects.count() == count

    original = awards(client.get(editor_url(report)), table)
    submit(original, 1)
    assert xp_value(table.models[0]) == 2
    assert_books(table)
    assert table.gang.credits == 1020
    first = report.revisions.get(sequence=1)
    assert first.inputs["participation_confirmed"]
    assert first.receipt["credits_total"] == 20
    recorded = first.receipt
    xp_assignment = Assignment.objects.get(
        miniature_root=table.models[0], counter=table.xp
    )
    with operation(table.gang, actor=table.owner) as op:
        op.tally(xp_assignment, 4, note="Later battle")
        op.receive_credits(30, note="Later income")
    client.force_login(table.arbitrator)
    assert (
        client.post(reverse("n26-post-battle-correct", args=[report.pk])).status_code
        == 302
    )
    correction = html_fields(
        client.get(editor_url(report)),
        intent="apply",
        credits="10",
        **{f"model-{table.models[0].pk}-xp": "1"},
    )
    submit(correction, 2)
    assert xp_value(table.models[0]) == 5
    assert_books(table)
    assert table.gang.credits == 1040
    assert report.revisions.count() == 2
    assert report.revisions.get(sequence=1).receipt == recorded
    assert report.revisions.get(sequence=2).inputs["credit_lines"][0]["amount"] == 10


@pytest.mark.parametrize("adapter", ["native", "json"])
def test_an_empty_credit_source_keeps_its_identity_across_reloads(
    client, table, adapter
):
    report, data = command_page(client, table)
    line = data["credit_line"][0]
    data["intent"] = f"remove-credit-line:{line}"
    url = command_url(report) if adapter == "json" else editor_url(report)
    removed = client.post(url, data)
    assert removed.status_code == 200
    props = removed.json()["display"] if adapter == "json" else react_props(removed)
    (blank,) = props["mission"]["creditLines"]
    first = react_props(client.get(editor_url(report)))
    second_page = client.get(editor_url(report))
    second = react_props(second_page)
    assert first["revision"] == second["revision"]
    assert first["mission"]["creditLines"][0]["id"] == blank["id"]
    assert second["mission"]["creditLines"][0]["id"] == blank["id"]
    entered = html_fields(second_page)
    entered.update(intent="save", command_key=str(uuid4()))
    entered[f"credit-{blank['id']}-amount"] = "45"
    entered[f"credit-{blank['id']}-reason"] = "Retained after reload"
    saved = client.post(url, entered)
    assert saved.status_code == (200 if adapter == "json" else 302)
    report.refresh_from_db()
    assert report.draft["credit_lines"] == [
        {"id": blank["id"], "amount": "45", "reason": "Retained after reload"}
    ]


def test_an_apply_in_another_tab_exposes_read_only_receipt_navigation(client, table):
    report, stale = command_page(client, table)
    applying = dict(
        stale, intent="apply", command_key=str(uuid4()), participation_confirmed="on"
    )
    applied = client.post(command_url(report), applying)
    assert applied.status_code == 200
    stale.update(command_key=str(uuid4()), intent="save")
    stale[f"model-{table.models[0].pk}-note"] = "Keep this unsaved note"
    refused = client.post(command_url(report), stale)
    assert refused.status_code == 409
    result = refused.json()
    assert result["conflict"]
    assert result["currentDisplay"]["applied"]
    assert result["currentDisplay"]["receiptHref"] == reverse(
        "n26-post-battle-receipt", args=[report.pk]
    )
    assert result["display"]["models"][0]["note"] == "Keep this unsaved note"
    assert report.revisions.count() == 1
