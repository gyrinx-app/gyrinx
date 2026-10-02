"""The owner's name dialog saves without rebuilding the card or editors."""

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.models import LedgerEvent
from n26.core.reconcile import assert_reconciled
from n26.library.models import Skill
from n26.tests.sandbox.actions import (
    create_category,
    create_collection,
    create_skill,
    found_gang,
    hire_with_option,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def vex(gang_type, make_profile, make_statline):
    owner = User.objects.create_user("name-editor")
    gang = found_gang("The Ashen Choir", gang_type, owner=owner, budget=1000)
    profile = make_profile("Ganger", price=100)
    make_statline(profile)
    return hire_with_option(gang, profile, "Vex", paid=80, rating=100)


def rename_url(vex):
    return reverse("n26-rename-fighter", args=[vex.pk]) + "?back=edit"


def edit_url(vex):
    return reverse("n26-edit-fighter", args=[vex.pk])


class TestTheNameDialog:
    def test_the_edit_pencil_fetches_only_the_dialog(self, client, vex):
        client.force_login(vex.gang.owner)
        page = client.get(edit_url(vex))
        pencil = BeautifulSoup(page.content, "html.parser").find(
            "a", attrs={"aria-label": "Rename Vex"}
        )
        assert pencil["hx-get"] == rename_url(vex)
        assert pencil["hx-swap"] == "none"
        assert pencil["id"] == f"n26-name-pencil-{vex.pk}"
        response = client.get(rename_url(vex), HTTP_HX_REQUEST="true")
        assert response.context["rename_dialog"]["value"] == "Vex"
        assert response.context["rename_dialog"]["csrfToken"]
        assert response["HX-Replace-Url"] == f"{edit_url(vex)}?rename={vex.pk}"
        assert "n26-model-card-host" not in response.content.decode()

    def test_reload_draws_the_same_dialog(self, client, vex):
        client.force_login(vex.gang.owner)
        response = client.get(edit_url(vex), {"rename": str(vex.pk)})
        assert response.context["rename_dialog"]["value"] == "Vex"

    @pytest.mark.parametrize("name", [" ", "x" * 201])
    def test_server_validation_keeps_the_draft_in_the_dialog(self, client, vex, name):
        client.force_login(vex.gang.owner)
        response = client.post(rename_url(vex), {"name": name}, HTTP_HX_REQUEST="true")
        assert response.status_code == 200
        assert response.context["rename_dialog"]["value"] == name
        assert response.context["rename_dialog"]["errors"]
        vex.refresh_from_db()
        assert vex.name == "Vex"

    def test_save_updates_displayed_names_and_preserves_the_card_and_editors(
        self, client, vex
    ):
        client.force_login(vex.gang.owner)
        response = client.post(
            rename_url(vex), {"name": "Karn"}, HTTP_HX_REQUEST="true"
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        for name in ["name", "title", "breadcrumb"]:
            target = soup.find(id=f"n26-model-{name}-{vex.pk}")
            assert target["hx-swap-oob"] == "true"
            assert "Karn" in target.get_text()
        assert soup.title.get_text() == "Karn | Gyrinx"
        pencil = soup.find("a", attrs={"aria-label": "Rename Karn"})
        assert pencil["hx-get"] == rename_url(vex)
        assert soup.find(id="n26-model-card-host") is None
        assert soup.find("textarea") is None
        assert not soup.find(id="n26-rename-dialog-host").get_text(strip=True)
        assert soup.find(id="n26-fighter-switcher")["hx-swap-oob"] == "true"
        assert soup.find(id="n26-gang-figures")["hx-swap-oob"] == "true"
        assert "Override Karn" in soup.find(id=f"n26-model-rating-{vex.pk}").decode()
        assert response["HX-Replace-Url"] == edit_url(vex)
        vex.refresh_from_db()
        assert vex.name == "Karn"
        assert vex.rating == 100
        event = vex.ledger_events.get(kind=LedgerEvent.Kind.RENAMED)
        assert event.actor == vex.gang.owner
        assert event.note == "Vex → Karn"
        assert_reconciled(vex.gang)

    def test_an_empty_skills_tab_keeps_name_independent_copy_after_rename(
        self, client, vex
    ):
        category = create_category("Skills", "Agility")
        create_skill("Catfall", category=category)
        create_collection("Skills & Powers", contains=[Skill])
        client.force_login(vex.gang.owner)
        page = client.get(edit_url(vex), {"skills": "their-sets"})
        skills = BeautifulSoup(page.content, "html.parser").find(id="n26-skills-box")
        assert skills is not None
        assert (
            "No skill set has been put in a tier for this model." in skills.get_text()
        )
        assert "Vex" not in skills.get_text()
        response = client.post(
            rename_url(vex), {"name": "Karn"}, HTTP_HX_REQUEST="true"
        )
        assert response.status_code == 200
        updates = BeautifulSoup(response.content, "html.parser")
        assert updates.find(id="n26-skills-box") is None
        assert "Karn" in updates.find(id=f"n26-model-name-{vex.pk}").get_text()
        assert "Vex" not in skills.get_text()
        assert_reconciled(vex.gang)

    def test_no_change_closes_the_dialog_without_an_extra_event(self, client, vex):
        client.force_login(vex.gang.owner)
        client.post(rename_url(vex), {"name": "Karn"}, HTTP_HX_REQUEST="true")
        response = client.post(
            rename_url(vex), {"name": "Karn"}, HTTP_HX_REQUEST="true"
        )
        assert response.status_code == 200
        assert vex.ledger_events.filter(kind=LedgerEvent.Kind.RENAMED).count() == 1

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_a_stranger_cannot_load_or_save_the_dialog(self, client, vex, method):
        client.force_login(User.objects.create_user("stranger"))
        assert (
            getattr(client, method)(
                rename_url(vex), {"name": "Stolen"}, HTTP_HX_REQUEST="true"
            ).status_code
            == 404
        )

    def test_open_queries_do_not_grow_with_the_roster(self, client, vex, make_profile):
        client.force_login(vex.gang.owner)

        def queries():
            client.get(rename_url(vex), HTTP_HX_REQUEST="true")
            with CaptureQueriesContext(connection) as captured:
                assert (
                    client.get(rename_url(vex), HTTP_HX_REQUEST="true").status_code
                    == 200
                )
            return len(captured)

        before = queries()
        profile = make_profile("Extra", price=100)
        for number in range(5):
            hire_with_option(vex.gang, profile, f"Extra {number}", paid=100, rating=100)
        assert queries() <= before

    def test_save_queries_do_not_grow_with_the_roster(self, client, vex, make_profile):
        client.force_login(vex.gang.owner)

        def queries():
            client.post(rename_url(vex), {"name": "Karn"}, HTTP_HX_REQUEST="true")
            with CaptureQueriesContext(connection) as captured:
                assert (
                    client.post(
                        rename_url(vex), {"name": "Vex"}, HTTP_HX_REQUEST="true"
                    ).status_code
                    == 200
                )
            return len(captured)

        before = queries()
        profile = make_profile("Extra", price=100)
        for number in range(5):
            hire_with_option(vex.gang, profile, f"Extra {number}", paid=100, rating=100)
        assert queries() <= before
