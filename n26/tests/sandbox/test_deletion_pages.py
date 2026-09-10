"""The delete pages, as an author meets them.

A row's delete page says what would go before anything is clicked: the
test gangs holding it, or what refuses it. A delete that takes a gang is
recorded and run on the task runner, and the page that shows the outcome
is where the author lands. The Staged content page offers a delete per
row and one for everything staged — the way back from a book that did
not work out.
"""

import pytest
from django.contrib.auth.models import User

from gyrinx.maintenance.models import Backfill
from n26.core.models import Gang
from n26.library.models import GangType, Profile, Weapon
from n26.tests.sandbox.actions import (
    create_gang_type,
    create_profile,
    create_weapon,
    found_gang,
    give_weapon,
    hire,
)

pytestmark = pytest.mark.django_db

STAGED_URL = "/n26/authoring/staged/"
STAGED_DELETE_URL = "/n26/authoring/staged/delete/"


@pytest.fixture
def author(client):
    user = User.objects.create_user("author", is_staff=True)
    client.force_login(user)
    return user


@pytest.fixture
def player(db):
    return User.objects.create_user("player")


@pytest.fixture
def test_type(default_pack):
    return create_gang_type("Test Gang", starting_credits=1000, staged=True)


@pytest.fixture
def test_fighter(test_type, person_type):
    return create_profile("Tester", person_type, test_type, price=50, staged=True)


@pytest.fixture
def test_weapon(default_pack):
    return create_weapon("Test lasgun", price=15, staged=True)


def checked_by(owner, test_type, test_fighter, test_weapon, name="Checking"):
    gang = found_gang(name, test_type, owner=owner)
    model = hire(gang, test_fighter, "One", paid=50)
    give_weapon(model, test_weapon, paid=15)
    gang.archive()
    return gang


def delete_page(thing, kind):
    return f"/n26/authoring/{kind}/{thing.pk}/delete/"


class TestARowsDeletePage:
    def test_it_names_the_test_gangs_before_the_click(
        self, author, client, test_type, test_fighter, test_weapon
    ):
        checked_by(author, test_type, test_fighter, test_weapon)

        body = client.get(delete_page(test_weapon, "weapon")).content.decode()

        assert "Test gangs that go with it" in body
        assert "Checking" in body
        assert "Archived" in body
        assert "Delete Test lasgun and 1 test gang" in body
        assert Weapon.objects.filter(pk=test_weapon.pk).exists()

    def test_a_test_campaign_is_named_apart_from_the_gangs(
        self, author, client, default_pack, test_type, test_fighter, test_weapon
    ):
        from n26.library.authoring import create_campaign_type
        from n26.tests.sandbox.actions import found_campaign, join_campaign

        staged_type = create_campaign_type("Test campaign type", staged=True)
        mine = checked_by(author, test_type, test_fighter, test_weapon, "Mine")
        found_campaign("Rehearsal", staged_type, owner=author)
        campaign = found_campaign("Rehearsal", staged_type, owner=author)
        join_campaign(mine, campaign)

        body = client.get(delete_page(staged_type, "campaign-type")).content.decode()

        assert "Test campaigns that go with it" in body
        assert "Rehearsal" in body
        assert "Test gangs that go with it" in body
        assert "Delete Test campaign type and 1 test gang and 2 test campaigns" in body

    def test_a_players_gang_refuses_before_the_click(
        self, author, client, player, test_type, test_fighter, test_weapon
    ):
        checked_by(player, test_type, test_fighter, test_weapon, "Theirs")

        body = client.get(delete_page(test_weapon, "weapon")).content.decode()

        assert "Something still holds it" in body
        assert "Theirs" in body
        assert "not staff" in body
        assert "Delete it" not in body

    def test_deleting_with_a_test_gang_is_recorded_and_done(
        self, author, client, test_type, test_fighter, test_weapon
    ):
        gang = checked_by(author, test_type, test_fighter, test_weapon)

        response = client.post(delete_page(test_weapon, "weapon"))

        record = Backfill.objects.get()
        assert response["Location"] == f"/n26/authoring/deletions/{record.pk}/"
        assert record.triggered_by == author
        # Tasks run inline here, so the record has its ending already.
        assert record.status == Backfill.Status.DONE
        assert not Weapon.objects.filter(pk=test_weapon.pk).exists()
        assert not Gang.objects.filter(pk=gang.pk).exists()

        body = client.get(response["Location"]).content.decode()
        assert "Deleted" in body
        assert "Checking" in body
        assert "author" in body

    def test_a_refused_post_deletes_nothing_and_says_why(
        self, author, client, player, test_type, test_fighter, test_weapon
    ):
        gang = checked_by(player, test_type, test_fighter, test_weapon, "Theirs")

        response = client.post(delete_page(test_weapon, "weapon"), follow=True)

        body = response.content.decode()
        assert "still in use, so nothing was deleted" in body
        assert "Theirs" in body
        assert Weapon.objects.filter(pk=test_weapon.pk).exists()
        assert Gang.objects.filter(pk=gang.pk).exists()
        assert not Backfill.objects.exists()

    def test_an_unused_row_is_deleted_in_the_request(self, author, client, test_weapon):
        body = client.get(delete_page(test_weapon, "weapon")).content.decode()
        assert "Nothing else holds it" in body

        response = client.post(delete_page(test_weapon, "weapon"))

        assert response["Location"] == "/n26/authoring/weapon/"
        assert not Weapon.objects.filter(pk=test_weapon.pk).exists()
        assert not Backfill.objects.exists()

    def test_a_second_deletion_waits_for_the_first(
        self, author, client, test_type, test_fighter, test_weapon
    ):
        """The runner holds one lock per operation and a second copy
        stands down without writing an ending, so a second run is
        refused at the page rather than left saying running for ever."""
        gang = checked_by(author, test_type, test_fighter, test_weapon)
        Backfill.objects.create(
            operation="n26_delete_test_content", status=Backfill.Status.RUNNING
        )

        response = client.post(delete_page(test_weapon, "weapon"), follow=True)

        assert "Another deletion is still running" in response.content.decode()
        assert Weapon.objects.filter(pk=test_weapon.pk).exists()
        assert Gang.objects.filter(pk=gang.pk).exists()
        assert Backfill.objects.count() == 1

    def test_the_run_page_reloads_while_running(self, author, client):
        record = Backfill.objects.create(
            operation="n26_delete_test_content",
            triggered_by=author,
            status=Backfill.Status.RUNNING,
            summary={"preview": ["delete 1 weapons"], "attempts": 0},
        )
        body = client.get(f"/n26/authoring/deletions/{record.pk}/").content.decode()
        assert 'http-equiv="refresh"' in body
        assert "Deleting" in body

    def test_a_record_of_another_operation_is_not_a_deletion(self, author, client):
        record = Backfill.objects.create(operation="n26_audit_reconcile")
        assert client.get(f"/n26/authoring/deletions/{record.pk}/").status_code == 404


class TestTheStagedContentPage:
    def test_each_row_offers_its_delete_page(
        self, author, client, test_type, test_weapon
    ):
        body = client.get(STAGED_URL).content.decode()
        assert delete_page(test_weapon, "weapon") in body
        assert delete_page(test_type, "gang-type") in body
        assert STAGED_DELETE_URL in body

    def test_deleting_everything_staged_takes_the_test_gang_too(
        self, author, client, test_type, test_fighter, test_weapon
    ):
        gang = checked_by(author, test_type, test_fighter, test_weapon)
        live = create_weapon("Lasgun")

        body = client.get(STAGED_DELETE_URL).content.decode()
        assert "Delete everything staged and 1 test gang" in body
        assert "Gang types" in body
        assert "Checking" in body

        response = client.post(STAGED_DELETE_URL)

        record = Backfill.objects.get()
        assert response["Location"] == f"/n26/authoring/deletions/{record.pk}/"
        assert record.status == Backfill.Status.DONE
        assert not GangType.objects.filter(pk=test_type.pk).exists()
        assert not Profile.objects.filter(pk=test_fighter.pk).exists()
        assert not Weapon.objects.filter(pk=test_weapon.pk).exists()
        assert not Gang.objects.filter(pk=gang.pk).exists()
        assert Weapon.objects.filter(pk=live.pk).exists()

    def test_with_nothing_staged_the_question_says_so(self, author, client):
        create_weapon("Lasgun")
        body = client.get(STAGED_DELETE_URL).content.decode()
        assert "Nothing is staged" in body

    def test_it_is_for_staff(self, client, db):
        client.force_login(User.objects.create_user("player"))
        assert client.get(STAGED_DELETE_URL).status_code == 302
