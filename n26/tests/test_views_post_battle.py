"""The actual report form saves unfinished work and applies a gang's results once."""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import Group, User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import campaign_operation
from n26.core.crews import CrewSelection, save_crew
from n26.core.models import Assignment, CounterValue, LedgerEvent, PostBattleReport
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.core.status import Status
from n26.flags import CAMPAIGNS, FOUNDING
from n26.library.authoring import (
    add_built_in,
    add_picklist_member,
    create_counter,
    create_pickable,
    create_picklist,
    create_slot,
    create_slot_type,
    ef_adds,
    op_sets_status,
    targets_model,
)
from n26.tests.sandbox.actions import (
    found_campaign,
    found_gang,
    hire,
    join_campaign,
    op_changes_counter,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def feature():
    return FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )


@pytest.fixture
def table(
    client, default_pack, gang_type, campaign_type, make_profile, counter_tracking
):
    owner = User.objects.create_user("report-owner")
    arbitrator = User.objects.create_user("report-arbitrator")
    campaign = found_campaign("Dust Falls", campaign_type, owner=arbitrator)
    gang = found_gang("Ashen Choir", gang_type, owner=owner, budget=1000)
    join_campaign(gang, campaign)
    xp = create_counter("XP")
    kind = create_slot_type("Lasting injury", is_lasting_effect=True)
    wound = create_pickable(
        "Grievous Wound",
        kind,
        effects=[(targets_model(), op_sets_status(Status.RECOVERY))],
    )
    picklist = create_picklist("Lasting injuries", kind, members=[wound])
    slot = create_slot("Lasting injury", kind, picklist, min_picks=0, max_picks=100)
    profile = make_profile("Ganger")
    add_built_in(profile, xp)
    add_built_in(profile, slot)
    models = [hire(gang, profile, name) for name in ("Cinder", "Ember")]
    with campaign_operation(campaign, actor=arbitrator) as act:
        battle = act.record_battle(date(2026, 9, 20), [gang], scenario="Stand-off")
    client.force_login(owner)
    return SimpleNamespace(
        owner=owner,
        arbitrator=arbitrator,
        campaign=campaign,
        gang=gang,
        battle=battle,
        models=models,
        xp=xp,
        wound=wound,
        injury_kind=kind,
        injury_table=picklist,
    )


def start_url(table, *, standalone=False):
    if standalone:
        return reverse("n26-gang-post-battle", args=[table.gang.pk])
    return reverse(
        "n26-battle-report",
        args=[table.campaign.pk, table.battle.pk, table.gang.pk],
    )


def editor_url(report):
    return reverse("n26-post-battle-editor", args=[report.pk])


def receipt_url(report, sequence=None):
    return reverse(
        "n26-post-battle-revision" if sequence else "n26-post-battle-receipt",
        args=[report.pk, sequence] if sequence else [report.pk],
    )


def html_fields(response, **changes):
    """Submit the controls the browser received, including all hidden versions."""
    document = BeautifulSoup(response.content, "html.parser")
    form = document.find("form", id="post-battle-form") or document.find(
        "form", method="post"
    )
    assert form is not None
    data = {}
    for element in form.select("input[name], select[name], textarea[name]"):
        if element.has_attr("disabled"):
            continue
        name = element["name"]
        if element.name == "select":
            selected = element.select("option[selected]")
            if not selected and not element.has_attr("multiple"):
                selected = element.select("option")[:1]
            values = [option.get("value", option.get_text()) for option in selected]
        elif element.name == "textarea":
            values = [element.get_text()]
        else:
            kind = element.get("type", "text")
            if kind in {"checkbox", "radio"} and not element.has_attr("checked"):
                continue
            values = [element.get("value", "on" if kind == "checkbox" else "")]
        data.setdefault(name, []).extend(values)
    return data | changes


def start(client, table, *, standalone=False):
    url = start_url(table, standalone=standalone)
    initial = client.get(url)
    assert initial.status_code == 200
    response = client.post(
        url,
        html_fields(initial, date="2026-09-20", reference="Stand-off"),
    )
    assert response.status_code == 302
    report = PostBattleReport.objects.get(gang=table.gang)
    assert response.url == editor_url(report)
    return report


def awards(response, table, **changes):
    return (
        html_fields(
            response,
            intent="apply",
            credits="20",
            reason="Scenario reward",
            participation_confirmed="on",
            **{
                f"model-{table.models[0].pk}-participated": "on",
                f"model-{table.models[0].pk}-xp": "2",
            },
        )
        | changes
    )


def xp_value(model):
    return CounterValue.objects.get(
        assignment__miniature_root=model, assignment__counter__name="XP"
    ).value


def assert_books(table):
    table.gang.refresh_from_db()
    assert_reconciled(table.gang)


def dependent_injury(table, *, required):
    kind = create_slot_type("Injured location")
    hand = create_pickable("Hand", kind)
    choices = create_picklist("Locations", kind, members=[hand])
    slot = create_slot("Choose location", kind, choices, min_picks=int(required))
    injury = create_pickable(
        "Location injury",
        table.injury_kind,
        effects=[(targets_model(), ef_adds(slot))],
    )
    add_picklist_member(table.injury_table, injury)
    return injury, hand


def with_effect(client, table, report, injury):
    added = client.post(
        editor_url(report),
        awards(
            client.get(editor_url(report)),
            table,
            intent=f"add-effect:{table.models[0].pk}",
        ),
    )
    effect_id = added.context["models"][0].effects[0].id
    option = next(
        value
        for value, _ in added.context["models"][0].effect_options
        if value.endswith(f"|{injury.pk}")
    )
    checked = client.post(
        editor_url(report),
        html_fields(added, intent="check", **{f"effect-{effect_id}-pick": option}),
    )
    assert checked.status_code == 200
    return checked, effect_id


class TestReportLayout:
    """Participation is tabular; confirmation and submit share one form footer."""

    def test_each_model_has_one_participation_and_xp_control_in_the_table(
        self, client, table, feature
    ):
        report = start(client, table)
        document = BeautifulSoup(client.get(editor_url(report)).content, "html.parser")
        form = document.find("form", id="post-battle-form")
        participants = form.find("table")
        assert participants.caption.get_text(strip=True) == (
            "Models that took part and XP awarded"
        )
        assert len(participants.tbody.find_all("tr")) == len(table.models)
        for model in table.models:
            for field in ("participated", "xp"):
                name = f"model-{model.pk}-{field}"
                assert len(form.select(f'[name="{name}"]')) == 1
                assert participants.select_one(f'[name="{name}"]') is not None
            assert participants.select_one(f'[name="model_id"][value="{model.pk}"]')
            details = form.find("fieldset", id=f"result-{model.pk}")
            assert details.find("select", attrs={"name": f"model-{model.pk}-status"})
            assert details.find("select", attrs={"name": f"model-{model.pk}-equipment"})
        footer = form.select_one("[data-battle-actions]")
        confirmation = footer.find("input", attrs={"name": "participation_confirmed"})
        assert confirmation["aria-required"] == "true"
        assert footer.select_one('button[name="intent"][value="save"]')
        assert footer.select_one('button[name="intent"][value="apply"]')
        assert len(form.select('[name="participation_confirmed"]')) == 1
        assert "battle-actions.js" in str(document)

    def test_xp_errors_are_next_to_the_participation_table_controls(
        self, client, table, feature
    ):
        report = start(client, table)
        model = table.models[0]
        response = client.post(
            editor_url(report),
            html_fields(
                client.get(editor_url(report)),
                intent="check",
                **{f"model-{model.pk}-xp": "-1"},
            ),
        )
        document = BeautifulSoup(response.content, "html.parser")
        participants = document.find("table")
        field = participants.find("input", id=f"model-{model.pk}-xp")
        help_text = participants.find(id=field["aria-describedby"])
        error_link = help_text.find("a")
        errors = participants.select_one(error_link["href"])
        assert "Enter a whole number" in errors.get_text()
        assert "Cinder's XP" in errors.get_text()

    def test_checked_summary_includes_the_final_xp_total(self, client, table, feature):
        report = start(client, table)
        model = table.models[0]
        response = client.post(
            editor_url(report),
            html_fields(
                client.get(editor_url(report)),
                intent="check",
                **{f"model-{model.pk}-xp": "2"},
            ),
        )
        document = BeautifulSoup(response.content, "html.parser")
        assert "XP total: 0 → 2" in document.find("aside").get_text()

    def test_summary_shows_xp_removed_with_a_lasting_effect(
        self, client, table, feature
    ):
        lesson = create_pickable(
            "Lesson Learned",
            table.injury_kind,
            effects=[
                (targets_model(), op_changes_counter(table.xp, mode="add", amount=2))
            ],
        )
        add_picklist_member(table.injury_table, lesson)
        report = start(client, table)
        model = table.models[0]
        checked, effect_id = with_effect(client, table, report, lesson)
        applied = client.post(
            editor_url(report),
            html_fields(checked, intent="apply", **{f"model-{model.pk}-xp": "0"}),
        )
        assert applied.status_code == 302
        assert xp_value(model) == 2
        client.post(reverse("n26-post-battle-correct", args=[report.pk]))
        response = client.post(
            editor_url(report),
            html_fields(
                client.get(editor_url(report)), intent=f"remove-effect:{effect_id}"
            ),
        )
        document = BeautifulSoup(response.content, "html.parser")
        assert "XP total: 2 → 0" in document.find("aside").get_text()
        assert xp_value(model) == 2


class TestGangActions:
    """The roster groups actions without combining their feature permissions."""

    @pytest.mark.parametrize("campaigns_open", [False, True])
    @pytest.mark.parametrize("founding_open", [False, True])
    def test_post_battle_is_in_actions_with_its_own_feature_gate(
        self, client, table, feature, campaigns_open, founding_open
    ):
        feature.availability = (
            Availability.EVERYONE if campaigns_open else Availability.OFF
        )
        feature.save()
        FeatureFlag.objects.create(
            slug=FOUNDING,
            name="Founding",
            availability=Availability.EVERYONE if founding_open else Availability.OFF,
        )
        response = client.get(reverse("n26-gang", args=[table.gang.pk]))
        assert response.status_code == 200
        document = BeautifulSoup(response.content, "html.parser")
        panel = document.select_one('[role="region"][aria-label="Actions"]')
        assert bool(panel) == (campaigns_open or founding_open)
        links = document.select(f'a[href="{start_url(table, standalone=True)}"]')
        assert len(links) == int(campaigns_open)
        if campaigns_open:
            assert links[0] in panel.find_all("a")
            assert links[0].get_text(strip=True) == "Post-battle"
        if panel:
            founding_url = reverse("n26-gang-founding-action", args=[table.gang.pk])
            assert bool(panel.find("form", action=founding_url)) == founding_open
            assert ("Recent history" in panel.get_text()) == founding_open
            assert "Hire Fighters" not in panel.get_text()
            if not founding_open:
                assert "No action is open." not in panel.get_text()
                assert "No history for this gang yet." not in panel.get_text()

    @pytest.mark.parametrize("member", [False, True])
    def test_one_campaigns_group_controls_the_link_and_creation_page(
        self, client, table, feature, member
    ):
        group = Group.objects.create(name="Campaigns preview")
        feature.availability = Availability.ALLOWLIST
        feature.group = group
        feature.save()
        if member:
            table.owner.groups.add(group)
        url = start_url(table, standalone=True)
        document = BeautifulSoup(
            client.get(reverse("n26-gang", args=[table.gang.pk])).content,
            "html.parser",
        )
        assert bool(document.find("a", href=url)) == member
        assert client.get(url).status_code == (200 if member else 404)
        if not member:
            assert client.post(url, {}).status_code == 404
        assert not PostBattleReport.objects.exists()

    @pytest.mark.parametrize("who", ["arbitrator", "anonymous"])
    def test_other_readers_get_neither_the_panel_nor_standalone_creation(
        self, client, table, feature, who
    ):
        FeatureFlag.objects.create(
            slug=FOUNDING, name="Founding", availability=Availability.EVERYONE
        )
        if who == "arbitrator":
            client.force_login(table.arbitrator)
        else:
            client.logout()
        document = BeautifulSoup(
            client.get(reverse("n26-gang", args=[table.gang.pk])).content,
            "html.parser",
        )
        assert document.select_one('[role="region"][aria-label="Actions"]') is None
        url = start_url(table, standalone=True)
        assert document.find("a", href=url) is None
        assert client.get(url).status_code == 404
        assert client.post(url, {}).status_code == 404


class TestStartingAndResuming:
    """Reading creates nothing; starting and saving can safely be retried."""

    def test_start_page_get_does_not_write(self, client, table, feature):
        for standalone in (False, True):
            response = client.get(start_url(table, standalone=standalone))
            assert response.status_code == 200
            assert not PostBattleReport.objects.exists()

    @pytest.mark.parametrize("standalone", [False, True])
    def test_starting_twice_creates_one_report(
        self, client, table, feature, standalone
    ):
        url = start_url(table, standalone=standalone)
        data = html_fields(client.get(url), date="2026-09-20", reference="Stand-off")
        first = client.post(url, data)
        second = client.post(url, data)
        assert first.url == second.url
        report = PostBattleReport.objects.get(gang=table.gang)
        assert report.battle_id == (None if standalone else table.battle.pk)
        assert report.reference == "Stand-off"

    def test_saved_crew_only_preselects_starting_models(self, client, table, feature):
        save_crew(
            battle=table.battle,
            gang=table.gang,
            actor=table.owner,
            revision=0,
            selections=[
                CrewSelection(str(table.models[0].pk), "starting"),
                CrewSelection(str(table.models[1].pk), "reserve"),
            ],
            confirm=True,
        )
        report = start(client, table)
        payload = client.get(editor_url(report)).context["payload"]
        by_id = {row["id"]: row for row in payload["models"]}
        assert by_id[str(table.models[0].pk)]["participated"]
        assert not by_id[str(table.models[1].pk)]["participated"]
        assert not payload["participation_confirmed"]
        assert all(row["xp"] == "" for row in payload["models"])

    def test_incomplete_draft_is_saved_and_resumed_without_gameplay_changes(
        self, client, table, feature
    ):
        report = start(client, table, standalone=True)
        initial = client.get(editor_url(report))
        before = LedgerEvent.objects.count()
        effect_id = str(uuid4())
        model_id = str(table.models[0].pk)
        response = client.post(
            editor_url(report),
            html_fields(
                initial,
                intent="save",
                credits="still deciding",
                reason='A reason with "quotes" & brackets <kept>',
                **{
                    f"model-{model_id}-xp": "not finished",
                    f"model-{model_id}-participated": "on",
                    f"model-{model_id}-effect": [effect_id],
                    f"effect-{effect_id}-pick": "",
                    f"effect-{effect_id}-question": ["unfinished-choice"],
                    f"effect-{effect_id}-choice-unfinished-choice": ["remember-this"],
                },
            ),
        )
        assert response.status_code == 302
        resumed = client.get(response.url)
        raw = resumed.context["payload"]
        assert raw["credits"] == "still deciding"
        assert raw["models"][0]["xp"] == "not finished"
        assert raw["models"][0]["effects"][0]["choices"] == {
            "unfinished-choice": ["remember-this"]
        }
        round_trip = html_fields(resumed)
        assert round_trip["credits"] == ["still deciding"]
        assert round_trip[f"effect-{effect_id}-choice-unfinished-choice"] == [
            "remember-this"
        ]
        assert LedgerEvent.objects.count() == before
        assert xp_value(table.models[0]) == 0
        assert (
            "Continue draft"
            in client.get(start_url(table, standalone=True)).content.decode()
        )
        assert_books(table)

    def test_autosave_returns_the_next_revision_and_persists_the_draft(
        self, client, table, feature
    ):
        report = start(client, table)
        response = client.post(
            editor_url(report),
            html_fields(
                client.get(editor_url(report)), intent="autosave", credits="15"
            ),
            HTTP_ACCEPT="application/json",
        )
        assert response.status_code == 200
        report.refresh_from_db()
        assert response.json()["revision"] == report.draft_revision == 1
        assert response.json()["generation"] == str(report.generation)
        assert response.json()["saved"]
        assert report.draft["credits"] == "15"
        assert xp_value(table.models[0]) == 0


class TestApplyingAndCorrecting:
    """A plain first Apply works, while retries and corrections preserve later play."""

    @pytest.mark.parametrize("standalone", [False, True])
    def test_first_apply_needs_no_separate_check_step(
        self, client, table, feature, standalone
    ):
        report = start(client, table, standalone=standalone)
        response = client.post(
            editor_url(report), awards(client.get(editor_url(report)), table)
        )
        assert response.status_code == 302
        assert response.url == receipt_url(report, 1)
        receipt = client.get(response.url)
        assert receipt.status_code == 200
        assert xp_value(table.models[0]) == 2
        assert xp_value(table.models[1]) == 0
        assert_books(table)
        assert table.gang.credits == 1020
        assert report.revisions.count() == 1

    def test_participation_confirmation_is_mandatory_and_entries_survive_refusal(
        self, client, table, feature
    ):
        report = start(client, table)
        data = awards(client.get(editor_url(report)), table)
        data.pop("participation_confirmed")
        before = LedgerEvent.objects.count()
        response = client.post(editor_url(report), data)
        assert response.status_code == 409
        assert "Confirm which models took part" in response.content.decode()
        assert response.context["payload"]["credits"] == "20"
        assert response.context["models"][0].xp == "2"
        assert html_fields(response)["credits"] == ["20"]
        assert LedgerEvent.objects.count() == before
        assert not report.revisions.exists()
        accepted = client.post(
            editor_url(report),
            html_fields(response, intent="apply", participation_confirmed="on"),
        )
        assert accepted.status_code == 302
        assert xp_value(table.models[0]) == 2

    def test_retry_and_late_autosave_cannot_apply_or_reopen_results(
        self, client, table, feature
    ):
        report = start(client, table)
        data = awards(client.get(editor_url(report)), table)
        assert client.post(editor_url(report), data).status_code == 302
        events = LedgerEvent.objects.count()
        assert client.post(editor_url(report), data).status_code == 302
        late = client.post(
            editor_url(report), data | {"intent": "autosave", "credits": "999"}
        )
        assert late.status_code == 302
        report.refresh_from_db()
        assert report.state == PostBattleReport.State.APPLIED
        assert report.revisions.count() == 1
        assert LedgerEvent.objects.count() == events
        assert xp_value(table.models[0]) == 2
        assert_books(table)

    def test_correction_applies_the_difference_and_keeps_the_original_receipt(
        self, client, table, feature
    ):
        report = start(client, table)
        original_data = awards(client.get(editor_url(report)), table)
        first = client.post(editor_url(report), original_data)
        assert first.status_code == 302
        original_receipt = report.revisions.get(sequence=1).receipt
        xp_assignment = Assignment.objects.get(
            miniature_root=table.models[0], counter=table.xp
        )
        with operation(table.gang, actor=table.owner) as op:
            op.tally(xp_assignment, 4, note="A later battle")
            op.receive_credits(30, note="Later income")
        client.force_login(table.arbitrator)
        correction_url = reverse("n26-post-battle-correct", args=[report.pk])
        assert client.get(correction_url).status_code == 405
        corrected = client.post(correction_url)
        assert corrected.url == editor_url(report)
        correction_page = client.get(corrected.url)
        assert "Correcting recorded results" in correction_page.content.decode()
        assert html_fields(correction_page)["generation"] != original_data["generation"]
        response = client.post(
            editor_url(report),
            html_fields(
                correction_page,
                intent="apply",
                credits="10",
                **{f"model-{table.models[0].pk}-xp": "1"},
            ),
        )
        assert response.url == receipt_url(report, 2)
        assert xp_value(table.models[0]) == 5
        assert_books(table)
        assert table.gang.credits == 1040
        assert report.revisions.get(sequence=1).receipt == original_receipt
        assert client.get(receipt_url(report, 1)).status_code == 200


class TestDraftActions:
    """Conveniences change saved inputs, never XP or injuries before Apply."""

    def test_bulk_xp_and_undo_only_change_selected_participants(
        self, client, table, feature
    ):
        report = start(client, table)
        first, reserve = table.models
        data = html_fields(
            client.get(editor_url(report)),
            intent="participation-xp",
            **{
                f"model-{first.pk}-participated": "on",
                f"model-{first.pk}-xp": "3",
                f"model-{reserve.pk}-xp": "5",
            },
        )
        response = client.post(editor_url(report), data)
        assert response.status_code == 200
        assert [row.xp for row in response.context["models"]] == ["4", "5"]
        assert "Undo XP addition" in response.content.decode()
        undone = client.post(
            editor_url(report), html_fields(response, intent="undo-xp")
        )
        assert undone.status_code == 200
        assert [row.xp for row in undone.context["models"]] == ["3", "5"]
        assert "Undo XP addition" not in undone.content.decode()
        assert xp_value(first) == xp_value(reserve) == 0

    def test_undo_preserves_an_extra_manual_xp_change(self, client, table, feature):
        report = start(client, table)
        model = table.models[0]
        response = client.post(
            editor_url(report),
            html_fields(
                client.get(editor_url(report)),
                intent="participation-xp",
                **{f"model-{model.pk}-participated": "on", f"model-{model.pk}-xp": "3"},
            ),
        )
        undone = client.post(
            editor_url(report),
            html_fields(response, intent="undo-xp", **{f"model-{model.pk}-xp": "8"}),
        )
        assert undone.context["models"][0].xp == "7"

    def test_an_optional_dependent_choice_may_stay_blank(self, client, table, feature):
        injury, hand = dependent_injury(table, required=False)
        report = start(client, table)
        checked, effect_id = with_effect(client, table, report, injury)
        question = checked.context["models"][0].effects[0].questions[0]
        submitted = html_fields(checked, intent="apply")
        assert submitted[f"effect-{effect_id}-choice-{question.key}"] == [""]
        response = client.post(editor_url(report), submitted)
        assert response.status_code == 302, response.context["errors"]
        assert Assignment.objects.filter(
            miniature=table.models[0], pickable=injury, archived=False
        ).exists()
        assert not Assignment.objects.filter(
            miniature=table.models[0], pickable=hand, archived=False
        ).exists()
        assert_books(table)

    def test_changed_injury_exposes_a_way_to_reset_its_choices(
        self, client, table, feature
    ):
        injury, hand = dependent_injury(table, required=True)
        report = start(client, table)
        checked, effect_id = with_effect(client, table, report, injury)
        question = checked.context["models"][0].effects[0].questions[0]
        chosen = client.post(
            editor_url(report),
            html_fields(
                checked,
                intent="check",
                **{
                    f"effect-{effect_id}-choice-{question.key}": [
                        question.options[0].value
                    ]
                },
            ),
        )
        replacement = next(
            value
            for value, _ in chosen.context["models"][0].effect_options
            if value.endswith(f"|{table.wound.pk}")
        )
        changed = client.post(
            editor_url(report),
            html_fields(
                chosen,
                intent="check",
                credits="31",
                reason="Keep this edited reason",
                **{f"effect-{effect_id}-pick": replacement},
            ),
        )
        assert changed.status_code == 200
        assert "Reset effect choices" in BeautifulSoup(
            changed.content, "html.parser"
        ).get_text(" ", strip=True), changed.context["models"][0].effects
        assert html_fields(changed)[f"effect-{effect_id}-choice-{question.key}"] == [
            question.options[0].value
        ]
        cleared = client.post(
            editor_url(report),
            html_fields(changed, intent=f"clear-choices:{effect_id}"),
        )
        assert cleared.status_code == 200
        assert "Reset effect choices" not in cleared.content.decode()
        kept = html_fields(cleared)
        assert kept["credits"] == ["31"]
        assert kept["reason"] == ["Keep this edited reason"]
        assert kept[f"model-{table.models[0].pk}-xp"] == ["2"]
        assert kept[f"effect-{effect_id}-pick"] == [replacement]
        assert f"effect-{effect_id}-choice-{question.key}" not in kept
        assert cleared.context["payload"]["models"][0]["effects"][0]["choices"] == {}
        applied = client.post(editor_url(report), kept | {"intent": "apply"})
        assert applied.status_code == 302
        assert Assignment.objects.filter(
            miniature=table.models[0], pickable=table.wound, archived=False
        ).exists()
        assert not Assignment.objects.filter(
            miniature=table.models[0], pickable=hand, archived=False
        ).exists()
        assert_books(table)

    def test_xp_undo_survives_adding_and_removing_a_lasting_effect(
        self, client, table, feature
    ):
        report = start(client, table)
        model = table.models[0]
        incremented = client.post(
            editor_url(report),
            html_fields(
                client.get(editor_url(report)),
                intent="participation-xp",
                **{
                    f"model-{model.pk}-participated": "on",
                    f"model-{model.pk}-xp": "3",
                },
            ),
        )
        added = client.post(
            editor_url(report),
            html_fields(incremented, intent=f"add-effect:{model.pk}"),
        )
        assert "Undo XP addition" in added.content.decode()
        effect_id = added.context["models"][0].effects[0].id
        removed = client.post(
            editor_url(report),
            html_fields(added, intent=f"remove-effect:{effect_id}"),
        )
        assert "Undo XP addition" in removed.content.decode()
        undone = client.post(editor_url(report), html_fields(removed, intent="undo-xp"))
        assert undone.context["models"][0].xp == "3"
        assert "Undo XP addition" not in undone.content.decode()
        assert xp_value(model) == 0

    def test_repeated_injuries_keep_separate_occurrences_and_remove_one(
        self, client, table, feature
    ):
        report = start(client, table)
        model = table.models[0]
        first = client.post(
            editor_url(report),
            html_fields(
                client.get(editor_url(report)), intent=f"add-effect:{model.pk}"
            ),
        )
        choice = first.context["models"][0].effect_options[0][0]
        first_id = first.context["models"][0].effects[0].id
        second = client.post(
            editor_url(report),
            html_fields(
                first,
                intent=f"add-effect:{model.pk}",
                **{f"effect-{first_id}-pick": choice},
            ),
        )
        second_id = second.context["models"][0].effects[1].id
        assert first_id != second_id
        saved = client.post(
            editor_url(report),
            html_fields(second, intent="save", **{f"effect-{second_id}-pick": choice}),
        )
        resumed = client.get(saved.url)
        assert [effect.selected for effect in resumed.context["models"][0].effects] == [
            choice,
            choice,
        ]
        removed = client.post(
            editor_url(report), html_fields(resumed, intent=f"remove-effect:{first_id}")
        )
        assert [effect.id for effect in removed.context["models"][0].effects] == [
            second_id
        ]
        assert not Assignment.objects.filter(
            miniature_root=model, pickable=table.wound
        ).exists()
        model.refresh_from_db()
        assert model.status == Status.ACTIVE


class TestStaleAndMalformedForms:
    """Refusals preserve typed values without issuing a fresh stale-save token."""

    @pytest.mark.parametrize("intent", ["save", "apply"])
    def test_stale_submission_keeps_all_entries_and_the_old_version(
        self, client, table, feature, intent
    ):
        report = start(client, table)
        initial = client.get(editor_url(report))
        current = html_fields(initial, intent="autosave", credits="10")
        assert client.post(editor_url(report), current).status_code == 200
        effect_id = str(uuid4())
        model_id = str(table.models[0].pk)
        stale_data = awards(
            initial,
            table,
            intent=intent,
            credits="30",
            reason="Unsaved old tab",
            **{
                f"model-{model_id}-status": "dead",
                f"model-{model_id}-equipment": "lost",
                f"model-{model_id}-effect": [effect_id],
                f"effect-{effect_id}-pick": "",
            },
        )
        response = client.post(editor_url(report), stale_data)
        assert response.status_code == 409
        assert response.context["stale"]
        kept = html_fields(response)
        for name in ("generation", "revision", "submission_key"):
            assert kept[name] == stale_data[name]
        assert kept["credits"] == ["30"]
        assert kept["reason"] == ["Unsaved old tab"]
        assert kept[f"model-{model_id}-xp"] == ["2"]
        assert kept[f"model-{model_id}-status"] == ["dead"]
        assert kept[f"model-{model_id}-equipment"] == ["lost"]
        assert kept[f"model-{model_id}-effect"] == [effect_id]
        report.refresh_from_db()
        assert report.draft["credits"] == "10"
        assert (
            client.post(editor_url(report), kept | {"intent": "save"}).status_code
            == 409
        )

    @pytest.mark.parametrize(
        "change", [{"generation": "bad"}, {"revision": "-1"}, {"submission_key": "bad"}]
    )
    def test_invalid_versions_are_explained_without_saving(
        self, client, table, feature, change
    ):
        report = start(client, table)
        response = client.post(
            editor_url(report),
            awards(client.get(editor_url(report)), table, **change),
        )
        assert response.status_code == 400
        assert "version is missing or invalid" in response.content.decode()
        assert html_fields(response)["credits"] == ["20"]
        report.refresh_from_db()
        assert report.draft_revision == 0
        assert not report.revisions.exists()

    def test_stale_autosave_returns_an_error_without_overwriting(
        self, client, table, feature
    ):
        report = start(client, table)
        data = html_fields(
            client.get(editor_url(report)), intent="autosave", credits="10"
        )
        assert client.post(editor_url(report), data).status_code == 200
        response = client.post(editor_url(report), data | {"credits": "20"})
        assert response.status_code == 409
        assert "another tab" in response.json()["error"]
        report.refresh_from_db()
        assert report.draft["credits"] == "10"

    @pytest.mark.parametrize("field", ["model", "effect"])
    def test_malformed_content_ids_do_not_raise_500(
        self, client, table, feature, field
    ):
        report = start(client, table)
        data = awards(client.get(editor_url(report)), table)
        if field == "model":
            data["model_id"] = ["bad-id"]
        else:
            data[f"model-{table.models[0].pk}-effect"] = ["bad-occurrence"]
            data["effect-bad-occurrence-pick"] = "bad-slot|bad-pick"
        response = client.post(editor_url(report), data)
        assert response.status_code == 409
        assert not report.revisions.exists()


class TestReportPermissions:
    """Owners and current arbitrators may record; private drafts stay private."""

    def test_current_arbitrator_can_start_and_save_battle_results(
        self, client, table, feature
    ):
        client.force_login(table.arbitrator)
        report = start(client, table)
        response = client.post(
            editor_url(report),
            html_fields(client.get(editor_url(report)), intent="save", credits="10"),
        )
        assert response.status_code == 302
        report.refresh_from_db()
        assert report.last_editor == table.arbitrator

    def test_departed_gang_keeps_owner_access_but_loses_arbitrator_access(
        self, client, table, feature
    ):
        report = start(client, table)
        with operation(table.gang, actor=table.owner) as op:
            op.leave_campaign()
        client.force_login(table.arbitrator)
        assert client.get(editor_url(report)).status_code == 404
        assert client.post(editor_url(report), {}).status_code == 404
        client.force_login(table.owner)
        assert client.get(editor_url(report)).status_code == 200

    def test_arbitrator_cannot_edit_an_owners_standalone_report(
        self, client, table, feature
    ):
        report = start(client, table, standalone=True)
        client.force_login(table.arbitrator)
        assert client.get(editor_url(report)).status_code == 404
        assert client.post(editor_url(report), {}).status_code == 404

    @pytest.mark.parametrize("who", ["stranger", "anonymous"])
    def test_private_drafts_are_not_readable_by_others(
        self, client, table, feature, who
    ):
        report = start(client, table)
        if who == "stranger":
            client.force_login(User.objects.create_user("stranger"))
        else:
            client.logout()
        for url in (editor_url(report), receipt_url(report), start_url(table)):
            assert client.get(url).status_code == 404
            assert client.post(url, {}).status_code == 404

    def test_flag_off_blocks_every_route(self, client, table, feature):
        report = start(client, table)
        feature.availability = Availability.OFF
        feature.save()
        urls = [
            start_url(table),
            start_url(table, standalone=True),
            editor_url(report),
            receipt_url(report),
            receipt_url(report, 1),
            reverse("n26-post-battle-correct", args=[report.pk]),
        ]
        for url in urls:
            for method in (client.get, client.post):
                assert method(url).status_code == 404

    @pytest.mark.parametrize(
        "route",
        [
            "n26-post-battle-editor",
            "n26-post-battle-receipt",
            "n26-post-battle-correct",
            "n26-gang-post-battle",
        ],
    )
    def test_malformed_route_ids_are_404(self, client, table, feature, route):
        url = reverse(route, args=["bad-id"])
        assert client.post(url).status_code == 404

    def test_nonparticipant_cannot_start_a_battle_report(
        self, client, table, feature, gang_type
    ):
        other = found_gang("Not playing", gang_type, owner=table.owner)
        url = reverse(
            "n26-battle-report", args=[table.campaign.pk, table.battle.pk, other.pk]
        )
        assert client.get(url).status_code == 404
        assert client.post(url).status_code == 404


class TestReportQueryGrowth:
    """More roster models reuse the same equipment and effect fetches."""

    def test_more_models_do_not_add_editor_queries(self, client, table, feature):
        report = start(client, table)
        with_effect(client, table, report, table.wound)

        def count():
            client.get(editor_url(report))
            with CaptureQueriesContext(connection) as captured:
                response = client.get(editor_url(report))
                assert response.status_code == 200
            return len(captured)

        small = count()
        profile = table.models[0].membership.profile
        for name in ("Ash", "Flare", "Coal"):
            hire(table.gang, profile, name)
        assert count() <= small
        assert len(client.get(editor_url(report)).context["models"]) == 5
