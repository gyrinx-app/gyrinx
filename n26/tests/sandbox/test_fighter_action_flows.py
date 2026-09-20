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
def hunt(default_pack, fighter_type, fighter_stats, make_statline, counter_tracking):
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
    def test_an_invalid_hidden_request_key_has_a_visible_explanation(
        self, client, hunt
    ):
        client.force_login(hunt.owner)
        response = client.post(
            reverse("n26-action-start", args=[hunt.fighter.pk, hunt.action.pk]),
            {"request_key": "not-a-request", "outcome": str(hunt.clear.pk)},
        )
        assert response.status_code == 200
        assert (
            "This form is not recognised. Reload this page and try again."
            in response.content.decode()
        )
        assert not ActionRecord.objects.filter(fighter=hunt.fighter).exists()

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

    def test_the_edit_page_keeps_only_three_recent_results_per_action(
        self, client, hunt
    ):
        records = [
            ActionRecord.objects.create(
                gang=hunt.gang,
                fighter=hunt.fighter,
                action=hunt.action,
                outcome=hunt.clear,
                request_key=uuid4(),
                state=ActionRecord.State.COMPLETED,
            )
            for _ in range(5)
        ]
        client.force_login(hunt.owner)

        response = client.get(reverse("n26-edit-fighter", args=[hunt.fighter.pk]))

        panel = next(
            panel
            for panel in response.context["action_panels"]
            if panel.action_id == str(hunt.action.pk)
        )
        assert [result.key for result in panel.completed] == [
            str(record.pk) for record in reversed(records[-3:])
        ]

    def test_the_edit_page_places_action_panels_below_the_model_card(
        self, client, hunt
    ):
        from bs4 import BeautifulSoup

        client.force_login(hunt.owner)
        response = client.get(reverse("n26-edit-fighter", args=[hunt.fighter.pk]))
        assert response.status_code == 200
        html = response.content.decode()
        page = BeautifulSoup(html, "html.parser")
        actions = page.find(id="n26-action-panels")
        title = actions.find("h3", string="Suit Evolution")
        header = title.find_parent("div")
        start_button = actions.find(
            "a", attrs={"aria-label": "Start Suit Evolution flow"}
        )

        assert actions.find("span", string="Actions")
        assert title.find_parent("section") in actions.descendants
        assert "After a cycle" in header.get_text(" ", strip=True)
        assert start_button.get_text(" ", strip=True) == "Start flow"
        assert "bg-accent" in start_button.get("class", [])
        assert html.index("Available") < html.index("Price")
        assert "After payment" not in html

    def test_the_gear_menu_sits_with_the_name_above_its_tier(self, client, hunt):
        from bs4 import BeautifulSoup

        client.force_login(hunt.owner)
        response = client.get(reverse("n26-edit-fighter", args=[hunt.fighter.pk]))
        page = BeautifulSoup(response.content, "html.parser")
        menu = page.find(attrs={"aria-label": "More for Hunting rig"})
        gear_line = menu.find_parent("li")
        name_line = gear_line.find("div", recursive=False)

        assert "Hunting rig" in name_line.get_text(" ", strip=True)
        assert menu in name_line.descendants
        assert "Rig augmentation" not in name_line.get_text(" ", strip=True)
        assert "Rig augmentation" in gear_line.get_text(" ", strip=True)

    def test_credit_prices_use_the_credit_unit(self, client, hunt):
        paid = a.create_action(
            "Paid maintenance",
            "post_cycle",
            outcomes=[hunt.clear],
            use_price=[{"resource": "credits", "payer": "gang", "amount": 20}],
        )
        with operation(hunt.gang, actor=hunt.owner) as op:
            op.assign(paid, miniature=hunt.fighter)
        client.force_login(hunt.owner)

        response = client.get(reverse("n26-edit-fighter", args=[hunt.fighter.pk]))

        panel = next(
            panel
            for panel in response.context["action_panels"]
            if panel.action_id == str(paid.pk)
        )
        available = hunt.gang.recompute_credits()
        assert panel.prices[0].label == ""
        assert panel.prices[0].available == f"{available}¢"
        assert panel.prices[0].price == "20¢"
        assert panel.prices[0].remaining == f"{available - 20}¢"

    def test_inactive_tracking_explains_why_a_flow_cannot_start(
        self, client, hunt, counter_tracking
    ):
        counter_tracking.delete()
        client.force_login(hunt.owner)
        edit = client.get(reverse("n26-edit-fighter", args=[hunt.fighter.pk]))
        html = edit.content.decode()
        assert edit.status_code == 200
        assert "This flow is temporarily unavailable." in html
        assert "Start Suit Evolution flow" not in html

        url = reverse("n26-action-start", args=[hunt.fighter.pk, hunt.action.pk])
        start_page = client.get(url)
        assert start_page.status_code == 200
        assert "This flow is temporarily unavailable." in start_page.content.decode()
        posted = client.post(
            url,
            {
                "request_key": str(uuid4()),
                "outcome": str(hunt.clear.pk),
                "allowance": "",
            },
        )
        assert posted.status_code == 200
        assert not ActionRecord.objects.filter(fighter=hunt.fighter).exists()

    def test_inactive_tracking_keeps_an_unfinished_flow_available_to_cancel(
        self, client, hunt, counter_tracking
    ):
        record, _, _ = start(client, hunt, hunt.upgrade)
        counter_tracking.delete()

        edit = client.get(reverse("n26-edit-fighter", args=[hunt.fighter.pk]))
        assert edit.status_code == 200
        assert "Resume Suit Evolution flow" in edit.content.decode()

        cancelled = client.post(
            reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "cancel"])
        )
        assert cancelled.status_code == 302
        record.refresh_from_db()
        assert record.state == ActionRecord.State.CANCELLED

    def test_inactive_tracking_does_not_expose_an_unassigned_action(
        self, client, hunt, counter_tracking
    ):
        hidden = a.create_action(
            "Hidden maintenance", "post_cycle", outcomes=[hunt.clear]
        )
        counter_tracking.delete()
        client.force_login(hunt.owner)

        response = client.get(
            reverse("n26-action-start", args=[hunt.fighter.pk, hidden.pk])
        )

        assert response.status_code == 404
        assert "Hidden maintenance" not in response.content.decode()

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
        revisit = client.post(
            response.context["change_href"],
            {"outcome": str(hunt.clear.pk)},
            follow=True,
        )
        assert revisit.status_code == 200
        assert "Glitch Count: 2 → 0" in revisit.content.decode()
        assert revisit.context["prices"][0].available == "7"
        fresh_token = revisit.context["form"]["review"].value()
        assert client.post(url, {"review": fresh_token}).status_code == 302
        hunt.kills.counter_value.refresh_from_db()
        assert hunt.kills.counter_value.value == 3
        hunt.gang.refresh_from_db()
        assert_reconciled(hunt.gang)

    def test_tallying_a_counter_refreshes_the_flow_panels_on_edit(self, client, hunt):
        client.force_login(hunt.owner)
        response = client.post(
            reverse("n26-tally", args=[hunt.kills.pk]),
            {
                "change": "-3",
                "back": reverse("n26-edit-fighter", args=[hunt.fighter.pk]),
            },
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        html = response.content.decode()
        assert 'id="n26-action-panels" hx-swap-oob="outerHTML"' in html
        assert "This flow needs 1 more Kill Count." in html
        assert "Start Suit Evolution flow" not in html

    def test_changing_the_outcome_keeps_one_unpaid_record(self, client, hunt):
        record, _, _ = start(client, hunt, hunt.upgrade)
        choose = reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "choose"])
        client.post(choose, {"selection": f"{hunt.item.pk}|{hunt.tiers[0].pk}"})
        changed = client.post(
            reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "outcome"]),
            {"outcome": str(hunt.clear.pk)},
            follow=True,
        )
        assert changed.status_code == 200
        record.refresh_from_db()
        assert record.outcome == hunt.clear
        assert record.terms == {"outcome": str(hunt.clear.pk)}
        assert not record.payment_id
        assert ActionRecord.objects.filter(fighter=hunt.fighter).count() == 1

    def test_a_missing_price_counter_is_shown_on_the_outcome_page(self, client, hunt):
        record, _, _ = start(client, hunt, hunt.upgrade)
        hunt.kills.archived = True
        hunt.kills.save(update_fields=["archived"])

        response = client.get(
            reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "outcome"])
        )

        assert response.status_code == 200
        assert "That counter is no longer available." in response.content.decode()

    def test_a_missing_price_counter_is_shown_on_the_item_page(self, client, hunt):
        record, _, _ = start(client, hunt, hunt.upgrade)
        hunt.kills.archived = True
        hunt.kills.save(update_fields=["archived"])

        response = client.get(
            reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "choose"])
        )

        assert response.status_code == 200
        assert "That counter is no longer available." in response.content.decode()

    def test_a_changed_item_is_shown_when_revisiting_a_completed_correction(
        self, client, hunt
    ):
        record, _, _ = start(client, hunt, hunt.upgrade)
        choose = reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "choose"])
        review_url = client.post(
            choose, {"selection": f"{hunt.item.pk}|{hunt.tiers[0].pk}"}
        ).url
        review = client.get(review_url)
        confirmed = client.post(
            review_url, {"review": review.context["form"]["review"].value()}
        )
        assert confirmed.status_code == 302
        hunt.item.archived = True
        hunt.item.save(update_fields=["archived"])

        response = client.get(
            reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "correct"])
        )

        assert response.status_code == 200
        assert (
            "The original item or tier has changed. "
            "Review the change before continuing."
        ) in response.content.decode()

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
