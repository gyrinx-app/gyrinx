"""A player follows a priced action from the Edit page to its receipt."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.models import ActionRecord, Assignment
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.library import authoring as a
from n26.library.models import Slot
from n26.tests.sandbox.actions import buy, found_gang, hire

pytestmark = pytest.mark.django_db


@pytest.fixture
def hunt(default_pack, fighter_type, fighter_stats, make_statline):
    owner = User.objects.create_user("flow-player")
    gang_type = a.create_gang_type("Hunting party", starting_credits=1000)
    gang = found_gang("The Descent", gang_type, owner=owner, budget=1000)
    profile = a.create_profile("Hunter", fighter_type, gang_type, price=100)
    make_statline(profile)
    fighter = hire(gang, profile, "Vex")
    kills = a.create_counter("Kill Count")
    glitches = a.create_counter("Glitch Count")
    augmentation = a.create_slot_type("Augmentation", allows_repeats=False)
    glitch_type = a.create_slot_type("Glitch")
    rig = a.create_wargear("Hunting rig", price=0)
    strength = fighter_stats["S"]
    tiers = [
        a.create_pickable(
            f"Tier {level}",
            augmentation,
            rating_contribution=20 * level,
            effects=[
                (
                    a.targets_model(),
                    a.ef_changes_stat(strength, mode="improve", amount=level),
                )
            ],
        )
        for level in [1, 2]
    ]
    picklist = a.create_picklist("Rig tiers", augmentation)
    for level, tier in enumerate(tiers, start=1):
        a.add_picklist_member(picklist, tier, level=level)
    slot = a.create_slot(
        "Rig augmentation",
        augmentation,
        picklist,
        min_picks=0,
        max_picks=1,
        mode=Slot.Mode.TIER_LADDER,
    )
    a.add_built_in(rig, slot)
    upgrade = a.create_outcome(
        "Augment a carried item", a.augment_carried_item(augmentation)
    )
    clear = a.create_outcome(
        "Clear all glitches",
        a.apply_changes(
            a.counter_change(glitches, "set", 0), a.remove_picks(glitch_type)
        ),
    )
    action = a.create_action(
        "Suit Evolution",
        "post_cycle",
        outcomes=[upgrade, clear],
        use_price=[
            {"resource": "counter", "payer": "fighter", "counter": kills, "amount": 4}
        ],
    )
    with operation(gang, actor=owner) as op:
        op.assign(action, miniature=fighter)
        kill_balance = op.assign(kills, miniature=fighter)
        glitch_balance = op.assign(glitches, miniature=fighter)
        op.tally(kill_balance, 6)
        op.tally(glitch_balance, 2)
    item = buy(fighter, thing=rig, paid=0)
    return SimpleNamespace(
        owner=owner,
        gang=gang,
        fighter=fighter,
        action=action,
        upgrade=upgrade,
        clear=clear,
        item=item,
        tiers=tiers,
        kills=kill_balance,
        glitches=glitch_balance,
    )


def start(client, hunt, outcome):
    client.force_login(hunt.owner)
    url = reverse("n26-action-start", args=[hunt.fighter.pk, hunt.action.pk])
    payload = {"request_key": str(uuid4()), "outcome": str(outcome.pk), "allowance": ""}
    response = client.post(url, payload)
    assert response.status_code == 302
    return ActionRecord.objects.get(fighter=hunt.fighter), url, payload


class TestSuitEvolutionForms:
    def test_more_action_panels_do_not_add_queries_per_action(self, client, hunt):
        client.force_login(hunt.owner)
        url = reverse("n26-edit-fighter", args=[hunt.fighter.pk])

        def measure():
            client.get(url)
            with CaptureQueriesContext(connection) as queries:
                response = client.get(url)
            assert response.status_code == 200
            return len(queries)

        one = measure()
        with operation(hunt.gang, actor=hunt.owner) as op:
            for number in range(5):
                extra = a.create_action(
                    f"Equipment maintenance {number}",
                    "post_cycle",
                    outcomes=[hunt.clear],
                    use_price=[{"resource": "credits", "payer": "gang", "amount": 20}],
                )
                op.assign(extra, miniature=hunt.fighter)
        assert measure() == one

    def test_the_edit_page_places_action_panels_below_the_model_card(
        self, client, hunt
    ):
        client.force_login(hunt.owner)
        response = client.get(reverse("n26-edit-fighter", args=[hunt.fighter.pk]))
        assert response.status_code == 200
        html = response.content.decode()
        assert "Start Suit Evolution flow" in html
        assert html.index("Available") < html.index("After payment")

    def test_a_carried_item_is_reviewed_before_any_kills_are_spent(self, client, hunt):
        record, _, _ = start(client, hunt, hunt.upgrade)
        choose = reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "choose"])
        response = client.get(choose)
        assert response.status_code == 200
        assert "Hunting rig" in response.content.decode()
        assert hunt.kills.counter_value.value == 6
        response = client.post(
            choose, {"selection": f"{hunt.item.pk}|{hunt.tiers[0].pk}"}
        )
        assert response.status_code == 302
        review = client.get(response.url)
        assert review.status_code == 200
        assert "Hunting rig: Tier 1" in review.content.decode()
        token = review.context["form"]["review"].value()
        confirmed = client.post(response.url, {"review": token})
        assert confirmed.status_code == 302
        receipt = client.get(confirmed.url)
        assert "6 → 2" in receipt.content.decode()
        assert "+20¢" in receipt.content.decode()
        assert (
            ActionRecord.objects.get(pk=record.pk).state == ActionRecord.State.COMPLETED
        )
        hunt.gang.refresh_from_db()
        assert_reconciled(hunt.gang)

    def test_clearing_glitches_and_repeating_confirmation_pays_once(self, client, hunt):
        record, start_url, payload = start(client, hunt, hunt.clear)
        review_url = reverse(
            "n26-action-flow", args=[hunt.fighter.pk, record.pk, "review"]
        )
        review = client.get(review_url)
        token = review.context["form"]["review"].value()
        assert client.post(review_url, {"review": token}).status_code == 302
        assert client.post(review_url, {"review": token}).status_code == 302
        assert client.post(start_url, payload).status_code == 302
        hunt.kills.counter_value.refresh_from_db()
        hunt.glitches.counter_value.refresh_from_db()
        assert hunt.kills.counter_value.value == 2
        assert hunt.glitches.counter_value.value == 0
        assert ActionRecord.objects.filter(fighter=hunt.fighter).count() == 1
        hunt.gang.refresh_from_db()
        assert_reconciled(hunt.gang)

    def test_a_changed_balance_requires_another_review(self, client, hunt):
        record, _, _ = start(client, hunt, hunt.clear)
        url = reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "review"])
        token = client.get(url).context["form"]["review"].value()
        with operation(hunt.gang, actor=hunt.owner) as op:
            op.tally(hunt.kills, 1)
        response = client.post(url, {"review": token})
        assert response.status_code == 200
        assert response.context["form"].non_field_errors()
        record.refresh_from_db()
        assert record.state == ActionRecord.State.STARTED
        assert not record.payment_id
        hunt.gang.refresh_from_db()
        assert_reconciled(hunt.gang)

    def test_another_owner_cannot_open_or_complete_the_flow(self, client, hunt):
        record, _, _ = start(client, hunt, hunt.clear)
        stranger = User.objects.create_user("other-flow-player")
        client.force_login(stranger)
        url = reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "review"])
        assert client.get(url).status_code == 404
        assert client.post(url, {"review": "anything"}).status_code == 404
        record.refresh_from_db()
        assert record.state == ActionRecord.State.STARTED

    def test_leaving_and_resuming_an_unpaid_selection_does_not_create_another_record(
        self, client, hunt
    ):
        record, start_url, payload = start(client, hunt, hunt.upgrade)
        assert client.post(start_url, payload).status_code == 302
        resume = reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "resume"])
        response = client.get(resume, follow=True)
        assert response.status_code == 200
        assert response.context["stage"] == "choose"
        assert not Assignment.objects.filter(
            miniature_root=hunt.fighter, pickable__in=hunt.tiers
        ).exists()
        assert ActionRecord.objects.filter(fighter=hunt.fighter).count() == 1
