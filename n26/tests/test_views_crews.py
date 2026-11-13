"""Crew pages work as ordinary forms and keep drafts private."""

import json
from datetime import date
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import WritePause
from n26.core.campaigns import campaign_operation
from n26.core.crews import CrewSelection, save_crew
from n26.core.models import BattleCrew, Miniature, PrintConfig
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.core.status import Status
from n26.library.models import Profile
from n26.tests.sandbox.actions import (
    assign,
    attach,
    buy,
    choose,
    create_assignment_set,
    create_pickable,
    create_picklist,
    create_slot,
    create_slot_type,
    create_wargear,
    create_weapon,
    create_weapon_accessory,
    found_campaign,
    found_gang,
    give_weapon,
    hire,
    join_campaign,
    modifier,
    op_adds_model,
    targets_model,
)
from n26.write_pause import WritesPaused

pytestmark = pytest.mark.django_db


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
    def test_get_does_not_create_or_draw_a_crew(self, client, table):
        response = client.get(address(table))
        assert response.status_code == 200
        assert "Choose crew" in response.content.decode()
        assert not BattleCrew.objects.exists()

    def test_plain_post_saves_the_whole_crew_and_draws_real_model_cards(
        self, client, table
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

    def test_sheet_links_the_battle_in_its_header_and_matches_action_buttons(
        self, client, table
    ):
        give_weapon(table.models[0], create_weapon("Bolt pistol"), paid=10)
        give_weapon(table.models[1], create_weapon("Knife"), paid=5)
        client.post(address(table), fields(table))
        body = client.get(address(table, sheet=True)).content.decode()
        assert "Back to battle" not in body
        document = BeautifulSoup(body, "html.parser")
        lead = document.find("h1", string="Iron Hounds crew").find_next_sibling("p")
        back = lead.find(
            "a",
            href=reverse("n26-battle", args=[table.campaign.pk, table.battle.pk]),
        )
        assert back.get_text(" ", strip=True) == table.battle.title
        assert back.find("svg") is not None
        assert "20 September 2026" in lead.get_text()
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
        assert labels["Starting crew"] == "1"
        assert labels["Reinforcements"] == "1 5¢"
        assert labels["Crew rating"] == "0¢"
        stats = document.find("dt", string="Crew rating").find_parent("dl").select("dd")
        assert len(stats) == 3
        assert stats[0]["class"] == stats[1]["class"] == stats[2]["class"]
        assert "when selected" not in body
        assert "The saved cards keep their equipment selection" not in body
        assert "Saved crew" not in body

    @pytest.mark.parametrize("surface", ["battle", "sheet", "print"])
    def test_selected_equipment_rating_is_frozen_on_reads_and_updated_on_resave(
        self, client, table, surface
    ):
        starting = table.models[0]
        selected = give_weapon(starting, create_weapon("Selected pistol"), paid=15)
        omitted = give_weapon(starting, create_weapon("Omitted sword"), paid=25)
        table.card.assignments.add(selected)
        give_weapon(table.models[1], create_weapon("Reserve knife"), paid=7)
        assert client.post(address(table), fields(table)).status_code == 302
        crew = BattleCrew.objects.get()

        if surface == "battle":
            url = reverse(
                "n26-battle",
                kwargs={"pk": table.campaign.pk, "battle_pk": table.battle.pk},
            )
        else:
            url = address(table, sheet=True) + (
                "?print=1" if surface == "print" else ""
            )

        def ratings():
            response = client.get(url)
            assert response.status_code == 200
            if surface == "battle":
                saved = response.context["participants"][0].crew
            else:
                saved = response.context[
                    "crew_sheet" if surface == "print" else "sheet"
                ]
                for line in [*saved.starting, *saved.reserves]:
                    assert line.card.rating == line.member.rating
            return saved.starting_rating, saved.reserve_rating

        assert ratings() == (15, 7)
        table.card.assignments.set([omitted])
        attach(selected, create_weapon_accessory("Sight"), paid=3)
        assert ratings() == (15, 7)
        editor = client.get(address(table))
        picker = editor.context["crew_picker"]
        assert picker["models"][0]["fullRating"] == 43
        assert [model["role"]["value"] for model in picker["models"]] == [
            "starting",
            "reserve",
        ]
        payload = fields(table, revision=str(crew.revision))
        for model in table.models:
            key = f"card_{model.pk}"
            payload[key] = editor.context["form"][key].value()
        assert client.post(address(table), payload).status_code == 302
        assert ratings() == (18, 7)
        table.gang.refresh_from_db()
        assert_reconciled(table.gang)

    def test_picker_props_preserve_saved_choices_and_use_one_react_owner(
        self, client, table
    ):
        client.post(address(table), fields(table))
        response = client.get(address(table))
        document = BeautifulSoup(response.content, "html.parser")
        host = document.select_one("[data-react-name='crew-workflow']")
        assert host is not None
        props = json.loads(document.find(id=host["data-react-props"]).string)
        assert props == response.context["crew_workflow"]
        assert props["battleUrl"] == reverse(
            "n26-battle", args=[table.campaign.pk, table.battle.pk]
        )
        assert props["revision"] == 1
        assert len(props["models"]) == 2
        for model in props["models"]:
            assert model["available"] is True
            assert model["savedSource"] == "Added to this crew manually."
            labels = [choice["label"] for choice in model["card"]["choices"]]
            assert not any("saved selection" in label for label in labels)
            assert len(labels) == len(set(labels))
            assert model["role"]["name"] == f"role_{model['id']}"
        values = {model["id"]: model["card"]["value"] for model in props["models"]}
        assert values == {
            str(table.models[0].pk): str(table.card.pk),
            str(table.models[1].pk): "full",
        }
        assert host.find_parent("form") is None
        assert not host.select("[x-data], [x-model], [x-show]")
        assert not host.select('script[src$="battle-actions.js"]')

    def test_the_longer_explanations_sit_behind_help_icons(self, client, table):
        response = client.get(address(table))
        document = BeautifulSoup(response.content, "html.parser")
        props = response.context["crew_workflow"]
        assert props["crewHelp"]["label"] == "More about crew selection"
        assert props["drawHelp"]["label"] == "More about the random draw"
        assert not document.select("[data-react-name='help']")
        assert "Each drawn model gets a random equipment set" not in document.get_text(
            " ", strip=True
        )

    def test_invalid_post_preserves_picker_values_and_field_errors(self, client, table):
        model = table.models[0]
        model.status = Status.RECOVERY
        model.save(update_fields=["status"])
        response = client.post(address(table), fields(table))
        assert response.status_code == 200
        props = response.context["crew_picker"]
        selected = props["models"][0]
        assert selected["role"]["value"] == "starting"
        assert selected["card"]["value"] == str(table.card.pk)
        assert selected["mayOverride"] is True
        assert selected["override"]["value"] is False
        assert selected["override"]["errors"] == [
            "Allow this model for this battle or remove it from the crew."
        ]
        assert not BattleCrew.objects.exists()

    def test_picker_json_escapes_model_names(self, client, table):
        model = table.models[0]
        model.name = '</script><script>alert("model")</script>'
        model.save(update_fields=["name"])
        response = client.get(address(table))
        document = BeautifulSoup(response.content, "html.parser")
        host = document.select_one("[data-react-name='crew-workflow']")
        props = json.loads(document.find(id=host["data-react-props"]).string)
        selected = next(item for item in props["models"] if item["id"] == str(model.pk))
        assert selected["name"] == model.name
        assert model.name not in response.content.decode()

    def test_crew_cards_show_injuries_without_editing_prompts(self, client, table):
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
        assert "Lasting injuries" not in cards[1].get_text()
        for card in cards:
            assert not card.select("a[href], form")
            assert not {"Add", "Choose", "Dismiss", "Restore"}.intersection(
                card.stripped_strings
            )
        assert not document.select('[aria-label="Model cards"]')

    def test_saved_draft_reopens_with_selections(self, client, table):
        response = client.post(address(table), fields(table, action="draft"))
        assert response.url == address(table)
        crew = BattleCrew.objects.get()
        assert not crew.confirmed
        sheet = client.get(address(table, sheet=True))
        assert sheet.status_code == 200
        document = BeautifulSoup(sheet.content, "html.parser")
        assert "Draft" in document.stripped_strings
        assert "Saved crew" not in sheet.content.decode()
        response = client.get(address(table))
        assert (
            response.context["form"][f"role_{table.models[0].pk}"].value() == "starting"
        )
        assert response.context["form"][f"card_{table.models[0].pk}"].value() == str(
            table.card.pk
        )

    def test_a_card_edited_since_it_was_saved_keeps_its_saved_entry(
        self, client, table
    ):
        client.post(address(table), fields(table, action="draft"))
        table.card.assignments.clear()
        response = client.get(address(table))
        (mara,) = [
            model
            for model in response.context["crew_picker"]["models"]
            if model["id"] == str(table.models[0].pk)
        ]
        assert mara["card"]["value"].startswith("saved:")
        assert mara["card"]["choices"][0]["label"] == "Long range — saved selection"

    def test_refusal_keeps_submitted_values_and_revision(self, client, table):
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

    def test_random_draw_posts_once_and_gets_never_redraw(self, client, table):
        payload = fields(
            table, action="draw", **{f"role_{m.pk}": "out" for m in table.models}
        )
        response = client.post(address(table), payload)
        assert response.url == address(table)
        crew = BattleCrew.objects.get()
        snapshot = crew.last_draw.copy()
        editor = client.get(address(table))
        assert [
            model["savedSource"]
            for model in editor.context["crew_picker"]["models"]
            if model["role"]["value"] != "out"
        ] == ["Added to this crew by a random draw."]
        client.get(address(table))
        response = client.post(address(table), payload)
        assert response.status_code == 302
        crew.refresh_from_db()
        assert crew.draw_number == 1
        assert crew.last_draw == snapshot

    def test_resaving_a_drawn_card_keeps_it_marked_as_drawn(self, client, table):
        client.post(
            address(table),
            fields(table, action="draw", random_count="2")
            | {f"role_{m.pk}": "out" for m in table.models},
        )
        editor = client.get(address(table))
        payload = {"revision": "1", "random_role": "starting", "action": "save"}
        for model in editor.context["crew_picker"]["models"]:
            payload[model["role"]["name"]] = model["role"]["value"]
            payload[model["card"]["name"]] = model["card"]["value"]
        response = client.post(address(table), payload)
        assert response.status_code == 302
        crew = BattleCrew.objects.get()
        assert set(crew.members.values_list("card_source", flat=True)) == {"random"}

    def test_recovery_override_is_visible_and_required(self, client, table):
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

    def test_missing_model_fields_cannot_silently_clear_the_crew(self, client, table):
        payload = fields(table)
        del payload[f"role_{table.models[1].pk}"]
        response = client.post(address(table), payload)
        assert response.status_code == 200
        assert f"role_{table.models[1].pk}" in response.context["form"].errors
        assert not BattleCrew.objects.exists()

    def test_invalid_card_and_action_are_refused(self, client, table):
        response = client.post(
            address(table),
            fields(table, **{f"card_{table.models[1].pk}": str(table.card.pk)}),
        )
        assert response.status_code == 200
        assert f"card_{table.models[1].pk}" in response.context["form"].errors
        response = client.post(address(table), fields(table, action="unknown"))
        assert response.status_code == 200
        assert not BattleCrew.objects.exists()


@pytest.fixture
def pet(table, person_type, gang_type):
    """Mara buys wargear that brings a pet, so the pet has an owner."""
    profile = Profile.objects.create(
        name="Cyber-mastiff", profile_type=person_type, gang_type=gang_type, price=0
    )
    wargear = create_wargear("Cyber-mastiff (pet)")
    modifier(
        "Cyber-mastiff wargear brings a pet",
        targets_model(),
        op_adds_model(profile),
        carried_by=wargear,
    )
    assign(wargear, miniature=table.models[0])
    found = Miniature.objects.get(name="Cyber-mastiff", membership__gang=table.gang)
    assert found.owned_by == table.models[0]
    return found


class TestCrewPets:
    @pytest.mark.parametrize(
        "role, label",
        [("starting", "Starting crew"), ("reserve", "Reinforcements")],
    )
    def test_a_pet_occupies_its_own_grid_cell_after_its_owner(
        self, client, table, pet, role, label
    ):
        client.post(
            address(table),
            fields(table, **{f"role_{model.pk}": role for model in table.models}),
        )
        response = client.get(address(table, sheet=True))
        document = BeautifulSoup(response.content, "html.parser")
        section = document.find("section", attrs={"aria-label": label})
        grid = section.find("div", class_="grid", recursive=False)
        cells = grid.find_all("div", recursive=False)
        assert [
            [
                name.get_text(strip=True)
                for name in cell.select('[id^="n26-model-name-"]')
            ]
            for cell in cells
        ] == [["Mara"], ["Cyber-mastiff"], ["Nell"]]

    def test_a_pet_is_not_offered_or_drawn(self, client, table, pet):
        response = client.get(address(table))
        ids = {model["id"] for model in response.context["crew_picker"]["models"]}
        assert ids == {str(model.pk) for model in table.models}
        response = client.post(
            address(table),
            fields(table, action="draw", random_count="3")
            | {f"role_{m.pk}": "out" for m in table.models},
        )
        assert response.status_code == 200
        assert "Only 2 eligible models remain" in response.content.decode()
        assert not BattleCrew.objects.exists()

    def test_a_pet_bought_into_the_stash_is_listed(
        self, client, table, person_type, gang_type
    ):
        profile = Profile.objects.create(
            name="Phyrr Cat", profile_type=person_type, gang_type=gang_type, price=0
        )
        wargear = create_wargear("Phyrr Cat (pet)")
        modifier(
            "Phyrr Cat wargear brings a pet",
            targets_model(),
            op_adds_model(profile),
            carried_by=wargear,
        )
        assign(wargear, stash=table.gang.stash)
        stashed = Miniature.objects.get(name="Phyrr Cat", membership__gang=table.gang)
        assert stashed.owned_by is None
        response = client.get(address(table))
        ids = {model["id"] for model in response.context["crew_picker"]["models"]}
        assert str(stashed.pk) in ids

    def test_a_saved_pet_leaves_the_crew_on_resave(self, client, table, pet):
        crew = BattleCrew.objects.create(battle=table.battle, gang=table.gang)
        crew.members.create(
            miniature=pet,
            miniature_name=pet.name,
            role="starting",
            card_name="Full equipment",
        )
        response = client.post(address(table), fields(table, revision="0"))
        assert response.status_code == 302
        assert not crew.members.filter(miniature=pet).exists()

    def test_the_sheet_draws_a_pet_after_its_owner_and_does_not_count_it(
        self, client, table, pet
    ):
        client.post(address(table), fields(table))
        sheet = client.get(address(table, sheet=True))
        (owner_line,) = [
            line
            for line in sheet.context["sheet"].starting
            if line.member.miniature_id == table.models[0].pk
        ]
        assert [card.name for card in owner_line.pets] == ["Cyber-mastiff"]
        assert len(sheet.context["sheet"].starting) == 1
        body = sheet.content.decode()
        assert "Goes with its owner. Not counted in the crew." in body
        printed = client.get(address(table, sheet=True) + "?print=1")
        titles = [row["card"].name for row in printed.context["rows"]]
        assert titles.index("Cyber-mastiff") == titles.index("Mara") + 1

    def test_a_pet_saved_as_a_member_is_drawn_once_with_its_owner(
        self, client, table, pet
    ):
        owner = table.models[0]
        crew = BattleCrew.objects.create(
            battle=table.battle, gang=table.gang, confirmed=True
        )
        for model in (owner, pet):
            crew.members.create(
                miniature=model,
                miniature_name=model.name,
                role="starting",
                card_name="Full equipment",
                rating=10,
            )
        sheet = client.get(address(table, sheet=True)).context["sheet"]
        assert [line.member.miniature_id for line in sheet.starting] == [owner.pk]
        assert [card.name for card in sheet.starting[0].pets] == ["Cyber-mastiff"]
        assert sheet.starting_rating == 10

    def test_a_pet_whose_owner_is_not_in_the_crew_is_not_drawn(
        self, client, table, pet
    ):
        client.post(
            address(table), fields(table, **{f"role_{table.models[0].pk}": "out"})
        )
        sheet = client.get(address(table, sheet=True))
        assert all(not line.pets for line in sheet.context["sheet"].reserves)
        assert "Cyber-mastiff" not in sheet.content.decode()


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

    def test_login_guards_both_pages(self, client, table):
        client.logout()
        for url in (address(table), address(table, sheet=True)):
            response = client.get(url)
            assert response.status_code == 302
            assert "/accounts/login/" in response["Location"]

    def test_other_readers_see_saved_cards_but_not_drafts_or_management(
        self, client, table
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

    def test_current_arbitrator_can_edit_the_crew(self, client, table):
        client.force_login(table.arbitrator)
        assert client.get(address(table)).status_code == 200
        assert client.post(address(table), fields(table)).status_code == 302

    def test_print_opens_the_paper_layout_without_configuration_or_writes(
        self, client, table
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
        assert "Reinforcements · All equipment" in paper.get_text()
        header = paper.select_one(".n26-print-card")
        entries = {
            entry.select_one(".n26-print-entry-label").get_text(
                strip=True
            ): entry.select_one(".n26-print-entry-value").get_text(" ", strip=True)
            for entry in header.select(".n26-print-entry")
        }
        assert entries["Starting crew"] == "1 · 0¢"
        assert entries["Reinforcements"] == "1 · 5¢"
        assert "when selected" not in paper.get_text()
        toolbar = document.select_one('[aria-label="Crew print controls"]')
        assert "print:hidden" in toolbar["class"]
        assert toolbar.find("button", onclick="window.print()") is not None
        assert toolbar.find("a", href=address(table, sheet=True)) is not None
        crew.refresh_from_db()
        assert crew.revision == revision
        assert PrintConfig.objects.count() == config_count

    def test_print_keeps_saved_weapons_and_wargear_after_named_card_changes(
        self, client, table
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

    def test_print_keeps_a_missing_model_in_its_saved_crew_role(self, client, table):
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

    def test_bad_addresses_are_not_server_errors(self, client, table):
        path = address(table).replace(str(table.gang.pk), "not-an-id")
        assert client.get(path).status_code == 404


class TestCrewPageQueryGrowth:
    def test_more_models_add_no_per_model_query_to_the_picker(self, client, table):
        client.get(address(table))
        with CaptureQueriesContext(connection) as small:
            assert client.get(address(table)).status_code == 200
        profile = table.models[0].membership.profile
        for number in range(4):
            hire(table.gang, profile, f"Extra {number}")
        client.get(address(table))
        with CaptureQueriesContext(connection) as large:
            response = client.get(address(table))
            assert response.status_code == 200
        assert len(response.context["crew_picker"]["models"]) == 6
        assert len(large) <= len(small)

    @pytest.mark.parametrize("print_view", [False, True])
    def test_more_models_add_no_per_card_query_to_the_sheet(
        self, client, table, print_view
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


def command_address(table):
    return reverse(
        "n26-battle-crew-command",
        args=[table.campaign.pk, table.battle.pk, table.gang.pk],
    )


class TestCrewWorkflowCommands:
    @pytest.mark.parametrize("transport", ["native", "json"])
    @pytest.mark.parametrize("action", ["save", "draft", "draw"])
    def test_both_adapters_share_selection_draw_snapshots_and_destinations(
        self, client, table, transport, action
    ):
        from uuid import uuid4

        from n26.core.models import CrewCommandReceipt, LedgerEvent

        before = LedgerEvent.objects.filter(gang=table.gang).count()
        payload = fields(table, action=action, request_key=str(uuid4()))
        if action == "draw":
            payload[f"role_{table.models[1].pk}"] = "out"
        response = client.post(
            command_address(table) if transport == "json" else address(table), payload
        )
        assert response.status_code == (200 if transport == "json" else 302)
        destination = (
            response.json()["nextUrl"] if transport == "json" else response.url
        )
        assert destination == address(table, sheet=action == "save")
        crew = BattleCrew.objects.get()
        assert crew.revision == 1
        assert crew.confirmed is (action == "save")
        assert crew.draw_number == (1 if action == "draw" else 0)
        assert crew.members.count() == 2
        assert crew.members.get(miniature=table.models[0]).equipment_ids == [
            str(table.card.assignments.get().pk)
        ]
        assert crew.members.get(miniature=table.models[1]).source == (
            "random" if action == "draw" else "manual"
        )
        receipt = CrewCommandReceipt.objects.get()
        assert receipt.inputs["action"] == [action]
        assert (
            receipt.actor == table.owner
            and receipt.gang == table.gang
            and receipt.battle == table.battle
        )
        assert receipt.result["revision"] == 1 and receipt.result["confirmed"] is (
            action == "save"
        )
        assert len(receipt.result["selections"]) == 2
        assert LedgerEvent.objects.filter(gang=table.gang).count() == before
        assert_reconciled(table.gang)

    def test_a_lost_draw_response_replays_its_original_result_after_later_changes(
        self, client, table
    ):
        from uuid import uuid4

        from n26.core.models import CrewCommandReceipt

        original = fields(
            table,
            action="draw",
            request_key=str(uuid4()),
            **{f"role_{table.models[1].pk}": "out"},
        )
        first = client.post(command_address(table), original).json()
        changed = fields(
            table,
            action="draft",
            revision="1",
            request_key=str(uuid4()),
            **{f"role_{table.models[1].pk}": "out"},
        )
        assert client.post(command_address(table), changed).status_code == 200
        table.card.delete()
        with operation(table.gang, actor=table.owner) as act:
            act.set_status(table.models[0], Status.DEAD)
        replay = client.post(command_address(table), original)
        assert replay.status_code == 200
        assert replay.json()["acknowledged"] == first["acknowledged"]
        assert replay.json()["newer"] is True
        assert CrewCommandReceipt.objects.count() == 2
        crew = BattleCrew.objects.get()
        assert crew.revision == 2 and crew.draw_number == 1
        assert crew.members.count() == 1

    @pytest.mark.parametrize(
        "change",
        [{"action": "draw"}, {"random_count": "01"}, {"unexpected": "changed"}],
    )
    def test_a_save_key_cannot_describe_different_raw_inputs(
        self, client, table, change
    ):
        from uuid import uuid4

        payload = fields(table, request_key=str(uuid4()))
        assert client.post(command_address(table), payload).status_code == 200
        response = client.post(command_address(table), payload | change)
        assert response.status_code == 409
        assert response.json()["code"] == "key_conflict"
        assert BattleCrew.objects.get().revision == 1

    def test_the_same_key_from_another_authorised_actor_is_refused(self, client, table):
        from uuid import uuid4

        payload = fields(table, request_key=str(uuid4()))
        assert client.post(command_address(table), payload).status_code == 200
        client.force_login(table.arbitrator)
        assert client.post(command_address(table), payload).status_code == 409
        assert BattleCrew.objects.get().revision == 1

    def test_the_same_key_for_another_battle_is_refused(self, client, table):
        from uuid import uuid4

        payload = fields(table, request_key=str(uuid4()))
        assert client.post(command_address(table), payload).status_code == 200
        with campaign_operation(table.campaign, actor=table.arbitrator) as act:
            battle = act.record_battle(
                date(2026, 9, 21), [table.gang], scenario="Second battle"
            )
        url = reverse(
            "n26-battle-crew-command",
            args=[table.campaign.pk, battle.pk, table.gang.pk],
        )
        assert client.post(url, payload).status_code == 409
        assert BattleCrew.objects.count() == 1

    @pytest.mark.parametrize("resource", ["battle", "campaign", "gang"])
    def test_archival_allows_an_authorised_prior_receipt_but_no_new_save(
        self, client, table, resource
    ):
        from uuid import uuid4

        payload = fields(table, request_key=str(uuid4()))
        first = client.post(command_address(table), payload).json()
        obj = getattr(table, resource)
        obj.archived = True
        obj.save(update_fields=["archived"])
        replay = client.post(command_address(table), payload)
        assert replay.json()["acknowledged"] == first["acknowledged"]
        assert "recover=1&saved=" in replay.json()["nextUrl"]
        assert client.get(replay.json()["nextUrl"]).status_code == 200
        fresh = payload | {"revision": "1", "request_key": str(uuid4())}
        assert client.post(command_address(table), fresh).status_code == 409
        native_replay = client.post(address(table), payload)
        assert native_replay.status_code == 302
        assert client.get(native_replay.url).status_code == 200
        assert client.post(address(table), fresh).status_code == 404
        assert client.post(address(table), {}).status_code == 404
        assert BattleCrew.objects.get().revision == 1
        assert client.get(address(table)).status_code == 404
        recovery = client.get(address(table) + "?recover=1")
        assert (
            recovery.status_code == 200
            and recovery.context["crew_workflow"]["readOnly"] is True
        )

    @pytest.mark.parametrize("authority", ["owner", "arbitrator", "participant"])
    def test_revoked_authority_cannot_recall_a_saved_result(
        self, client, table, authority
    ):
        from uuid import uuid4

        from django.utils import timezone

        if authority == "arbitrator":
            client.force_login(table.arbitrator)
        payload = fields(table, request_key=str(uuid4()))
        assert client.post(command_address(table), payload).status_code == 200
        if authority == "owner":
            table.gang.owner = table.arbitrator
            table.gang.save(update_fields=["owner"])
        elif authority == "arbitrator":
            table.gang.campaign_memberships.update(left=timezone.now())
        else:
            table.battle.gangs.remove(table.gang)
        response = client.post(command_address(table), payload)
        assert response.status_code == 404
        assert "acknowledged" not in response.content.decode()
        assert BattleCrew.objects.get().revision == 1

    def test_revision_conflicts_keep_submitted_values_and_current_facts_separate(
        self, client, table
    ):
        from uuid import uuid4

        assert client.post(address(table), fields(table)).status_code == 302
        payload = fields(
            table,
            action="draft",
            request_key=str(uuid4()),
            **{f"role_{table.models[0].pk}": "reserve"},
        )
        response = client.post(command_address(table), payload)
        assert (
            response.status_code == 409
            and response.json()["code"] == "revision_conflict"
        )
        assert response.json()["current"]["revision"] == 1
        assert response.json()["current"]["selections"][0]["role"] == "Starting crew"
        native = client.post(address(table), payload)
        assert (
            native.context["crew_workflow"]["values"][f"role_{table.models[0].pk}"]
            == "reserve"
        )
        assert native.context["crew_workflow"]["values"]["revision"] == "0"
        assert native.context["crew_workflow"]["initialConflict"] is True

    def test_json_requires_a_key_and_read_routes_never_save(self, client, table):
        from n26.core.models import CrewCommandReceipt

        response = client.post(command_address(table), fields(table))
        assert response.status_code == 422
        url = reverse(
            "n26-battle-crew-display",
            args=[table.campaign.pk, table.battle.pk, table.gang.pk],
        )
        assert client.get(url).status_code == 200
        assert client.get(address(table)).status_code == 200
        assert (
            not BattleCrew.objects.exists() and not CrewCommandReceipt.objects.exists()
        )
        client.logout()
        assert client.post(command_address(table), fields(table)).status_code == 401
        assert client.get(url).status_code == 401

    def test_a_receipt_failure_rolls_back_the_crew_and_draw(
        self, client, table, monkeypatch
    ):
        from uuid import uuid4

        from n26.core import crew_workflow
        from n26.core.models import CrewCommandReceipt

        def fail(*args, **kwargs):
            raise RuntimeError("Receipt storage failed")

        monkeypatch.setattr(crew_workflow, "snapshot", fail)
        with pytest.raises(RuntimeError, match="Receipt storage failed"):
            client.post(
                command_address(table),
                fields(
                    table,
                    action="draw",
                    request_key=str(uuid4()),
                    **{f"role_{table.models[1].pk}": "out"},
                ),
            )
        assert (
            not BattleCrew.objects.exists() and not CrewCommandReceipt.objects.exists()
        )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_crew_commands_save_once_under_the_shared_locks(table, same_key):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import uuid4

    from django.db import close_old_connections
    from django.http import QueryDict

    from n26.core import crew_workflow
    from n26.core.models import CrewCommandReceipt

    barrier = Barrier(2)
    key = str(uuid4())

    def save(index):
        close_old_connections()
        try:
            payload = QueryDict(mutable=True)
            payload.update(
                fields(
                    table,
                    action="draw",
                    request_key=key if same_key or index == 0 else str(uuid4()),
                    **{f"role_{table.models[1].pk}": "out"},
                )
            )
            barrier.wait(timeout=10)
            result = crew_workflow.perform(
                battle=table.battle,
                gang=table.gang,
                actor=table.owner,
                data=payload,
                require_key=True,
            )
            return (
                result.saved,
                result.replayed,
                result.conflict,
                result.receipt.result if result.receipt else None,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(save, [0, 1]))
    crew = BattleCrew.objects.get()
    assert crew.revision == 1 and crew.draw_number == 1
    assert CrewCommandReceipt.objects.count() == 1
    if same_key:
        assert all(result[0] for result in results)
        assert sum(result[1] for result in results) == 1
        assert results[0][3] == results[1][3]
    else:
        assert sum(result[0] for result in results) == 1
        assert sum(result[2] for result in results) == 1


@pytest.mark.parametrize("shape", ["added", "removed"])
def test_native_rejected_roster_changes_preserve_raw_fields_and_require_review(
    client, table, shape
):
    payload = fields(table)
    if shape == "added":
        hire(table.gang, table.models[0].membership.profile, "New model")
    else:
        from n26.core.models import Miniature

        removed = table.models[0]
        with operation(table.gang, actor=table.owner) as act:
            act.remove(removed.membership)
        assert Miniature.objects.filter(pk=removed.pk).exists()
    response = client.post(address(table), payload)
    assert response.status_code == 200
    props = response.context["crew_workflow"]
    assert props["rosterChanged"] is True
    for name, value in payload.items():
        if name.startswith(("role_", "card_")):
            assert props["values"][name] == value
    assert not BattleCrew.objects.exists()


@pytest.mark.parametrize(
    "status", [Status.RECOVERY, Status.CRITICAL, Status.CAPTURED, Status.RANSOMED]
)
def test_each_nonactive_status_requires_an_explicit_battle_allowance(
    client, table, status
):
    from uuid import uuid4

    with operation(table.gang, actor=table.owner) as act:
        act.set_status(table.models[0], status)
    payload = fields(table, request_key=str(uuid4()))
    refused = client.post(command_address(table), payload)
    assert refused.status_code == 422
    assert f"override_{table.models[0].pk}" in refused.json()["errors"]
    accepted = client.post(
        command_address(table), payload | {f"override_{table.models[0].pk}": "on"}
    )
    assert accepted.status_code == 200
    assert (
        BattleCrew.objects.get()
        .members.get(miniature=table.models[0])
        .eligibility_override
    )


def test_vehicle_warnings_use_the_vehicle_status_label(
    client, table, vehicle_type, make_profile
):
    profile = make_profile("Cargo crawler", profile_type=vehicle_type)
    model = hire(table.gang, profile, "Mule")
    with operation(table.gang, actor=table.owner) as act:
        act.set_status(model, Status.CRITICAL)
    response = client.get(address(table))
    selected = next(
        item
        for item in response.context["crew_workflow"]["models"]
        if item["id"] == str(model.pk)
    )
    assert (
        selected["warning"] == "Critically Damaged. Usually unavailable for selection."
    )


def test_bound_native_checkbox_values_are_kept_exactly_in_display_props(client, table):
    payload = fields(
        table, random_count="invalid", **{f"override_{table.models[0].pk}": "false"}
    )
    response = client.post(address(table), payload)
    assert (
        response.context["crew_workflow"]["values"][f"override_{table.models[0].pk}"]
        == "false"
    )
    assert response.context["crew_workflow"]["values"]["random_count"] == "invalid"


def test_crew_json_commands_enforce_csrf(client, table):
    from django.test import Client

    guarded = Client(enforce_csrf_checks=True)
    guarded.force_login(table.owner)
    response = guarded.post(
        command_address(table), fields(table), HTTP_ACCEPT="application/json"
    )
    assert response.status_code == 403
    assert not BattleCrew.objects.exists()


@pytest.mark.parametrize("change", ["owner", "participant", "archive"])
@pytest.mark.parametrize("transport", ["native", "json"])
def test_crew_authority_and_archive_are_rechecked_under_the_write_locks(
    client, table, monkeypatch, change, transport
):
    from contextlib import contextmanager
    from uuid import uuid4

    from n26.core import crew_workflow
    from n26.core.models import Battle, CrewCommandReceipt, Gang

    original = crew_workflow.locked_crew

    @contextmanager
    def changed_before_lock(**kwargs):
        if change == "owner":
            Gang.objects.filter(pk=table.gang.pk).update(owner=table.arbitrator)
        elif change == "participant":
            table.battle.gangs.remove(table.gang)
        else:
            Battle.objects.filter(pk=table.battle.pk).update(archived=True)
        with original(**kwargs) as locked:
            yield locked

    monkeypatch.setattr(crew_workflow, "locked_crew", changed_before_lock)
    response = client.post(
        command_address(table) if transport == "json" else address(table),
        fields(table, request_key=str(uuid4())),
    )
    assert response.status_code == (409 if transport == "json" else 404)
    if transport == "json":
        assert "acknowledged" not in response.json()
    assert not BattleCrew.objects.exists() and not CrewCommandReceipt.objects.exists()


@pytest.mark.parametrize("change", ["equipment", "roster", "status"])
@pytest.mark.parametrize("transport", ["native", "json"])
def test_stale_crew_revision_allows_review_despite_mutable_field_errors(
    client, table, change, transport
):
    from uuid import uuid4

    from n26.core.models import CrewCommandReceipt

    stale = fields(table, request_key=str(uuid4()))
    assert client.post(address(table), fields(table)).status_code == 302
    if change == "equipment":
        table.card.delete()
    elif change == "roster":
        hire(table.gang, table.models[0].membership.profile, "Cal")
    else:
        with operation(table.gang, actor=table.owner) as act:
            act.set_status(table.models[0], Status.RECOVERY)
    receipts = CrewCommandReceipt.objects.count()

    response = client.post(
        command_address(table) if transport == "json" else address(table), stale
    )
    if transport == "json":
        assert response.status_code == 409
        assert response.json()["code"] == "revision_conflict"
        assert response.json()["current"]["revision"] == 1
    else:
        assert response.status_code == 200
        assert response.context["crew_workflow"]["initialConflict"] is True
        assert response.context["crew_workflow"]["values"]["revision"] == "0"
    assert BattleCrew.objects.get().revision == 1
    assert CrewCommandReceipt.objects.count() == receipts


@pytest.mark.parametrize(
    "invalid",
    [
        {"revision": ""},
        {"revision": "not a number"},
        {"request_key": ""},
        {"request_key": "not a key"},
    ],
)
def test_invalid_crew_revision_or_key_cannot_confirm_a_stale_retry(
    client, table, invalid
):
    from uuid import uuid4

    from n26.core.models import CrewCommandReceipt

    stale = fields(table, request_key=str(uuid4())) | invalid
    assert client.post(address(table), fields(table)).status_code == 302
    table.card.delete()
    receipts = CrewCommandReceipt.objects.count()
    response = client.post(command_address(table), stale)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid"
    assert BattleCrew.objects.get().revision == 1
    assert CrewCommandReceipt.objects.count() == receipts


def test_crew_key_conflict_precedes_a_stale_revision_and_roster_errors(client, table):
    from uuid import uuid4

    original = fields(table, request_key=str(uuid4()))
    assert client.post(command_address(table), original).status_code == 200
    table.card.delete()
    response = client.post(command_address(table), original | {"action": "draft"})
    assert response.status_code == 409
    assert response.json()["code"] == "key_conflict"
    assert BattleCrew.objects.get().revision == 1
