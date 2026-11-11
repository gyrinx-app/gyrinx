"""The report form saves drafts and applies each submitted revision once."""

import json
from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.activities import POST_BATTLE_HELP
from n26.core.campaigns import campaign_operation
from n26.core.crews import CrewSelection, save_crew
from n26.core.models import (
    Activity,
    Assignment,
    BattleCrew,
    CounterValue,
    LedgerEvent,
    Miniature,
    PostBattleReport,
    PostBattleRevision,
)
from n26.core.operations import LibraryError, Refusal, operation
from n26.core.post_battle import preview_report, start_report
from n26.core.reconcile import assert_reconciled
from n26.core.status import Status
from n26.core.views.post_battle import _initial_payload
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
from n26.library.models import (
    Counter,
    GangType,
    Pickable,
    Picklist,
    Profile,
    ProfileType,
    SlotType,
    Stat,
    StatlineType,
    StatlineTypeStat,
    get_default_pack,
)
from n26.tests.fixtures import library_setup
from n26.tests.sandbox.actions import (
    assign,
    create_wargear,
    found_campaign,
    found_gang,
    hire,
    join_campaign,
    modifier,
    op_adds_model,
    op_changes_counter,
    open_founding,
    remove,
    tally,
)
from n26.tests.sandbox.actions import targets_model as targets_the_model

pytestmark = pytest.mark.django_db


@library_setup
def report_content(make_profile):
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
    return xp, kind, wound, picklist, profile


@library_setup
def _seed_report_catalogue():
    # Use a three-stat Person fixture without seeded stat limits.
    pack = get_default_pack()
    shape = StatlineType.objects.create(name="Person", pack=pack)
    definitions = [
        ("M", "Movement", {"is_inches": True}),
        ("WS", "Weapon Skill", {"is_target": True, "is_inverted": True}),
        ("T", "Toughness", {}),
    ]
    for position, (short, full, flags) in enumerate(definitions):
        stat = Stat.objects.create(short_name=short, full_name=full, pack=pack, **flags)
        StatlineTypeStat.objects.create(
            statline_type=shape, stat=stat, position=position, pack=pack
        )
    kind = ProfileType.objects.create(name="Fighter", statline_type=shape, pack=pack)
    gang_type = GangType.objects.create(name="Escher", pack=pack)

    def make_profile(name):
        return Profile.objects.create(
            name=name, profile_type=kind, gang_type=gang_type, pack=pack
        )

    report_content(make_profile)


@pytest.fixture(scope="module")
def _prepared_report_catalogue(django_db_setup, django_db_blocker):
    """Share content only; ordinary case rollback isolates every player write."""
    with django_db_blocker.unblock(), transaction.atomic():
        _seed_report_catalogue()
        try:
            yield
        finally:
            transaction.set_rollback(True)


@pytest.fixture
def person_statline_type(default_pack, _prepared_report_catalogue):
    return StatlineType.objects.get(name="Person", pack=default_pack)


@pytest.fixture
def person_type(person_statline_type):
    return ProfileType.objects.get(name="Fighter", statline_type=person_statline_type)


@pytest.fixture
def gang_type(default_pack, _prepared_report_catalogue):
    return GangType.objects.get(name="Escher", pack=default_pack)


def _report_content():
    """Reload shared content for the current test’s fixtures."""
    return (
        Counter.objects.get(name="XP"),
        SlotType.objects.get(name="Lasting injury"),
        Pickable.objects.get(name="Grievous Wound"),
        Picklist.objects.get(name="Lasting injuries"),
        Profile.objects.get(name="Ganger"),
    )


@pytest.fixture
def table(
    client,
    default_pack,
    gang_type,
    campaign_type,
    make_profile,
    counter_tracking,
    request,
):
    owner = User.objects.create_user("report-owner")
    arbitrator = User.objects.create_user("report-arbitrator")
    campaign = found_campaign("Dust Falls", campaign_type, owner=arbitrator)
    gang = open_founding(found_gang("Ashen Choir", gang_type, owner=owner, budget=1000))
    join_campaign(gang, campaign)
    xp, kind, wound, picklist, profile = _report_content()
    models = [
        hire(gang, profile, name)
        for name in ("Cinder", "Ember")[: getattr(request, "param", 2)]
    ]
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


def editor_props(response):
    """Read the JSON contract embedded in the complete editor root."""
    document = BeautifulSoup(response.content, "html.parser")
    host = document.select_one('[data-react-name="post-battle"]')
    assert host is not None, response.content.decode()[:500]
    return json.loads(document.find(id=host["data-react-props"]).string)


def model_props(response, model):
    return next(
        row for row in editor_props(response)["models"] if row["id"] == str(model.pk)
    )


def effect_options(model):
    return [
        (option["value"], option["label"])
        for group in model["effectGroups"]
        for option in group["options"]
    ]


def html_fields(response, **changes):
    """Submit the controls the browser received, including all hidden versions."""
    document = BeautifulSoup(response.content, "html.parser")
    form = document.find("form", id="post-battle-form") or document.find(
        "form", method="post"
    )
    if form is None:
        host = document.select_one('[data-react-name="post-battle"]')
        assert host is not None
        props = json.loads(document.find(id=host["data-react-props"]).string)
        data = {
            "generation": [props["generation"]],
            "revision": [str(props["revision"])],
            "submission_key": [props.get("submissionKey", str(uuid4()))],
            "review": [props["review"]],
            "credit_line": [line["id"] for line in props["mission"]["creditLines"]],
            "model_id": [model["id"] for model in props["models"]],
        }
        if props["participationConfirmed"]:
            data["participation_confirmed"] = ["on"]
        for line in props["mission"]["creditLines"]:
            data[f"credit-{line['id']}-amount"] = [line["amount"]]
            data[f"credit-{line['id']}-reason"] = [line["reason"]]
        for counter in props["mission"]["counters"]:
            if counter["editable"]:
                data.setdefault(counter["listName"], []).append(counter["id"])
                data[counter["prefix"]] = [counter["entered"]]
        for model in props["models"]:
            prefix = model["prefix"]
            for key in ("xp", "status", "equipment", "note"):
                data[f"{prefix}-{key}"] = [model[key]]
            if model["participated"]:
                data[f"{prefix}-participated"] = ["on"]
            for counter in model["counters"]:
                if counter["editable"]:
                    data.setdefault(counter["listName"], []).append(counter["id"])
                    data[counter["prefix"]] = [counter["entered"]]
            data[f"{prefix}-effect"] = [effect["id"] for effect in model["effects"]]
            for effect in model["effects"]:
                ep = f"effect-{effect['id']}"
                data[f"{ep}-pick"] = [effect["selected"]]
                questions = [*effect["retainedChoices"], *effect["questions"]]
                data[f"{ep}-question"] = [question["key"] for question in questions]
                for question in questions:
                    if question["selected"]:
                        data[f"{ep}-choice-{question['key']}"] = question["selected"]
        return with_first_credits(data, changes)
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
    return with_first_credits(data, changes)


def with_first_credits(data, changes):
    """Map credits and reason aliases onto the first credit line."""
    changes = dict(changes)
    line = (data.get("credit_line") or [None])[0]
    if line is not None:
        for short, field in (("credits", "amount"), ("reason", "reason")):
            name = f"credit-{line}-{field}"
            if short in changes:
                changes[name] = changes.pop(short)
            data[short] = changes.get(name, data.get(name))
    return data | changes


def first_credits(payload):
    """The first line of credits in a saved draft or context payload."""
    return payload["credit_lines"][0]["amount"]


def record_results_form(response, url):
    """The Record results form that posts to ``url`` on a rendered page."""
    document = BeautifulSoup(response.content, "html.parser")
    form = document.find("form", action=url)
    assert form is not None
    return form


def record_results_fields(response, url):
    form = record_results_form(response, url)
    return {
        element["name"]: element.get("value", "")
        for element in form.select("input[name]")
    }


def start(client, table, *, standalone=False):
    """Prepare a real draft without exercising another page's entry flow."""
    battle = None if standalone else table.battle
    return start_report(
        table.gang,
        actor=table.owner,
        battle=battle,
        request_key=uuid4(),
        date=date(2026, 9, 20),
        reference="Stand-off",
        payload=_initial_payload(table.gang, battle),
    )


def start_through_page(client, table, *, standalone=False):
    url = start_url(table, standalone=standalone)
    if standalone:
        data = html_fields(client.get(url), date="2026-09-20", reference="Stand-off")
    else:
        battle_page = reverse("n26-battle", args=[table.campaign.pk, table.battle.pk])
        data = record_results_fields(client.get(battle_page), url)
    response = client.post(url, data)
    assert response.status_code == 302
    report = PostBattleReport.objects.get(gang=table.gang)
    assert response.url == editor_url(report)
    return report


@pytest.mark.parametrize("transport", ["autosave", "refresh", "save"])
@pytest.mark.parametrize("validation", [False, True])
def test_report_errors_show_only_public_messages(
    client, table, monkeypatch, transport, validation
):
    report = start(client, table)
    page = client.get(editor_url(report))
    public = "Reload this draft before saving."
    secret = "SELECT secret FROM private_report_table"

    class DiagnosticRefusal(Refusal):
        def __str__(self):
            return secret

    def refuse(*args, **kwargs):
        try:
            raise RuntimeError(secret)
        except RuntimeError as cause:
            error = (
                ValidationError([public, "Review the draft."])
                if validation
                else DiagnosticRefusal(public)
            )
            raise error from cause

    monkeypatch.setattr("n26.core.post_battle_workflow.save_draft", refuse)
    before = LedgerEvent.objects.count()
    if transport == "refresh":
        response = refresh(client, report, page, table.models[0])
    else:
        response = client.post(editor_url(report), html_fields(page, intent=transport))
    assert response.status_code == 409
    expected = public + (" Review the draft." if validation else "")
    if transport == "autosave":
        assert response.json() == {"error": expected}
    elif transport == "refresh":
        assert response.content.decode() == expected
    else:
        assert public in editor_props(response)["errors"]
        if validation:
            assert "Review the draft." in editor_props(response)["errors"]
    assert secret not in response.content.decode()
    assert LedgerEvent.objects.count() == before
    report.refresh_from_db()
    assert report.draft_revision == 0


@pytest.mark.parametrize("error_type", [RuntimeError, LibraryError])
def test_unexpected_report_errors_use_the_server_error_handler(
    client, table, monkeypatch, settings, caplog, error_type
):
    settings.DEBUG = False
    client.raise_request_exception = False
    report = start(client, table)
    page = client.get(editor_url(report))
    secret = "SELECT secret FROM private_report_table"

    def fail(*args, **kwargs):
        raise error_type(secret)

    monkeypatch.setattr("n26.core.post_battle_workflow.save_draft", fail)
    response = client.post(editor_url(report), html_fields(page, intent="autosave"))
    assert response.status_code == 500
    assert secret not in response.content.decode()
    assert secret in caplog.text


def awards(response, table, **changes):
    return with_first_credits(
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
        ),
        changes,
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
    effect_id = editor_props(added)["models"][0]["effects"][0]["id"]
    option = next(
        value
        for value, _ in effect_options(editor_props(added)["models"][0])
        if value.endswith(f"|{injury.pk}")
    )
    checked = client.post(
        editor_url(report),
        html_fields(added, intent="check", **{f"effect-{effect_id}-pick": option}),
    )
    assert checked.status_code == 200
    return checked, effect_id


class TestReportLayout:
    """One editor contract contains each model's inputs, validation and preview facts."""

    def test_each_model_has_one_module_holding_all_its_controls(self, client, table):
        report = start(client, table)
        response = client.get(editor_url(report))
        document = BeautifulSoup(response.content, "html.parser")
        assert len(document.select('[data-react-name="post-battle"]')) == 1
        assert not document.select(
            '[data-react-name="post-battle-toolbar"], [data-react-name="post-battle-preview"]'
        )
        props = editor_props(response)
        assert props["participationConfirmed"] is False
        assert props["action"] == editor_url(report)
        for model in table.models:
            shown = model_props(response, model)
            assert shown["name"] == model.name
            assert shown["prefix"] == f"model-{model.pk}"
            fields = html_fields(response)
            assert fields["model_id"].count(str(model.pk)) == 1
            for name in ("xp", "status", "equipment", "note"):
                assert len(fields[f"model-{model.pk}-{name}"]) == 1
        model = table.models[0]
        added = client.post(
            editor_url(report), html_fields(response, intent=f"add-effect:{model.pk}")
        )
        shown = model_props(added, model)
        assert len(shown["effects"]) == 1
        assert shown["effects"][0]["label"] == "Lasting injury 1"
        assert shown["statusOptions"]
        assert shown["equipment"] == "keep"

    def test_xp_errors_are_inside_the_model_module(self, client, table):
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
        shown = model_props(response, model)
        assert editor_props(response)["showErrors"]
        assert any(
            "Enter a whole number" in error and "Cinder's XP" in error
            for error in shown["errors"]
        )
        assert not model_props(response, table.models[1])["errors"]

    def test_summary_shows_xp_removed_with_a_lasting_effect(self, client, table):
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
        assert "-2 XP (2 → 0)" in summary_text(response)
        assert xp_value(model) == 2


class TestGangActions:
    """The roster groups the owner's actions in one panel."""

    def test_post_battle_is_in_actions(self, client, table):
        with operation(table.gang, actor=table.owner) as act:
            act.set_status(table.models[0], Status.RANSOMED)
            act.set_status(table.models[1], Status.RECOVERY)
        response = client.get(reverse("n26-gang", args=[table.gang.pk]))
        assert response.status_code == 200
        document = BeautifulSoup(response.content, "html.parser")
        panel = document.select_one('[role="region"][aria-label="Actions"]')
        assert panel
        links = document.select(f'a[href="{start_url(table, standalone=True)}"]')
        assert len(links) == 1
        assert links[0] in panel.find_all("a")
        assert links[0].get_text(strip=True) == "Post-battle"
        assert POST_BATTLE_HELP in links[0].parent.get_text()
        assert "No action is open." not in panel.get_text()
        founding_url = reverse("n26-gang-founding-action", args=[table.gang.pk])
        assert panel.find("form", action=founding_url)
        assert "Recent history" not in panel.get_text()
        history = panel.find(
            "a", href=reverse("n26-gang-history", args=[table.gang.pk])
        )
        assert history.get_text(strip=True) == "History"
        assert "Hire Fighters" not in panel.get_text()
        square = response.context["activities_square"]
        assert square.founding
        verbs = [step.verb for step in square.to_do]
        assert verbs == ["Pay ransom", "Clean House", "Post-battle"]
        assert "Pay ransom" in panel.get_text()
        assert "Clean House" in panel.get_text()

    def test_the_panel_shares_the_open_visit_and_history(self, client, table):
        with operation(table.gang, actor=table.owner) as act:
            act.close_activity(table.gang.open_activity(Activity.Kind.FOUNDING))
            act.open_activity(Activity.Kind.TRADING_POST_VISIT, trade_points=3)
        response = client.get(reverse("n26-gang", args=[table.gang.pk]))
        square = response.context["activities_square"]
        assert square.founding is None
        assert square.start_founding == ""
        assert square.visit.trade_points_left == 3
        assert square.visit.href == reverse(
            "n26-gang-trade-points", args=[table.gang.pk]
        )
        panel = BeautifulSoup(response.content, "html.parser").select_one(
            '[role="region"][aria-label="Actions"]'
        )
        assert "Trading Post visit open" in panel.get_text()
        assert "Recent history" not in panel.get_text()
        assert panel.find("a", href=reverse("n26-gang-history", args=[table.gang.pk]))
        assert panel.find("a", href=start_url(table, standalone=True))

    def test_the_shared_panel_has_no_per_model_queries(
        self, client, table, make_profile
    ):
        profile = make_profile("Extra ganger")
        hire(table.gang, profile, "Extra 0")
        url = reverse("n26-gang", args=[table.gang.pk])

        def measure():
            with CaptureQueriesContext(connection) as captured:
                response = client.get(url)
                assert response.status_code == 200
            return len(captured)

        measure()
        small = measure()
        for number in range(1, 6):
            hire(table.gang, profile, f"Extra {number}")
        assert measure() == small

    @pytest.mark.parametrize("who", ["arbitrator", "anonymous"])
    def test_other_readers_get_neither_the_panel_nor_standalone_creation(
        self, client, table, who
    ):
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
        refused = 404 if who == "arbitrator" else 302
        assert client.get(url).status_code == refused
        assert client.post(url, {}).status_code == refused
        assert not PostBattleReport.objects.exists()


class TestReportGroups:
    """Every saved report belongs to one group and has one continuation link."""

    @pytest.mark.parametrize("applied", [False, True])
    def test_campaign_report_appears_once_beside_its_battle(
        self, client, table, applied
    ):
        report = start(client, table)
        if applied:
            response = client.post(
                editor_url(report), awards(client.get(editor_url(report)), table)
            )
            assert response.status_code == 302
        standalone = start_report(
            table.gang,
            actor=table.owner,
            request_key=uuid4(),
            reference="A separate battle",
        )
        response = client.get(start_url(table, standalone=True))
        document = BeautifulSoup(response.content, "html.parser")
        campaign_group = document.select_one("#campaign-battles")
        standalone_group = document.select_one("#standalone-reports")
        destination = receipt_url(report) if applied else editor_url(report)
        assert len(document.find_all("a", href=destination)) == 1
        assert campaign_group.find("a", href=destination).get_text(strip=True) == (
            "View results" if applied else "Continue draft"
        )
        assert campaign_group.find("a", href=start_url(table)) is None
        assert campaign_group.find("form", action=start_url(table)) is None
        assert standalone_group.find("a", href=destination) is None
        assert len(document.find_all("a", href=editor_url(standalone))) == 1
        assert standalone_group.find("a", href=editor_url(standalone)) is not None
        assert campaign_group.find("a", href=editor_url(standalone)) is None
        assert "Saved reports" not in document.get_text()
        assert "Start a standalone report" in standalone_group.get_text()

    def test_other_gangs_reports_do_not_change_this_gangs_battle_action(
        self, client, table, gang_type
    ):
        opponent = found_gang("Opponents", gang_type, owner=table.arbitrator)
        join_campaign(opponent, table.campaign)
        with campaign_operation(table.campaign, actor=table.arbitrator) as act:
            act.edit_battle(
                table.battle,
                scenario=table.battle.scenario,
                date=table.battle.date,
                gangs=[table.gang, opponent],
                result="not_recorded",
                winners=[],
                revision=0,
            )
        report = start_report(
            opponent,
            actor=table.arbitrator,
            battle=table.battle,
            request_key=uuid4(),
        )
        document = BeautifulSoup(
            client.get(start_url(table, standalone=True)).content, "html.parser"
        )
        assert len(document.find_all("form", action=start_url(table))) == 1
        assert document.find("a", href=editor_url(report)) is None
        assert "Continue draft" not in document.get_text()

    def test_empty_groups_are_named_and_keep_the_standalone_form(self, client, table):
        with campaign_operation(table.campaign, actor=table.arbitrator) as act:
            act.archive()
        document = BeautifulSoup(
            client.get(start_url(table, standalone=True)).content, "html.parser"
        )
        assert (
            document.select_one("#campaign-battles h2").get_text(strip=True)
            == "Campaign battles"
        )
        assert (
            document.select_one("#standalone-reports h2").get_text(strip=True)
            == "Standalone reports"
        )
        assert "No campaign battles yet." in document.get_text()
        assert "No standalone reports yet." in document.get_text()
        assert document.select_one("#standalone-reports form[method=post]") is not None

    @pytest.mark.parametrize("unavailable", ["archived", "removed"])
    def test_unavailable_drafts_stay_with_their_battle_without_broken_links(
        self, client, table, unavailable
    ):
        report = start(client, table)
        if unavailable == "archived":
            with campaign_operation(table.campaign, actor=table.arbitrator) as act:
                act.archive()
            explanation = "This campaign is archived."
        else:
            # A legacy participant list may not include the gang its report names.
            table.battle.gangs.remove(table.gang)
            explanation = "This gang is no longer a participant in this battle."
        document = BeautifulSoup(
            client.get(start_url(table, standalone=True)).content, "html.parser"
        )
        campaign_group = document.select_one("#campaign-battles")
        assert table.battle.title in campaign_group.get_text()
        assert "Draft saved" in campaign_group.get_text()
        assert explanation in campaign_group.get_text()
        assert document.find("a", href=editor_url(report)) is None
        assert document.find("a", href=start_url(table)) is None
        assert document.find("form", action=start_url(table)) is None
        assert (
            table.battle.title
            not in document.select_one("#standalone-reports").get_text()
        )

    def test_older_reports_remain_reachable_in_their_own_groups(self, client, table):
        report = start(client, table)
        with campaign_operation(table.campaign, actor=table.arbitrator) as act:
            for index in range(30):
                act.record_battle(
                    date(2026, 9, 21), [table.gang], scenario=f"Later battle {index}"
                )
        standalone = [
            start_report(
                table.gang,
                actor=table.owner,
                request_key=uuid4(),
                reference=f"Standalone {index}",
            )
            for index in range(51)
        ]
        url = start_url(table, standalone=True)
        first = client.get(url)
        assert len(first.context["campaign_entries"]) == 30
        assert len(first.context["standalone_page"]) == 50
        second = client.get(url, {"campaign_page": 2, "standalone_page": 2})
        document = BeautifulSoup(second.content, "html.parser")
        campaign_group = document.select_one("#campaign-battles")
        standalone_group = document.select_one("#standalone-reports")
        assert campaign_group.find("a", href=editor_url(report)) is not None
        assert standalone_group.find("a", href=editor_url(standalone[0])) is not None
        campaign_previous = campaign_group.select_one("nav a[href]")["href"]
        standalone_previous = standalone_group.select_one("nav a[href]")["href"]
        assert parse_qs(urlsplit(campaign_previous).query) == {
            "campaign_page": ["1"],
            "standalone_page": ["2"],
        }
        assert parse_qs(urlsplit(standalone_previous).query) == {
            "campaign_page": ["2"],
            "standalone_page": ["1"],
        }

    def test_more_battles_and_reports_do_not_add_per_entry_queries(self, client, table):
        start(client, table)
        start_report(table.gang, actor=table.owner, request_key=uuid4())
        url = start_url(table, standalone=True)

        def count():
            client.get(url)
            with CaptureQueriesContext(connection) as queries:
                response = client.get(url)
                assert response.status_code == 200
            return len(queries)

        before = count()
        for index in range(4):
            with campaign_operation(table.campaign, actor=table.arbitrator) as act:
                battle = act.record_battle(
                    date(2026, 9, 21), [table.gang], scenario=f"Battle {index}"
                )
            start_report(
                table.gang, actor=table.owner, battle=battle, request_key=uuid4()
            )
            start_report(table.gang, actor=table.owner, request_key=uuid4())
        assert count() <= before


class TestStartingAndResuming:
    """Reading creates nothing; starting and saving can safely be retried."""

    @pytest.mark.parametrize("standalone", [False, True])
    def test_starting_twice_creates_one_report(self, client, table, standalone):
        url = start_url(table, standalone=standalone)
        if standalone:
            response = client.get(url)
            assert response.status_code == 200
            assert not PostBattleReport.objects.exists()
            data = html_fields(response, date="2026-09-20", reference="Stand-off")
        else:
            data = {"request_key": str(uuid4())}
        first = client.post(url, data)
        second = client.post(url, data)
        assert first.url == second.url
        report = PostBattleReport.objects.get(gang=table.gang)
        assert report.battle_id == (None if standalone else table.battle.pk)
        assert report.reference == ("Stand-off" if standalone else table.battle.title)

    def test_a_pet_is_preselected_when_its_owner_starts(
        self, client, table, person_type, gang_type
    ):
        profile = Profile.objects.create(
            name="Cyber-mastiff", profile_type=person_type, gang_type=gang_type
        )
        wargear = create_wargear("Cyber-mastiff (pet)")
        modifier(
            "Cyber-mastiff wargear brings a pet",
            targets_the_model(),
            op_adds_model(profile),
            carried_by=wargear,
        )
        assign(wargear, miniature=table.models[0])
        pet = Miniature.objects.get(name="Cyber-mastiff", membership__gang=table.gang)
        save_crew(
            battle=table.battle,
            gang=table.gang,
            actor=table.owner,
            revision=0,
            selections=[CrewSelection(str(table.models[0].pk), "starting")],
            confirm=True,
        )
        report = start_through_page(client, table)
        payload = editor_props(client.get(editor_url(report)))["payload"]
        by_id = {row["id"]: row for row in payload["models"]}
        assert by_id[str(pet.pk)]["participated"]
        assert not by_id[str(table.models[1].pk)]["participated"]

    def test_a_pet_saved_as_starting_does_not_take_part_without_its_owner(
        self, client, table, person_type, gang_type
    ):
        profile = Profile.objects.create(
            name="Cyber-mastiff", profile_type=person_type, gang_type=gang_type
        )
        wargear = create_wargear("Cyber-mastiff (pet)")
        modifier(
            "Cyber-mastiff wargear brings a pet",
            targets_the_model(),
            op_adds_model(profile),
            carried_by=wargear,
        )
        assign(wargear, miniature=table.models[0])
        pet = Miniature.objects.get(name="Cyber-mastiff", membership__gang=table.gang)
        crew = BattleCrew.objects.create(battle=table.battle, gang=table.gang)
        crew.members.create(
            miniature=pet,
            miniature_name=pet.name,
            role="starting",
            card_name="Full equipment",
        )
        report = start_through_page(client, table)
        payload = editor_props(client.get(editor_url(report)))["payload"]
        by_id = {row["id"]: row for row in payload["models"]}
        assert not by_id[str(pet.pk)]["participated"]

    def test_a_deleted_starting_member_does_not_tick_every_model(self, client, table):
        crew = BattleCrew.objects.create(battle=table.battle, gang=table.gang)
        crew.members.create(
            miniature=None,
            miniature_name="Gone",
            role="starting",
            card_name="Full equipment",
        )
        report = start_through_page(client, table)
        payload = editor_props(client.get(editor_url(report)))["payload"]
        assert not any(row["participated"] for row in payload["models"])

    def test_saved_crew_only_preselects_starting_models(self, client, table):
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
        report = start_through_page(client, table)
        payload = editor_props(client.get(editor_url(report)))["payload"]
        by_id = {row["id"]: row for row in payload["models"]}
        assert by_id[str(table.models[0].pk)]["participated"]
        assert not by_id[str(table.models[1].pk)]["participated"]
        assert not payload["participation_confirmed"]
        assert all(row["xp"] == "" for row in payload["models"])

    def test_incomplete_draft_is_saved_and_resumed_without_gameplay_changes(
        self, client, table
    ):
        report = start_through_page(client, table, standalone=True)
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
        raw = editor_props(resumed)["payload"]
        assert raw["credit_lines"][0]["amount"] == "still deciding"
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
        self, client, table
    ):
        report = start_through_page(client, table)
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
        assert first_credits(report.draft) == "15"
        assert xp_value(table.models[0]) == 0


class TestApplyingAndCorrecting:
    """Applying a revision is idempotent; corrections preserve later gang changes."""

    @pytest.mark.parametrize("standalone", [False, True])
    def test_first_apply_needs_no_separate_check_step(self, client, table, standalone):
        report = start_through_page(client, table, standalone=standalone)
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
        document = BeautifulSoup(receipt.content, "html.parser")
        assert document.find("h1").get_text(strip=True) == "Recorded results"
        breadcrumb = document.select_one('[aria-label="Breadcrumb"]')
        assert breadcrumb.select_one('[aria-current="page"]').get_text(strip=True) == (
            "Stand-off" if standalone else "Recorded results"
        )
        callout = document.select_one('[role="alert"]:not([data-message])')
        assert "rounded-box" in callout["class"]
        assert "bg-green-50" in callout["class"]
        assert "rounded-xl" not in callout["class"]
        assert not any("emerald" in value for value in callout["class"])
        assert "Recorded by" in callout.get_text(" ", strip=True)
        assert "Recorded results" not in callout.get_text()
        assert "Results applied" not in callout.get_text()
        assert callout.find(class_="font-medium") is None
        assert "w-full" in callout.parent["class"]
        assert "mx-auto" not in callout.parent["class"]
        assert "max-w-4xl" not in callout.parent["class"]

    def test_participation_confirmation_is_mandatory_and_entries_survive_refusal(
        self, client, table
    ):
        report = start_through_page(client, table)
        data = awards(client.get(editor_url(report)), table)
        data.pop("participation_confirmed")
        before = LedgerEvent.objects.count()
        response = client.post(editor_url(report), data)
        assert response.status_code == 409
        assert "Confirm which models took part" in response.content.decode()
        assert first_credits(editor_props(response)["payload"]) == "20"
        assert editor_props(response)["models"][0]["xp"] == "2"
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
        self, client, table
    ):
        report = start_through_page(client, table)
        data = awards(client.get(editor_url(report)), table)
        assert client.post(editor_url(report), data).status_code == 302
        events = LedgerEvent.objects.count()
        assert client.post(editor_url(report), data).status_code == 302
        late = client.post(
            editor_url(report),
            with_first_credits(data, {"intent": "autosave", "credits": "999"}),
        )
        assert late.status_code == 302
        report.refresh_from_db()
        assert report.state == PostBattleReport.State.APPLIED
        assert report.revisions.count() == 1
        assert LedgerEvent.objects.count() == events
        assert xp_value(table.models[0]) == 2
        assert_books(table)

    def test_correction_applies_the_difference_and_keeps_the_original_receipt(
        self, client, table
    ):
        report = start_through_page(client, table)
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
        assert editor_props(correction_page)["correcting"]
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

    def test_an_optional_dependent_choice_may_stay_blank(self, client, table):
        injury, hand = dependent_injury(table, required=False)
        report = start(client, table)
        checked, effect_id = with_effect(client, table, report, injury)
        question = editor_props(checked)["models"][0]["effects"][0]["questions"][0]
        submitted = html_fields(checked, intent="apply")
        assert not submitted.get(f"effect-{effect_id}-choice-{question['key']}")
        response = client.post(editor_url(report), submitted)
        assert response.status_code == 302, editor_props(response)["errors"]
        assert Assignment.objects.filter(
            miniature=table.models[0], pickable=injury, archived=False
        ).exists()
        assert not Assignment.objects.filter(
            miniature=table.models[0], pickable=hand, archived=False
        ).exists()
        assert_books(table)

    def test_changed_injury_exposes_a_way_to_reset_its_choices(self, client, table):
        injury, hand = dependent_injury(table, required=True)
        report = start(client, table)
        checked, effect_id = with_effect(client, table, report, injury)
        question = editor_props(checked)["models"][0]["effects"][0]["questions"][0]
        chosen = client.post(
            editor_url(report),
            html_fields(
                checked,
                intent="check",
                **{
                    f"effect-{effect_id}-choice-{question['key']}": [
                        question["options"][0]["value"]
                    ]
                },
            ),
        )
        replacement = next(
            value
            for value, _ in effect_options(editor_props(chosen)["models"][0])
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
        assert editor_props(changed)["models"][0]["effects"][0]["retainedChoices"]
        assert html_fields(changed)[f"effect-{effect_id}-choice-{question['key']}"] == [
            question["options"][0]["value"]
        ]
        cleared = client.post(
            editor_url(report),
            html_fields(changed, intent=f"clear-choices:{effect_id}"),
        )
        assert cleared.status_code == 200
        assert not editor_props(cleared)["models"][0]["effects"][0]["retainedChoices"]
        kept = html_fields(cleared)
        assert kept["credits"] == ["31"]
        assert kept["reason"] == ["Keep this edited reason"]
        assert kept[f"model-{table.models[0].pk}-xp"] == ["2"]
        assert kept[f"effect-{effect_id}-pick"] == [replacement]
        assert f"effect-{effect_id}-choice-{question['key']}" not in kept
        assert (
            editor_props(cleared)["payload"]["models"][0]["effects"][0]["choices"] == {}
        )
        applied = client.post(editor_url(report), kept | {"intent": "apply"})
        assert applied.status_code == 302
        assert Assignment.objects.filter(
            miniature=table.models[0], pickable=table.wound, archived=False
        ).exists()
        assert not Assignment.objects.filter(
            miniature=table.models[0], pickable=hand, archived=False
        ).exists()
        assert_books(table)

    def test_repeated_injuries_keep_separate_occurrences_and_remove_one(
        self, client, table
    ):
        report = start(client, table)
        model = table.models[0]
        first = client.post(
            editor_url(report),
            html_fields(
                client.get(editor_url(report)), intent=f"add-effect:{model.pk}"
            ),
        )
        choice = effect_options(editor_props(first)["models"][0])[0][0]
        first_id = editor_props(first)["models"][0]["effects"][0]["id"]
        second = client.post(
            editor_url(report),
            html_fields(
                first,
                intent=f"add-effect:{model.pk}",
                **{f"effect-{first_id}-pick": choice},
            ),
        )
        second_id = editor_props(second)["models"][0]["effects"][1]["id"]
        assert first_id != second_id
        saved = client.post(
            editor_url(report),
            html_fields(second, intent="save", **{f"effect-{second_id}-pick": choice}),
        )
        resumed = client.get(saved.url)
        assert [
            effect["selected"]
            for effect in editor_props(resumed)["models"][0]["effects"]
        ] == [
            choice,
            choice,
        ]
        removed = client.post(
            editor_url(report), html_fields(resumed, intent=f"remove-effect:{first_id}")
        )
        assert [
            effect["id"] for effect in editor_props(removed)["models"][0]["effects"]
        ] == [second_id]
        assert not Assignment.objects.filter(
            miniature_root=model, pickable=table.wound
        ).exists()
        model.refresh_from_db()
        assert model.status == Status.ACTIVE


class TestStaleAndMalformedForms:
    """Refusals preserve typed values without issuing a fresh stale-save token."""

    @pytest.mark.parametrize("intent", ["save", "apply"])
    def test_stale_submission_keeps_all_entries_and_the_old_version(
        self, client, table, intent
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
        assert editor_props(response)["initialConflict"]
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
        assert first_credits(report.draft) == "10"
        assert (
            client.post(editor_url(report), kept | {"intent": "save"}).status_code
            == 409
        )

    @pytest.mark.parametrize(
        "change", [{"generation": "bad"}, {"revision": "-1"}, {"submission_key": "bad"}]
    )
    def test_invalid_versions_are_explained_without_saving(self, client, table, change):
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

    def test_stale_autosave_returns_an_error_without_overwriting(self, client, table):
        report = start(client, table)
        data = html_fields(
            client.get(editor_url(report)), intent="autosave", credits="10"
        )
        assert client.post(editor_url(report), data).status_code == 200
        response = client.post(
            editor_url(report), with_first_credits(data, {"credits": "20"})
        )
        assert response.status_code == 409
        assert "another tab" in response.json()["error"]
        report.refresh_from_db()
        assert first_credits(report.draft) == "10"

    @pytest.mark.parametrize("field", ["model", "effect"])
    def test_malformed_content_ids_do_not_raise_500(self, client, table, field):
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

    def test_current_arbitrator_can_start_and_save_battle_results(self, client, table):
        client.force_login(table.arbitrator)
        report = start_through_page(client, table)
        response = client.post(
            editor_url(report),
            html_fields(client.get(editor_url(report)), intent="save", credits="10"),
        )
        assert response.status_code == 302
        report.refresh_from_db()
        assert report.last_editor == table.arbitrator

    def test_departed_gang_keeps_owner_access_but_loses_arbitrator_access(
        self, client, table
    ):
        report = start_through_page(client, table)
        with operation(table.gang, actor=table.owner) as op:
            op.leave_campaign()
        client.force_login(table.arbitrator)
        assert client.get(editor_url(report)).status_code == 404
        assert client.post(editor_url(report), {}).status_code == 404
        client.force_login(table.owner)
        assert client.get(editor_url(report)).status_code == 200

    def test_arbitrator_cannot_edit_an_owners_standalone_report(self, client, table):
        report = start_through_page(client, table, standalone=True)
        client.force_login(table.arbitrator)
        assert client.get(editor_url(report)).status_code == 404
        assert client.post(editor_url(report), {}).status_code == 404

    @pytest.mark.parametrize("who", ["stranger", "anonymous"])
    def test_private_drafts_are_not_readable_by_others(self, client, table, who):
        report = start_through_page(client, table)
        if who == "stranger":
            client.force_login(User.objects.create_user("stranger"))
        else:
            client.logout()
        refused = 404 if who == "stranger" else 302
        for url in (editor_url(report), receipt_url(report), start_url(table)):
            assert client.get(url).status_code == refused
            assert client.post(url, {}).status_code == refused

    @pytest.mark.parametrize(
        "route",
        [
            "n26-post-battle-editor",
            "n26-post-battle-receipt",
            "n26-post-battle-correct",
            "n26-gang-post-battle",
        ],
    )
    def test_malformed_route_ids_are_404(self, client, table, route):
        url = reverse(route, args=["bad-id"])
        assert client.post(url).status_code == 404

    def test_nonparticipant_cannot_start_a_battle_report(
        self, client, table, gang_type
    ):
        other = found_gang("Not playing", gang_type, owner=table.owner)
        url = reverse(
            "n26-battle-report", args=[table.campaign.pk, table.battle.pk, other.pk]
        )
        assert client.get(url).status_code == 404
        assert client.post(url).status_code == 404


class TestReportQueryGrowth:
    """More roster models reuse the same equipment and effect fetches."""

    def test_more_models_do_not_add_editor_queries(self, client, table):
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
        assert len(editor_props(client.get(editor_url(report)))["models"]) == 5


def step(client, report, response, intent, **changes):
    stepped = client.post(
        editor_url(report), html_fields(response, intent=intent, **changes)
    )
    assert stepped.status_code == 200, editor_props(stepped)["errors"]
    return stepped


def entered_xp(response):
    return [row["xp"] for row in editor_props(response)["models"]]


def toolbar_text(response, name):
    props = editor_props(response)
    count = sum(model["participated"] for model in props["models"])
    return props["toolbar"][f"{name}{'One' if count == 1 else 'Many'}"].replace(
        "{n}", str(count)
    )


class TestXpSteps:
    """The toolbar steps the entered XP of selected models, never the gang."""

    def test_steps_change_only_selected_participants(self, client, table):
        report = start(client, table)
        first, reserve = table.models
        added = step(
            client,
            report,
            client.get(editor_url(report)),
            "xp-step:+1",
            **{
                f"model-{first.pk}-participated": "on",
                f"model-{first.pk}-xp": "3",
                f"model-{reserve.pk}-xp": "5",
            },
        )
        assert entered_xp(added) == ["4", "5"]
        removed = step(client, report, added, "xp-step:-1")
        assert entered_xp(removed) == ["3", "5"]
        assert xp_value(first) == xp_value(reserve) == 0

    def test_repeated_steps_persist_and_stop_at_zero(self, client, table):
        report = start(client, table)
        ticked = {f"model-{m.pk}-participated": "on" for m in table.models}
        page = client.get(editor_url(report))
        assert not any(model["participated"] for model in editor_props(page)["models"])
        page = step(client, report, page, "xp-step:+1", **ticked)
        assert (
            toolbar_text(page, "plus")
            == "Add 1 XP to each of the 2 models that took part"
        )
        page = step(client, report, page, "xp-step:+1")
        page = step(client, report, page, "xp-step:+1")
        page = step(client, report, page, "xp-step:-1")
        assert entered_xp(page) == ["2", "2"]
        resumed = client.get(editor_url(report))
        assert entered_xp(resumed) == ["2", "2"]
        for _ in range(3):
            resumed = step(client, report, resumed, "xp-step:-1")
        assert entered_xp(resumed) == ["0", "0"]
        assert all(
            model["participated"] and model["xpAvailable"]
            for model in editor_props(resumed)["models"]
        )

    def test_a_stale_version_keeps_the_entries(self, client, table):
        report = start(client, table)
        model = table.models[0]
        page = client.get(editor_url(report))
        step(client, report, page, "check")
        refused = client.post(
            editor_url(report),
            html_fields(
                page,
                intent="xp-step:+1",
                **{f"model-{model.pk}-participated": "on", f"model-{model.pk}-xp": "4"},
            ),
        )
        assert refused.status_code == 409
        assert html_fields(refused)[f"model-{model.pk}-xp"] == ["5"]
        report.refresh_from_db()
        assert report.draft["models"][0]["xp"] == ""

    def test_an_old_draft_undo_record_is_ignored(self, client, table):
        report = start(client, table)
        model = table.models[0]
        report.draft["bulk_undo"] = {str(model.pk): "3"}
        report.save(update_fields=["draft"])
        page = client.get(editor_url(report))
        assert page.status_code == 200
        saved = step(client, report, page, "check")
        assert "bulk_undo" not in editor_props(saved)["payload"]
        report.refresh_from_db()
        assert "bulk_undo" not in report.draft


class TestXpBlockedModels:
    """A model that cannot take XP says why and never blocks the others."""

    @pytest.fixture
    def visitor(self, table, make_profile):
        return hire(table.gang, make_profile("Civilian"), "Visitor")

    def test_steps_skip_a_model_without_an_xp_counter(self, client, table, visitor):
        report = start(client, table)
        first = table.models[0]
        page = step(
            client,
            report,
            client.get(editor_url(report)),
            "xp-step:+1",
            **{
                f"model-{first.pk}-participated": "on",
                f"model-{visitor.pk}-participated": "on",
            },
        )
        by_id = {row["id"]: row["xp"] for row in editor_props(page)["models"]}
        assert by_id[str(first.pk)] == "1"
        assert by_id[str(visitor.pk)] == ""
        assert toolbar_text(page, "count") == "2 models took part"
        shown = model_props(page, visitor)
        assert not shown["xpAvailable"]
        assert (
            shown["xpHelp"]
            == "Visitor has no XP counter, so XP cannot be recorded here."
        )
        applied = client.post(
            editor_url(report),
            html_fields(
                page,
                intent="apply",
                credits="20",
                reason="Scenario reward",
                participation_confirmed="on",
            ),
        )
        assert applied.status_code == 302
        assert xp_value(first) == 1
        assert_books(table)

    def test_a_stray_value_on_a_blocked_model_does_not_block_apply(
        self, client, table, visitor
    ):
        report = start(client, table)
        for model in report.draft["models"]:
            if model["id"] == str(visitor.pk):
                model["xp"] = "1"
        report.save(update_fields=["draft"])
        page = client.get(editor_url(report))
        assert html_fields(page)[f"model-{visitor.pk}-xp"] == [""]
        assert model_props(page, visitor)["xp"] == ""
        assert not any(
            error.startswith("Visitor:") for error in editor_props(page)["errors"]
        )
        assert "Visitor" not in summary_text(page)
        applied = client.post(editor_url(report), awards(page, table))
        assert applied.status_code == 302

    def test_a_correction_after_the_xp_counter_is_removed_applies(self, client, table):
        report = start(client, table)
        model = table.models[0]
        first = client.post(
            editor_url(report), awards(client.get(editor_url(report)), table)
        )
        assert first.status_code == 302, editor_props(first)["errors"]
        counter = Assignment.objects.get(
            miniature_root=model, counter__isnull=False, archived=False
        )
        with operation(table.gang, actor=table.owner) as op:
            op.remove(counter)
        corrected = client.post(reverse("n26-post-battle-correct", args=[report.pk]))
        page = client.get(corrected.url)
        assert not model_props(page, model)["xpAvailable"]
        assert model_props(page, model)["xpHelp"]
        assert html_fields(page)[f"model-{model.pk}-xp"] == ["2"]
        applied = client.post(
            editor_url(report), html_fields(page, intent="apply", credits="30")
        )
        assert applied.status_code == 302, editor_props(applied)["errors"]
        assert applied.url == receipt_url(report, 2)
        counter.refresh_from_db()
        assert counter.archived
        assert CounterValue.objects.get(assignment=counter).value == 2
        assert_books(table)

    def test_a_crafted_award_for_a_blocked_model_is_refused(
        self, client, table, visitor
    ):
        report = start(client, table)
        refused = client.post(
            editor_url(report),
            awards(
                client.get(editor_url(report)),
                table,
                **{f"model-{visitor.pk}-xp": "2"},
            ),
        )
        assert refused.status_code == 409
        assert (
            "Visitor: This model has no XP counter, so XP cannot be recorded here."
            in editor_props(refused)["errors"]
        )
        assert not Assignment.objects.filter(
            miniature=visitor, counter__isnull=False
        ).exists()


class TestRecordResultsEntry:
    """Record results starts the draft on POST and opens the editor straight away."""

    def test_battle_entry_reads_and_refusals_then_start_and_resume(self, client, table):
        response = client.get(start_url(table))
        assert response.status_code == 302
        assert response.url == reverse(
            "n26-battle", args=[table.campaign.pk, table.battle.pk]
        )
        assert not PostBattleReport.objects.exists()
        response = client.post(start_url(table), {})
        assert response.url == reverse(
            "n26-battle", args=[table.campaign.pk, table.battle.pk]
        )
        assert not PostBattleReport.objects.exists()
        battle_page = reverse("n26-battle", args=[table.campaign.pk, table.battle.pk])
        button = record_results_form(client.get(battle_page), start_url(table)).find(
            "button"
        )
        assert button["aria-label"] == f"Record results for {table.gang.name}"
        report = start_through_page(client, table)
        assert report.battle_id == table.battle.pk
        assert report.date == table.battle.date
        assert report.reference == table.battle.title
        response = client.get(start_url(table))
        assert response.status_code == 302
        assert response.url == editor_url(report)
        document = BeautifulSoup(client.get(battle_page).content, "html.parser")
        link = document.find("a", href=start_url(table))
        assert link.get_text(strip=True) == "Continue draft"
        assert link["aria-label"] == f"Continue draft for {table.gang.name}"

    def test_a_second_request_key_still_opens_the_one_battle_report(
        self, client, table
    ):
        url = start_url(table)
        first = client.post(url, {"request_key": str(uuid4())})
        second = client.post(url, {"request_key": str(uuid4())})
        assert first.url == second.url
        assert PostBattleReport.objects.filter(gang=table.gang).count() == 1

    def test_the_post_battle_list_starts_a_campaign_report_by_post(self, client, table):
        url = start_url(table)
        data = record_results_fields(client.get(start_url(table, standalone=True)), url)
        assert data["request_key"]
        response = client.post(url, data)
        report = PostBattleReport.objects.get(gang=table.gang)
        assert response.url == editor_url(report)
        assert report.battle_id == table.battle.pk

    def test_campaign_report_breadcrumb_links_the_battle_and_the_gang(
        self, client, table
    ):
        report = start_through_page(client, table)
        for page in ("editor", "receipt"):
            if page == "receipt":
                assert (
                    client.post(
                        editor_url(report),
                        awards(client.get(editor_url(report)), table),
                    ).status_code
                    == 302
                )
            response = client.get(
                editor_url(report) if page == "editor" else receipt_url(report)
            )
            if page == "editor":
                crumbs = [
                    (item["label"], item.get("href"))
                    for item in editor_props(response)["breadcrumbs"]
                ]
            else:
                document = BeautifulSoup(response.content, "html.parser")
                header = document.find("h1").find_parent("div", class_="gap-1")
                crumbs = [
                    (item.get_text(strip=True), item.get("href"))
                    for item in header.select("nav li a, nav li [aria-current]")
                ]
            assert crumbs == [
                (
                    table.battle.title,
                    reverse("n26-battle", args=[table.campaign.pk, table.battle.pk]),
                ),
                (table.gang.name, reverse("n26-gang", args=[table.gang.pk])),
                (
                    "Post-battle results" if page == "editor" else "Recorded results",
                    None,
                ),
            ]
            assert [label for label, _ in crumbs].count(table.gang.name) == 1

    def test_standalone_breadcrumb_links_the_gang_and_its_reports(self, client, table):
        report = start_through_page(client, table, standalone=True)
        crumbs = [
            (item["label"], item.get("href"))
            for item in editor_props(client.get(editor_url(report)))["breadcrumbs"]
        ]
        assert crumbs == [
            (table.gang.name, reverse("n26-gang", args=[table.gang.pk])),
            ("Post-battle", reverse("n26-gang-post-battle", args=[table.gang.pk])),
            ("Stand-off", None),
        ]
        assert [label for label, _ in crumbs].count(table.gang.name) == 1

    def test_the_editor_delivers_a_saved_draft_and_an_autosave_command(
        self, client, table
    ):
        report = start_through_page(client, table)
        props = editor_props(client.get(editor_url(report)))
        assert props["commandHref"] == reverse(
            "n26-post-battle-command", args=[report.pk]
        )
        assert props["savedAt"]
        assert props["generation"] == str(report.generation)
        assert props["revision"] == report.draft_revision


def refresh(client, report, response, model, *, after=None, navigate=True, **changes):
    """Submit a cached section intent and follow its full-editor redirect."""
    fields = html_fields(response, intent=f"refresh-model:{model.pk}", **changes)
    if after is not None:
        version = html_fields(after)
        for name in ("generation", "revision", "submission_key", "review"):
            fields[name] = version[name]
    result = client.post(editor_url(report), fields, HTTP_HX_REQUEST="true")
    if navigate and result.status_code == 204:
        assert urlsplit(result["HX-Redirect"]).path == editor_url(report)
        return client.get(result["HX-Redirect"])
    return result


@pytest.mark.parametrize("table", [1], indirect=True)
class TestModelModule:
    """Model display contracts retain table labels and dynamic result controls."""

    def test_a_vehicle_table_is_named_by_its_own_label(
        self, client, table, make_profile, vehicle_type
    ):
        kind = create_slot_type("Lasting Damage", is_lasting_effect=True)
        result = create_pickable("Superficial Damage", kind)
        damage = create_picklist("Lasting Damage Table", kind, members=[result])
        slot = create_slot("Lasting Damage", kind, damage, min_picks=0, max_picks=100)
        profile = make_profile("Test vehicle", profile_type=vehicle_type)
        add_built_in(profile, table.xp)
        add_built_in(profile, slot)
        vehicle = hire(table.gang, profile, "Vehicle")
        report = start(client, table)
        added = client.post(
            editor_url(report),
            html_fields(
                client.get(editor_url(report)), intent=f"add-effect:{vehicle.pk}"
            ),
        )
        shown = model_props(added, vehicle)
        assert shown["addEffectLabel"] == "Add Lasting Damage"
        assert shown["effects"][0]["label"] == "Lasting Damage 1"
        assert shown["effectGroups"][0]["label"] == "Lasting Damage"
        assert (
            model_props(added, table.models[0])["addEffectLabel"]
            == "Add Lasting injury"
        )
        assert "lasting effect" not in json.dumps(shown).lower()

    def test_a_plural_card_heading_still_names_one_result(
        self, client, table, make_profile
    ):
        profile = make_profile("Test fighter")
        add_built_in(
            profile,
            create_slot(
                "Test slot",
                table.injury_kind,
                table.injury_table,
                label="Lasting injuries",
                min_picks=0,
                max_picks=9,
            ),
        )
        model = hire(table.gang, profile, "Third model")
        report = start(client, table)
        added = client.post(
            editor_url(report),
            html_fields(
                client.get(editor_url(report)), intent=f"add-effect:{model.pk}"
            ),
        )
        shown = model_props(added, model)
        assert [group["label"] for group in shown["effectGroups"]] == ["Lasting injury"]
        assert shown["addEffectLabel"] == "Add Lasting injury"

    def test_options_lead_with_their_roll_band(self, client, table):
        kind = create_slot_type("Test table (dice)", is_lasting_effect=True)
        banded = create_picklist(
            "Test table (dice)", kind, dice="d66", roll_selects="band"
        )
        out_cold = create_pickable("Out Cold", kind)
        add_picklist_member(banded, out_cold, roll_low=11, roll_high=16)
        profile = table.models[0].membership.profile
        add_built_in(
            profile,
            create_slot("Test table (dice)", kind, banded, min_picks=0, max_picks=9),
        )
        model = hire(table.gang, profile, "Third model")
        report = start(client, table)
        added = client.post(
            editor_url(report),
            html_fields(
                client.get(editor_url(report)), intent=f"add-effect:{model.pk}"
            ),
        )
        shown = model_props(added, model)
        groups = {
            group["label"]: [option["label"] for option in group["options"]]
            for group in shown["effectGroups"]
        }
        assert groups["Test table (dice)"] == ["11–16 Out Cold"]
        assert groups["Lasting injury"] == ["Grievous Wound"]
        assert any(
            value.endswith(f"|{out_cold.pk}") for value, _ in effect_options(shown)
        )

    def test_refresh_redirects_to_the_complete_editor_with_the_saved_version(
        self, client, table
    ):
        report = start(client, table)
        model = table.models[0]
        response = refresh(
            client,
            report,
            client.get(editor_url(report)),
            model,
            navigate=False,
            **{f"model-{model.pk}-status": "dead"},
        )
        assert response.status_code == 204
        assert response["HX-Redirect"] == editor_url(report)
        report.refresh_from_db()
        shown = client.get(response["HX-Redirect"])
        assert model_props(shown, model)["equipmentApplies"]
        assert editor_props(shown)["revision"] == report.draft_revision
        assert report.draft["models"][0]["status"] == "dead"

    def test_a_stale_refresh_is_refused_and_keeps_the_saved_draft(self, client, table):
        report = start(client, table)
        model = table.models[0]
        page = client.get(editor_url(report))
        assert refresh(client, report, page, model).status_code == 200
        report.refresh_from_db()
        saved = report.draft
        stale = refresh(
            client, report, page, model, **{f"model-{model.pk}-status": "dead"}
        )
        assert stale.status_code == 409
        assert stale["Content-Type"].startswith("text/plain")
        report.refresh_from_db()
        assert report.draft == saved

    def test_refresh_without_htmx_draws_the_whole_page(self, client, table):
        report = start(client, table)
        model = table.models[0]
        response = client.post(
            editor_url(report),
            html_fields(
                client.get(editor_url(report)), intent=f"refresh-model:{model.pk}"
            ),
        )
        assert response.status_code == 200
        assert editor_props(response)["reportId"] == str(report.pk)

    def test_status_badges_use_the_prepared_status_and_colour(self, client, table):
        model = table.models[0]
        report = start(client, table)
        for status, label, colour in [
            (Status.ACTIVE, "Active", "ink"),
            (Status.RECOVERY, "In Recovery", "amber"),
            (Status.CAPTURED, "Captured", "red"),
            (Status.DEAD, "Dead", "red"),
        ]:
            model.status = status
            model.save(update_fields=["status"])
            shown = model_props(client.get(editor_url(report)), model)
            assert shown["statusLabel"] == label
            assert shown["statusColour"] == colour

    def test_equipment_choice_shows_only_for_a_dead_model(self, client, table):
        report = start(client, table)
        model = table.models[0]
        page = client.get(editor_url(report))
        assert not model_props(page, model)["equipmentApplies"]
        assert html_fields(page)[f"model-{model.pk}-equipment"] == ["keep"]
        dead = refresh(
            client,
            report,
            page,
            model,
            **{
                f"model-{model.pk}-status": "dead",
                f"model-{model.pk}-equipment": "lost",
            },
        )
        shown = model_props(dead, model)
        assert shown["equipmentApplies"]
        assert shown["equipment"] == "lost"
        assert shown["equipmentLabel"] == "What happens to Cinder's equipment"
        alive_again = refresh(
            client,
            report,
            page,
            model,
            after=dead,
            **{f"model-{model.pk}-status": "", f"model-{model.pk}-equipment": "lost"},
        )
        assert alive_again.status_code == 200
        assert not model_props(alive_again, model)["equipmentApplies"]
        assert html_fields(alive_again)[f"model-{model.pk}-equipment"] == ["lost"]
        assert "Cinder" not in summary_text(alive_again)


class TestModuleRefreshEdges:
    """Cached section requests navigate to the complete editor and retain errors."""

    def test_a_report_applied_elsewhere_sends_htmx_to_the_receipt(self, client, table):
        report = start(client, table)
        model = table.models[0]
        page = client.get(editor_url(report))
        applied = client.post(editor_url(report), awards(page, table))
        assert applied.status_code == 302
        response = refresh(client, report, page, model, navigate=False)
        assert response.status_code == 204
        assert response["HX-Redirect"] == receipt_url(report)

    def test_a_model_gone_from_the_roster_reloads_the_editor(self, client, table):
        report = start(client, table)
        model = table.models[0]
        page = client.get(editor_url(report))
        model.membership.archived = True
        model.membership.save(update_fields=["archived"])
        response = refresh(client, report, page, model, navigate=False)
        assert response.status_code == 204
        assert response["HX-Redirect"] == editor_url(report)

    def test_shown_errors_follow_the_entries(self, client, table):
        report = start(client, table)
        model = table.models[0]
        checked = client.post(
            editor_url(report),
            html_fields(
                client.get(editor_url(report)),
                intent="check",
                **{f"model-{model.pk}-xp": "-1"},
            ),
        )
        assert any(
            "Cinder's XP" in error for error in model_props(checked, model)["errors"]
        )
        still_wrong = refresh(client, report, checked, model, showing_errors="1")
        assert any(
            "Cinder's XP" in error
            for error in model_props(still_wrong, model)["errors"]
        )
        assert any(
            "Cinder's XP" in error for error in editor_props(still_wrong)["errors"]
        )
        fixed = refresh(
            client,
            report,
            checked,
            model,
            after=still_wrong,
            showing_errors="1",
            **{f"model-{model.pk}-xp": "1"},
        )
        assert not any(
            "Cinder's XP" in error for error in model_props(fixed, model)["errors"]
        )
        assert not any(
            "Cinder's XP" in error for error in editor_props(fixed)["errors"]
        )

    def test_without_shown_errors_a_refresh_sends_none(self, client, table):
        report = start(client, table)
        model = table.models[0]
        response = refresh(
            client,
            report,
            client.get(editor_url(report)),
            model,
            **{f"model-{model.pk}-xp": "-1"},
        )
        assert not editor_props(response)["showErrors"]
        assert not editor_props(response)["errors"]
        assert any(
            "Cinder's XP" in error for error in model_props(response, model)["errors"]
        )


def summary_text(response):
    preview = editor_props(response)["preview"]
    parts = [part for row in preview["rows"] for part in (row["label"], row["value"])]
    parts.extend(
        part
        for model in preview["models"]
        for part in (model["name"], *model["lines"], model["error"])
    )
    return " ".join(" ".join(parts).split())


class TestWhatTheSummaryAndReceiptList:
    """Only what a report records: no empty slots, no unchanged totals."""

    def test_the_summary_lists_only_models_with_changes(self, client, table):
        report = start(client, table)
        cinder, ember = table.models
        added = client.post(
            editor_url(report),
            html_fields(
                client.get(editor_url(report)), intent=f"add-effect:{ember.pk}"
            ),
        )
        checked = client.post(
            editor_url(report),
            html_fields(added, intent="check", **{f"model-{cinder.pk}-xp": "1"}),
        )

        text = summary_text(checked)
        assert "Cinder +1 XP (0 → 1)" in text
        assert "Ember" not in text
        assert "XP adjustment" not in text
        assert "Final status" not in text

    def test_a_model_ending_in_recovery_says_how_long(self, client, table):
        report = start(client, table)
        assert "campaign cycle" not in client.get(editor_url(report)).content.decode()

        checked, _ = with_effect(client, table, report, table.wound)

        text = summary_text(checked)
        assert "Final status: In Recovery" in text
        assert "Stays In Recovery until the end of the campaign cycle." in text
        data = awards(checked, table)
        data.pop(f"model-{table.models[1].pk}-participated", None)
        applied = client.post(editor_url(report), data)
        assert applied.status_code == 302

        receipt = BeautifulSoup(client.get(applied.url).content, "html.parser")
        models = receipt.select("main li h3")
        assert [h.get_text(strip=True) for h in models] == ["Cinder"]
        text = " ".join(models[0].find_parent("li").get_text(" ").split())
        assert text.index("+2 XP") < text.index("Grievous Wound")
        assert text.index("Grievous Wound") < text.index("Status:")
        assert "XP adjustment" not in text

    def test_a_receipt_leaves_out_an_unchanged_status(self, client, table):
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
        assert "+2 XP (0 → 2)" in summary_text(response)
        applied = client.post(editor_url(report), awards(response, table))

        text = client.get(applied.url).content.decode()
        assert "Status:" not in text
        assert "+2 XP" in text

    def test_a_model_that_cannot_take_xp_shows_no_xp_figures(
        self, client, table, make_profile
    ):
        visitor = hire(table.gang, make_profile("Civilian"), "Visitor")
        report = start(client, table)
        shown = model_props(client.get(editor_url(report)), visitor)
        assert not shown["xpAvailable"]
        assert shown["xpHelp"]
        assert shown["xp"] == ""

    def test_check_names_a_result_that_disagrees_with_the_status(self, client, table):
        death = create_pickable(
            "Memorable Death",
            table.injury_kind,
            effects=[(targets_model(), op_sets_status(Status.DEAD))],
        )
        add_picklist_member(table.injury_table, death)
        with operation(table.gang, actor=table.owner) as op:
            op.set_status(table.models[0], Status.RECOVERY)
        report = start(client, table)

        checked, _ = with_effect(client, table, report, death)

        assert (
            "Cinder: Memorable Death makes Cinder Dead, but Cinder's final status "
            "is In Recovery. Choose the final status."
        ) in editor_props(checked)["errors"]


class TestConflictingStatuses:
    """Results that set different statuses ask for a choice at once."""

    def test_the_module_and_summary_show_the_conflict_as_it_arises(self, client, table):
        death = create_pickable(
            "Memorable Death",
            table.injury_kind,
            effects=[(targets_model(), op_sets_status(Status.DEAD))],
        )
        add_picklist_member(table.injury_table, death)
        report = start(client, table)
        cinder = table.models[0]
        page = client.get(editor_url(report))
        for _ in range(2):
            page = client.post(
                editor_url(report), html_fields(page, intent=f"add-effect:{cinder.pk}")
            )
        shown = model_props(page, cinder)
        first, second = (effect["id"] for effect in shown["effects"])
        options = {value.split("|")[1]: value for value, _ in effect_options(shown)}
        redrawn = refresh(
            client,
            report,
            page,
            cinder,
            **{
                f"effect-{first}-pick": options[str(table.wound.pk)],
                f"effect-{second}-pick": options[str(death.pk)],
            },
        )
        message = "Grievous Wound makes Cinder In Recovery and Memorable Death makes Cinder Dead. Choose the final status."
        assert model_props(redrawn, cinder)["statusConflict"] == message
        assert not model_props(redrawn, cinder)["statusChanges"]
        assert message in summary_text(redrawn)
        assert "Final status" not in summary_text(redrawn)


def mission(response):
    return editor_props(response)["mission"]


def mission_step(client, report, response, intent, **changes):
    """A cached mission intent navigates to the complete saved editor."""
    updated = client.post(
        editor_url(report),
        html_fields(response, intent=intent, **changes),
        HTTP_HX_REQUEST="true",
    )
    assert updated.status_code == 204
    assert urlsplit(updated["HX-Redirect"]).path == editor_url(report)
    if intent == "check":
        assert parse_qs(urlsplit(updated["HX-Redirect"]).query) == {
            "show_errors": ["1"]
        }
    return client.get(updated["HX-Redirect"])


def credit_line_ids(response):
    return [line["id"] for line in mission(response)["creditLines"]]


@pytest.fixture
def reputation(table):
    counter = assign(create_counter("Reputation"), gang=table.gang, actor=table.owner)
    tally(counter, 5)
    return counter


class TestMissionResults:
    """Mission display data preserves credit lines and the gang's counter changes."""

    def test_the_section_starts_with_one_line_and_adds_and_removes_lines(
        self, client, table
    ):
        report = start(client, table)
        page = client.get(editor_url(report))
        assert mission(page)["canAddLine"]
        (first,) = credit_line_ids(page)
        assert mission(page)["creditLines"][0]["amount"] == ""
        assert mission(page)["creditLines"][0]["reason"] == ""
        added = mission_step(client, report, page, "add-credit-line")
        assert added.status_code == 200
        ids = credit_line_ids(added)
        assert len(ids) == 2 and ids[0] == first
        report.refresh_from_db()
        assert [line["id"] for line in report.draft["credit_lines"]] == ids
        page = client.get(editor_url(report))
        removed = mission_step(client, report, page, f"remove-credit-line:{first}")
        assert removed.status_code == 200
        assert credit_line_ids(removed) == [ids[1]]

    def test_total_and_two_lines_reach_the_ledger_and_receipt(self, client, table):
        report = start(client, table)
        page = client.post(
            editor_url(report),
            html_fields(client.get(editor_url(report)), intent="add-credit-line"),
        )
        first, second = credit_line_ids(page)
        fields = awards(
            page,
            table,
            intent="check",
            **{
                f"credit-{first}-amount": "40",
                f"credit-{first}-reason": "Scenario reward",
                f"credit-{second}-amount": "15",
                f"credit-{second}-reason": "Bounty",
            },
        )
        checked = client.post(editor_url(report), fields)
        assert mission(checked)["totalText"] == "+55¢"
        applied = client.post(editor_url(report), html_fields(checked, intent="apply"))
        assert applied.status_code == 302
        assert list(
            LedgerEvent.objects.filter(
                gang=table.gang, kind=LedgerEvent.Kind.INCOME
            ).values_list("credits_delta", flat=True)
        ) == [-40, -15]
        receipt = client.get(receipt_url(report)).content.decode()
        assert "Scenario reward" in receipt and "Bounty" in receipt
        assert_books(table)

    def test_gang_counter_input_shows_before_and_after(self, client, table, reputation):
        report = start(client, table)
        page = client.get(editor_url(report))
        key = str(reputation.pk)
        (counter,) = mission(page)["counters"]
        assert counter["name"] == "Reputation"
        assert counter["prefix"] == f"gang-counter-{key}"
        assert counter["editable"]
        stepped = mission_step(
            client, report, page, "check", **{f"gang-counter-{key}": "1"}
        )
        (counter,) = mission(stepped)["counters"]
        assert (counter["before"], counter["entered"], counter["after"]) == (5, "1", 6)
        assert not mission(stepped)["counterEffects"]
        report.refresh_from_db()
        assert report.draft["gang_counters"] == {key: "1"}

    def test_applied_counter_change_is_on_the_receipt(self, client, table, reputation):
        report = start(client, table)
        page = client.get(editor_url(report))
        fields = awards(page, table, **{f"gang-counter-{reputation.pk}": "2"})
        checked = client.post(editor_url(report), fields | {"intent": "check"})
        applied = client.post(editor_url(report), html_fields(checked, intent="apply"))
        assert applied.status_code == 302
        assert CounterValue.objects.get(assignment=reputation).value == 7
        receipt = BeautifulSoup(
            client.get(receipt_url(report)).content, "html.parser"
        ).get_text(" ", strip=True)
        assert "Reputation 5 → 7" in " ".join(receipt.split())

    def test_a_correction_applies_after_a_changed_counter_is_removed(
        self, client, table, reputation
    ):
        report = start(client, table)
        page = client.get(editor_url(report))
        fields = awards(page, table, **{f"gang-counter-{reputation.pk}": "2"})
        checked = client.post(editor_url(report), fields | {"intent": "check"})
        assert (
            client.post(
                editor_url(report), html_fields(checked, intent="apply")
            ).status_code
            == 302
        )
        remove(reputation, actor=table.owner)
        corrected = client.post(reverse("n26-post-battle-correct", args=[report.pk]))
        assert corrected.status_code == 302
        page = client.get(editor_url(report))
        assert not any(counter["editable"] for counter in mission(page)["counters"])
        checked = client.post(
            editor_url(report), html_fields(page, intent="check", credits="25")
        )
        assert not editor_props(checked)["errors"], editor_props(checked)["errors"]
        applied = client.post(editor_url(report), html_fields(checked, intent="apply"))
        assert applied.status_code == 302
        revision = report.revisions.get(sequence=2)
        assert revision.inputs["gang_counters"] == {str(reputation.pk): 2}
        assert_books(table)

    def test_an_old_receipt_still_shows_its_reason(self, client, table):
        report = start(client, table)
        page = client.get(editor_url(report))
        applied = client.post(editor_url(report), awards(page, table))
        assert applied.status_code == 302
        revision = report.revisions.get()
        receipt = dict(revision.receipt)
        for key in ("credit_lines", "credits_total", "gang_counters"):
            receipt.pop(key)
        receipt["reason"] = "Old single reason"
        PostBattleRevision.objects.filter(pk=revision.pk).update(receipt=receipt)
        text = client.get(receipt_url(report)).content.decode()
        assert "Old single reason" in text
        assert "Mission results" in text


class TestMissionResultsAddUp:
    """Counter previews combine starting values, entered changes and result effects;
    credits display the report total.
    """

    def apply_first(self, client, table, report, **changes):
        page = client.get(editor_url(report))
        checked = client.post(
            editor_url(report), awards(page, table, intent="check", **changes)
        )
        applied = client.post(editor_url(report), html_fields(checked, intent="apply"))
        assert applied.status_code == 302
        corrected = client.post(reverse("n26-post-battle-correct", args=[report.pk]))
        assert corrected.status_code == 302
        return client.get(editor_url(report))

    def test_a_correction_shows_the_counter_before_this_report(
        self, client, table, reputation
    ):
        report = start(client, table)
        page = self.apply_first(
            client, table, report, **{f"gang-counter-{reputation.pk}": "2"}
        )
        (counter,) = mission(page)["counters"]
        assert (counter["before"], counter["entered"], counter["after"]) == (5, "2", 7)

    def test_a_negative_amount_is_refused_by_its_field(self, client, table):
        report = start(client, table)
        page = client.get(editor_url(report))
        (line,) = credit_line_ids(page)
        checked = client.post(
            editor_url(report),
            html_fields(
                page,
                intent="check",
                **{f"credit-{line}-amount": "-40", f"credit-{line}-reason": "Fine"},
            ),
        )
        (shown,) = mission(checked)["creditLines"]
        assert shown["amount"] == "-40"
        assert any(
            "Enter a whole number from 0 to 1,000,000" in error
            for error in shown["amountErrors"]
        )
        assert mission(checked)["totalText"] == "+0¢"

    def test_a_corrected_receipt_shows_the_total_and_the_change(self, client, table):
        report = start(client, table)
        page = self.apply_first(client, table, report)
        (line,) = credit_line_ids(page)
        checked = client.post(
            editor_url(report),
            html_fields(page, intent="check", **{f"credit-{line}-amount": "5"}),
        )
        summary = summary_text(checked)
        assert "Credits from this battle +5¢" in summary
        assert "Change from the last version −15¢" in summary
        applied = client.post(editor_url(report), html_fields(checked, intent="apply"))
        assert applied.status_code == 302

        second = " ".join(
            BeautifulSoup(client.get(receipt_url(report, 2)).content, "html.parser")
            .find("main")
            .get_text(" ", strip=True)
            .split()
        )
        assert "Credits from this battle +5¢" in second
        assert "Change from the last version −15¢" in second
        first = client.get(receipt_url(report, 1)).content.decode()
        assert "+20¢" in first
        assert "Change from the last version" not in first
        assert "Credits adjustment" not in first


@pytest.fixture
def kills(table):
    counter = assign(create_counter("Kill Count"), miniature=table.models[0])
    tally(counter, 2)
    return counter


def counter_step(client, report, response, model, intent, **changes):
    """A cached counter intent saves and navigates to the complete editor."""
    updated = client.post(
        editor_url(report),
        html_fields(response, intent=intent, **changes),
        HTTP_HX_REQUEST="true",
    )
    assert updated.status_code == 204
    assert urlsplit(updated["HX-Redirect"]).path == editor_url(report)
    if intent == "check":
        assert parse_qs(urlsplit(updated["HX-Redirect"]).query) == {
            "show_errors": ["1"]
        }
    return client.get(updated["HX-Redirect"])


class TestModelCounters:
    """A model's counters sit under its XP and step in place."""

    def test_a_step_saves_and_redraws_the_counter_with_its_limits(
        self, client, table, kills
    ):
        report = start(client, table)
        page = client.get(editor_url(report))
        cinder, ember = table.models
        key = str(kills.pk)
        (counter,) = model_props(page, cinder)["counters"]
        assert counter["name"] == "Kill Count"
        assert counter["prefix"] == f"model-{cinder.pk}-counter-{key}"
        assert counter["limit"] == 1000
        assert counter["minusLabel"] and counter["plusLabel"]
        assert not model_props(page, ember)["counters"]
        stepped = counter_step(
            client, report, page, cinder, f"model-counter-step:{cinder.pk}:{key}:+1"
        )
        (counter,) = model_props(stepped, cinder)["counters"]
        assert (counter["before"], counter["entered"], counter["after"]) == (2, "1", 3)
        report.refresh_from_db()
        assert report.draft["models"][0]["counters"] == {key: "1"}

    def test_applied_counter_is_on_the_receipt(self, client, table, kills):
        report = start(client, table)
        cinder = table.models[0]
        fields = awards(
            client.get(editor_url(report)),
            table,
            **{f"model-{cinder.pk}-counter-{kills.pk}": "1"},
        )
        checked = client.post(editor_url(report), fields | {"intent": "check"})
        summary = summary_text(checked)
        assert "+1 Kill Count (2 → 3)" in summary
        applied = client.post(editor_url(report), html_fields(checked, intent="apply"))
        assert applied.status_code == 302
        assert CounterValue.objects.get(assignment=kills).value == 3
        receipt = " ".join(
            BeautifulSoup(client.get(receipt_url(report)).content, "html.parser")
            .get_text(" ", strip=True)
            .split()
        )
        assert "Kill Count: 2 → 3 (+1 entered)" in receipt
        assert_books(table)

    def test_a_correction_shows_where_the_counter_started(self, client, table, kills):
        bloodied = create_pickable(
            "Bloodied",
            table.injury_kind,
            effects=[
                (
                    targets_model(),
                    op_changes_counter(kills.counter, mode="add", amount=1),
                )
            ],
        )
        add_picklist_member(table.injury_table, bloodied)
        report = start(client, table)
        cinder = table.models[0]
        field = f"model-{cinder.pk}-counter-{kills.pk}"
        checked, _ = with_effect(client, table, report, bloodied)
        applied = client.post(
            editor_url(report), awards(checked, table, intent="apply", **{field: "1"})
        )
        assert applied.status_code == 302
        assert CounterValue.objects.get(assignment=kills).value == 4
        client.post(reverse("n26-post-battle-correct", args=[report.pk]))

        page = client.get(editor_url(report))

        (counter,) = model_props(page, cinder)["counters"]
        assert (
            counter["before"],
            counter["entered"],
            counter["fromResults"],
            counter["after"],
        ) == (2, "1", 1, 4)
        assert model_props(page, cinder)["counterEffects"]

    def test_a_correction_applies_after_a_changed_counter_is_removed(
        self, client, table, kills
    ):
        report = start(client, table)
        cinder = table.models[0]
        fields = awards(
            client.get(editor_url(report)),
            table,
            **{f"model-{cinder.pk}-counter-{kills.pk}": "1"},
        )
        checked = client.post(editor_url(report), fields | {"intent": "check"})
        assert (
            client.post(
                editor_url(report), html_fields(checked, intent="apply")
            ).status_code
            == 302
        )
        remove(kills, actor=table.owner)
        corrected = client.post(reverse("n26-post-battle-correct", args=[report.pk]))
        assert corrected.status_code == 302
        page = client.get(editor_url(report))
        assert not any(
            counter["editable"] for counter in model_props(page, cinder)["counters"]
        )
        checked = client.post(
            editor_url(report),
            html_fields(page, intent="check", **{f"model-{cinder.pk}-xp": "3"}),
        )
        assert not editor_props(checked)["errors"], editor_props(checked)["errors"]
        applied = client.post(editor_url(report), html_fields(checked, intent="apply"))
        assert applied.status_code == 302
        revision = report.revisions.get(sequence=2)
        assert revision.inputs["models"][0]["counters"] == {str(kills.pk): 1}
        assert_books(table)


class TestModelNotes:
    """An optional note goes into the model's notes once."""

    def test_the_note_is_added_to_the_model_notes_and_the_receipt(self, client, table):
        report = start(client, table)
        cinder = table.models[0]
        page = client.get(editor_url(report))
        assert (
            model_props(page, cinder)["noteLabel"] == "Add to Cinder's notes (optional)"
        )
        fields = awards(page, table, **{f"model-{cinder.pk}-note": "Held the bridge."})
        checked = client.post(editor_url(report), fields | {"intent": "check"})
        assert "Adds a note to Cinder's notes." in summary_text(checked)
        applied = client.post(editor_url(report), html_fields(checked, intent="apply"))
        assert applied.status_code == 302
        cinder.refresh_from_db()
        assert cinder.notes.count("Held the bridge.") == 1
        assert "Stand-off, 20 September 2026" in cinder.notes
        receipt = client.get(receipt_url(report)).content.decode()
        assert "Held the bridge." in receipt

    def test_a_changed_note_in_a_correction_says_the_earlier_one_stays(
        self, client, table
    ):
        report = start(client, table)
        cinder = table.models[0]
        note = f"model-{cinder.pk}-note"
        fields = awards(client.get(editor_url(report)), table, **{note: "First."})
        checked = client.post(editor_url(report), fields | {"intent": "check"})
        client.post(editor_url(report), html_fields(checked, intent="apply"))
        client.post(reverse("n26-post-battle-correct", args=[report.pk]))
        page = client.get(editor_url(report))
        assert model_props(page, cinder)["note"] == "First."
        help_text = model_props(page, cinder)["noteHelp"]
        assert help_text == "The earlier note stays in Cinder's notes. Edit it there."
        checked = client.post(
            editor_url(report), html_fields(page, intent="check", **{note: "Second."})
        )
        help_text = model_props(checked, cinder)["noteHelp"]
        assert help_text == "The earlier note stays in Cinder's notes. Edit it there."
        client.post(editor_url(report), html_fields(checked, intent="apply"))
        cinder.refresh_from_db()
        assert cinder.notes.count("First.") == 1
        assert cinder.notes.count("Second.") == 1


class TestModelResultEdges:
    """Posted values the page would not send, and line breaks in notes."""

    def test_a_note_at_the_limit_with_line_breaks_is_accepted(self, client, table):
        report = start(client, table)
        cinder = table.models[0]
        # 1,995 characters as the browser counts them, 2,001 once each line
        # break is posted as two.
        text = "\r\n".join(["x" * 285, *["x" * 284] * 6])
        assert len(text.replace("\r\n", "\n")) == 1995
        assert len(text) == 2001
        fields = awards(
            client.get(editor_url(report)),
            table,
            intent="check",
            **{f"model-{cinder.pk}-note": text},
        )
        checked = client.post(editor_url(report), fields)
        assert not editor_props(checked)["errors"], editor_props(checked)["errors"]
        assert editor_props(checked)["models"][0]["note"] == text.replace("\r\n", "\n")

    def test_a_change_to_a_counter_the_model_does_not_hold_is_refused(
        self, client, table, kills
    ):
        glitch = create_counter("Glitch Count")
        ember_counter = assign(create_counter("Grudges"), miniature=table.models[1])
        report = start(client, table)
        cinder = table.models[0]
        prefix = f"model-{cinder.pk}"
        for key in ("", str(glitch.pk), str(ember_counter.pk)):
            fields = awards(client.get(editor_url(report)), table, intent="check")
            fields[f"{prefix}-counter"] = [str(kills.pk), key]
            fields[f"{prefix}-counter-{key}"] = "1"
            checked = client.post(editor_url(report), fields)
            errors = editor_props(checked)["errors"]
            assert any("You cannot correct the change to" in error for error in errors)
        assert not report.revisions.exists()


class TestLivePreview:
    """Live previews match saved drafts without applying gameplay changes."""

    def test_autosave_previews_counters_without_applying_them(
        self, client, table, reputation, kills
    ):
        report = start(client, table)
        page = client.get(editor_url(report))
        data = html_fields(
            page,
            intent="autosave",
            **{
                f"gang-counter-{reputation.pk}": "3",
                f"model-{table.models[0].pk}-counter-{kills.pk}": "1",
            },
        )
        before = LedgerEvent.objects.count()
        response = client.post(editor_url(report), data)
        assert response.status_code == 200
        result = response.json()
        assert {
            "id": f"gang-counter:{reputation.pk}",
            "label": "+3 Reputation",
            "value": "5 → 8",
        } in result["preview"]["rows"]
        assert any(
            "+1 Kill Count (2 → 3)" in line
            for model in result["preview"]["models"]
            for line in model["lines"]
        )
        assert result["review"]
        assert CounterValue.objects.get(assignment=reputation).value == 5
        assert CounterValue.objects.get(assignment=kills).value == 2
        assert LedgerEvent.objects.count() == before
        data.update(revision=result["revision"], generation=result["generation"])
        again = client.post(editor_url(report), data).json()
        assert again["preview"] == result["preview"]
        assert LedgerEvent.objects.count() == before

    def test_autosave_corrects_removed_xp_before_saving_and_returns_matching_fields(
        self, client, table
    ):

        report = start(client, table)
        page = client.get(editor_url(report))
        data = awards(page, table, intent="autosave")
        model = table.models[0]
        xp = Assignment.objects.get(
            miniature_root=model, counter__isnull=False, archived=False
        )
        with operation(table.gang, actor=table.owner) as op:
            op.remove(xp)
        saved = client.post(editor_url(report), data)
        assert saved.status_code == 200
        result = saved.json()
        field = f"model-{model.pk}-xp"
        assert result["corrections"] == {field: ""}
        report.refresh_from_db()
        assert (
            next(m for m in report.draft["models"] if m["id"] == str(model.pk))["xp"]
            == ""
        )
        assert result["review"] == preview_report(report, actor=table.owner).review
        data.update(result["corrections"])
        data.update(
            intent="apply",
            revision=result["revision"],
            generation=result["generation"],
            review=result["review"],
        )
        applied = client.post(editor_url(report), data)
        assert applied.status_code == 302
        xp.refresh_from_db()
        assert xp.archived
        assert CounterValue.objects.get(assignment=xp).value == 0

    def test_mark_all_attended_keeps_xp_and_confirmation_independent(
        self, client, table
    ):
        report = start(client, table)
        page = client.get(editor_url(report))
        marked = client.post(editor_url(report), html_fields(page, intent="attend-all"))
        assert marked.status_code == 200
        report.refresh_from_db()
        assert all(model["participated"] for model in report.draft["models"])
        assert not report.draft["participation_confirmed"]
        assert all(not model["xp"] for model in report.draft["models"])
        data = html_fields(marked, intent="autosave")
        data.pop(f"model-{table.models[1].pk}-participated")
        assert client.post(editor_url(report), data).status_code == 200
        report.refresh_from_db()
        assert [model["participated"] for model in report.draft["models"]] == [
            True,
            False,
        ]

    def test_model_profile_caption_and_standalone_preview(self, client, table):
        report = start(client, table, standalone=True)
        page = client.get(editor_url(report))
        assert all(
            row["profileName"] == "Ganger" for row in editor_props(page)["models"]
        )
        assert model_props(page, table.models[0])["profileName"] == "Ganger"
        result = client.post(
            editor_url(report), html_fields(page, intent="autosave")
        ).json()
        assert "territory" not in result["preview"]
        assert editor_props(page)["territory"] is None

    @pytest.mark.parametrize("result", ["winners", "not_recorded"])
    def test_recorded_territory_is_attributed_and_never_replayed(
        self, client, table, result
    ):
        from n26.library.models import AssetType

        other = open_founding(
            found_gang(
                "Rust Kings", table.gang.gang_type, owner=table.owner, budget=1000
            )
        )
        join_campaign(other, table.campaign)
        with campaign_operation(table.campaign, actor=table.arbitrator) as act:
            kind = act.add_asset_type(
                "Territory", AssetType.Ownership.HOLDING, "Territories"
            )
            token = act.add_asset(act.create_asset(kind, "Sump Gate"))
            act.assign(token, table.gang.campaign_memberships.get(left__isnull=True))
            act.edit_battle(
                table.battle,
                scenario="Stand-off",
                date=table.battle.date,
                gangs=[table.gang, other],
                result=result,
                winners=[other] if result == "winners" else [],
                revision=table.battle.revision,
                stake=token,
                stake_awarded_to=other,
            )
        table.battle.refresh_from_db()
        report = start(client, table)
        before = LedgerEvent.objects.count()
        page = client.get(editor_url(report))
        data = html_fields(page, intent="autosave")
        result = client.post(editor_url(report), data).json()
        assert "territory" not in result["preview"]
        territory = editor_props(page)["territory"]
        assert "Sump Gate" in territory["name"]
        assert territory["outcome"] == "Moved from Ashen Choir to Rust Kings."
        assert territory["applied"]
        assert territory["note"] == "Already applied."
        assert "Sump Gate" not in summary_text(page)
        assert "territory" not in editor_props(page)["preview"]
        assert LedgerEvent.objects.count() == before
        applied = client.post(
            editor_url(report), awards(client.get(editor_url(report)), table)
        )
        assert applied.status_code == 302
        token.refresh_from_db()
        assert token.holder.gang_id == other.pk
        with campaign_operation(table.campaign, actor=table.arbitrator) as act:
            act.unassign(token)
            act.assign(token, table.gang.campaign_memberships.get(left__isnull=True))
        client.post(reverse("n26-post-battle-correct", args=[report.pk]))
        page = client.get(editor_url(report))
        # Corrections retain the historical winner separately from today's holder.
        assert (
            editor_props(page)["territory"]["outcome"]
            == "Moved from Ashen Choir to Rust Kings."
        )
        assert "Ashen Choir" in editor_props(page)["territory"]["currentHolder"]

    def test_autosave_query_count_does_not_grow_with_roster(self, client, table):
        report = start(client, table)

        def count():
            page = client.get(editor_url(report))
            with CaptureQueriesContext(connection) as queries:
                response = client.post(
                    editor_url(report), html_fields(page, intent="autosave")
                )
                assert response.status_code == 200
            return len(queries)

        small = count()
        for name in ("Ash", "Flare", "Coal"):
            hire(table.gang, table.models[0].membership.profile, name)
        assert count() <= small

    def test_unrecorded_stake_does_not_claim_a_transfer(self, client, table):
        from n26.library.models import AssetType

        with campaign_operation(table.campaign, actor=table.arbitrator) as act:
            kind = act.add_asset_type(
                "Territory", AssetType.Ownership.HOLDING, "Territories"
            )
            token = act.add_asset(act.create_asset(kind, "Unresolved Gate"))
            act.assign(token, table.gang.campaign_memberships.get(left__isnull=True))
            act.edit_battle(
                table.battle,
                scenario="Stand-off",
                date=table.battle.date,
                gangs=[table.gang],
                result="not_recorded",
                winners=[],
                revision=table.battle.revision,
                stake=token,
                stake_awarded_to=None,
            )
        report = start(client, table)
        page = client.get(editor_url(report))
        territory = editor_props(page)["territory"]
        assert territory["outcome"] == "Outcome not recorded."
        assert "arbitrator records" in territory["note"]
        assert not territory["applied"]
        assert "territory" not in editor_props(page)["preview"]


@pytest.fixture
def report_pet(table, make_profile):
    profile = make_profile("Cyber-mastiff")
    slot = create_slot(
        "Pet lasting injury",
        table.injury_kind,
        table.injury_table,
        min_picks=0,
        max_picks=100,
    )
    add_built_in(profile, table.xp)
    add_built_in(profile, slot)
    wargear = create_wargear("Cyber-mastiff (pet)")
    modifier(
        "Cyber-mastiff wargear brings a pet",
        targets_the_model(),
        op_adds_model(profile),
        carried_by=wargear,
    )
    assign(wargear, miniature=table.models[0])
    return Miniature.objects.get(name="Cyber-mastiff", membership__gang=table.gang)


class TestPetResults:
    def test_the_pet_is_visible_immediately_after_its_owner(
        self, client, table, report_pet
    ):
        report = start(client, table)
        response = client.get(editor_url(report))
        models = editor_props(response)["models"]
        assert [model["id"] for model in models] == [
            str(table.models[0].pk),
            str(report_pet.pk),
            str(table.models[1].pk),
        ]
        pet = model_props(response, report_pet)
        assert pet["ownedBy"] == table.models[0].name
        assert pet["xpAvailable"]
        assert pet["addEffectLabel"] == "Add Lasting injury"
        from n26.core.crews import crew_roster

        assert report_pet.pk not in {
            item.miniature.pk for item in crew_roster(table.gang)
        }

    def test_nested_pets_stay_with_their_owners_and_keep_sibling_order(
        self, client, table, report_pet, make_profile
    ):
        wargear = report_pet.membership.caused_by.wargear
        sibling_token = assign(wargear, miniature=table.models[0])
        sibling = Miniature.objects.get(membership__caused_by=sibling_token)
        profile = make_profile("Giant rat")
        collar = create_wargear("Brood collar")
        modifier(
            "The collar brings a Giant rat",
            targets_the_model(),
            op_adds_model(profile),
            carried_by=collar,
        )
        token = assign(collar, miniature=report_pet)
        rat = Miniature.objects.get(membership__caused_by=token)
        report = start(client, table)
        response = client.get(editor_url(report))
        assert [model["id"] for model in editor_props(response)["models"]] == [
            str(table.models[0].pk),
            str(report_pet.pk),
            str(rat.pk),
            str(sibling.pk),
            str(table.models[1].pk),
        ]
        assert model_props(response, rat)["ownedBy"] == report_pet.name
        assert_books(table)

    def test_a_fighter_and_pet_receive_xp_and_a_pet_injury_once(
        self, client, table, report_pet
    ):
        report = start(client, table)
        response = client.post(
            editor_url(report),
            awards(
                client.get(editor_url(report)),
                table,
                intent=f"add-effect:{report_pet.pk}",
                **{
                    f"model-{report_pet.pk}-xp": "3",
                    f"model-{report_pet.pk}-participated": "on",
                },
            ),
        )
        pet = next(
            model
            for model in editor_props(response)["models"]
            if model["id"] == str(report_pet.pk)
        )
        effect = pet["effects"][0]
        choice = next(
            value
            for value, _ in effect_options(pet)
            if value.endswith(f"|{table.wound.pk}")
        )
        checked = client.post(
            editor_url(report),
            html_fields(
                response,
                intent="check",
                participation_confirmed="on",
                **{f"effect-{effect['id']}-pick": choice},
            ),
        )
        assert checked.status_code == 200
        data = html_fields(checked, intent="apply", participation_confirmed="on")
        applied = client.post(editor_url(report), data)
        assert applied.status_code == 302
        assert client.post(editor_url(report), data).status_code == 302
        assert xp_value(table.models[0]) == 2
        assert xp_value(report_pet) == 3
        report_pet.refresh_from_db()
        assert report_pet.status == Status.RECOVERY
        assert report_pet.owned_by.pk == table.models[0].pk
        assert (
            Assignment.objects.filter(
                miniature_root=report_pet, pickable=table.wound, archived=False
            ).count()
            == 1
        )
        assert PostBattleRevision.objects.filter(report=report).count() == 1
        assert_books(table)

    @pytest.mark.parametrize("nested", [False, True])
    def test_more_pets_do_not_add_per_model_queries(
        self, client, table, report_pet, nested
    ):
        report = start(client, table)

        def count():
            client.get(editor_url(report))
            with CaptureQueriesContext(connection) as queries:
                response = client.get(editor_url(report))
                assert response.status_code == 200
            return len(queries)

        before = count()
        wargear = report_pet.membership.caused_by.wargear
        owner = report_pet if nested else table.models[1]
        for _ in range(3):
            assign(wargear, miniature=owner)
        assert count() <= before


class TestArchivedBattleReceipts:
    def test_saved_results_and_crews_remain_readable_without_edit_actions(
        self, client, table
    ):
        report = start_through_page(client, table)
        assert (
            client.post(
                editor_url(report), awards(client.get(editor_url(report)), table)
            ).status_code
            == 302
        )
        save_crew(
            battle=table.battle,
            gang=table.gang,
            actor=table.owner,
            revision=0,
            selections=[CrewSelection(str(table.models[0].pk), "starting")],
            confirm=True,
        )
        before = report.revisions.get(sequence=1).receipt
        client.force_login(table.arbitrator)
        with campaign_operation(table.campaign, actor=table.arbitrator) as act:
            act.remove_battle(table.battle, revision=table.battle.revision)
        client.force_login(table.owner)
        response = client.get(receipt_url(report))
        assert response.status_code == 200
        assert not response.context["may_edit"]
        assert response.context["receipt"] == before
        assert client.get(receipt_url(report, 1)).status_code == 200
        sheet = client.get(
            reverse(
                "n26-battle-crew-sheet",
                args=[table.campaign.pk, table.battle.pk, table.gang.pk],
            )
        )
        assert sheet.status_code == 200
        assert not sheet.context["editable"]
        detail = client.get(
            reverse("n26-battle", args=[table.campaign.pk, table.battle.pk])
        )
        assert "View results" in detail.content.decode()
        assert "Edit crew" not in detail.content.decode()
        assert_books(table)
