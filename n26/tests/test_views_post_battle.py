"""The actual report form saves unfinished work and applies a gang's results once."""

from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import Group, User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
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
)
from n26.core.operations import operation
from n26.core.post_battle import start_report
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
from n26.library.models import Profile
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
)
from n26.tests.sandbox.actions import targets_model as targets_the_model

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
    gang = open_founding(found_gang("Ashen Choir", gang_type, owner=owner, budget=1000))
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
    """Each model's results sit in one module; submit shares one form footer."""

    def test_each_model_has_one_module_holding_all_its_controls(
        self, client, table, feature
    ):
        report = start(client, table)
        document = BeautifulSoup(client.get(editor_url(report)).content, "html.parser")
        form = document.find("form", id="post-battle-form")
        assert form.find("table") is None
        for model in table.models:
            module = form.find("fieldset", id=f"result-{model.pk}")
            assert module.legend.get_text(strip=True) == model.name
            assert module.select_one(f'[name="model_id"][value="{model.pk}"]')
            for field in ("participated", "xp", "status", "equipment"):
                name = f"model-{model.pk}-{field}"
                scripted = [
                    element
                    for element in form.select(f'[name="{name}"]')
                    if element.find_parent("noscript") is None
                ]
                assert len(scripted) == 1
                assert module.select_one(f'[name="{name}"]') is not None
        footer = form.select_one("[data-battle-actions]")
        confirmation = footer.find("input", attrs={"name": "participation_confirmed"})
        assert confirmation["aria-required"] == "true"
        assert footer.select_one('button[name="intent"][value="save"]')
        assert footer.select_one('button[name="intent"][value="apply"]')
        assert len(form.select('[name="participation_confirmed"]')) == 1
        assert "battle-actions.js" in str(document)

    def test_module_sections_run_from_took_part_to_equipment(
        self, client, table, feature
    ):
        report = start(client, table)
        model = table.models[0]
        page = client.post(
            editor_url(report),
            html_fields(
                client.get(editor_url(report)), intent=f"add-effect:{model.pk}"
            ),
        )
        module = BeautifulSoup(page.content, "html.parser").find(
            "fieldset", id=f"result-{model.pk}"
        )
        effect = page.context["models"][0].effects[0]
        order = [
            f"model-{model.pk}-participated",
            f"model-{model.pk}-xp",
            f"effect-{effect.id}-pick",
            f"model-{model.pk}-status",
            f"model-{model.pk}-equipment",
        ]
        names = list(
            dict.fromkeys(element["name"] for element in module.select("[name]"))
        )
        assert [name for name in names if name in order] == order

    def test_xp_errors_are_inside_the_model_module(self, client, table, feature):
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
        module = BeautifulSoup(response.content, "html.parser").find(
            "fieldset", id=f"result-{model.pk}"
        )
        field = module.find("input", id=f"model-{model.pk}-xp")
        help_text = module.find(id=field["aria-describedby"])
        errors = module.select_one(help_text.find("a")["href"])
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
        with operation(table.gang, actor=table.owner) as act:
            act.set_status(table.models[0], Status.RANSOMED)
            act.set_status(table.models[1], Status.RECOVERY)
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
            assert POST_BATTLE_HELP in links[0].parent.get_text()
            assert "No action is open." not in panel.get_text()
        if panel:
            founding_url = reverse("n26-gang-founding-action", args=[table.gang.pk])
            assert bool(panel.find("form", action=founding_url)) == founding_open
            assert "Recent history" not in panel.get_text()
            history = panel.find(
                "a", href=reverse("n26-gang-history", args=[table.gang.pk])
            )
            assert history.get_text(strip=True) == "History"
            assert "Hire Fighters" not in panel.get_text()
            square = response.context["activities_square"]
            assert bool(square.founding) == founding_open
            verbs = [step.verb for step in square.to_do]
            assert verbs == (
                (["Pay ransom", "Clean House"] if founding_open else [])
                + (["Post-battle"] if campaigns_open else [])
            )
            assert ("Pay ransom" in panel.get_text()) == founding_open
            assert ("Clean House" in panel.get_text()) == founding_open
            if not founding_open:
                assert "Current action" not in panel.get_text()
                assert not panel.find("form")
                assert "No history for this gang yet." not in panel.get_text()

    def test_campaigns_alone_keeps_the_existing_founding_and_status_guards(
        self, client, table, feature
    ):
        urls = [
            reverse("n26-gang-founding-action", args=[table.gang.pk]),
            reverse("n26-clean-house", args=[table.gang.pk]),
            reverse("n26-mark-fighter", args=[table.models[0].pk]),
        ]
        for url in urls:
            assert client.post(url, {}).status_code == 404
        assert table.gang.open_activity(Activity.Kind.FOUNDING) is not None

    def test_campaigns_alone_shares_the_open_visit_and_history(
        self, client, table, feature
    ):
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

    @pytest.mark.parametrize("founding_open", [False, True])
    def test_the_shared_panel_has_no_per_model_queries(
        self, client, table, feature, make_profile, founding_open
    ):
        FeatureFlag.objects.create(
            slug=FOUNDING,
            name="Founding",
            availability=Availability.EVERYONE if founding_open else Availability.OFF,
        )
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


class TestReportGroups:
    """Every saved report belongs to one group and has one continuation link."""

    @pytest.mark.parametrize("applied", [False, True])
    def test_campaign_report_appears_once_beside_its_battle(
        self, client, table, feature, applied
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
        self, client, table, feature, gang_type
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

    def test_empty_groups_are_named_and_keep_the_standalone_form(
        self, client, table, feature
    ):
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
        self, client, table, feature, unavailable
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

    def test_older_reports_remain_reachable_in_their_own_groups(
        self, client, table, feature
    ):
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

    def test_more_battles_and_reports_do_not_add_per_entry_queries(
        self, client, table, feature
    ):
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

    def test_start_page_get_does_not_write(self, client, table, feature):
        response = client.get(start_url(table, standalone=True))
        assert response.status_code == 200
        assert not PostBattleReport.objects.exists()

    @pytest.mark.parametrize("standalone", [False, True])
    def test_starting_twice_creates_one_report(
        self, client, table, feature, standalone
    ):
        url = start_url(table, standalone=standalone)
        if standalone:
            data = html_fields(
                client.get(url), date="2026-09-20", reference="Stand-off"
            )
        else:
            data = {"request_key": str(uuid4())}
        first = client.post(url, data)
        second = client.post(url, data)
        assert first.url == second.url
        report = PostBattleReport.objects.get(gang=table.gang)
        assert report.battle_id == (None if standalone else table.battle.pk)
        assert report.reference == ("Stand-off" if standalone else table.battle.title)

    def test_a_pet_is_preselected_when_its_owner_starts(
        self, client, table, feature, person_type, gang_type
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
        report = start(client, table)
        payload = client.get(editor_url(report)).context["payload"]
        by_id = {row["id"]: row for row in payload["models"]}
        assert by_id[str(pet.pk)]["participated"]
        assert not by_id[str(table.models[1].pk)]["participated"]

    def test_a_pet_saved_as_starting_does_not_take_part_without_its_owner(
        self, client, table, feature, person_type, gang_type
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
        report = start(client, table)
        payload = client.get(editor_url(report)).context["payload"]
        by_id = {row["id"]: row for row in payload["models"]}
        assert not by_id[str(pet.pk)]["participated"]

    def test_a_deleted_starting_member_does_not_tick_every_model(
        self, client, table, feature
    ):
        crew = BattleCrew.objects.create(battle=table.battle, gang=table.gang)
        crew.members.create(
            miniature=None,
            miniature_name="Gone",
            role="starting",
            card_name="Full equipment",
        )
        report = start(client, table)
        payload = client.get(editor_url(report)).context["payload"]
        assert not any(row["participated"] for row in payload["models"])

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
    def test_receipt_uses_a_shared_alert_and_consistent_left_aligned_heading(
        self, client, table, feature, standalone
    ):
        report = start(client, table, standalone=standalone)
        response = client.post(
            editor_url(report), awards(client.get(editor_url(report)), table)
        )
        receipt = client.get(response.url)
        assert receipt.status_code == 200
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
        assert "Reset choices" in BeautifulSoup(
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
        assert "Reset choices" not in cleared.content.decode()
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


def step(client, report, response, intent, **changes):
    stepped = client.post(
        editor_url(report), html_fields(response, intent=intent, **changes)
    )
    assert stepped.status_code == 200, stepped.context["errors"]
    return stepped


def entered_xp(response):
    return [row.xp for row in response.context["models"]]


def toolbar_button(response, value):
    document = BeautifulSoup(response.content, "html.parser")
    return document.select_one(f'button[name="intent"][value="{value}"]')


class TestXpSteps:
    """The toolbar steps the entered XP of selected models, never the gang."""

    def test_steps_change_only_selected_participants(self, client, table, feature):
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

    def test_repeated_steps_persist_and_stop_at_zero(self, client, table, feature):
        report = start(client, table)
        ticked = {f"model-{m.pk}-participated": "on" for m in table.models}
        page = client.get(editor_url(report))
        assert toolbar_button(page, "xp-step:-1").has_attr("disabled")
        assert toolbar_button(page, "xp-step:+1").has_attr("disabled")
        page = step(client, report, page, "xp-step:+1", **ticked)
        assert toolbar_button(page, "xp-step:+1")["aria-label"] == (
            "Add 1 XP to each of the 2 models that took part"
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
        assert toolbar_button(resumed, "xp-step:-1").has_attr("disabled")
        assert not toolbar_button(resumed, "xp-step:+1").has_attr("disabled")

    def test_a_stale_version_keeps_the_entries(self, client, table, feature):
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

    def test_an_old_draft_undo_record_is_ignored(self, client, table, feature):
        report = start(client, table)
        model = table.models[0]
        report.draft["bulk_undo"] = {str(model.pk): "3"}
        report.save(update_fields=["draft"])
        page = client.get(editor_url(report))
        assert page.status_code == 200
        saved = step(client, report, page, "check")
        assert "bulk_undo" not in saved.context["payload"]
        report.refresh_from_db()
        assert "bulk_undo" not in report.draft


class TestXpBlockedModels:
    """A model that cannot take XP says why and never blocks the others."""

    @pytest.fixture
    def visitor(self, table, make_profile):
        return hire(table.gang, make_profile("Civilian"), "Visitor")

    def test_steps_skip_a_model_without_an_xp_counter(
        self, client, table, feature, visitor
    ):
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
        by_id = {row.id: row.xp for row in page.context["models"]}
        assert by_id[str(first.pk)] == "1"
        assert by_id[str(visitor.pk)] == ""
        document = BeautifulSoup(page.content, "html.parser")
        toolbar = document.select_one("[data-xp-toolbar]")
        assert "cannot take XP" not in toolbar.get_text(" ", strip=True)
        assert toolbar.select_one("[data-xp-count]").get_text(strip=True) == (
            "2 models took part"
        )
        assert document.select_one(f'input[id="model-{visitor.pk}-xp"]') is None
        why = document.select_one(f'button[id="model-{visitor.pk}-xp-why-button"]')
        assert why["type"] == "button"
        assert why["aria-label"] == "Why Visitor cannot take XP"
        assert why["aria-expanded"] == "false"
        reason = document.find(id=why["aria-controls"])
        assert reason.get_text(" ", strip=True) == (
            "Visitor has no XP counter, so XP cannot be recorded here."
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
        assert applied.status_code == 302, applied.context["errors"]
        assert xp_value(first) == 1
        assert_books(table)

    def test_a_stray_value_on_a_blocked_model_does_not_block_apply(
        self, client, table, feature, visitor
    ):
        report = start(client, table)
        payload = report.draft
        for model in payload["models"]:
            if model["id"] == str(visitor.pk):
                model["xp"] = "1"
        report.draft = payload
        report.save(update_fields=["draft"])
        page = client.get(editor_url(report))
        assert html_fields(page)[f"model-{visitor.pk}-xp"] == [""]
        shown = next(m for m in page.context["plan"].models if m.id == str(visitor.pk))
        assert shown.xp_change == 0
        assert not any(
            error.startswith("Visitor:") for error in page.context["plan"].errors
        )
        summary = BeautifulSoup(page.content, "html.parser").find(
            "aside", attrs={"aria-labelledby": "changes-heading"}
        )
        assert "Visitor" not in summary.get_text(" ", strip=True)
        applied = client.post(editor_url(report), awards(page, table))
        assert applied.status_code == 302, applied.context["errors"]

    def test_a_correction_after_the_xp_counter_is_removed_applies(
        self, client, table, feature
    ):
        report = start(client, table)
        model = table.models[0]
        first = client.post(
            editor_url(report), awards(client.get(editor_url(report)), table)
        )
        assert first.status_code == 302, first.context["errors"]
        counter = Assignment.objects.get(
            miniature_root=model, counter__isnull=False, archived=False
        )
        with operation(table.gang, actor=table.owner) as op:
            op.remove(counter)
        corrected = client.post(reverse("n26-post-battle-correct", args=[report.pk]))
        page = client.get(corrected.url)
        document = BeautifulSoup(page.content, "html.parser")
        assert document.select_one(f'input[id="model-{model.pk}-xp"]') is None
        assert document.select_one(f'button[id="model-{model.pk}-xp-why-button"]')
        assert html_fields(page)[f"model-{model.pk}-xp"] == ["2"]
        applied = client.post(
            editor_url(report), html_fields(page, intent="apply", credits="30")
        )
        assert applied.status_code == 302, applied.context["errors"]
        assert applied.url == receipt_url(report, 2)
        counter.refresh_from_db()
        assert counter.archived
        assert CounterValue.objects.get(assignment=counter).value == 2
        assert_books(table)

    def test_a_crafted_award_for_a_blocked_model_is_refused(
        self, client, table, feature, visitor
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
            in refused.context["errors"]
        )
        assert not Assignment.objects.filter(
            miniature=visitor, counter__isnull=False
        ).exists()


class TestRecordResultsEntry:
    """Record results starts the draft on POST and opens the editor straight away."""

    def test_battle_report_get_does_not_write_and_returns_to_the_battle(
        self, client, table, feature
    ):
        response = client.get(start_url(table))
        assert response.status_code == 302
        assert response.url == reverse(
            "n26-battle", args=[table.campaign.pk, table.battle.pk]
        )
        assert not PostBattleReport.objects.exists()

    def test_battle_report_get_with_a_report_goes_to_it(self, client, table, feature):
        report = start(client, table)
        response = client.get(start_url(table))
        assert response.status_code == 302
        assert response.url == editor_url(report)

    def test_record_results_opens_the_editor_with_the_battle_details(
        self, client, table, feature
    ):
        report = start(client, table)
        assert report.battle_id == table.battle.pk
        assert report.date == table.battle.date
        assert report.reference == table.battle.title

    def test_a_second_request_key_still_opens_the_one_battle_report(
        self, client, table, feature
    ):
        url = start_url(table)
        first = client.post(url, {"request_key": str(uuid4())})
        second = client.post(url, {"request_key": str(uuid4())})
        assert first.url == second.url
        assert PostBattleReport.objects.filter(gang=table.gang).count() == 1

    def test_a_missing_request_key_returns_to_the_battle_without_writing(
        self, client, table, feature
    ):
        response = client.post(start_url(table), {})
        assert response.url == reverse(
            "n26-battle", args=[table.campaign.pk, table.battle.pk]
        )
        assert not PostBattleReport.objects.exists()

    def test_the_post_battle_list_starts_a_campaign_report_by_post(
        self, client, table, feature
    ):
        url = start_url(table)
        data = record_results_fields(client.get(start_url(table, standalone=True)), url)
        assert data["request_key"]
        response = client.post(url, data)
        report = PostBattleReport.objects.get(gang=table.gang)
        assert response.url == editor_url(report)
        assert report.battle_id == table.battle.pk

    @pytest.mark.parametrize("page", ["editor", "receipt"])
    def test_campaign_report_breadcrumb_links_the_battle_and_the_gang(
        self, client, table, feature, page
    ):
        report = start(client, table)
        if page == "receipt":
            applied = client.post(
                editor_url(report), awards(client.get(editor_url(report)), table)
            )
            assert applied.status_code == 302
        response = client.get(
            editor_url(report) if page == "editor" else receipt_url(report)
        )
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
        assert header.get_text().count(table.gang.name) == 1

    def test_standalone_breadcrumb_links_the_gang_and_its_reports(
        self, client, table, feature
    ):
        report = start(client, table, standalone=True)
        document = BeautifulSoup(client.get(editor_url(report)).content, "html.parser")
        header = document.find("h1").find_parent("div", class_="gap-1")
        crumbs = [
            (item.get_text(strip=True), item.get("href"))
            for item in header.select("nav li a, nav li [aria-current]")
        ]
        assert crumbs == [
            (table.gang.name, reverse("n26-gang", args=[table.gang.pk])),
            ("Post-battle", reverse("n26-gang-post-battle", args=[table.gang.pk])),
            ("Stand-off", None),
        ]
        assert header.get_text().count(table.gang.name) == 1

    def test_the_action_bar_says_entries_save_as_you_go(self, client, table, feature):
        report = start(client, table)
        text = BeautifulSoup(
            client.get(editor_url(report)).content, "html.parser"
        ).get_text(" ", strip=True)
        assert (
            "Entries save as you go. The gang changes only when you apply the results."
            in text
        )
        assert "Changes apply to this gang only." not in text

    def test_battle_page_buttons_name_the_gang(self, client, table, feature):
        battle_page = reverse("n26-battle", args=[table.campaign.pk, table.battle.pk])
        button = record_results_form(client.get(battle_page), start_url(table)).find(
            "button"
        )
        assert button["aria-label"] == f"Record results for {table.gang.name}"
        start(client, table)
        document = BeautifulSoup(client.get(battle_page).content, "html.parser")
        link = document.find("a", href=start_url(table))
        assert link.get_text(strip=True) == "Continue draft"
        assert link["aria-label"] == f"Continue draft for {table.gang.name}"


def refresh(client, report, response, model, *, after=None, **changes):
    """Post the form as a changed select does: htmx, one model's intent.

    ``after`` is an earlier refresh: its version replaces the page's, as
    the out-of-band swap does in the browser.
    """
    fields = html_fields(response, intent=f"refresh-model:{model.pk}", **changes)
    if after is not None:
        version = BeautifulSoup(after.content, "html.parser").find(
            id="post-battle-version"
        )
        for element in version.select("input[name]"):
            fields[element["name"]] = [element.get("value", "")]
    return client.post(editor_url(report), fields, HTTP_HX_REQUEST="true")


def module(response, model):
    return BeautifulSoup(response.content, "html.parser").find(
        "fieldset", id=f"result-{model.pk}"
    )


class TestModelModule:
    """One module per model, worded by its tables, redrawn in place."""

    def test_a_vehicle_table_is_named_by_its_own_label(
        self, client, table, feature, make_profile, vehicle_type
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
        box = module(added, vehicle)
        assert box.find("button", value=f"add-effect:{vehicle.pk}").get_text(
            strip=True
        ) == ("Add Lasting Damage")
        (field,) = box.select("select[id$='-pick']")
        assert box.find("label", attrs={"for": field["id"]}).get_text(strip=True) == (
            "Lasting Damage 1"
        )
        assert box.find("optgroup")["label"] == "Lasting Damage"
        fighter = module(added, table.models[0])
        assert fighter.find(
            "button", value=f"add-effect:{table.models[0].pk}"
        ).get_text(strip=True) == ("Add Lasting injury")
        assert "lasting effect" not in added.content.decode().lower()

    def test_a_plural_card_heading_still_names_one_result(
        self, client, table, feature, make_profile
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
        box = module(added, model)
        assert [group["label"] for group in box.find_all("optgroup")] == [
            "Lasting injury"
        ]
        assert box.find("button", value=f"add-effect:{model.pk}").get_text(
            strip=True
        ) == ("Add Lasting injury")

    def test_options_lead_with_their_roll_band(self, client, table, feature):
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
        groups = {
            group["label"]: [option.get_text(strip=True) for option in group("option")]
            for group in module(added, model).find_all("optgroup")
        }
        assert groups["Test table (dice)"] == ["11–16 Out Cold"]
        assert groups["Lasting injury"] == ["Grievous Wound"]
        (row,) = [row for row in added.context["models"] if row.id == str(model.pk)]
        values = [value for value, _ in row.effect_options]
        assert any(value.endswith(f"|{out_cold.pk}") for value in values)

    def test_refresh_returns_the_module_summary_and_new_version(
        self, client, table, feature
    ):
        report = start(client, table)
        model = table.models[0]
        page = client.get(editor_url(report))
        response = refresh(
            client, report, page, model, **{f"model-{model.pk}-status": "dead"}
        )
        assert response.status_code == 200
        document = BeautifulSoup(response.content, "html.parser")
        assert document.find("form") is None
        box = document.find("fieldset", id=f"result-{model.pk}")
        assert box.find("select", attrs={"name": f"model-{model.pk}-equipment"})
        assert document.find(id="post-battle-summary")["hx-swap-oob"] == "true"
        version = document.find(id="post-battle-version")
        assert version["hx-swap-oob"] == "true"
        report.refresh_from_db()
        assert version.find("input", attrs={"name": "revision"})["value"] == str(
            report.draft_revision
        )
        assert report.draft["models"][0]["status"] == "dead"

    def test_a_stale_refresh_is_refused_and_keeps_the_saved_draft(
        self, client, table, feature
    ):
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

    def test_refresh_without_htmx_draws_the_whole_page(self, client, table, feature):
        report = start(client, table)
        model = table.models[0]
        response = client.post(
            editor_url(report),
            html_fields(
                client.get(editor_url(report)), intent=f"refresh-model:{model.pk}"
            ),
        )
        assert response.status_code == 200
        assert b'id="post-battle-form"' in response.content

    @pytest.mark.parametrize(
        "status,label,colour",
        [
            (Status.ACTIVE, "Active", "ink"),
            (Status.RECOVERY, "In Recovery", "amber"),
            (Status.CAPTURED, "Captured", "red"),
            (Status.DEAD, "Dead", "red"),
        ],
    )
    def test_the_heading_carries_a_status_badge(
        self, client, table, feature, status, label, colour
    ):
        model = table.models[0]
        model.status = status
        model.save(update_fields=["status"])
        report = start(client, table)
        response = client.get(editor_url(report))
        heading = module(response, model).find("h3")
        assert heading.get_text(" ", strip=True) == f"{model.name} Status: {label}"
        assert response.context["models"][0].status_colour == colour

    def test_equipment_choice_shows_only_for_a_dead_model(self, client, table, feature):
        report = start(client, table)
        model = table.models[0]
        page = client.get(editor_url(report))
        alive = module(page, model)
        # Only a browser without scripts draws the choice for a live model.
        (fallback,) = alive.find_all(
            "select", attrs={"name": f"model-{model.pk}-equipment"}
        )
        assert fallback.find_parent("noscript") is not None
        kept = alive.find("input", attrs={"name": f"model-{model.pk}-equipment"})
        assert kept["type"] == "hidden"
        assert "only when this model is dead or destroyed" in alive.get_text()
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
        box = module(dead, model)
        assert box.find("noscript") is None
        select = box.find("select", attrs={"name": f"model-{model.pk}-equipment"})
        assert select.find("option", selected=True)["value"] == "lost"
        assert "What happens to Cinder's equipment" in box.get_text()
        alive_again = refresh(
            client,
            report,
            page,
            model,
            after=dead,
            **{f"model-{model.pk}-status": "", f"model-{model.pk}-equipment": "lost"},
        )
        assert alive_again.status_code == 200
        kept = module(alive_again, model).find(
            "input", attrs={"name": f"model-{model.pk}-equipment"}
        )
        assert kept["value"] == "lost"
        summary = BeautifulSoup(alive_again.content, "html.parser").find(
            id="post-battle-summary"
        )
        # An ignored choice changes nothing, so the model is not listed.
        assert "Cinder" not in summary.get_text()


class TestModuleRefreshEdges:
    """An in-place update never swaps a whole page into a module."""

    def test_a_report_applied_elsewhere_sends_htmx_to_the_receipt(
        self, client, table, feature
    ):
        report = start(client, table)
        model = table.models[0]
        page = client.get(editor_url(report))
        applied = client.post(editor_url(report), awards(page, table))
        assert applied.status_code == 302
        response = refresh(client, report, page, model)
        assert response.status_code == 204
        assert response["HX-Redirect"] == receipt_url(report)

    def test_a_model_gone_from_the_roster_reloads_the_editor(
        self, client, table, feature
    ):
        report = start(client, table)
        model = table.models[0]
        page = client.get(editor_url(report))
        model.membership.archived = True
        model.membership.save(update_fields=["archived"])
        response = refresh(client, report, page, model)
        assert response.status_code == 204
        assert response["HX-Redirect"] == editor_url(report)

    def test_shown_errors_follow_the_entries(self, client, table, feature):
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
        assert "Cinder's XP" in module(checked, model).get_text()
        still_wrong = refresh(client, report, checked, model)
        document = BeautifulSoup(still_wrong.content, "html.parser")
        assert "Cinder's XP" in module(still_wrong, model).get_text()
        region = document.find(id="post-battle-errors")
        assert region["hx-swap-oob"] == "true"
        assert "Cinder's XP" in region.get_text()
        fixed = refresh(
            client,
            report,
            checked,
            model,
            after=still_wrong,
            **{f"model-{model.pk}-xp": "1"},
        )
        document = BeautifulSoup(fixed.content, "html.parser")
        assert "Cinder's XP" not in module(fixed, model).get_text()
        assert "Cinder's XP" not in document.find(id="post-battle-errors").get_text()

    def test_without_shown_errors_a_refresh_sends_none(self, client, table, feature):
        report = start(client, table)
        model = table.models[0]
        response = refresh(
            client,
            report,
            client.get(editor_url(report)),
            model,
            **{f"model-{model.pk}-xp": "-1"},
        )
        document = BeautifulSoup(response.content, "html.parser")
        assert document.find(id="post-battle-errors") is None
        assert "Cinder's XP" not in module(response, model).get_text()


def summary_text(response):
    summary = BeautifulSoup(response.content, "html.parser").find(
        id="post-battle-summary"
    )
    return " ".join(summary.get_text(" ").split())


class TestWhatTheSummaryAndReceiptList:
    """Only what a report records: no empty slots, no unchanged totals."""

    def test_the_summary_lists_only_models_with_changes(self, client, table, feature):
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
        assert "Cinder +1 XP XP total: 0 → 1" in text
        assert "Ember" not in text
        assert "XP adjustment" not in text
        assert "Final status" not in text

    def test_a_model_ending_in_recovery_says_how_long(self, client, table, feature):
        report = start(client, table)
        assert "campaign cycle" not in client.get(editor_url(report)).content.decode()

        checked, _ = with_effect(client, table, report, table.wound)

        text = summary_text(checked)
        assert "Final status: In Recovery" in text
        assert "Stays In Recovery until the end of the campaign cycle." in text

    def test_the_receipt_follows_the_editor_and_skips_what_did_not_change(
        self, client, table, feature
    ):
        report = start(client, table)
        checked, _ = with_effect(client, table, report, table.wound)
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

    def test_a_receipt_leaves_out_an_unchanged_status(self, client, table, feature):
        report = start(client, table)
        applied = client.post(
            editor_url(report), awards(client.get(editor_url(report)), table)
        )

        text = client.get(applied.url).content.decode()
        assert "Status:" not in text
        assert "+2 XP" in text

    def test_a_model_that_cannot_take_xp_shows_no_xp_figures(
        self, client, table, feature, make_profile
    ):
        visitor = hire(table.gang, make_profile("Civilian"), "Visitor")
        report = start(client, table)

        box = module(client.get(editor_url(report)), visitor)

        assert "Current XP" not in box.get_text()
        assert box.select_one("[data-xp-why]") is not None

    def test_check_names_a_result_that_disagrees_with_the_status(
        self, client, table, feature
    ):
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
        ) in checked.context["errors"]
