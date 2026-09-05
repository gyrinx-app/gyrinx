"""The named forms and routes for copying gangs and models."""

import pytest
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.urls import reverse

from n26.core.models import Gang, Miniature
from n26.core.operations import Refusal, operation

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    return User.objects.create_user("player")


@pytest.fixture
def gang(tester, gang_type):
    return Gang.objects.create(
        name="The Ashen Choir",
        owner=tester,
        gang_type=gang_type,
        starting_credits=1000,
        credits=1000,
    )


@pytest.fixture
def vex(tester, gang, make_profile, make_statline):
    profile = make_profile("Ganger", price=0)
    make_statline(profile)
    with operation(gang, actor=tester) as op:
        return op.hire(profile, "Vex")


def gang_clone_url(gang):
    return reverse("n26-clone-gang", args=[gang.pk])


def fighter_clone_url(miniature):
    return reverse("n26-clone-fighter", args=[miniature.pk])


class TestNamingAGangClone:
    """Following Clone opens a form and changes nothing."""

    def test_the_gang_menu_opens_the_clone_form(self, client, tester, gang):
        client.force_login(tester)
        url = gang_clone_url(gang)

        sheet = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        response = client.get(url)

        assert url in sheet
        assert "Clone gang" in sheet
        assert "data-dropdown-scriptless" in sheet
        assert response.status_code == 200
        assert f'action="{url}"' in response.content.decode()
        assert response.context["form"]["name"].value() == ("The Ashen Choir (Clone)")

    def test_another_player_is_offered_clone(self, client, gang):
        client.force_login(User.objects.create_user("someone-else"))
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert gang_clone_url(gang) in body
        assert "data-dropdown-scriptless" in body
        assert "Clone gang" in body

    def test_reading_the_form_creates_nothing(self, client, tester, gang):
        client.force_login(tester)
        before = Gang.objects.count()

        client.get(gang_clone_url(gang))

        assert Gang.objects.count() == before

    def test_the_default_keeps_its_suffix_at_the_field_limit(
        self, client, tester, gang
    ):
        gang.name = "A" * 200
        gang.save(update_fields=["name", "modified"])
        client.force_login(tester)

        response = client.get(gang_clone_url(gang))

        assert response.context["form"]["name"].value() == ("A" * 192 + " (Clone)")

    def test_a_blank_name_redraws_the_form_and_creates_nothing(
        self, client, tester, gang
    ):
        client.force_login(tester)
        before = Gang.objects.count()

        response = client.post(gang_clone_url(gang), {"name": ""})

        assert response.status_code == 200
        assert Gang.objects.count() == before
        assert response.context["form"].errors["name"]

    def test_an_operation_refusal_is_shown_on_the_form(
        self, client, tester, gang, monkeypatch
    ):
        def refuse(*args, **kwargs):
            raise Refusal("This gang cannot be cloned.")

        monkeypatch.setattr("n26.core.operations.clone_gang", refuse)
        client.force_login(tester)

        response = client.post(gang_clone_url(gang), {"name": "Copy"})

        assert response.status_code == 200
        assert "This gang cannot be cloned." in response.content.decode()
        assert response.context["form"].non_field_errors()


class TestCloningAGang:
    """A valid POST copies the gang, records it and opens the copy."""

    def test_the_owner_clones_the_gang(self, client, tester, gang, monkeypatch):
        recorded = []

        def remember(*args, **kwargs):
            recorded.append((args, kwargs))

        monkeypatch.setattr("n26.analytics.record", remember)
        client.force_login(tester)

        response = client.post(gang_clone_url(gang), {"name": "Ashen Echo"})

        cloned = Gang.objects.exclude(pk=gang.pk).get()
        assert response.status_code == 302
        assert response.url == reverse("n26-gang", args=[cloned.pk])
        assert cloned.name == "Ashen Echo"
        assert cloned.owner == tester
        assert cloned.gang_type == gang.gang_type
        assert [str(message) for message in get_messages(response.wsgi_request)] == [
            "Cloned The Ashen Choir as Ashen Echo."
        ]

        from n26.analytics import EventVerb, N26Noun

        args, context = recorded[0]
        assert args[1:4] == (N26Noun.GANG, EventVerb.CLONE, cloned)
        assert context["source_gang_id"] == str(gang.pk)

    def test_another_player_gets_the_form_and_owns_the_copy(self, client, gang):
        reader = User.objects.create_user("someone-else")
        client.force_login(reader)
        url = gang_clone_url(gang)

        assert client.get(url).status_code == 200
        response = client.post(url, {"name": "Mine"})

        cloned = Gang.objects.exclude(pk=gang.pk).get()
        assert response.status_code == 302
        assert response.url == reverse("n26-gang", args=[cloned.pk])
        assert cloned.owner == reader
        assert gang.owner != reader

    def test_a_signed_out_reader_is_sent_to_login(self, client, gang):
        response = client.get(gang_clone_url(gang))

        assert response.status_code == 302
        assert "/accounts/login/" in response.url


class TestNamingAModelClone:
    """Clone is offered on the model's own edit page, not on its card."""

    def test_the_edit_page_opens_the_clone_form(self, client, tester, gang, vex):
        client.force_login(tester)
        url = fighter_clone_url(vex)

        edit = client.get(reverse("n26-edit-fighter", args=[vex.pk])).content.decode()
        response = client.get(url)

        assert url in edit
        assert "Clone model" in edit
        assert "data-dropdown-scriptless" in edit
        assert response.status_code == 200
        assert f'action="{url}"' in response.content.decode()
        assert response.context["form"]["name"].value() == "Vex (Clone)"

    def test_the_gang_sheet_does_not_offer_model_clone(self, client, tester, gang, vex):
        client.force_login(tester)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert fighter_clone_url(vex) not in body

    def test_reading_the_form_creates_nothing(self, client, tester, vex):
        client.force_login(tester)
        before = Miniature.objects.count()

        client.get(fighter_clone_url(vex))

        assert Miniature.objects.count() == before

    def test_the_default_keeps_its_suffix_at_the_field_limit(self, client, tester, vex):
        vex.name = "V" * 200
        vex.save(update_fields=["name", "modified"])
        client.force_login(tester)

        response = client.get(fighter_clone_url(vex))

        assert response.context["form"]["name"].value() == ("V" * 192 + " (Clone)")

    def test_a_blank_name_redraws_the_form_and_creates_nothing(
        self, client, tester, vex
    ):
        client.force_login(tester)
        before = Miniature.objects.count()

        response = client.post(fighter_clone_url(vex), {"name": ""})

        assert response.status_code == 200
        assert Miniature.objects.count() == before
        assert response.context["form"].errors["name"]

    def test_an_operation_refusal_is_shown_on_the_form(
        self, client, tester, vex, monkeypatch
    ):
        def refuse(*args, **kwargs):
            raise Refusal("This model cannot be cloned.")

        monkeypatch.setattr(
            "n26.core.operations.Operation.clone_miniature",
            refuse,
        )
        client.force_login(tester)

        response = client.post(fighter_clone_url(vex), {"name": "Vex Two"})

        assert response.status_code == 200
        assert "This model cannot be cloned." in response.content.decode()
        assert response.context["form"].non_field_errors()


class TestCloningAModel:
    """A valid POST copies the model, records it and opens the copy."""

    def test_the_owner_clones_the_model(self, client, tester, gang, vex, monkeypatch):
        recorded = []

        def remember(*args, **kwargs):
            recorded.append((args, kwargs))

        monkeypatch.setattr("n26.analytics.record", remember)
        client.force_login(tester)

        response = client.post(fighter_clone_url(vex), {"name": "Vex Two"})

        cloned = Miniature.objects.exclude(pk=vex.pk).get()
        assert response.status_code == 302
        assert response.url == reverse("n26-edit-fighter", args=[cloned.pk])
        assert cloned.name == "Vex Two"
        assert cloned.owner == tester
        assert cloned.gang == gang
        assert [str(message) for message in get_messages(response.wsgi_request)] == [
            "Cloned Vex as Vex Two."
        ]

        from n26.analytics import EventVerb, N26Noun

        args, context = recorded[0]
        assert args[1:4] == (N26Noun.MODEL, EventVerb.CLONE, cloned)
        assert context["source_model_id"] == str(vex.pk)

    def test_a_stranger_cannot_get_or_post_the_form(self, client, vex):
        client.force_login(User.objects.create_user("someone-else"))
        url = fighter_clone_url(vex)

        assert client.get(url).status_code == 404
        assert client.post(url, {"name": "Mine"}).status_code == 404
        assert Miniature.objects.count() == 1

    def test_a_signed_out_reader_is_sent_to_login(self, client, vex):
        response = client.get(fighter_clone_url(vex))

        assert response.status_code == 302
        assert "/accounts/login/" in response.url
