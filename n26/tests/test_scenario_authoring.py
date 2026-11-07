"""Scenario authoring, catalogue eligibility and stable result references."""

import random
from importlib import import_module
from io import BytesIO

import pytest
from bs4 import BeautifulSoup
from django.apps import apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.models import ProtectedError
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from PIL import Image

from n26.core.forms import ScenarioGeneratorForm
from n26.core.scenarios import parse, roll_side_jobs
from n26.library import authoring
from n26.library.deletion import plan_deletion
from n26.library.models import ScenarioEntry, ScenarioTable
from n26.library.scenario_tables import load_catalogue
from n26.tests.fixtures import island_props

seed = import_module(
    "n26.library.migrations.0130_scenario_content_is_author_editable"
).seed

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("scenario_content")]


@pytest.fixture
def staff(client):
    user = User.objects.create_user("scenario-author", is_staff=True)
    client.force_login(user)
    return user


@pytest.fixture
def draft():
    return authoring.create_scenario_table("Synthetic side jobs")


def complete(table):
    for roll in range(1, 7):
        authoring.add_scenario_entry(
            table,
            roll,
            f"Synthetic result {roll}",
            f"Original test description {roll}.",
        )
    return table


def here(table):
    return reverse("authoring-detail", args=["scenario-table", table.pk])


def test_migration_content_is_complete_and_bootstrap_preserves_authored_edits():
    assert ScenarioTable.objects.count() == 7
    assert ScenarioEntry.objects.count() == 42
    entry = ScenarioEntry.objects.get(table__legacy_key="crew", roll=2)
    authoring.revise(
        entry, name="Authored replacement", text="Original authored description."
    )
    seed(apps)
    assert ScenarioEntry.objects.get(pk=entry.pk).name == "Authored replacement"
    assert parse({"crew": "2"})[0][0].entry.label == "Authored replacement"


def test_new_sets_are_stable_and_only_complete_live_sets_are_offered(draft):
    original_key = draft.key
    assert original_key not in {s.key for s in load_catalogue().side_job_sets}
    assert original_key not in {
        s.key for s in load_catalogue(include_staged=True).side_job_sets
    }
    complete(draft)
    assert original_key in {
        s.key for s in load_catalogue(include_staged=True).side_job_sets
    }
    assert original_key not in {s.key for s in load_catalogue().side_job_sets}
    authoring.put_live(draft)
    authoring.revise(draft, name="Renamed side jobs")
    assert draft.key == original_key
    assert load_catalogue().side_job_set(original_key).name == "Renamed side jobs"
    form = ScenarioGeneratorForm({"side_job_pick": f"{original_key}-3"})
    assert form.is_valid(), form.errors
    assert form.generate()["side_job"] == f"{original_key}-3"


def test_individual_and_bulk_release_cannot_publish_an_incomplete_table(draft):
    for release in (
        lambda: authoring.put_live(draft),
        lambda: authoring.put_selected_live([f"scenariotable:{draft.pk}"]),
    ):
        with pytest.raises(ValidationError, match="six D6 entries"):
            release()
        draft.refresh_from_db()
        assert draft.staged


def test_bulk_release_is_atomic_when_a_table_is_incomplete(draft):
    other = authoring.create_gang_type("Synthetic staged gang", staged=True)
    with pytest.raises(ValidationError):
        authoring.put_selected_live(
            [f"gangtype:{other.pk}", f"scenariotable:{draft.pk}"]
        )
    other.refresh_from_db()
    assert other.staged


def test_retirement_preserves_known_results_but_stops_new_selection(draft):
    complete(draft)
    authoring.put_live(draft)
    value = f"{draft.key}-2"
    authoring.revise(draft, archived=True)
    found, wrong = parse({"side_job": value})
    assert not wrong and found[0].entry.label == "Synthetic result 2"
    form = ScenarioGeneratorForm({"side_job_pick": value})
    assert not form.is_valid()
    assert draft.key not in {s.key for s in load_catalogue().side_job_sets}


def test_identity_and_published_rolls_cannot_be_changed():
    table = ScenarioTable.objects.get(legacy_key="general")
    with pytest.raises(ValidationError, match="identity"):
        authoring.revise(table, legacy_key="changed")
    entry = ScenarioEntry.objects.get(table=table, roll=1)
    with pytest.raises(ValidationError, match="result number"):
        authoring.revise(entry, roll=6)


def test_scenario_content_cannot_be_deleted_through_either_library_path(draft):
    entry = authoring.add_scenario_entry(
        draft, 1, "Synthetic", "Original test description."
    )
    for record in (draft, entry):
        assert not plan_deletion([record]).ok
        with pytest.raises(ProtectedError):
            authoring.delete_content(record)


def test_catalogue_computation_issues_no_queries_and_avoids_duplicates():
    catalogue = load_catalogue()
    table = catalogue.side_job_set("escher")
    with CaptureQueriesContext(connection) as queries:
        found, wrong = parse({"deployment": "2", "side_job": "escher-3"}, catalogue)
        values = roll_side_jobs([(table, None)] * 6, random.Random(1))
    assert not queries
    assert not wrong and len(found) == 2
    assert len(set(values)) == 6


def test_authoring_is_staff_only(client):
    client.force_login(User.objects.create_user("reader"))
    assert (
        client.get(reverse("authoring-create", args=["scenario-table"])).status_code
        == 302
    )
    assert client.get(here(ScenarioTable.objects.first())).status_code == 302


def test_staff_create_and_edit_using_the_spec_generated_forms(client, staff):
    response = client.post(
        reverse("authoring-create", args=["scenario-table"]),
        {"name": "Browser-style set", "position": "8"},
    )
    assert response.status_code == 302
    table = ScenarioTable.objects.get(name="Browser-style set")
    assert table.staged
    for roll in range(1, 7):
        response = client.post(
            here(table),
            {
                "act": "add-entry",
                "roll": roll,
                "name": f"Result {roll}",
                "text": "Original synthetic description.",
            },
        )
        assert response.status_code == 302
    response = client.post(here(table), {"act": "put_live"})
    assert response.status_code == 302
    table.refresh_from_db()
    assert not table.staged
    response = client.get(here(table))
    props = island_props(response.content, "scenario-authoring")
    assert props["complete"] and len(props["entries"]) == 6
    assert props["previewUrl"]
    entry = table.entries.get(roll=2)
    response = client.post(
        here(table),
        {
            "act": "edit-entry",
            "entry": str(entry.pk),
            f"entry-{entry.pk}-name": "Revised entry",
            f"entry-{entry.pk}-text": "Original revised description.",
        },
    )
    assert response.status_code == 302
    assert parse({"side_job": f"{table.key}-2"})[0][0].entry.label == "Revised entry"


def test_invalid_entry_submission_keeps_errors_and_values(client, staff, draft):
    response = client.post(
        here(draft),
        {
            "act": "add-entry",
            "roll": "7",
            "name": "Kept name",
            "text": "Kept description.",
        },
    )
    props = island_props(response.content, "scenario-authoring")
    assert props["addForm"]["fields"][0]["errors"]
    assert (
        next(f for f in props["addForm"]["fields"] if f["name"] == "name")["value"]
        == "Kept name"
    )
    assert not draft.entries.exists()


def test_uploaded_diagrams_reach_both_prop_and_print_renderers(
    client, staff, tmp_path, settings
):
    settings.MEDIA_ROOT = tmp_path
    entry = ScenarioEntry.objects.get(table__legacy_key="deployment", roll=1)
    data = BytesIO()
    Image.new("RGB", (20, 20), "white").save(data, format="PNG")
    response = client.post(
        here(entry.table),
        {
            "act": "edit-entry",
            "entry": str(entry.pk),
            f"entry-{entry.pk}-name": "Synthetic deployment",
            f"entry-{entry.pk}-text": "Original deployment description.",
            f"entry-{entry.pk}-diagram_alt": "Two synthetic deployment areas.",
            f"entry-{entry.pk}-diagram": SimpleUploadedFile(
                "test.png", data.getvalue(), content_type="image/png"
            ),
        },
    )
    assert response.status_code == 302
    entry.refresh_from_db()
    assert entry.diagram.name.startswith("n26/scenario-diagrams/")
    response = client.get(reverse("n26-scenario-print"), {"deployment": "1"})
    assert (
        BeautifulSoup(response.content, "html.parser").find(
            "img", alt="Two synthetic deployment areas."
        )["src"]
        == entry.diagram.url
    )
    assert "Two synthetic deployment areas." in response.content.decode()
    from n26.core.views.scenario_props import battle_scenario_props

    assert (
        battle_scenario_props({})["tables"][0]["entries"][0]["imageAlt"]
        == "Two synthetic deployment areas."
    )


def test_query_count_does_not_grow_with_more_side_jobs(client, staff):
    url = reverse("n26-generate-scenario")
    small = {"side_job": "escher-1", "side_jobs": "1"}
    large = {
        **small,
        **{f"side_job_{n}": f"escher-{n}" for n in range(2, 7)},
        "side_jobs": "6",
    }
    for values in (small, large):
        assert client.get(url, values).status_code == 200
    with CaptureQueriesContext(connection) as queries:
        client.get(url, small)
    count = len(queries)
    with CaptureQueriesContext(connection) as queries:
        client.get(url, large)
    assert len(queries) == count


def test_history_catalogue_queries_do_not_grow_with_saved_scenarios(
    staff, campaign_type
):
    from n26.core.campaigns import campaign_operation
    from n26.core.history import campaign_history
    from n26.tests.sandbox.actions import found_campaign

    campaign = found_campaign("Synthetic scenario history", campaign_type, owner=staff)
    with campaign_operation(campaign, actor=staff) as act:
        act.save_scenario({"side_job": "escher-3"}, name="Synthetic first scenario")
    campaign_history(campaign, viewer=staff)
    with CaptureQueriesContext(connection) as queries:
        first = campaign_history(campaign, viewer=staff)
    catalogue_count = sum(
        '"library_scenariotable"' in q["sql"] or '"library_scenarioentry"' in q["sql"]
        for q in queries
    )
    with campaign_operation(campaign, actor=staff) as act:
        for n in range(8):
            act.save_scenario({"side_job": "escher-3"}, name=f"Synthetic scenario {n}")
    with CaptureQueriesContext(connection) as queries:
        larger = campaign_history(campaign, viewer=staff)
    assert len(larger) > len(first)
    assert (
        sum(
            '"library_scenariotable"' in q["sql"]
            or '"library_scenarioentry"' in q["sql"]
            for q in queries
        )
        == catalogue_count
        == 2
    )


def test_new_set_identities_survive_hidden_fields_and_campaign_operations(
    draft, staff, campaign_type
):
    from datetime import date

    from n26.core.campaigns import campaign_operation
    from n26.core.forms import SaveScenarioForm
    from n26.tests.sandbox.actions import found_campaign

    complete(draft)
    authoring.put_live(draft)
    value = f"{draft.key}-3"
    assert len(value) > 20
    form = SaveScenarioForm({"name": "Synthetic saved result", "side_job": value})
    assert form.is_valid(), form.errors
    campaign = found_campaign(
        "Synthetic authored scenario campaign", campaign_type, owner=staff
    )
    with campaign_operation(campaign, actor=staff) as act:
        act.save_scenario(
            form.cleaned_data["scenario_rolls"], name=form.cleaned_data["name"]
        )
        battle = act.record_battle(
            date(2026, 11, 7),
            scenario="Synthetic authored battle",
            scenario_rolls={"side_job": value},
        )
    assert battle.scenario_rolls["side_job"] == value
    assert parse(battle.scenario_rolls)[0][0].entry.label == "Synthetic result 3"


def test_inline_props_separate_retained_results_from_new_choices(draft):
    from n26.core.views.scenario_props import battle_scenario_props

    complete(draft)
    authoring.put_live(draft)
    value = f"{draft.key}-2"
    for fields in ({"staged": True}, {"staged": False, "archived": True}):
        authoring.revise(draft, **fields)
        props = battle_scenario_props({"deployment": "1", "side_job": value})
        assert draft.key not in {table["key"] for table in props["sideJobSets"]}
        assert props["referencedSideJobSets"][0]["key"] == draft.key
        assert (
            props["referencedSideJobSets"][0]["entries"][1]["name"]
            == "Synthetic result 2"
        )


def test_original_deployment_diagrams_are_not_prefixed_twice(client, staff):
    from django.templatetags.static import static

    for route in ("n26-generate-scenario", "n26-scenario-print"):
        response = client.get(reverse(route), {"deployment": "1"})
        images = BeautifulSoup(response.content, "html.parser").find_all("img")
        assert static("n26/scenarios/deployment-1.png") in [
            image.get("src") for image in images
        ]
        assert not any("/static/static/" in image.get("src", "") for image in images)


def test_single_staged_page_publication_shows_an_incomplete_table_error(
    client, staff, draft
):
    response = client.post(
        reverse("authoring-staged"),
        {"act": "put_live", "model": "scenariotable", "pk": str(draft.pk)},
    )
    assert response.status_code == 400
    props = island_props(response.content, "authoring-staged")
    assert any("six D6 entries" in error for error in props["errors"])
    draft.refresh_from_db()
    assert draft.staged


def test_rerolling_a_live_job_can_retain_an_existing_retired_job(
    draft, staff, campaign_type
):
    from datetime import date

    from n26.core.campaigns import campaign_operation
    from n26.core.operations import Refusal
    from n26.tests.sandbox.actions import found_campaign

    complete(draft)
    authoring.put_live(draft)
    value = f"{draft.key}-3"
    campaign = found_campaign(
        "Synthetic retained result campaign", campaign_type, owner=staff
    )
    with campaign_operation(campaign, actor=staff) as act:
        battle = act.record_battle(
            date(2026, 11, 7),
            scenario="Synthetic retained result",
            scenario_rolls={"side_job": value, "side_job_2": "escher-2"},
        )
    authoring.revise(draft, archived=True)
    with campaign_operation(campaign, actor=staff) as act:
        act.connect_scenario(
            battle,
            {"side_job": value, "side_job_2": "escher-4"},
            revision=battle.revision,
        )
    battle.refresh_from_db()
    assert battle.scenario_rolls == {"side_job": value, "side_job_2": "escher-4"}
    with pytest.raises(Refusal):
        with campaign_operation(campaign, actor=staff) as act:
            act.connect_scenario(
                battle,
                {"side_job": f"{draft.key}-4", "side_job_2": "escher-4"},
                revision=battle.revision,
            )


def test_frozen_seed_runs_against_the_migrations_historical_models(settings):
    from django.db.migrations.loader import MigrationLoader
    from django.test import override_settings

    with override_settings(MIGRATION_MODULES={}):
        historical = (
            MigrationLoader(None)
            .project_state([("library", "0130_scenario_content_is_author_editable")])
            .apps
        )
    seed(historical)
    assert historical.get_model("library", "ScenarioTable").objects.count() == 7
    assert historical.get_model("library", "ScenarioEntry").objects.count() == 42


@pytest.mark.parametrize("legacy_pick", ["roll", "2"])
def test_legacy_general_picks_cannot_silently_drop_a_retired_set(legacy_pick):
    table = ScenarioTable.objects.get(legacy_key="general")
    authoring.revise(table, archived=True)
    form = ScenarioGeneratorForm({"side_job_pick": legacy_pick})
    assert not form.is_valid()
    assert "side_job_pick" in form.errors
    assert parse({"side_job": "2"})[0][0].entry.roll == 2


@pytest.mark.parametrize("lifecycle", ["staged", "archived"])
def test_stale_scalar_edit_preserves_latest_lifecycle(draft, lifecycle):
    complete(draft)
    authoring.put_live(draft)
    stale = ScenarioTable.objects.get(pk=draft.pk)
    authoring.revise(draft, **{lifecycle: True})
    authoring.revise(stale, name="Edited after lifecycle changed")
    stale.refresh_from_db()
    assert getattr(stale, lifecycle)
    assert stale.key not in {each.key for each in load_catalogue().side_job_sets}


def test_retired_editor_has_no_new_generation_preview(client, staff, draft):
    complete(draft)
    authoring.revise(draft, archived=True)
    props = island_props(client.get(here(draft)).content, "scenario-authoring")
    assert props["complete"]
    assert not props["previewUrl"]


@pytest.mark.parametrize("campaign_page", [False, True])
@pytest.mark.parametrize("explicit_menus", [False, True])
def test_full_generators_reroll_with_retired_results_and_keep_menu_positions(
    client, staff, draft, campaign_type, campaign_page, explicit_menus
):
    from urllib.parse import parse_qsl, urlsplit

    from n26.tests.sandbox.actions import found_campaign

    complete(draft)
    authoring.put_live(draft)
    authoring.revise(draft, archived=True)
    if campaign_page:
        campaign = found_campaign("Retained generator", campaign_type, owner=staff)
        url = reverse("n26-scenario-generator", args=[campaign.pk])
    else:
        url = reverse("n26-generate-scenario")
    query = {
        "deployment_pick": "leave",
        "objective_pick": "leave",
        "crew_pick": "leave",
        "side_job": f"{draft.key}-3",
        "side_job_2": "escher-2",
    }
    if explicit_menus:
        query.update(
            side_jobs="3",
            side_job_pick="",
            side_job_2_pick=draft.key,
            side_job_3_pick="escher",
        )
    response = client.get(url, query)
    props = island_props(response.content, "scenario-picks")
    expected = ["", draft.key, "escher"] if explicit_menus else [draft.key, "escher"]
    assert props["sidePicks"] == expected
    assert not props["errors"]
    assert draft.key in {s["key"] for s in props["referencedSideJobSets"]}
    assert draft.key not in {s["key"] for s in props["sideJobSets"]}

    response = client.get(
        url, {**query, "reroll": "side_job_2", "reroll_set": "escher"}
    )
    assert response.status_code == 302
    state = dict(parse_qsl(urlsplit(response.url).query))
    assert state["side_job"] == f"{draft.key}-3"
    assert state["side_job_2"].startswith("escher-")
    pick_slot = "side_job_3_pick" if explicit_menus else "side_job_2_pick"
    assert state[pick_slot] == "escher"

    refused = client.get(url, {**state, "generate": "1"})
    assert refused.status_code == 200
    assert refused.context["form"].errors

    response = client.get(url, {**state, "reroll": "side_job", "reroll_set": "general"})
    assert response.status_code == 302
    state = dict(parse_qsl(urlsplit(response.url).query))
    assert state["side_job"].startswith("general-")
    replaced_slot = "side_job_2_pick" if explicit_menus else "side_job_pick"
    assert state[replaced_slot] == "general"
    response = client.get(url, {**state, "generate": "1"})
    assert response.status_code == 302
    state = dict(parse_qsl(urlsplit(response.url).query))
    assert state["side_job"].startswith("general-")
    assert state["side_job_2"].startswith("escher-")


def test_native_replacement_set_discards_only_the_known_previous_retired_pick(draft):
    complete(draft)
    authoring.put_live(draft)
    authoring.revise(draft, archived=True)
    form = ScenarioGeneratorForm(
        {
            "generate": "1",
            "side_job_set": "general",
            "side_job_pick": draft.key,
            "side_job": f"{draft.key}-3",
        }
    )
    assert form.is_valid(), form.errors
    assert form.generate()["side_job"].startswith("general-")


def test_native_retained_named_pick_selects_its_set_and_cannot_silently_disappear(
    draft,
):
    complete(draft)
    authoring.put_live(draft)
    authoring.revise(draft, archived=True)
    value = f"{draft.key}-3"
    form = ScenarioGeneratorForm({"side_job_pick": value, "side_job": value})
    assert form.is_valid(), form.errors
    menu = form.side_job_menus()[0]
    assert menu["unavailable"]
    assert menu["set_value"] == draft.key
    generated = ScenarioGeneratorForm(
        {
            "generate": "1",
            "side_job": value,
            "side_job_set": menu["set_value"],
            "side_job_pick": menu["value"],
        }
    )
    assert not generated.is_valid()
    assert "side_job_pick" in generated.errors
