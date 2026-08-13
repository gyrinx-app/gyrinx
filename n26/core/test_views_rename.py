"""Renaming a fighter: the pencil on the card, the dialog the URL opens,
and the act behind it.

The hire form promises "you can name them later", and this is the later
it promised. Open is a server state — the pencil is a link to
``?rename=<pk>`` and the sheet draws the dialog only when that names one
of the gang's own live members — so everything here works with no script
and an open dialog is an address someone can send.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Gang, LedgerEntry

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    """The signed-in person these tests look at the app as."""
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
    from n26.core.operations import operation

    profile = make_profile("Ganger", price=0)
    make_statline(profile)
    with operation(gang, actor=tester) as op:
        return op.hire(profile, "Vex")


class TestThePencilOnTheCard:
    """The sheet says a name can be edited by carrying the way to do it."""

    def test_every_card_offers_the_rename(self, client, tester, gang, vex):
        client.force_login(tester)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert 'aria-label="Rename Vex"' in body
        assert f"?rename={vex.pk}" in body

    def test_the_url_opens_the_dialog_with_the_name_in_it(
        self, client, tester, gang, vex
    ):
        client.force_login(tester)
        url = reverse("n26-gang", args=[gang.pk])
        body = client.get(f"{url}?rename={vex.pk}").content.decode()
        assert "Rename Vex" in body
        assert f'action="{reverse("n26-rename-fighter", args=[vex.pk])}"' in body
        # Prefilled, because most renames are small edits to what is there.
        assert 'value="Vex"' in body

    def test_a_stale_name_draws_no_dialog(self, client, tester, gang, vex):
        """A link that no longer names one of this gang's live members is
        a page without a dialog, not an error worth a screen."""
        client.force_login(tester)
        url = reverse("n26-gang", args=[gang.pk])
        for stray in ("not-a-ulid", "01KZZZZZZZZZZZZZZZZZZZZZZZ"):
            response = client.get(f"{url}?rename={stray}")
            assert response.status_code == 200
            assert "<dialog" not in response.content.decode()


class TestTheAct:
    """POST renames; everything else about the address only asks again."""

    def test_the_owner_renames(self, client, tester, gang, vex):
        client.force_login(tester)
        response = client.post(
            reverse("n26-rename-fighter", args=[vex.pk]), {"name": "Karn"}
        )
        assert response.status_code == 302
        assert response.url == reverse("n26-gang", args=[gang.pk])
        vex.refresh_from_db()
        assert vex.name == "Karn"

    def test_a_rename_moves_no_money(self, client, tester, gang, vex):
        """The name is the model's own and nothing the books watch: no
        ledger row is written, so the gang's totals cannot drift."""
        client.force_login(tester)
        before = LedgerEntry.objects.count()
        client.post(reverse("n26-rename-fighter", args=[vex.pk]), {"name": "Karn"})
        assert LedgerEntry.objects.count() == before

    def test_a_stranger_gets_a_404_and_changes_nothing(self, client, gang, vex):
        """Which fighters exist is not something to probe for, so the
        answer to somebody else's rename is the same as to no fighter
        at all."""
        client.force_login(User.objects.create_user("someone-else"))
        response = client.post(
            reverse("n26-rename-fighter", args=[vex.pk]), {"name": "Mine Now"}
        )
        assert response.status_code == 404
        vex.refresh_from_db()
        assert vex.name == "Vex"

    def test_a_blank_name_is_refused(self, client, tester, gang, vex):
        client.force_login(tester)
        response = client.post(
            reverse("n26-rename-fighter", args=[vex.pk]), {"name": "   "}
        )
        # Back to the open dialog, with the fighter still named.
        assert response.status_code == 302
        assert f"?rename={vex.pk}" in response.url
        vex.refresh_from_db()
        assert vex.name == "Vex"

    def test_get_only_reopens_the_dialog(self, client, tester, gang, vex):
        """The act's address can be followed, sent, or reloaded without
        renaming anyone — GET goes back to the question."""
        client.force_login(tester)
        response = client.get(reverse("n26-rename-fighter", args=[vex.pk]))
        assert response.status_code == 302
        assert f"?rename={vex.pk}" in response.url
        vex.refresh_from_db()
        assert vex.name == "Vex"
