"""Authors decide whether a slot's empty choice can be hidden."""

from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.models import DismissedOffer
from n26.core.render import render_gang
from n26.core.views.choose import find_slot, link_slots, settle_dismissed
from n26.library.authoring import (
    create_pickable,
    create_picklist,
    create_slot,
    create_slot_type,
    revise,
)
from n26.tests.sandbox.actions import assign, found_gang, hire

pytestmark = pytest.mark.django_db


@pytest.fixture
def gang(gang_type, owner):
    return found_gang("Choice keepers", gang_type, owner=owner)


@pytest.fixture(params=["model", "gang"])
def choice(request, gang, make_profile):
    kind = create_slot_type("Custom choice")
    pick = create_pickable("First option", kind)
    picks = create_picklist("Options", kind, members=[pick])
    slot = create_slot("Available choice", kind, picks)
    miniature = None
    if request.param == "model":
        miniature = hire(gang, make_profile("Ganger"), "Rook")
        assign(slot, miniature=miniature)
        edit = reverse("n26-edit-fighter", args=[miniature.pk])
    else:
        assign(slot, gang=gang)
        edit = reverse("n26-edit-gang", args=[gang.pk]) + "?tab=dismissed"
    sheet = render_gang(gang)
    holder = sheet.models[0] if miniature else sheet
    link_slots(gang, holder)
    line = next(line for line in holder.questions if line.kind_label == slot.name)
    return SimpleNamespace(
        slot=slot, kind=kind, pick=pick, line=line, miniature=miniature, edit=edit
    )


def dismiss_url(gang, choice):
    return reverse("n26-dismiss-offer", args=[gang.pk, choice.line.key])


def restore_url(gang, choice):
    return reverse("n26-restore-offer", args=[gang.pk, choice.line.key])


class TestChoicesThatStayAvailable:
    def test_the_choice_link_stays_without_a_dismiss_button(
        self, client, owner, gang, choice
    ):
        client.force_login(owner)
        revise(choice.slot, allow_dismissal=False)
        addresses = [reverse("n26-gang", args=[gang.pk])]
        if choice.miniature:
            addresses.append(choice.edit)
        for address in addresses:
            body = client.get(address).content.decode()
            assert choice.line.href in body
            assert dismiss_url(gang, choice) not in body

    def test_a_stale_dismiss_request_is_refused(self, client, owner, gang, choice):
        client.force_login(owner)
        revise(choice.slot, allow_dismissal=False)
        response = client.post(
            dismiss_url(gang, choice), {"back": choice.edit}, follow=True
        )
        assert response.status_code == 200
        assert "This choice must stay available." in response.content.decode()
        assert not DismissedOffer.objects.filter(gang=gang).exists()

    def test_a_previously_dismissed_choice_becomes_available_again(
        self, client, owner, gang, choice
    ):
        client.force_login(owner)
        client.post(dismiss_url(gang, choice))
        assert DismissedOffer.objects.filter(gang=gang).exists()
        revise(choice.slot, allow_dismissal=False)

        sheet = render_gang(gang)
        settle_dismissed(gang, hide_only=(sheet, *sheet.models))
        holder = sheet.models[0] if choice.miniature else sheet
        line = next(line for line in holder.questions if line.key == choice.line.key)
        assert line.dismissed is False
        assert line.allow_dismissal is False

        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert choice.line.href in body
        edit = client.get(choice.edit).content.decode()
        assert restore_url(gang, choice) not in edit
        assert dismiss_url(gang, choice) not in edit
        if choice.miniature:
            assert choice.line.href in edit

    def test_players_can_still_make_the_choice(self, client, owner, gang, choice):
        client.force_login(owner)
        revise(choice.slot, allow_dismissal=False)
        response = client.post(
            choice.line.href, {"thing": f"library.pickable:{choice.pick.pk}"}
        )
        assert response.status_code == 302
        assert find_slot(gang, choice.line.key).slot.chosen_name == choice.pick.name

    def test_allowing_dismissal_again_restores_the_normal_controls(
        self, client, owner, gang, choice
    ):
        client.force_login(owner)
        revise(choice.slot, allow_dismissal=False)
        revise(choice.slot, allow_dismissal=True)
        client.post(dismiss_url(gang, choice))
        assert DismissedOffer.objects.filter(gang=gang).exists()
        body = client.get(choice.edit).content.decode()
        assert restore_url(gang, choice) in body
        client.post(restore_url(gang, choice))
        assert not DismissedOffer.objects.filter(gang=gang).exists()


def test_protected_choices_do_not_add_queries_per_model(gang, make_profile):
    kind = create_slot_type("Custom choice")
    picks = create_picklist("Options", kind)
    slot = create_slot("Available choice", kind, picks, allow_dismissal=False)
    profile = make_profile("Ganger")

    def add_model(name):
        miniature = hire(gang, profile, name)
        assign(slot, miniature=miniature)

    def draw():
        sheet = render_gang(gang)
        settle_dismissed(gang, hide_only=(sheet, *sheet.models))
        link_slots(gang, sheet, *sheet.models)
        assert all(
            not line.allow_dismissal
            for card in sheet.models
            for line in card.questions
            if line.kind_label == slot.name
        )

    add_model("Rook")
    with CaptureQueriesContext(connection) as one:
        draw()
    for name in ("Finch", "Wren", "Jay", "Crow"):
        add_model(name)
    with CaptureQueriesContext(connection) as five:
        draw()
    assert len(five) == len(one)


def test_an_earlier_dismissal_cannot_hide_a_protected_injury_control(
    client, owner, gang, make_profile
):
    kind = create_slot_type("Custom injury", is_lasting_effect=True)
    picks = create_picklist("Custom injury table", kind)
    slot = create_slot("Record injuries", kind, picks)
    miniature = hire(gang, make_profile("Ganger"), "Rook")
    assign(slot, miniature=miniature)
    edit_url = reverse("n26-edit-fighter", args=[miniature.pk])
    client.force_login(owner)
    from bs4 import BeautifulSoup

    page = BeautifulSoup(client.get(edit_url).content, "html.parser")
    dismiss = page.find("form", action=lambda url: url and url.endswith("/dismiss/"))
    assert dismiss is not None
    client.post(dismiss["action"])
    assert DismissedOffer.objects.filter(gang=gang).exists()
    revise(slot, allow_dismissal=False)

    page = BeautifulSoup(client.get(edit_url).content, "html.parser")
    link = page.find("a", href=lambda url: url and "/choose/" in url)
    assert link is not None
    assert "Record injuries" in page.get_text()
    assert page.find("form", action=dismiss["action"]) is None
    assert (
        "Record injuries"
        not in client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    )
