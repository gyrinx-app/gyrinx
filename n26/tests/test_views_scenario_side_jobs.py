"""Side jobs in the scenario generators: picking a set, then a job; adding
and removing side jobs; and the side jobs reaching a battle, the log and
the print."""

import random
from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.campaigns import campaign_operation
from n26.core.forms import ScenarioGeneratorForm
from n26.library.scenario_tables import side_job_set
from n26.tests.sandbox.actions import found_campaign

pytestmark = pytest.mark.django_db

GENERATOR = "n26-generate-scenario"


@pytest.fixture
def campaign(client, campaign_type):
    owner = User.objects.create_user("arb")
    client.force_login(owner)
    return found_campaign("Dust Falls", campaign_type, owner=owner)


def query_of(location):
    return parse_qs(urlparse(location).query)


def generated(client, **picks):
    response = client.get(reverse(GENERATOR), {"generate": "1", **picks})
    assert response.status_code == 302
    return response["Location"], query_of(response["Location"])


def test_a_side_job_menu_lists_the_sets_until_one_is_picked(client, campaign):
    response = client.get(reverse(GENERATOR))
    (menu,) = response.context["form"].side_job_menus()
    assert menu["label"] == "Side job 1"
    assert [label for _, label, _ in menu["options"]] == [
        "Choose a side job set",
        "Leave out",
        "General side jobs",
        "Escher side jobs",
        "Goliath side jobs",
    ]


def test_a_picked_set_lists_its_jobs_and_a_way_back(client, campaign):
    response = client.get(reverse(GENERATOR), {"side_job_pick": "goliath-2"})
    (menu,) = response.context["form"].side_job_menus()
    assert menu["label"] == "Side job 1: Goliath side jobs"
    assert menu["value"] == "goliath-2"
    labels = [label for _, label, _ in menu["options"]]
    assert labels[0] == "Roll a D6"
    assert labels[2] == "2. Personal Vendetta"
    assert labels[-1] == "Change set"
    assert [value for value, _, switch in menu["options"] if switch] == [""]


def test_changing_a_menu_keeps_the_scenario_in_view(client, campaign):
    response = client.get(
        reverse(GENERATOR),
        {"side_job_pick": "escher", "update": "1", "side_jobs": "1", "crew": "2"},
    )
    assert response.status_code == 302
    assert response["Location"].endswith("#scenario-components")
    assert query_of(response["Location"]) == {
        "side_job_pick": ["escher"],
        "crew": ["2"],
    }


def test_add_side_job_adds_a_menu_up_to_the_limit(client, campaign):
    response = client.get(
        reverse(GENERATOR), {"side_job_pick": "escher", "add_side_job": "1"}
    )
    assert query_of(response["Location"])["side_jobs"] == ["2"]
    page = client.get(response["Location"])
    assert len(page.context["form"].side_job_menus()) == 2
    assert "Remove side job 2" in page.content.decode()
    assert "Remove side job 1" not in page.content.decode()

    full = client.get(reverse(GENERATOR), {"side_jobs": "6"})
    assert "Add side job" not in full.content.decode()
    capped = client.get(reverse(GENERATOR), {"side_jobs": "9"})
    assert len(capped.context["form"].side_job_menus()) == 6


def test_removing_a_side_job_moves_the_later_ones_up(client, campaign):
    response = client.get(
        reverse(GENERATOR),
        {
            "side_jobs": "3",
            "side_job_pick": "escher",
            "side_job_2_pick": "goliath-3",
            "side_job_3_pick": "general",
            "remove_side_job": "2",
        },
    )
    assert query_of(response["Location"]) == {
        "side_job_pick": ["escher"],
        "side_job_2_pick": ["general"],
        "side_jobs": ["2"],
    }


def test_the_first_side_job_is_never_removed(client, campaign):
    response = client.get(
        reverse(GENERATOR), {"side_job_pick": "escher", "remove_side_job": "1"}
    )
    assert query_of(response["Location"]) == {"side_job_pick": ["escher"]}


def test_generating_rolls_each_side_job_on_its_set_in_menu_order(client, campaign):
    location, query = generated(
        client,
        side_jobs="4",
        side_job_pick="escher",
        side_job_2_pick="leave",
        side_job_3_pick="goliath-6",
        deployment_pick="leave",
        objective_pick="leave",
        crew_pick="leave",
    )
    assert query["side_job"][0].startswith("escher-")
    assert query["side_job_2"] == ["goliath-6"]
    assert "side_job_3" not in query
    results = client.get(location).context["scenario"]
    assert [result.heading for result in results] == [
        "Side job 1 (Escher)",
        "Side job 2 (Goliath)",
    ]


def test_a_side_job_alone_is_enough_to_generate(client, campaign):
    _, query = generated(
        client,
        deployment_pick="leave",
        objective_pick="leave",
        crew_pick="leave",
        side_job_pick="general-2",
    )
    assert query["side_job"] == ["general-2"]


def test_rolled_side_jobs_from_one_set_are_never_the_same():
    form = ScenarioGeneratorForm(
        {
            "side_jobs": "6",
            **{
                f"side_job{'' if place == 1 else f'_{place}'}_pick": "escher"
                for place in range(1, 7)
            },
        }
    )
    assert form.is_valid()
    # A seeded game die for a repeatable test, not a secret.
    generated = form.generate(rng=random.Random(4))  # nosec B311
    side_jobs = [value for key, value in generated.items() if "side_job" in key]
    assert sorted(side_jobs) == [f"escher-{roll}" for roll in range(1, 7)]


def test_links_made_before_there_were_sets_read_as_general(client, campaign):
    response = client.get(reverse(GENERATOR), {"side_job": "2", "side_job_pick": "4"})
    (result,) = response.context["scenario"]
    assert result.heading == "Side job 1 (General)"
    assert result.entry == side_job_set("general").entry(2)
    assert response.context["form"].side_job_picks() == ["general-4"]


def test_bold_text_is_drawn_bold_on_the_page_and_the_print(client, campaign):
    query = {"side_job": "goliath-6"}
    page = client.get(reverse(GENERATOR), query).content.decode()
    assert "<strong>at the same time</strong>" in page
    printed = client.get(reverse("n26-scenario-print"), query).content.decode()
    assert "<strong>at the same time</strong>" in printed
    assert "Side job 1 (Goliath)" in printed


def test_creating_a_battle_saves_every_side_job(client, campaign):
    rolls = {"crew": "2", "side_job": "escher-3", "side_job_2": "general-1"}
    response = client.post(
        reverse("n26-generate-scenario-record"),
        {"campaign": str(campaign.pk), **rolls},
    )
    form = client.get(response["Location"])
    assert [r.heading for r in form.context["scenario_results"]] == [
        "Crew",
        "Side job 1 (Escher)",
        "Side job 2 (General)",
    ]
    data = {key: value for key, value in rolls.items()}
    client.post(
        reverse("n26-campaign-add-battle", args=[campaign.pk]),
        {"date": "2026-10-28", "scenario": "Sump clash", **data},
    )
    battle = campaign.battles.get()
    assert battle.scenario_rolls == {
        "crew": 2,
        "side_job": "escher-3",
        "side_job_2": "general-1",
    }
    page = client.get(reverse("n26-battle", args=[campaign.pk, battle.pk]))
    assert "Side job 2 (General)" in page.content.decode()
    props = page.context["battle_scenario"]
    assert props["rolls"]["side_job_2"] == "general-1"


def test_generating_again_on_a_battle_replaces_its_side_jobs(client, campaign):
    with campaign_operation(campaign, actor=campaign.owner) as act:
        battle = act.record_battle(
            date(2026, 10, 28),
            scenario="Sump clash",
            scenario_rolls={"side_job": "escher-1", "side_job_2": "escher-2"},
        )
    response = client.post(
        reverse("n26-generate-scenario-save"),
        {
            "generate": "1",
            "format": "json",
            "campaign": str(campaign.pk),
            "battle": str(battle.pk),
            "revision": battle.revision,
            "side_job": "escher-1",
            "side_job_2": "escher-2",
            "side_job_pick": "goliath-4",
            "deployment_pick": "leave",
            "objective_pick": "leave",
            "crew_pick": "leave",
        },
    )
    assert response.status_code == 200
    battle.refresh_from_db()
    assert battle.scenario_rolls == {"side_job": "goliath-4"}


def test_the_log_names_each_side_job_with_its_set(client, campaign):
    with campaign_operation(campaign, actor=campaign.owner) as act:
        act.save_scenario(
            {"crew": 2, "side_job": "escher-3", "side_job_2": "goliath-1"},
            name="Sump clash",
        )
    log = client.get(reverse("n26-campaign-log", args=[campaign.pk]))
    text = log.content.decode()
    assert "Side job 1: Escher 3 (Hunt Together)" in text
    assert "Side job 2: Goliath 1 (Pit Fight)" in text


def reroll_island(response):
    return response.context["scenario_reroll"]


@pytest.mark.parametrize("campaign_page", [False, True])
def test_each_side_job_in_a_result_has_a_reroll_link(client, campaign, campaign_page):
    here = (
        reverse("n26-scenario-generator", args=[campaign.pk])
        if campaign_page
        else reverse(GENERATOR)
    )
    response = client.get(here, {"crew": "2", "side_job": "escher-3"})
    page = response.content.decode()
    assert 'aria-label="Reroll Side job 1 (Escher)"' in page
    assert "Reroll Crew" not in page
    assert reroll_island(response) is None
    link = response.context["reroll_links"]["side_job"]
    opened = client.get(link)
    props = reroll_island(opened)
    assert props["title"] == "Reroll side job 1"
    assert props["set"] == "escher"
    assert [s["value"] for s in props["sets"]] == ["general", "escher", "goliath"]
    assert ["side_job", "escher-3"] in props["fields"]
    assert ["reroll", "side_job"] in props["fields"]
    assert 'data-react-name="scenario-reroll"' in opened.content.decode()


def test_reroll_rolls_one_side_job_on_the_set_chosen_and_keeps_the_rest(
    client, campaign
):
    response = client.get(
        reverse(GENERATOR),
        {
            "crew": "2",
            "side_job": "general-1",
            "side_job_2": "escher-4",
            "side_job_pick": "general",
            "side_job_2_pick": "escher-4",
            "side_jobs": "2",
            "reroll": "side_job",
            "reroll_set": "goliath",
        },
    )
    assert response.status_code == 302
    assert response["Location"].endswith("#scenario")
    query = query_of(response["Location"])
    assert query["crew"] == ["2"]
    assert query["side_job"][0].startswith("goliath-")
    assert query["side_job_2"] == ["escher-4"]
    # The menu rolls on the new set too, for Generate again.
    assert query["side_job_pick"] == ["goliath"]
    assert query["side_job_2_pick"] == ["escher-4"]
    assert "reroll" not in query


def test_a_reroll_never_repeats_a_side_job_from_the_same_set(client, campaign):
    rolls = {
        "side_job": "escher-1",
        "side_job_2": "escher-2",
        "side_job_3": "escher-3",
        "side_job_4": "escher-4",
        "side_job_5": "escher-5",
        "side_job_6": "goliath-1",
    }
    for _ in range(5):
        response = client.get(
            reverse(GENERATOR),
            {**rolls, "reroll": "side_job_6", "reroll_set": "escher"},
        )
        assert query_of(response["Location"])["side_job_6"] == ["escher-6"]


def test_a_reroll_of_a_missing_side_job_or_set_changes_nothing(client, campaign):
    for extra in (
        {"reroll": "side_job_2", "reroll_set": "escher"},
        {"reroll": "side_job", "reroll_set": "orlock"},
    ):
        response = client.get(reverse(GENERATOR), {"side_job": "escher-3", **extra})
        assert query_of(response["Location"]) == {"side_job": ["escher-3"]}
    response = client.get(reverse(GENERATOR), {"crew": "2", "reroll": "side_job"})
    assert reroll_island(response) is None


def test_a_campaign_reroll_returns_to_the_campaign_generator(client, campaign):
    here = reverse("n26-scenario-generator", args=[campaign.pk])
    response = client.get(
        here, {"side_job": "escher-3", "reroll": "side_job", "reroll_set": "general"}
    )
    assert response["Location"].startswith(here + "?")
    assert query_of(response["Location"])["side_job"][0].startswith("general-")
