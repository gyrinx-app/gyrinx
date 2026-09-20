"""Crew pages work as ordinary forms and keep drafts private."""

from datetime import date
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag, WritePause
from n26.core.campaigns import campaign_operation
from n26.core.crews import CrewSelection, save_crew
from n26.core.models import BattleCrew, PrintConfig
from n26.core.operations import operation
from n26.core.status import Status
from n26.flags import CAMPAIGNS
from n26.tests.sandbox.actions import (
    assign,
    buy,
    choose,
    create_assignment_set,
    create_pickable,
    create_picklist,
    create_slot,
    create_slot_type,
    create_wargear,
    create_weapon,
    found_campaign,
    found_gang,
    give_weapon,
    hire,
    join_campaign,
)
from n26.write_pause import WritesPaused

pytestmark = pytest.mark.django_db


@pytest.fixture
def feature():
    return FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )


@pytest.fixture
def table(default_pack, gang_type, campaign_type, make_profile, client):
    owner = User.objects.create_user("crew-owner")
    arbitrator = User.objects.create_user("crew-arbitrator")
    campaign = found_campaign("Sump Road", campaign_type, owner=arbitrator)
    gang = found_gang("Iron Hounds", gang_type, owner=owner, budget=1000)
    join_campaign(gang, campaign)
    profile = make_profile("Gunner")
    models = [hire(gang, profile, name) for name in ["Mara", "Nell"]]
    gun = give_weapon(models[0], create_weapon("Autogun"))
    card = create_assignment_set(models[0], "Long range", [gun])
    with campaign_operation(campaign, actor=arbitrator) as act:
        battle = act.record_battle(date(2026, 9, 20), [gang], scenario="Toll bridge")
    client.force_login(owner)
    return SimpleNamespace(
        owner=owner,
        arbitrator=arbitrator,
        campaign=campaign,
        gang=gang,
        battle=battle,
        models=models,
        card=card,
    )


def address(table, sheet=False):
    return reverse(
        "n26-battle-crew-sheet" if sheet else "n26-battle-crew",
        kwargs={
            "pk": table.campaign.pk,
            "battle_pk": table.battle.pk,
            "gang_pk": table.gang.pk,
        },
    )


def fields(table, **changes):
    data = {
        "revision": "0",
        "random_count": "1",
        "random_role": "starting",
        "action": "save",
    }
    for index, model in enumerate(table.models):
        data[f"role_{model.pk}"] = "starting" if index == 0 else "reserve"
        data[f"card_{model.pk}"] = str(table.card.pk) if index == 0 else "full"
    return data | changes


class TestCrewForms:
    def test_get_does_not_create_or_draw_a_crew(self, client, table, feature):
        response = client.get(address(table))
        assert response.status_code == 200
        assert "Choose crew" in response.content.decode()
        assert not BattleCrew.objects.exists()

    def test_plain_post_saves_the_whole_crew_and_draws_real_model_cards(
        self, client, table, feature
    ):
        response = client.post(address(table), fields(table))
        assert response.status_code == 302
        assert response.url == address(table, sheet=True)
        crew = BattleCrew.objects.get()
        assert crew.confirmed and crew.members.count() == 2
        response = client.get(response.url)
        body = response.content.decode()
        assert response.status_code == 200
        assert "Long range" in body
        assert "Autogun" in body
        assert "n26-card-tabs" in body
        assert 'aria-label="Model cards"' not in body
        assert "Reinforcements" in body

    def test_sheet_puts_back_link_first_and_matches_action_button_markup(
        self, client, table, feature
    ):
        give_weapon(table.models[0], create_weapon("Bolt pistol"), paid=10)
        give_weapon(table.models[1], create_weapon("Knife"), paid=5)
        client.post(address(table), fields(table))
        body = client.get(address(table, sheet=True)).content.decode()
        assert body.index("Back to battle") < body.index("Iron Hounds crew</h1>")
        document = BeautifulSoup(body, "html.parser")
        edit = document.find("a", href=address(table))
        print_link = document.find("a", href="?print=1")
        assert edit.get_text(" ", strip=True) == "Edit crew"
        assert print_link.get_text(" ", strip=True) == "Print"
        assert edit["class"] == print_link["class"]
        assert edit.span["class"] == print_link.span["class"]
        labels = {
            label.get_text(strip=True): label.find_next_sibling("dd").get_text(
                " ", strip=True
            )
            for label in document.select("dt")
        }
        assert labels["Starting crew"] == "1 10¢ when selected"
        assert labels["Reinforcements"] == "1 5¢ when selected"

    def test_crew_cards_show_injuries_without_editing_prompts(
        self, client, table, feature
    ):
        kind = create_slot_type("Lasting injury", is_lasting_effect=True)
        wound = create_pickable("Grievous Wound", kind)
        choices = create_picklist("Injuries", kind, members=[wound])
        slot = create_slot(
            "Lasting injuries", kind, choices, min_picks=0, max_picks=100
        )
        for model in table.models:
            anchor = assign(slot, miniature=model)
            if model == table.models[0]:
                choose(anchor, wound)
        client.post(address(table), fields(table))
        response = client.get(address(table, sheet=True))
        document = BeautifulSoup(response.content, "html.parser")
        cards = document.select(".n26-card-tabs")
        assert len(cards) == 2
        assert "Grievous Wound" in cards[0].get_text()
        assert "None" in cards[1].stripped_strings
        for card in cards:
            assert not card.select("a[href], form")
            assert not {"Add", "Choose", "Dismiss", "Restore"}.intersection(
                card.stripped_strings
            )
        assert not document.select('[aria-label="Model cards"]')

    def test_saved_draft_reopens_with_selections(self, client, table, feature):
        response = client.post(address(table), fields(table, action="draft"))
        assert response.url == address(table)
        crew = BattleCrew.objects.get()
        assert not crew.confirmed
        response = client.get(address(table))
        assert (
            response.context["form"][f"role_{table.models[0].pk}"].value() == "starting"
        )
        assert (
            response.context["form"][f"card_{table.models[0].pk}"]
            .value()
            .startswith("saved:")
        )

    def test_refusal_keeps_submitted_values_and_revision(self, client, table, feature):
        client.post(address(table), fields(table))
        response = client.post(
            address(table), fields(table, **{f"role_{table.models[0].pk}": "reserve"})
        )
        assert response.status_code == 200
        assert "changed while" in response.content.decode()
        assert (
            response.context["form"][f"role_{table.models[0].pk}"].value() == "reserve"
        )
        assert response.context["form"]["revision"].value() == "0"
        assert (
            BattleCrew.objects.get().members.get(miniature=table.models[0]).role
            == "starting"
        )

    def test_random_draw_posts_once_and_gets_never_redraw(self, client, table, feature):
        payload = fields(
            table, action="draw", **{f"role_{m.pk}": "out" for m in table.models}
        )
        response = client.post(address(table), payload)
        assert response.url == address(table)
        crew = BattleCrew.objects.get()
        snapshot = crew.last_draw.copy()
        client.get(address(table))
        client.get(address(table))
        response = client.post(address(table), payload)
        assert response.status_code == 200
        crew.refresh_from_db()
        assert crew.draw_number == 1
        assert crew.last_draw == snapshot

    def test_recovery_override_is_visible_and_required(self, client, table, feature):
        with operation(table.gang, actor=table.owner) as act:
            act.set_status(table.models[0], Status.RECOVERY)
        response = client.post(address(table), fields(table))
        assert response.status_code == 200
        assert "Allow this model" in response.content.decode()
        response = client.post(
            address(table), fields(table, **{f"override_{table.models[0].pk}": "on"})
        )
        assert response.status_code == 302
        assert (
            BattleCrew.objects.get()
            .members.get(miniature=table.models[0])
            .eligibility_override
        )

    def test_missing_model_fields_cannot_silently_clear_the_crew(
        self, client, table, feature
    ):
        payload = fields(table)
        del payload[f"role_{table.models[1].pk}"]
        response = client.post(address(table), payload)
        assert response.status_code == 200
        assert f"role_{table.models[1].pk}" in response.context["form"].errors
        assert not BattleCrew.objects.exists()

    def test_invalid_card_and_action_are_refused(self, client, table, feature):
        response = client.post(
            address(table),
            fields(table, **{f"card_{table.models[1].pk}": str(table.card.pk)}),
        )
        assert response.status_code == 200
        assert f"card_{table.models[1].pk}" in response.context["form"].errors
        response = client.post(address(table), fields(table, action="unknown"))
        assert response.status_code == 200
        assert not BattleCrew.objects.exists()


class TestCrewPagePermissions:
    def test_write_pause_refuses_domain_save_before_creating_a_crew(self, table):
        pause = WritePause.objects.get(scope="n26")
        pause.state = WritePause.State.PAUSED
        pause.reason = "Maintenance is in progress."
        pause.generation += 1
        pause.save()
        with pytest.raises(WritesPaused):
            save_crew(
                battle=table.battle,
                gang=table.gang,
                actor=table.owner,
                revision=0,
                selections=[],
            )
        assert not BattleCrew.objects.exists()

    def test_feature_flag_and_login_guard_both_pages(self, client, table, feature):
        feature.availability = Availability.OFF
        feature.save()
        assert client.get(address(table)).status_code == 404
        assert client.get(address(table, sheet=True)).status_code == 404
        feature.availability = Availability.EVERYONE
        feature.save()
        client.logout()
        assert client.get(address(table)).status_code == 404

    def test_other_readers_see_saved_cards_but_not_drafts_or_management(
        self, client, table, feature
    ):
        crew = save_crew(
            battle=table.battle,
            gang=table.gang,
            actor=table.owner,
            revision=0,
            selections=[
                CrewSelection(str(table.models[0].pk), "starting", str(table.card.pk))
            ],
        ).crew
        reader = User.objects.create_user("crew-reader")
        client.force_login(reader)
        assert client.get(address(table)).status_code == 404
        assert client.get(address(table, sheet=True)).status_code == 404
        crew.confirmed = True
        crew.save()
        response = client.get(address(table, sheet=True))
        assert response.status_code == 200
        assert "Autogun" in response.content.decode()
        assert 'aria-label="Model cards"' not in response.content.decode()
        assert client.post(address(table), fields(table)).status_code == 404

    def test_current_arbitrator_can_edit_the_crew(self, client, table, feature):
        client.force_login(table.arbitrator)
        assert client.get(address(table)).status_code == 200
        assert client.post(address(table), fields(table)).status_code == 302

    def test_print_opens_the_paper_layout_without_configuration_or_writes(
        self, client, table, feature
    ):
        give_weapon(table.models[0], create_weapon("Bolt pistol"), paid=10)
        give_weapon(table.models[1], create_weapon("Knife"), paid=5)
        client.post(address(table), fields(table))
        crew = BattleCrew.objects.get()
        revision = crew.revision
        config_count = PrintConfig.objects.count()
        response = client.get(address(table, sheet=True) + "?print=1")
        assert response.status_code == 200
        assert "n26/print_gang.html" in {
            template.name for template in response.templates
        }
        document = BeautifulSoup(response.content, "html.parser")
        assert not document.select(".n26-card-tabs, form")
        paper = document.select_one(".n26-print-sheet")
        assert paper["data-page"] == "a4"
        assert paper["data-orientation"] == "portrait"
        assert "Autogun" in paper.get_text()
        assert "Toll bridge" in paper.get_text()
        assert "Starting crew · Long range" in paper.get_text()
        assert "Reinforcements · Full equipment" in paper.get_text()
        header = paper.select_one(".n26-print-card")
        entries = {
            entry.select_one(".n26-print-entry-label").get_text(
                strip=True
            ): entry.select_one(".n26-print-entry-value").get_text(" ", strip=True)
            for entry in header.select(".n26-print-entry")
        }
        assert entries["Starting crew"] == "1 · 10¢ when selected"
        assert entries["Reinforcements"] == "1 · 5¢ when selected"
        toolbar = document.select_one('[aria-label="Crew print controls"]')
        assert "print:hidden" in toolbar["class"]
        assert toolbar.find("button", onclick="window.print()") is not None
        assert toolbar.find("a", href=address(table, sheet=True)) is not None
        crew.refresh_from_db()
        assert crew.revision == revision
        assert PrintConfig.objects.count() == config_count

    def test_print_keeps_saved_weapons_and_wargear_after_named_card_changes(
        self, client, table, feature
    ):
        model = table.models[0]
        goggles = buy(model, thing=create_wargear("Photo-goggles"))
        respirator = buy(model, thing=create_wargear("Respirator"))
        knife = give_weapon(model, create_weapon("Knife"))
        table.card.assignments.add(goggles)
        client.post(address(table), fields(table))
        table.card.assignments.set([knife, respirator])
        response = client.get(address(table, sheet=True) + "?print=1")
        body = response.content.decode()
        assert "Autogun" in body
        assert "Photo-goggles" in body
        assert "Knife" not in body
        assert "Respirator" not in body
        card = response.context["rows"][0]["card"]
        assert [weapon.name for weapon in card.weapons] == ["Autogun"]
        assert [gear.name for gear in card.equipment] == ["Photo-goggles"]

    def test_print_keeps_a_missing_model_in_its_saved_crew_role(
        self, client, table, feature
    ):
        client.post(address(table), fields(table))
        BattleCrew.objects.get().members.filter(miniature=table.models[0]).update(
            miniature=None
        )
        response = client.get(address(table, sheet=True) + "?print=1")
        document = BeautifulSoup(response.content, "html.parser")
        printed_cards = document.select(".n26-print-grid .n26-print-card")
        assert len(printed_cards) == 2
        assert "Mara" in printed_cards[0].get_text()
        assert "Starting crew · Long range" in printed_cards[0].get_text()
        assert "This model is no longer on the roster." in printed_cards[0].get_text()

    def test_bad_addresses_are_not_server_errors(self, client, table, feature):
        path = address(table).replace(str(table.gang.pk), "not-an-id")
        assert client.get(path).status_code == 404


class TestCrewPageQueryGrowth:
    @pytest.mark.parametrize("print_view", [False, True])
    def test_more_models_add_no_per_card_query_to_the_sheet(
        self, client, table, feature, print_view
    ):
        client.post(
            address(table), fields(table, **{f"role_{table.models[1].pk}": "out"})
        )
        # Warm URL, content and template caches before measuring the page.
        sheet_url = address(table, sheet=True) + ("?print=1" if print_view else "")
        client.get(sheet_url)
        with CaptureQueriesContext(connection) as small:
            assert client.get(sheet_url).status_code == 200
        profile = table.models[1].membership.profile
        extra = [hire(table.gang, profile, f"Extra {number}") for number in range(4)]
        table.models.extend(extra)
        payload = fields(table, revision="1")
        for model in extra:
            payload[f"role_{model.pk}"] = "starting"
        assert client.post(address(table), payload).status_code == 302
        client.get(sheet_url)
        with CaptureQueriesContext(connection) as large:
            assert client.get(sheet_url).status_code == 200
        assert len(large) <= len(small)
