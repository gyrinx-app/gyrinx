"""The tactics collection updates in place, with server-owned permissions."""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.operations import operation
from n26.core.tactics import held
from n26.library.models import Picklist, Subtype
from n26.library.standard_content import STANDARD_CONTENT
from n26.tests.sandbox.actions import assign, found_gang, hire

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("counter_tracking")]


@pytest.fixture
def collection(default_pack, gang_type, make_profile, make_statline):
    STANDARD_CONTENT["tactics-contribution"].create()
    STANDARD_CONTENT["gang-tactics-tables"].create()
    owner = User.objects.create_user("tactics-owner")
    gang = found_gang("The Ashen Choir", gang_type, owner=owner)
    profile = make_profile("Leader", price=50)
    make_statline(profile)
    fighter = hire(gang, profile, "Vex")
    assign(Subtype.objects.get(name="Leader"), miniature=fighter)
    table = str(Picklist.objects.get(name="Escher", slot_type__name="Gang Tactic").pk)
    with operation(gang, actor=owner) as op:
        op.roll_tactics(table, 2)
    return gang, owner, table


def batch(client, gang, action, selected, **extra):
    return client.post(
        reverse("n26-batch-gang-tactics", args=[gang.pk]),
        {"action": action, "selected": selected, "confirmed": "yes", **extra},
        HTTP_ACCEPT="application/json",
    )


class TestCollectionActions:
    """Only valid owner selections can change the collection."""

    def test_delete_returns_the_remaining_cards_and_freed_allowance(
        self, client, collection
    ):
        gang, owner, _ = collection
        client.force_login(owner)
        keys = [str(tactic.pk) for tactic in held(gang)]
        response = batch(client, gang, "delete", [keys[0]])
        assert response.status_code == 200
        assert [card["pk"] for card in response.json()["cards"]] == keys[1:]
        assert response.json()["toGenerate"] == 1
        assert len(held(gang)) == 1

    def test_reroll_returns_a_new_card_without_spending_another_share(
        self, client, collection
    ):
        gang, owner, table = collection
        client.force_login(owner)
        key = str(held(gang)[0].pk)
        response = batch(client, gang, "reroll", [key], table=table)
        assert response.status_code == 200
        assert len(response.json()["cards"]) == 2
        assert key not in {card["pk"] for card in response.json()["cards"]}
        assert response.json()["toGenerate"] == 0

    def test_stale_selection_changes_nothing(self, client, collection):
        gang, owner, _ = collection
        client.force_login(owner)
        keys = [str(tactic.pk) for tactic in held(gang)]
        assert batch(client, gang, "delete", [*keys, "missing"]).status_code == 400
        assert {str(tactic.pk) for tactic in held(gang)} == set(keys)

    def test_another_account_cannot_change_the_collection(self, client, collection):
        gang, _, _ = collection
        client.force_login(User.objects.create_user("visitor"))
        key = str(held(gang)[0].pk)
        assert batch(client, gang, "delete", [key]).status_code == 404
        assert len(held(gang)) == 2
