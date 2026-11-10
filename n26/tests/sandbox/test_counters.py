"""Stored counter values, computed contributions and threshold effects. Profiles initialise
XP from built-ins. Tally writes stored changes to the ledger; contributions are
calculated on reads. This fixture grants a skill choice at 75 XP and a Veteran rule at
100 XP, withdrawing them below their thresholds.
"""

import json
from urllib.parse import parse_qs, urlsplit

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import Assignment
from n26.core.render import build_model_card
from n26.library.models import Skill
from n26.tests.sandbox.actions import (
    adds,
    assign,
    counter_at_least,
    create_affiliation,
    create_counter,
    create_default_set,
    create_rule,
    create_subtype,
    ef_contributes_to_counter,
    found_gang,
    has_subtypes,
    hire_with_option,
    modifier,
    offers_choice,
    remove,
    removes,
    tally,
    targets_every_model,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def xp(db):
    return create_counter("XP")


@pytest.fixture
def kills(db):
    """A second counter verifies that cards display multiple counters."""
    return create_counter("Kill Count")


@pytest.fixture
def gang(gang_type):
    return found_gang("The Bad Girls", gang_type, owner=User.objects.create_user("t"))


@pytest.fixture
def queen(make_profile, xp, gang_type):
    """Start at 61 XP, with gang-wide effects at 75 and 100 XP."""
    profile = make_profile("Gang Queen", price=135)
    profile.built_ins = create_default_set(
        "Queen built-ins", members=[(xp, {"amount": 61})]
    )
    profile.save()

    modifier(
        "Promotion offer at 75 XP",
        targets_every_model(counter_at_least(xp, 75)),
        offers_choice(Skill),
        carried_by=gang_type,
    )
    modifier(
        "Veteran title at 100 XP",
        targets_every_model(counter_at_least(xp, 100)),
        adds(create_rule("Veteran")),
        carried_by=gang_type,
    )
    return profile


def xp_row(miniature):
    return Assignment.objects.get(miniature=miniature, counter__name="XP")


def kill_row(miniature):
    return Assignment.objects.get(miniature=miniature, counter__name="Kill Count")


def drawn(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([n.assignable for n in card.all_nodes()])
    return build_model_card(miniature, card=card, computed=compute(card, index)), (
        compute(card, index)
    )


class TestTheTally:
    def test_a_fighter_arrives_at_their_starting_xp(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        assert xp_row(yolanda).counter_value.value == 61

    def test_tally_moves_it_and_floors_at_zero(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        row = xp_row(yolanda)

        assert tally(row, +5, note="won a battle") == 66
        assert tally(row, -100) == 0

    def test_every_change_is_a_ledger_event(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        row = xp_row(yolanda)
        tally(row, +5, note="won a battle")

        kinds = [event.kind for event in row.ledger_events.all()]
        assert kinds.count("tallied") == 1


class TestWhatTheCardShows:
    """The statline XP cell and counter controls use the same effective value."""

    def test_a_hired_fighters_card_opens_at_their_starting_xp(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        card, _ = drawn(yolanda)

        assert card.xp == 61
        assert card.xp_display == "61/–"

    def test_the_card_follows_the_tally(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), +5)

        assert drawn(yolanda)[0].xp == 66

    def test_a_counter_is_not_drawn_as_a_piece_of_equipment(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")

        assert [line.name for line in drawn(yolanda)[0].equipment] == []

    def test_a_counter_draws_a_line_of_its_own(self, gang, queen, kills):

        from n26.tests.sandbox.actions import assign

        yolanda = hire_with_option(gang, queen, "Yolanda")
        assign(kills, miniature=yolanda)

        assert [(line.name, line.value) for line in drawn(yolanda)[0].counters] == [
            ("XP", 61),
            ("Kill Count", 0),
        ]

    def test_the_line_follows_the_tally(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), +5)

        assert drawn(yolanda)[0].counters[0].value == 66

    def test_xp_leads_however_the_card_holds_them(self, gang, queen, kills):

        from n26.tests.sandbox.actions import assign

        yolanda = hire_with_option(gang, queen, "Yolanda")
        assign(kills, miniature=yolanda)

        assert [line.name for line in drawn(yolanda)[0].counters] == [
            "XP",
            "Kill Count",
        ]

    def test_a_line_carries_the_assignment_behind_it(self, gang, queen):
        """Counter controls need the stored assignment ID; library-only readings have none."""
        yolanda = hire_with_option(gang, queen, "Yolanda")

        assert drawn(yolanda)[0].counters[0].assignment_id == str(xp_row(yolanda).pk)

    def test_a_line_has_no_address_until_somebody_gives_it_one(self, gang, queen):
        """Card construction leaves editing links to the caller."""
        yolanda = hire_with_option(gang, queen, "Yolanda")

        assert drawn(yolanda)[0].counters[0].href == ""

    def test_an_xp_nobody_can_move_is_the_cell_and_not_a_line(self, gang, queen, kills):
        """Without an editing link, omit the duplicate XP counter line and retain the
        statline cell.
        """
        yolanda = hire_with_option(gang, queen, "Yolanda")
        from n26.tests.sandbox.actions import assign

        assign(kills, miniature=yolanda)
        card = drawn(yolanda)[0]

        assert [line.name for line in card.counter_lines] == ["Kill Count"]

    def test_it_is_a_line_again_once_it_can_be_moved(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        card = drawn(yolanda)[0]
        card.counters[0].href = "/somewhere/"

        assert [line.name for line in card.counter_lines] == ["XP"]


class TestMovingACounterByHand:
    """Counter controls target assignments, allowing one endpoint to handle model and gang
    counters.
    """

    def address(self, miniature):

        row = Assignment.objects.get(miniature=miniature, counter__name="XP")
        return reverse("n26-tally", args=[row.pk])

    def test_the_models_own_page_offers_the_control(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        page = client.get(reverse("n26-edit-fighter", args=[yolanda.pk]))

        assert self.address(yolanda) in page.content.decode()

    def test_the_gang_sheet_does_not(self, client, gang, queen, kills):
        """The roster displays counter values without per-model tally controls."""
        from n26.tests.sandbox.actions import assign

        yolanda = hire_with_option(gang, queen, "Yolanda")
        counted = assign(kills, miniature=yolanda)
        client.force_login(gang.owner)

        page = client.get(reverse("n26-gang", args=[gang.pk]))

        drawn_there = page.content.decode()

        assert "Kill Count" in drawn_there
        assert reverse("n26-tally", args=[counted.pk]) not in drawn_there

    def test_a_step_up_moves_it(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        client.post(self.address(yolanda), {"change": "1"})

        assert xp_row(yolanda).counter_value.value == 62

    def test_a_step_down_moves_it_back(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        client.post(self.address(yolanda), {"change": "-1"})

        assert xp_row(yolanda).counter_value.value == 60

    def test_it_floors_at_zero(self, client, gang, queen):

        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), -61)
        client.force_login(gang.owner)

        client.post(self.address(yolanda), {"change": "-1"})

        assert xp_row(yolanda).counter_value.value == 0

    def test_the_change_is_a_ledger_event(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        client.post(self.address(yolanda), {"change": "1"})

        event = xp_row(yolanda).ledger_events.filter(kind="tallied").latest("created")
        assert event.note == "+1 → 62"

    def test_it_returns_to_the_page_the_click_came_from(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        back = reverse("n26-edit-fighter", args=[yolanda.pk])
        client.force_login(gang.owner)

        response = client.post(self.address(yolanda), {"change": "1", "back": back})

        assert response.status_code == 302
        assert response["Location"] == back

    def test_it_will_not_be_sent_somewhere_else(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        response = client.post(
            self.address(yolanda), {"change": "1", "back": "https://elsewhere.test/"}
        )

        assert response["Location"] == reverse("n26-gang", args=[gang.pk])

    def test_somebody_elses_counter_is_not_theirs_to_move(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(User.objects.create_user("interloper"))

        response = client.post(self.address(yolanda), {"change": "1"})

        assert response.status_code == 404
        assert xp_row(yolanda).counter_value.value == 61

    def test_only_counters_are_tallied(self, client, gang, queen):

        from n26.tests.sandbox.actions import assign

        yolanda = hire_with_option(gang, queen, "Yolanda")
        not_a_counter = assign(create_rule("Bonded to the Rig"), miniature=yolanda)
        client.force_login(gang.owner)

        response = client.post(
            reverse("n26-tally", args=[not_a_counter.pk]), {"change": "1"}
        )

        assert response.status_code == 404

    def test_a_step_of_nothing_is_not_an_act(self, client, gang, queen):
        """Reject crafted zero-step requests without recording an event."""
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        response = client.post(self.address(yolanda), {"change": "0"})

        assert response.status_code == 404
        assert not xp_row(yolanda).ledger_events.filter(kind="tallied").exists()

    def test_a_step_past_what_the_column_holds_is_refused(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        response = client.post(self.address(yolanda), {"change": "99999999999"})

        assert response.status_code == 404
        assert xp_row(yolanda).counter_value.value == 61

    def test_a_change_that_is_not_a_number_is_no_address_at_all(
        self, client, gang, queen
    ):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        response = client.post(self.address(yolanda), {"change": "lots"})

        assert response.status_code == 404
        assert xp_row(yolanda).counter_value.value == 61


class TestMovingOneWithoutReloading:
    """HTMX tally requests replace the model card out of band. Ordinary form submissions
    redirect back to the page.
    """

    HTMX = {"HTTP_HX_REQUEST": "true"}

    def address(self, miniature):
        row = Assignment.objects.get(miniature=miniature, counter__name="XP")
        return reverse("n26-tally", args=[row.pk])

    def test_it_sends_back_the_card_addressed_to_its_host(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        page = client.post(self.address(yolanda), {"change": "1"}, **self.HTMX)

        drawn = page.content.decode()
        assert page.status_code == 200
        assert 'id="n26-model-card-host"' in drawn
        assert 'hx-swap-oob="true"' in drawn

    def test_the_card_it_sends_back_carries_the_new_value(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        page = client.post(self.address(yolanda), {"change": "1"}, **self.HTMX)

        assert "62" in page.content.decode()

    def test_the_card_it_sends_back_returns_to_the_tab_that_was_open(
        self, client, gang, queen
    ):
        """Preserve the current skills tab in refreshed choice and counter return URLs."""
        from urllib.parse import urlencode

        yolanda = hire_with_option(gang, queen, "Yolanda")
        # Reach the skill-offer threshold so refreshed choices have return URLs.
        tally(xp_row(yolanda), 14)
        client.force_login(gang.owner)
        here = f"{reverse('n26-edit-fighter', args=[yolanda.pk])}?skills=all"

        page = client.post(
            self.address(yolanda), {"change": "1", "back": here}, **self.HTMX
        )

        drawn = page.content.decode()
        assert "Choose skill" in drawn
        assert urlencode({"return": here}) in drawn
        pencil = BeautifulSoup(page.content, "html.parser").find(
            "a", attrs={"aria-label": "Edit XP"}
        )
        assert parse_qs(urlsplit(pencil["href"]).query)["back"] == [here]

    def test_the_card_it_sends_back_still_carries_the_rename(self, client, gang, queen):
        """Retain rename controls supplied by the edit view when redrawing the card."""
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        page = client.post(self.address(yolanda), {"change": "1"}, **self.HTMX)

        pencil = BeautifulSoup(page.content, "html.parser").find(
            "a", attrs={"aria-label": "Rename Yolanda"}
        )
        assert pencil is not None
        opened = client.get(pencil["href"])
        assert opened.status_code == 302
        assert opened.url == (
            f"{reverse('n26-edit-fighter', args=[yolanda.pk])}?rename={yolanda.pk}"
        )

    def test_the_card_it_sends_back_still_offers_sell(self, client, gang, queen):
        """Retain equipment sale controls when redrawing the edit card."""
        from n26.core.operations import operation
        from n26.core.reconcile import assert_reconciled
        from n26.library.authoring import create_wargear

        yolanda = hire_with_option(gang, queen, "Yolanda")
        sword = create_wargear("Sword", price=20)
        with operation(gang, actor=gang.owner) as op:
            held = op.buy(yolanda, thing=sword, paid=20)
        client.force_login(gang.owner)

        page = client.post(self.address(yolanda), {"change": "1"}, **self.HTMX)

        edit = reverse("n26-edit-fighter", args=[yolanda.pk])
        assert f"{edit}?sell={held.pk}" in page.content.decode()
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_the_card_it_sends_back_can_be_acted_on_again(self, client, gang, queen):

        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        page = client.post(self.address(yolanda), {"change": "1"}, **self.HTMX)

        assert self.address(yolanda) in page.content.decode()

    def test_the_card_it_sends_back_returns_to_the_page_not_the_act(
        self, client, gang, queen
    ):
        """Return links must target the originating page rather than the POST-only tally
        endpoint.
        """
        yolanda = hire_with_option(gang, queen, "Yolanda")
        page = reverse("n26-edit-fighter", args=[yolanda.pk])
        client.force_login(gang.owner)

        page_body = client.post(
            self.address(yolanda), {"change": "1", "back": page}, **self.HTMX
        )
        pencil = BeautifulSoup(page_body.content, "html.parser").find(
            "a", attrs={"aria-label": "Edit XP"}
        )

        assert parse_qs(urlsplit(pencil["href"]).query)["back"] == [page]
        assert (
            self.address(yolanda)
            not in parse_qs(urlsplit(pencil["href"]).query)["back"]
        )

    def test_the_page_itself_returns_to_itself(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        page = reverse("n26-edit-fighter", args=[yolanda.pk])
        client.force_login(gang.owner)

        pencil = BeautifulSoup(client.get(page).content, "html.parser").find(
            "a", attrs={"aria-label": "Edit XP"}
        )

        assert parse_qs(urlsplit(pencil["href"]).query)["back"] == [page]

    def test_a_refusal_redraws_nothing_and_says_why(self, client, gang, queen):
        """A refused tally returns no replacement card and reports its reason through
        HX-Trigger.
        """
        from unittest.mock import patch

        from n26.core.operations import Operation, Refusal

        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        with patch.object(Operation, "tally", side_effect=Refusal("No.")):
            page = client.post(self.address(yolanda), {"change": "1"}, **self.HTMX)

        assert page.status_code == 204
        assert "No." in page["HX-Trigger"]
        assert xp_row(yolanda).counter_value.value == 61

    def test_a_zero_step_is_turned_away_over_htmx_too(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        page = client.post(self.address(yolanda), {"change": "0"}, **self.HTMX)

        assert page.status_code == 404

    def test_without_htmx_the_same_act_is_a_redirect(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        back = reverse("n26-edit-fighter", args=[yolanda.pk])
        client.force_login(gang.owner)

        page = client.post(self.address(yolanda), {"change": "1", "back": back})

        assert page.status_code == 302
        assert page["Location"] == back

    def test_the_page_is_not_open_to_a_signed_out_reader(self, client, gang, queen):

        yolanda = hire_with_option(gang, queen, "Yolanda")

        page = client.get(reverse("n26-edit-fighter", args=[yolanda.pk]))

        assert page.status_code == 302
        assert "/accounts/login/" in page["Location"]

    def test_the_page_holds_the_host_the_update_addresses(self, client, gang, queen):
        """Out-of-band swaps require a matching host on the page."""
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        page = client.get(reverse("n26-edit-fighter", args=[yolanda.pk]))

        assert 'id="n26-model-card-host"' in page.content.decode()

    def test_every_counter_opens_the_amount_dialog_from_a_pencil(
        self, client, gang, queen, kills
    ):
        """The model edit page uses inline edit links to amount dialogs instead of
        one-point buttons.
        """
        from n26.tests.sandbox.actions import assign

        yolanda = hire_with_option(gang, queen, "Yolanda")
        assign(kills, miniature=yolanda)
        client.force_login(gang.owner)
        page = reverse("n26-edit-fighter", args=[yolanda.pk])

        soup = BeautifulSoup(client.get(page).content, "html.parser")

        for label, start in (
            ("Edit XP", self.address(yolanda)),
            ("Edit Kill Count", reverse("n26-tally", args=[kill_row(yolanda).pk])),
        ):
            pencil = soup.find("a", attrs={"aria-label": label})
            assert pencil["hx-get"] == pencil["href"]
            assert pencil["hx-swap"] == "none"
            assert pencil["href"].startswith(start)
            assert "text-accent-text" in pencil["class"]
            assert "inline-block" not in pencil["class"]
            assert pencil.select_one(".n26-icon-inline") is not None
        assert soup.find("button", attrs={"aria-label": "Add one to XP"}) is None
        assert (
            soup.find("button", attrs={"aria-label": "Add one to Kill Count"}) is None
        )
        assert soup.find(id="n26-campaign-state-dialog-host") is not None

    def test_the_pencil_saves_one_amount_and_closes_the_dialog(
        self, client, gang, queen
    ):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)
        page = reverse("n26-edit-fighter", args=[yolanda.pk])
        pencil = BeautifulSoup(client.get(page).content, "html.parser").find(
            "a", attrs={"aria-label": "Edit XP"}
        )

        opened = client.get(pencil["href"], **self.HTMX)

        dialog = BeautifulSoup(opened.content, "html.parser").find(
            id="n26-campaign-state-dialog"
        )
        assert dialog.find("form")["hx-post"] == self.address(yolanda)
        assert opened.context["counter_preview"]["value"] == 61
        assert opened.context["counter_preview"]["recorded"] == 61
        saved = client.post(
            self.address(yolanda),
            {"adjust": "1", "change": "15", "back": page},
            **self.HTMX,
        )

        body = BeautifulSoup(saved.content, "html.parser")
        assert "76" in body.find(id="n26-model-card-host").get_text()
        assert body.find("a", attrs={"aria-label": "Edit XP"}) is not None
        assert not body.find(id="n26-campaign-state-dialog-host").get_text(strip=True)
        assert saved["HX-Replace-Url"] == page
        assert (
            json.loads(saved["HX-Trigger"])["n26-toasts"][0]["message"]
            == "XP is now 76."
        )
        assert xp_row(yolanda).counter_value.value == 76

    def test_an_empty_amount_redraws_the_dialog_without_a_change(
        self, client, gang, queen
    ):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)
        page = reverse("n26-edit-fighter", args=[yolanda.pk])

        response = client.post(
            self.address(yolanda),
            {"adjust": "1", "change": "0", "back": page},
            **self.HTMX,
        )

        assert response.context["form"].errors["change"]
        assert BeautifulSoup(response.content, "html.parser").find(
            id="n26-campaign-state-dialog"
        )
        assert xp_row(yolanda).counter_value.value == 61

    def test_a_contribution_stays_outside_the_recorded_change(
        self, client, gang, queen, xp
    ):
        """Preview the effective total but apply the entered change only to the stored
        value.
        """
        yolanda = hire_with_option(gang, queen, "Yolanda")
        blooded = create_subtype("Blooded")
        modifier(
            "Blooded adds 5",
            targets_model(),
            ef_contributes_to_counter(xp, 5),
            carried_by=blooded,
        )
        assign(blooded, miniature=yolanda)
        client.force_login(gang.owner)
        page = reverse("n26-edit-fighter", args=[yolanda.pk])
        pencil = BeautifulSoup(client.get(page).content, "html.parser").find(
            "a", attrs={"aria-label": "Edit XP"}
        )

        opened = client.get(pencil["href"], **self.HTMX)

        assert (
            opened.context["counter_preview"]["value"],
            opened.context["counter_preview"]["recorded"],
        ) == (66, 61)
        saved = client.post(
            self.address(yolanda),
            {"adjust": "1", "change": "1", "back": page},
            **self.HTMX,
        )

        assert (
            json.loads(saved["HX-Trigger"])["n26-toasts"][0]["message"]
            == "XP is now 67."
        )
        assert xp_row(yolanda).counter_value.value == 62

    def test_equip_and_options_keep_the_one_point_buttons(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)

        for route in ("n26-equip", "n26-fighter-options"):
            response = client.get(reverse(route, args=[yolanda.pk]))
            soup = BeautifulSoup(response.content, "html.parser")
            name = "equip" if route == "n26-equip" else "model-options"
            host = soup.select_one(f'[data-react-name="{name}"]')
            page = json.loads(soup.find(id=host["data-react-props"]).string)
            card = page["model"]["card"] if route == "n26-equip" else page["card"]
            parts = [
                part
                for row in card["details"]
                for part in row["parts"]
                if part["kind"] == "counter"
            ]
            xp = next(part for part in parts if part["control"]["name"] == "XP")
            assert xp["control"]["assignment"] and xp["control"]["href"]
            assert xp["value"] == 61 and xp["control"]["tallied"] == 61

    def test_without_script_the_pencil_is_the_amount_page(self, client, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        client.force_login(gang.owner)
        page = reverse("n26-edit-fighter", args=[yolanda.pk])
        pencil = BeautifulSoup(client.get(page).content, "html.parser").find(
            "a", attrs={"aria-label": "Edit XP"}
        )

        opened = client.get(pencil["href"])

        assert opened.status_code == 200
        assert "Edit XP" in opened.content.decode()
        saved = client.post(
            self.address(yolanda), {"adjust": "1", "change": "4", "back": page}
        )
        assert saved.status_code == 302
        assert saved.url == page
        assert xp_row(yolanda).counter_value.value == 65


class TestTheNoteFitsTheColumn:
    """Truncate long reasons to the ledger note’s maximum length while preserving the
    counter change and resulting value.
    """

    def note_of(self, miniature):
        return (
            xp_row(miniature)
            .ledger_events.filter(kind="tallied")
            .latest("created")
            .note
        )

    def test_a_long_reason_is_cut_to_fit(self, gang, queen):
        from n26.core.models import LedgerEvent

        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), +1, note="x" * 400)

        held = self.note_of(yolanda)
        assert len(held) <= LedgerEvent._meta.get_field("note").max_length
        assert held.startswith("+1 → 62: xxx")
        assert held.endswith("…")

    def test_the_movement_survives_it(self, gang, queen):

        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), -1, note="y" * 400)

        assert self.note_of(yolanda).startswith("-1 → 60: ")

    def test_a_reason_that_fits_is_left_alone(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), +1, note="won a battle")

        assert self.note_of(yolanda) == "+1 → 62: won a battle"


class TestTheOtherSurfaces:
    """Text and print use visible counter lines. XP appears once in the statline even when
    the source card has editing controls.
    """

    def test_the_text_card_lists_them(self, gang, queen, kills):
        from n26.core.render_text import render_model_card
        from n26.tests.sandbox.actions import assign

        yolanda = hire_with_option(gang, queen, "Yolanda")
        assign(kills, miniature=yolanda)
        tally(kill_row(yolanda), +3)

        assert "Kill Count: 3" in "\n".join(render_model_card(drawn(yolanda)[0]))

    def test_the_text_card_keeps_xp_to_its_own_line(self, gang, queen):
        from n26.core.render_text import render_model_card

        yolanda = hire_with_option(gang, queen, "Yolanda")

        told = render_model_card(drawn(yolanda)[0])
        assert len([line for line in told if "XP" in line]) == 1

    def test_the_print_sheet_leads_with_them(self, gang, queen, kills):
        from n26.core.printing import detail_groups
        from n26.tests.sandbox.actions import assign

        yolanda = hire_with_option(gang, queen, "Yolanda")
        assign(kills, miniature=yolanda)

        groups = detail_groups(drawn(yolanda)[0])
        assert (groups[0].label, groups[0].text) == ("Kill Count", "0")

    def test_the_print_sheet_says_xp_once(self, gang, queen):

        from n26.core.printing import detail_groups

        yolanda = hire_with_option(gang, queen, "Yolanda")

        assert not [
            group for group in detail_groups(drawn(yolanda)[0]) if group.label == "XP"
        ]

    def test_neither_repeats_xp_for_a_card_that_could_be_edited(self, gang, queen):
        """Print and text omit the editing-only XP counter line."""
        from n26.core.printing import detail_groups
        from n26.core.render_text import render_model_card
        from n26.core.views.owned import link_counters

        yolanda = hire_with_option(gang, queen, "Yolanda")
        card = drawn(yolanda)[0]
        link_counters(card)

        assert not [group for group in detail_groups(card) if group.label == "XP"]
        assert len([line for line in render_model_card(card) if "XP" in line]) == 1


class TestWhatTheHistorySays:
    """History shows the actual counter change, resulting value and optional reason."""

    def told(self, gang):
        from n26.core import history

        return [
            "".join(span.text for span in act.spans)
            for act in history.build(gang, viewer=gang.owner)
        ]

    def test_it_says_what_moved_and_where_it_landed(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), +5)

        assert any(
            "changed XP" in told and "+5, now 66" in told for told in self.told(gang)
        )

    def test_a_step_that_hit_the_floor_says_where_it_stopped(self, gang, queen):
        """History records the actual reduction after applying the zero floor."""
        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), -100)

        assert any("-61, now 0" in told for told in self.told(gang))

    def test_what_caused_it_rides_along(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), +5, note="won a battle")

        assert any("(won a battle)" in told for told in self.told(gang))

    def test_the_note_is_not_printed_under_the_sentence_as_well(self, gang, queen):

        from n26.core import history

        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), +5, note="won a battle")

        # Join history spans using their existing spacing.
        tallied = [
            act
            for act in history.build(gang, viewer=gang.owner)
            if "changed XP" in "".join(span.text for span in act.spans)
        ]
        assert tallied and all(not act.note for act in tallied)


class TestEffectsHangOffValues:
    def test_below_the_threshold_nothing_shows(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        card, computed = drawn(yolanda)

        assert computed.choices == []
        assert card.rules == []

    def test_the_offer_appears_when_xp_crosses_75(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), +14)

        card, computed = drawn(yolanda)
        (slot,) = computed.choices
        assert slot.is_resolved is False
        assert card.rules == []  # The Veteran rule requires 100 XP.

    def test_the_title_appears_at_100_and_names_its_source(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), +39)

        card, _ = drawn(yolanda)
        (title,) = card.rules
        assert title.name == "Veteran"
        assert title.provenance.computed is True

    def test_it_withdraws_if_the_value_drops(self, gang, queen):
        yolanda = hire_with_option(gang, queen, "Yolanda")
        row = xp_row(yolanda)
        tally(row, +39)
        tally(row, -50)

        card, computed = drawn(yolanda)
        assert computed.choices == []
        assert card.rules == []

    def test_the_plan_shows_the_threshold_round(self, gang, queen):
        """The execution plan identifies the unmet threshold and evaluation round."""
        yolanda = hire_with_option(gang, queen, "Yolanda")
        _, computed = drawn(yolanda)

        step = next(s for s in computed.plan if "offers a choice" in s.effect)
        assert step.ran_in == 1  # Conditioned scopes wait for settled facts.
        assert step.outcome == "skipped"
        assert "at XP 75+" in step.scope


class TestARuleThatMovesACounter:
    """Assigning a carrier applies its stored counter operation once. Removing the carrier
    does not reverse changes to a pre-existing counter.
    """

    @pytest.fixture
    def leader_mark(self, xp):
        from n26.tests.sandbox.actions import create_subtype, op_changes_counter

        subtype = create_subtype("Chosen Leader")
        modifier(
            "The chosen Leader starts with 61 XP",
            targets_model(),
            op_changes_counter(xp, "set", 61),
            carried_by=subtype,
        )
        return subtype

    def test_assigning_the_carrier_sets_the_counter(self, gang, queen, leader_mark):
        from n26.core.reconcile import assert_reconciled
        from n26.tests.sandbox.actions import assign

        yolanda = hire_with_option(gang, queen, "Yolanda")
        tally(xp_row(yolanda), -51)  # Reduce stored XP to 10 before assigning the
        # carrier.
        assign(leader_mark, miniature=yolanda)

        assert xp_row(yolanda).counter_value.value == 61
        assert_reconciled(gang)

    def test_the_move_is_a_ledger_event_naming_its_source(
        self, gang, queen, leader_mark
    ):
        from n26.tests.sandbox.actions import assign

        yolanda = hire_with_option(gang, queen, "Yolanda")
        assign(leader_mark, miniature=yolanda)

        event = xp_row(yolanda).ledger_events.filter(kind="tallied").latest("created")
        # Include the change, resulting value and carrier name in the event note.
        assert event.note == "+0 → 61: Chosen Leader"

    def test_add_and_subtract_move_it_relative(self, gang, xp, make_profile):
        from n26.tests.sandbox.actions import (
            assign,
            create_default_set,
            create_subtype,
            op_changes_counter,
        )

        profile = make_profile("Plain Ganger", price=10)
        profile.built_ins = create_default_set("Kit", members=[(xp, {"amount": 10})])
        profile.save()
        fighter = hire_with_option(gang, profile, "Vex")

        bloodied = create_subtype("Bloodied")
        modifier(
            "Bloodied grants 3 XP",
            targets_model(),
            op_changes_counter(xp, "add", 3),
            carried_by=bloodied,
        )
        humbled = create_subtype("Humbled")
        modifier(
            "Humbled takes 100 XP",
            targets_model(),
            op_changes_counter(xp, "subtract", 100),
            carried_by=humbled,
        )

        assign(bloodied, miniature=fighter)
        assert xp_row(fighter).counter_value.value == 13
        assign(humbled, miniature=fighter)

        assert xp_row(fighter).counter_value.value == 0

    def test_a_bearer_without_the_counter_gains_it(self, gang, xp, make_profile):
        """A counter operation creates a missing counter assignment with provenance
        pointing to its carrier.
        """
        from n26.tests.sandbox.actions import (
            assign,
            create_subtype,
            op_changes_counter,
        )

        profile = make_profile("Counterless", price=10)
        fighter = hire_with_option(gang, profile, "Nix")

        marked = create_subtype("Marked")
        modifier(
            "Marked starts the count at 5",
            targets_model(),
            op_changes_counter(xp, "set", 5),
            carried_by=marked,
        )
        carrier = assign(marked, miniature=fighter)

        row = xp_row(fighter)
        assert row.counter_value.value == 5
        assert row.caused_by == carrier

    def test_taking_the_carrier_back_does_not_move_it_back(
        self, gang, queen, leader_mark
    ):
        from n26.tests.sandbox.actions import assign, remove

        yolanda = hire_with_option(gang, queen, "Yolanda")
        carrier = assign(leader_mark, miniature=yolanda)
        remove(carrier)

        # The pre-existing counter and its changed value survive removal of the carrier.
        assert xp_row(yolanda).counter_value.value == 61


class TestWhatAModifierContributes:
    """Counter contributions are computed while their carrier remains effective. They add
    to stored values without creating counter assignments or tally events.
    """

    @pytest.fixture
    def budget(self, db):
        return create_counter("Founding budget")

    @pytest.fixture
    def plain(self, make_profile):
        return make_profile("Plain Ganger", price=10)

    def carrier_adding(self, budget, amount, name):
        """Create a subtype with one computed counter contribution."""
        subtype = create_subtype(name)
        modifier(
            f"{name} adds {amount}",
            targets_model(),
            ef_contributes_to_counter(budget, amount),
            carried_by=subtype,
        )
        return subtype

    def reading(self, miniature, counter):
        _, computed = drawn(miniature)
        return sum(
            contribution.amount
            for contribution in computed.counter_contributions
            if contribution.counter == counter
        )

    def test_a_counter_nobody_holds_still_reads(self, gang, plain, budget):

        vex = hire_with_option(gang, plain, "Vex")
        assign(self.carrier_adding(budget, 4, "Chosen"), miniature=vex)

        card, _ = drawn(vex)
        (line,) = [line for line in card.counters if line.name == "Founding budget"]
        assert (line.value, line.assignment_id) == (4, "")

    def test_it_is_added_to_what_is_stored(self, gang, queen, xp):

        yolanda = hire_with_option(gang, queen, "Yolanda")
        assign(self.carrier_adding(xp, 5, "Blooded"), miniature=yolanda)

        card, _ = drawn(yolanda)
        (line,) = [line for line in card.counters if line.name == "XP"]
        assert line.value == 66

        assert xp_row(yolanda).counter_value.value == 61

    def test_a_contributed_xp_moves_the_statline_cell(self, gang, plain, xp):
        """The XP statline cell includes contributions even without a stored XP assignment."""
        vex = hire_with_option(gang, plain, "Vex")
        assign(self.carrier_adding(xp, 7, "Blooded"), miniature=vex)

        card, _ = drawn(vex)
        (line,) = [line for line in card.counters if line.name == "XP"]
        assert (line.value, line.assignment_id) == (7, "")
        assert (card.xp, card.xp_display) == (7, "7/\u2013")
        # The effective XP reading has no stored assignment to tally.
        assert not Assignment.objects.filter(miniature=vex, counter__name="XP").exists()

    def test_a_contributed_reading_offers_no_way_to_take_one_off(
        self, client, gang, plain, kills
    ):
        """A negative adjustment cannot reduce a zero stored value, even when contributions
        make the displayed total positive.
        """
        vex = hire_with_option(gang, plain, "Vex")
        counted = assign(kills, miniature=vex)
        assign(self.carrier_adding(kills, 4, "Chosen"), miniature=vex)
        client.force_login(gang.owner)
        page = reverse("n26-edit-fighter", args=[vex.pk])
        pencil = BeautifulSoup(client.get(page).content, "html.parser").find(
            "a", attrs={"aria-label": "Edit Kill Count"}
        )

        response = client.post(
            pencil["href"],
            {"adjust": "1", "change": "-1", "back": page},
            HTTP_HX_REQUEST="true",
        )

        assert "already 0" in response.context["form"].errors["change"][0]

        assert getattr(counted, "counter_value", None) is None

    def test_a_tallied_reading_can_still_be_reduced(self, client, gang, plain, kills):

        vex = hire_with_option(gang, plain, "Vex")
        counted = assign(kills, miniature=vex)
        tally(counted, +1)
        assign(self.carrier_adding(kills, 4, "Chosen"), miniature=vex)
        client.force_login(gang.owner)
        page = reverse("n26-edit-fighter", args=[vex.pk])

        saved = client.post(
            reverse("n26-tally", args=[counted.pk]),
            {"adjust": "1", "change": "-1", "back": page},
            HTTP_HX_REQUEST="true",
        )

        counted.counter_value.refresh_from_db()
        assert counted.counter_value.value == 0
        assert (
            json.loads(saved["HX-Trigger"])["n26-toasts"][0]["message"]
            == "Kill Count is now 4."
        )

    def test_two_carriers_add_up(self, gang, plain, budget):
        vex = hire_with_option(gang, plain, "Vex")
        assign(self.carrier_adding(budget, 4, "Chosen"), miniature=vex)
        assign(self.carrier_adding(budget, 1, "Clanless"), miniature=vex)

        assert self.reading(vex, budget) == 5

    def test_taking_the_carrier_away_takes_the_figure_with_it(
        self, gang, plain, budget
    ):
        vex = hire_with_option(gang, plain, "Vex")
        carrier = assign(self.carrier_adding(budget, 4, "Chosen"), miniature=vex)
        assert self.reading(vex, budget) == 4

        remove(carrier)

        assert self.reading(vex, budget) == 0
        card, _ = drawn(vex)
        assert [line for line in card.counters if line.name == "Founding budget"] == []

    def test_a_cancelled_carrier_contributes_nothing(self, gang, plain, budget):
        """Suppressing a carrier removes its contribution in the same computation."""
        chosen = self.carrier_adding(budget, 4, "Chosen")
        renounced = create_rule("Renounced")
        modifier(
            "Renounced cancels Chosen",
            targets_model(),
            removes(chosen),
            carried_by=renounced,
        )
        vex = hire_with_option(gang, plain, "Vex")
        assign(chosen, miniature=vex)
        assert self.reading(vex, budget) == 4

        assign(renounced, miniature=vex)

        assert self.reading(vex, budget) == 0

    def test_nothing_is_written_down(self, gang, plain, budget):

        from n26.core.models import LedgerEvent

        vex = hire_with_option(gang, plain, "Vex")
        assign(self.carrier_adding(budget, 4, "Chosen"), miniature=vex)
        drawn(vex)

        assert not Assignment.objects.filter(
            miniature=vex, counter__name="Founding budget"
        ).exists()
        assert not LedgerEvent.objects.filter(gang=gang, kind="tallied").exists()


class TestAThresholdReadsTheWholeReading:
    """Counter thresholds include computed contributions as well as stored values."""

    @pytest.fixture
    def budget(self, db):
        return create_counter("Founding budget")

    @pytest.fixture
    def plain(self, make_profile):
        return make_profile("Plain Ganger", price=10)

    @pytest.fixture
    def wealthy(self, gang_type, budget):
        """Grant a rule while the effective budget is at least five."""
        modifier(
            "Well funded at 5",
            targets_every_model(counter_at_least(budget, 5)),
            adds(create_rule("Well funded")),
            carried_by=gang_type,
        )

    @pytest.fixture
    def chosen(self, budget):
        subtype = create_subtype("Chosen")
        modifier(
            "Chosen adds 5",
            targets_model(),
            ef_contributes_to_counter(budget, 5),
            carried_by=subtype,
        )
        return subtype

    def test_it_fires_on_a_contribution_alone(self, gang, plain, wealthy, chosen):
        vex = hire_with_option(gang, plain, "Vex")
        assert drawn(vex)[0].rules == []

        assign(chosen, miniature=vex)

        assert [rule.name for rule in drawn(vex)[0].rules] == ["Well funded"]

    def test_it_stops_when_the_carrier_goes(self, gang, plain, wealthy, chosen):
        vex = hire_with_option(gang, plain, "Vex")
        carrier = assign(chosen, miniature=vex)
        remove(carrier)

        assert drawn(vex)[0].rules == []


class TestWhatTheGangHoldsReachesTheRanks:
    """A gang-held affiliation contributes to model counters only where its scope matches
    their ranks.
    """

    @pytest.fixture
    def budget(self, db):
        return create_counter("Founding budget")

    @pytest.fixture
    def ranks(self, db):
        return create_subtype("Leader"), create_subtype("Champion")

    @pytest.fixture
    def plain(self, make_profile):
        return make_profile("Plain Ganger", price=10)

    @pytest.fixture
    def affiliated(self, gang, budget, ranks):
        clanless = create_affiliation(
            "Clanless",
            effects=[
                (
                    targets_every_model(has_subtypes(*ranks)),
                    ef_contributes_to_counter(budget, 1),
                )
            ],
        )
        assign(clanless, gang=gang)
        return clanless

    def reading(self, miniature, counter):
        _, computed = drawn(miniature)
        return sum(
            contribution.amount
            for contribution in computed.counter_contributions
            if contribution.counter == counter
        )

    def test_it_reaches_every_model_of_a_named_rank_and_nobody_else(
        self, gang, plain, budget, ranks, affiliated
    ):
        leader, champion = ranks
        boss = hire_with_option(gang, plain, "Boss")
        assign(leader, miniature=boss)
        mags = hire_with_option(gang, plain, "Mags")
        assign(champion, miniature=mags)
        vex = hire_with_option(gang, plain, "Vex")

        assert {
            member.name: self.reading(member, budget) for member in (boss, mags, vex)
        } == {"Boss": 1, "Mags": 1, "Vex": 0}

    def test_the_gang_itself_reads_nothing(self, gang, budget, ranks, affiliated):
        """A model-targeting scope does not contribute to the gang’s own counter reading."""
        from n26.core.card import build_gang_card
        from n26.core.effects import compute_gang

        card = build_gang_card(gang)
        index = build_modifier_index([node.assignable for node in card.all_nodes()])

        assert compute_gang(card, index).counters == []


class TestACounterOnlyRulesRead:
    """A counter with drawn=False remains available to scopes but is omitted from display
    and editing controls.
    """

    @pytest.fixture
    def budget(self, db):
        return create_counter("Founding budget", drawn=False)

    @pytest.fixture
    def plain(self, make_profile):
        return make_profile("Plain Ganger", price=10)

    @pytest.fixture
    def chosen(self, budget):
        subtype = create_subtype("Chosen")
        modifier(
            "Chosen adds 4",
            targets_model(),
            ef_contributes_to_counter(budget, 4),
            carried_by=subtype,
        )
        return subtype

    def test_the_card_holds_it(self, gang, plain, chosen):
        vex = hire_with_option(gang, plain, "Vex")
        assign(chosen, miniature=vex)

        card, _ = drawn(vex)
        assert [(line.name, line.value) for line in card.counters] == [
            ("Founding budget", 4)
        ]

    def test_nothing_draws_it(self, gang, plain, chosen):
        vex = hire_with_option(gang, plain, "Vex")
        assign(chosen, miniature=vex)

        card, _ = drawn(vex)
        assert card.counter_lines == []

    def test_the_print_sheet_and_the_text_leave_it_out(self, gang, plain, chosen):
        from n26.core.printing import detail_groups
        from n26.core.render_text import render_model_card

        vex = hire_with_option(gang, plain, "Vex")
        assign(chosen, miniature=vex)
        card, _ = drawn(vex)

        assert not [
            group for group in detail_groups(card) if group.label == "Founding budget"
        ]
        assert not [
            line for line in render_model_card(card) if "Founding budget" in line
        ]

    def test_a_stored_one_is_given_no_control(self, gang, plain, budget, xp):

        from n26.core.views.owned import link_counters

        vex = hire_with_option(gang, plain, "Vex")
        assign(budget, miniature=vex)
        assign(xp, miniature=vex)
        card, _ = drawn(vex)
        link_counters(card)

        addressed = {line.name: bool(line.href) for line in card.counters}
        assert addressed == {"Founding budget": False, "XP": True}

    def test_the_fighter_page_does_not_show_it(
        self, client, gang, plain, budget, kills
    ):
        """Keep a visible counter alongside the hidden counter to isolate the drawn flag."""
        vex = hire_with_option(gang, plain, "Vex")
        counted = assign(budget, miniature=vex)
        assign(kills, miniature=vex)
        client.force_login(gang.owner)

        page = client.get(reverse("n26-edit-fighter", args=[vex.pk])).content.decode()

        assert "Kill Count" in page
        assert "Founding budget" not in page
        assert reverse("n26-tally", args=[counted.pk]) not in page

    def test_the_gang_sheet_does_not_show_the_gangs_own(self, gang, budget):
        from n26.core.render import render_gang

        assign(budget, gang=gang)

        assert render_gang(gang).counters == []

    def test_a_rule_still_reads_it(self, gang, plain, budget, gang_type):
        modifier(
            "Well funded at 3",
            targets_every_model(counter_at_least(budget, 3)),
            adds(create_rule("Well funded")),
            carried_by=gang_type,
        )
        vex = hire_with_option(gang, plain, "Vex")
        counted = assign(budget, miniature=vex)
        tally(counted, +3)

        assert [rule.name for rule in drawn(vex)[0].rules] == ["Well funded"]


class TestAuthoringAContribution:
    def test_the_verb_makes_the_effect(self, db):
        from n26.library.models import ContributesToCounter

        counter = create_counter("Trading Post visit contribution")
        effect = ef_contributes_to_counter(counter, 2)

        assert isinstance(effect, ContributesToCounter)
        assert (effect.counter, effect.amount) == (counter, 2)
        assert str(effect) == "adds 2 to Trading Post visit contribution"

    def test_it_lands_in_the_modifiers_own_column(self, db):
        counter = create_counter("Trading Post visit contribution")
        row = modifier(
            "Leader brings 2 TP",
            targets_model(),
            ef_contributes_to_counter(counter, 2),
            carried_by=create_subtype("Leader"),
        )

        assert row.contributes_to_counter is not None
        assert str(row.effect) == "adds 2 to Trading Post visit contribution"

    def test_the_plan_says_what_it_did(self, gang, make_profile):
        counter = create_counter("Trading Post visit contribution")
        leader = create_subtype("Leader")
        modifier(
            "Leader brings 2 TP",
            targets_model(),
            ef_contributes_to_counter(counter, 2),
            carried_by=leader,
        )
        vex = hire_with_option(gang, make_profile("Plain Ganger", price=10), "Vex")
        assign(leader, miniature=vex)

        _, computed = drawn(vex)
        (step,) = [
            step
            for step in computed.plan
            if step.effect == "adds 2 to Trading Post visit contribution"
        ]
        assert (step.outcome, step.round) == ("reached", 0)

    def test_the_reach_column_says_it_in_words(self, db):
        from n26.library import prose

        counter = create_counter("Trading Post visit contribution")
        carrier = create_subtype("Leader")
        row = modifier(
            "Leader brings 2 TP",
            targets_model(),
            ef_contributes_to_counter(counter, 2),
            carried_by=carrier,
        )

        said = prose.sentence_for(row, carriage=prose.SUBTYPE, thing=carrier)

        assert "2 is added to" in said.text
        assert "Trading Post visit contribution reading" in said.text
