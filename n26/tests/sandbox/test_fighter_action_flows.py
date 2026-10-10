"""A player follows a priced action from the Edit page to its receipt."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.models import ActionRecord, Assignment, LedgerEvent
from n26.core.operations import operation
from n26.core.owned import with_query
from n26.core.reconcile import assert_reconciled
from n26.library import authoring as a
from n26.library.models import Slot
from n26.tests.fixtures import library_setup
from n26.tests.sandbox.actions import buy, found_gang, hire

pytestmark = pytest.mark.django_db


@library_setup
def _hunt_action_content(fighter_stats):
    """The rig ladder and priced actions, authored before the player uses them."""
    kills = a.create_counter("Kill Count")
    glitches = a.create_counter("Glitch Count")
    augmentation = a.create_slot_type("Augmentation", allows_repeats=False)
    glitch_type = a.create_slot_type("Glitch", plural_name="Glitches")
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
    return kills, glitches, rig, tiers, upgrade, clear, action


@pytest.fixture
def hunt(default_pack, fighter_type, fighter_stats, make_statline, counter_tracking):
    owner = User.objects.create_user("flow-player")
    gang_type = a.create_gang_type("Hunting party", starting_credits=1000)
    gang = found_gang("The Descent", gang_type, owner=owner, budget=1000)
    profile = a.create_profile("Hunter", fighter_type, gang_type, price=100)
    make_statline(profile)
    fighter = hire(gang, profile, "Vex")
    kills, glitches, rig, tiers, upgrade, clear, action = _hunt_action_content(
        fighter_stats
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
    @pytest.mark.parametrize("location", ["model", "stash"])
    def test_more_ladders_do_not_add_per_item_queries(self, client, hunt, location):
        client.force_login(hunt.owner)
        if location == "stash":
            with operation(hunt.gang, actor=hunt.owner) as op:
                op.move(hunt.item, hunt.gang.stash)
            url = reverse("n26-gang", args=[hunt.gang.pk])
        else:
            url = reverse("n26-edit-fighter", args=[hunt.fighter.pk])

        def measure():
            client.get(url)
            with CaptureQueriesContext(connection) as queries:
                response = client.get(url)
            assert response.status_code == 200
            return len(queries)

        one = measure()
        for _ in range(4):
            item = buy(hunt.fighter, thing=hunt.item.wargear, paid=0)
            if location == "stash":
                with operation(hunt.gang, actor=hunt.owner) as op:
                    op.move(item, hunt.gang.stash)

        assert measure() == one

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

    @pytest.mark.parametrize("screen", ["n26-edit-fighter", "n26-equip"])
    def test_more_action_panels_do_not_add_queries_per_action(
        self, client, hunt, screen
    ):
        from bs4 import BeautifulSoup

        client.force_login(hunt.owner)
        url = reverse(screen, args=[hunt.fighter.pk])

        def measure(expected_panels):
            client.get(url)
            with CaptureQueriesContext(connection) as queries:
                response = client.get(url)
            assert response.status_code == 200
            assert len(response.context["action_panels"]) == expected_panels
            panel = next(
                panel
                for panel in response.context["action_panels"]
                if panel.action_id == str(hunt.action.pk)
            )
            assert panel.name == "Suit Evolution"
            assert panel.timing == "after a cycle"
            assert [(price.label, price.price) for price in panel.prices] == [
                ("Kill Count", "4")
            ]
            actions = BeautifulSoup(response.content, "html.parser").find(
                id="n26-action-panels"
            )
            link = actions.find("a", attrs={"aria-label": "Start Suit Evolution flow"})
            assert link["href"] == panel.start_href
            assert link.get_text(" ", strip=True) == "Start →"
            if screen == "n26-edit-fighter":
                page = BeautifulSoup(response.content, "html.parser")
                assert page.find(attrs={"aria-label": "More for Hunting rig"})
                tier_slot = hunt.item.caused.get(slot__mode=Slot.Mode.TIER_LADDER)
                tier_key = f"{hunt.fighter.pk}:{tier_slot.pk}:{tier_slot.slot_id}"
                tier_href = with_query(
                    reverse("n26-choose", args=[hunt.gang.pk, tier_key]),
                    **{"return": url},
                )
                tier_link = page.find("a", href=tier_href)
                assert tier_link.get_text(" ", strip=True) == "Choose tier"
            return len(queries)

        one = measure(1)
        with operation(hunt.gang, actor=hunt.owner) as op:
            for number in range(5):
                extra = a.create_action(
                    f"Equipment maintenance {number}",
                    "post_cycle",
                    outcomes=[hunt.clear],
                    use_price=[{"resource": "credits", "payer": "gang", "amount": 20}],
                )
                op.assign(extra, miniature=hunt.fighter)
        assert measure(6) == one

    def test_the_edit_page_keeps_only_three_recent_results_per_action(
        self, client, hunt
    ):
        from bs4 import BeautifulSoup

        records = [
            ActionRecord.objects.create(
                gang=hunt.gang,
                fighter=hunt.fighter,
                action=hunt.action,
                outcome=hunt.upgrade if number == 4 else hunt.clear,
                request_key=uuid4(),
                state=ActionRecord.State.COMPLETED,
                review={
                    "target": {
                        "selection": {
                            "item_name": "Hunting rig",
                            "candidate_tier": "Tier 2",
                            "effect": "improve S by 2",
                        }
                    }
                }
                if number == 4
                else {},
            )
            for number in range(5)
        ]
        client.force_login(hunt.owner)

        response = client.get(reverse("n26-edit-fighter", args=[hunt.fighter.pk]))

        panel = next(
            panel
            for panel in response.context["action_history_panels"]
            if panel.action_id == str(hunt.action.pk)
        )
        assert [result.key for result in panel.completed] == [
            str(record.pk) for record in reversed(records[-3:])
        ]
        assert [result.label for result in panel.completed] == [
            "Augment a carried item",
            "Clear all glitches",
            "Clear all glitches",
        ]
        assert panel.completed[0].detail == "Hunting rig: Tier 2. Improve S by 2"
        page = BeautifulSoup(response.content, "html.parser")
        actions = page.find(id="n26-action-panels")
        history = page.find(id="n26-action-history")
        for result, record in zip(panel.completed, reversed(records[-3:]), strict=True):
            assert result.href == reverse(
                "n26-action-flow", args=[hunt.fighter.pk, record.pk, "done"]
            )
            assert result.when is not None
            assert actions.find("a", href=result.href) is None
            link = history.find("a", href=result.href)
            assert link.get_text(" ", strip=True) == result.label
            timestamp = link.find_next("time")
            assert timestamp.get("datetime")
            assert timestamp.get("title")

    def test_an_action_with_no_available_use_is_not_actionable(self):
        from n26.core.action_flow import ActionPanel
        from n26.core.views.action_flows import split_action_panels

        available, history = split_action_panels(
            [
                ActionPanel(
                    action_id="spent",
                    name="Spent action",
                    timing="recruitment",
                    available_uses=0,
                )
            ]
        )

        assert available == []
        assert history == []

    def test_existing_duplicate_drafts_remain_resumable_without_another_start(
        self, client, hunt
    ):
        from bs4 import BeautifulSoup

        records = [
            ActionRecord.objects.create(
                gang=hunt.gang,
                fighter=hunt.fighter,
                action=hunt.action,
                request_key=uuid4(),
            )
            for _ in range(2)
        ]
        client.force_login(hunt.owner)
        response = client.get(reverse("n26-edit-fighter", args=[hunt.fighter.pk]))
        actions = BeautifulSoup(response.content, "html.parser").find(
            id="n26-action-panels"
        )

        assert not actions.find("a", attrs={"aria-label": "Start Suit Evolution flow"})
        for record in records:
            assert actions.find(
                "a",
                href=reverse(
                    "n26-action-flow", args=[hunt.fighter.pk, record.pk, "resume"]
                ),
            )
        assert len(actions.find_all("time")) == 2

    @pytest.mark.parametrize("screen", ["n26-edit-fighter", "n26-equip"])
    def test_counter_updates_refresh_available_flows_on_both_model_pages(
        self, client, hunt, screen
    ):
        from bs4 import BeautifulSoup

        client.force_login(hunt.owner)
        back = reverse(screen, args=[hunt.fighter.pk])
        response = client.post(
            reverse("n26-tally", args=[hunt.kills.pk]),
            {"change": "-3", "back": back},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        actions = BeautifulSoup(response.content, "html.parser").find(
            id="n26-action-panels"
        )
        assert actions["hx-swap-oob"] == "outerHTML"
        assert "This flow needs 1 more Kill Count." not in response.content.decode()
        assert "Start Suit Evolution flow" not in str(actions)

    @pytest.mark.parametrize("screen", ["n26-edit-fighter", "n26-equip"])
    def test_the_first_earned_advancement_populates_an_initially_empty_panel(
        self, client, hunt, screen
    ):
        from bs4 import BeautifulSoup

        from n26.core.models import ActionAllowance

        xp = a.create_counter("XP")
        ranks = a.create_rank_table("Hunter ranks", xp, thresholds=[4])
        kind = a.create_slot_type("Advancement")
        result = a.create_pickable("Increase Strength", kind)
        results = a.create_picklist("Hunter advancements", kind)
        a.add_picklist_member(results, result)
        slot = a.create_slot("Hunter advancement", kind, results)
        outcome = a.create_outcome("Advancement", a.resolve_advancement(slot))
        advancement = a.create_action(
            "Advancement",
            "post_cycle",
            outcomes=[outcome],
            allowance_rule=a.rank_allowance_rule(xp),
        )
        maintenance = a.create_action(
            "Maintenance",
            "post_cycle",
            outcomes=[hunt.clear],
            use_price=[{"resource": "credits", "payer": "gang", "amount": 2000}],
        )
        with operation(hunt.gang, actor=hunt.owner) as op:
            op.tally(hunt.kills, -6)
            op.assign(maintenance, miniature=hunt.fighter)
            op.assign(advancement, miniature=hunt.fighter)
            op.assign(ranks, miniature=hunt.fighter)
            counted = op.assign(xp, miniature=hunt.fighter)
            op.open_counter(counted, 0)
            op.tally(counted, 3)

        client.force_login(hunt.owner)
        back = reverse(screen, args=[hunt.fighter.pk])
        page = client.get(back)
        assert page.context["action_panels"] == []
        host = BeautifulSoup(page.content, "html.parser").find(id="n26-action-panels")
        assert host is not None
        assert not host.find("a")
        assert not ActionAllowance.objects.filter(fighter=hunt.fighter).exists()

        update = client.post(
            reverse("n26-tally", args=[counted.pk]),
            {"change": "1", "back": back},
            HTTP_HX_REQUEST="true",
        )
        assert update.status_code == 200
        actions = BeautifulSoup(update.content, "html.parser").find(
            id="n26-action-panels"
        )
        assert actions["hx-swap-oob"] == "outerHTML"
        assert actions.find("a", attrs={"aria-label": "Start Advancement flow"})
        assert "1 use available" in actions.get_text(" ", strip=True)
        assert not actions.find("a", attrs={"aria-label": "Start Maintenance flow"})
        assert (
            ActionAllowance.objects.filter(
                fighter=hunt.fighter, action=advancement, threshold=4
            ).count()
            == 1
        )
        roster = client.get(reverse("n26-gang", args=[hunt.gang.pk]))
        assert roster.status_code == 200
        model = next(
            card
            for card in roster.context["sheet"].models
            if card.id == str(hunt.fighter.pk)
        )
        assert "Advancement" in model.action_names

    def test_a_counter_priced_action_is_marked_once_it_is_affordable(
        self, client, hunt
    ):
        """Suit Evolution needs 4 Kill Count; the model has 6, so it is marked."""
        from bs4 import BeautifulSoup

        url = reverse("n26-gang", args=[hunt.gang.pk])
        client.force_login(hunt.owner)
        response = client.get(url)
        model = response.context["sheet"].models[0]
        assert model.action_names == ("Suit Evolution",)
        card = BeautifulSoup(response.content, "html.parser").find(
            id=f"model-{hunt.fighter.pk}"
        )
        href = f"{reverse('n26-edit-fighter', args=[hunt.fighter.pk])}#actions"
        links = card.parent.find_all("a", href=href)
        assert len(links) == 1
        strip = links[0]
        assert "bg-blue-50" in strip["class"]
        assert "Suit Evolution" in strip.get_text()
        assert "Available" in strip.get_text()
        edit = reverse("n26-edit-fighter", args=[hunt.fighter.pk])

        def edit_mark():
            page = client.get(edit)
            panels = BeautifulSoup(page.content, "html.parser").find(
                id="n26-action-panels"
            )
            return panels.find("svg", attrs={"aria-label": "Waiting"})

        assert edit_mark() is not None

        with operation(hunt.gang, actor=hunt.owner) as op:
            op.tally(hunt.kills, -3)
        roster = client.get(url)
        assert roster.context["sheet"].models[0].action_names == ()
        assert not BeautifulSoup(roster.content, "html.parser").find(
            "a", class_="bg-blue-50"
        )
        assert edit_mark() is None

        with operation(hunt.gang, actor=hunt.owner) as op:
            op.tally(hunt.kills, 3)
        assert edit_mark() is not None
        client.logout()
        roster = client.get(url)
        assert roster.context["sheet"].models[0].action_names == ()
        assert not BeautifulSoup(roster.content, "html.parser").find(
            "a", class_="bg-blue-50"
        )

    def test_a_credits_only_action_is_never_marked(self, client, hunt):
        """Maintenance is always there to buy, so it stays on Edit alone."""
        from bs4 import BeautifulSoup

        maintenance = a.create_action(
            "Suit Maintenance",
            "post_cycle",
            outcomes=[hunt.clear],
            use_price=[{"resource": "credits", "payer": "gang", "amount": 20}],
        )
        with operation(hunt.gang, actor=hunt.owner) as op:
            op.assign(maintenance, miniature=hunt.fighter)
            op.tally(hunt.kills, -3)
        client.force_login(hunt.owner)

        roster = client.get(reverse("n26-gang", args=[hunt.gang.pk]))
        assert roster.context["sheet"].models[0].action_names == ()
        page = client.get(reverse("n26-edit-fighter", args=[hunt.fighter.pk]))
        panels = BeautifulSoup(page.content, "html.parser").find(id="n26-action-panels")
        assert panels.find("a", attrs={"aria-label": "Start Suit Maintenance flow"})
        assert panels.find("svg", attrs={"aria-label": "Waiting"}) is None
        assert panels.find(class_="bg-blue-50") is None

        panel = next(
            panel
            for panel in page.context["action_panels"]
            if panel.action_id == str(maintenance.pk)
        )
        available = hunt.gang.recompute_credits()
        assert panel.flagged is False
        assert panel.prices[0].label == ""
        assert panel.prices[0].available == f"{available}¢"
        assert panel.prices[0].price == "20¢"
        assert panel.prices[0].remaining == f"{available - 20}¢"

    def test_available_actions_share_a_blue_mark_independent_of_gang_colour(
        self, client, hunt
    ):
        from bs4 import BeautifulSoup

        hunt.gang.colour = "red; background-image: url(https://example.com/x)"
        hunt.gang.save(update_fields=["colour"])
        start(client, hunt, hunt.clear)
        roster = client.get(reverse("n26-gang", args=[hunt.gang.pk]))
        card = BeautifulSoup(roster.content, "html.parser").find(
            id=f"model-{hunt.fighter.pk}"
        )
        strip = card.parent.find("a", class_="bg-blue-50")
        assert "text-blue-600" in strip.find("svg")["class"]
        page = client.get(reverse("n26-edit-fighter", args=[hunt.fighter.pk]))
        panels = BeautifulSoup(page.content, "html.parser").find(id="n26-action-panels")
        mark = panels.find("svg", attrs={"aria-label": "Waiting"})
        assert mark is not None
        assert "text-blue-600" in mark.parent["class"]
        assert panels.find(class_="bg-blue-50") is not None
        assert [panel.flagged for panel in page.context["action_panels"]] == [True]

        extra = a.create_action(
            "Advancement",
            "post_cycle",
            outcomes=[hunt.clear],
            use_price=[
                {
                    "resource": "counter",
                    "payer": "fighter",
                    "counter": hunt.kills.counter,
                    "amount": 4,
                }
            ],
        )
        with operation(hunt.gang, actor=hunt.owner) as op:
            op.assign(extra, miniature=hunt.fighter)
        roster = client.get(reverse("n26-gang", args=[hunt.gang.pk]))
        assert roster.context["sheet"].models[0].action_names == (
            "Advancement",
            "Suit Evolution",
        )
        card = BeautifulSoup(roster.content, "html.parser").find(
            id=f"model-{hunt.fighter.pk}"
        )
        href = f"{reverse('n26-edit-fighter', args=[hunt.fighter.pk])}#actions"
        links = card.parent.find_all("a", href=href)
        assert len(links) == 1
        assert " ".join(links[0].get_text().split()) == "Multiple actions available"
        assert links[0]["aria-label"].endswith(": Advancement, Suit Evolution")

    def test_a_started_flow_stays_on_the_roster_when_tracking_is_paused(
        self, client, hunt, counter_tracking
    ):
        start(client, hunt, hunt.clear)
        counter_tracking.delete()
        response = client.get(reverse("n26-gang", args=[hunt.gang.pk]))
        assert response.context["sheet"].models[0].action_names == ("Suit Evolution",)

    def test_roster_action_availability_has_no_per_model_query_growth(
        self, client, hunt
    ):
        client.force_login(hunt.owner)
        url = reverse("n26-gang", args=[hunt.gang.pk])

        def draft(fighter):
            ActionRecord.objects.create(
                gang=hunt.gang,
                fighter=fighter,
                action=hunt.action,
                request_key=uuid4(),
            )

        def measure():
            client.get(url)
            with CaptureQueriesContext(connection) as queries:
                response = client.get(url)
            assert response.status_code == 200
            assert all(
                model.action_names == ("Suit Evolution",)
                for model in response.context["sheet"].models
            )
            return len(queries)

        draft(hunt.fighter)
        one = measure()
        hired = []
        with operation(hunt.gang, actor=hunt.owner) as op:
            for number in range(3):
                model = op.hire(hunt.fighter.membership.profile, f"Hunter {number}")
                op.assign(hunt.action, miniature=model)
                hired.append(model)
        for model in hired:
            draft(model)
        assert measure() == one

    def test_credit_payment_figures_use_the_currency_symbol_without_a_unit(self):
        from bs4 import BeautifulSoup
        from django.template import Context, Template
        from django_cotton.compiler_regex import CottonCompiler

        from n26.core.flow import PaymentFigures

        figures = PaymentFigures("", "1500¢", "100¢", "1400¢")
        drawn = Template(
            CottonCompiler().process('<c-n26.payment-figures :figures="figures" />')
        ).render(Context({"figures": figures}))
        values = BeautifulSoup(drawn, "html.parser").find_all("dd")

        assert [value.get_text(" ", strip=True) for value in values] == [
            "1500¢",
            "100¢",
        ]
        assert "Credits" not in drawn

    def test_inactive_tracking_explains_why_a_flow_cannot_start(
        self, client, hunt, counter_tracking
    ):
        counter_tracking.delete()
        client.force_login(hunt.owner)
        edit = client.get(reverse("n26-edit-fighter", args=[hunt.fighter.pk]))
        html = edit.content.decode()
        assert edit.status_code == 200
        assert "This flow is temporarily unavailable." not in html
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

        cancel_url = reverse(
            "n26-action-flow", args=[hunt.fighter.pk, record.pk, "cancel"]
        )
        cancel_page = client.get(cancel_url).content.decode()
        assert "Save and return later" in cancel_page
        assert "Your saved choices will be discarded." in cancel_page
        cancelled = client.post(cancel_url)
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
        from bs4 import BeautifulSoup

        from n26.core.render import option_key

        record, _, _ = start(client, hunt, hunt.upgrade)
        choose = reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "choose"])
        response = client.get(choose)
        assert response.status_code == 200
        assert response.context["stage"] == "choose"
        assert (f"{hunt.item.pk}|{hunt.tiers[0].pk}", "Hunting rig: Tier 1") in (
            response.context["form"].fields["selection"].choices
        )
        assert response.context["cancel_href"] == reverse(
            "n26-action-flow", args=[hunt.fighter.pk, record.pk, "cancel"]
        )
        assert response.context["back_href"] == reverse(
            "n26-action-flow", args=[hunt.fighter.pk, record.pk, "outcome"]
        )
        assert response.context["submit_label"] == "Review"
        assert hunt.kills.counter_value.value == 6
        response = client.post(
            choose, {"selection": f"{hunt.item.pk}|{hunt.tiers[0].pk}"}
        )
        assert response.status_code == 302
        review = client.get(response.url)
        assert review.status_code == 200
        assert review.context["review_choice"]["title"] == "Hunting rig: Tier 1"
        assert review.context["change_href"] == choose
        assert [
            (fact.label, fact.value)
            for fact in review.context["payment_tallies"][0].facts
        ] == [
            ("Available", "6 Kill Count"),
            ("This action", "4 Kill Count"),
            ("Remaining", "2 Kill Count"),
        ]
        token = review.context["form"]["review"].value()
        confirmed = client.post(response.url, {"review": token})
        assert confirmed.status_code == 302
        receipt = client.get(confirmed.url)
        assert receipt.status_code == 200
        assert [(line.label, line.value) for line in receipt.context["receipt"]] == [
            ("Kill Count", "6 → 2"),
            ("Rating", "+20¢"),
        ]
        assert receipt.context["back_label"] == "Change result"
        assert receipt.context["back_href"] == reverse(
            "n26-action-flow", args=[hunt.fighter.pk, record.pk, "correct"]
        )
        assert receipt.context["done_href"] == reverse(
            "n26-edit-fighter", args=[hunt.fighter.pk]
        )
        assert receipt.context["stage"] == "done"
        completed = BeautifulSoup(receipt.content, "html.parser")
        assert (
            completed.find(
                "a", string=lambda value: value and value.strip() == "Change result"
            )["href"]
            == receipt.context["back_href"]
        )
        assert (
            completed.find("a", string=lambda value: value and value.strip() == "Done")[
                "href"
            ]
            == receipt.context["done_href"]
        )
        assert (
            ActionRecord.objects.get(pk=record.pk).state == ActionRecord.State.COMPLETED
        )
        tier_slot = Assignment.objects.get(
            caused_by=hunt.item, slot__mode=Slot.Mode.TIER_LADDER, archived=False
        )
        key = f"{hunt.fighter.pk}:{tier_slot.pk}:{tier_slot.slot_id}"
        picker = reverse("n26-choose", args=[hunt.gang.pk, key])
        assert client.post(picker, {"thing": "none"}).status_code == 302
        assert (
            client.post(picker, {"thing": option_key(hunt.tiers[0])}).status_code == 302
        )
        hunt.kills.refresh_from_db()
        assert hunt.kills.counter_value.value == 2
        assert ActionRecord.objects.filter(fighter=hunt.fighter).count() == 1
        assert client.get(confirmed.url).status_code == 200
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

    @pytest.mark.parametrize("destination", ["fighter", "stash", "weapon"])
    @pytest.mark.parametrize("item_kind", ["direct", "granted"])
    def test_an_augmented_rig_cannot_be_reassigned_through_a_direct_request(
        self, client, hunt, destination, item_kind
    ):
        from n26.core.card import build_card, build_modifier_index, carriers
        from n26.core.effects import compute
        from n26.core.render import build_model_card

        def statline():
            card = build_card(hunt.fighter, with_statlines=True)
            computed = compute(card, build_modifier_index(carriers(card)))
            return build_model_card(hunt.fighter, card=card, computed=computed).statline

        if item_kind == "granted":
            carrier = a.create_wargear("Rig carrier")
            a.add_built_in(carrier, hunt.item.wargear)
            moved_item = buy(hunt.fighter, thing=carrier, paid=0)
            hunt.item = Assignment.objects.get(
                caused_by=moved_item, wargear=hunt.item.wargear
            )
        else:
            moved_item = hunt.item
        record, _, _ = start(client, hunt, hunt.upgrade)
        with operation(hunt.gang, actor=hunt.owner) as op:
            record = op.review_action(
                record,
                outcome=hunt.upgrade,
                terms={
                    "item_assignment": str(hunt.item.pk),
                    "intended_pick": str(hunt.tiers[0].pk),
                },
            )
            record = op.complete_action(
                record,
                revision=record.revision,
                review=record.review,
                outcome=hunt.upgrade,
            )
            if destination != "stash":
                other = op.hire(
                    hunt.fighter.membership.profile, "Other hunter", paid=100
                )
            if destination == "weapon":
                weapon = op.give_weapon(other, a.create_weapon("Other weapon"), paid=0)
        before = statline()
        assert before.get("S").modified
        events = list(record.ledger_events.values_list("pk", flat=True))
        equip = reverse("n26-equip", args=[hunt.fighter.pk])
        body = client.get(equip).content.decode()
        assert f"reassign={moved_item.pk}" not in body
        assert (
            reverse("n26-reassign", args=[moved_item.pk])
            not in client.get(f"{equip}?reassign={moved_item.pk}").content.decode()
        )
        if destination == "fighter":
            payload = {"miniature": str(other.pk)}
        elif destination == "stash":
            payload = {"to": "stash"}
        else:
            payload = {"to": "weapon", "weapon": str(weapon.pk)}
        refused = client.post(
            reverse("n26-reassign", args=[moved_item.pk]), payload, follow=True
        )
        assert (
            "It has earned augmentations that cannot be transferred."
            in refused.content.decode()
        )
        hunt.item.refresh_from_db()
        assert hunt.item.miniature_root_id == hunt.fighter.pk
        assert statline() == before
        assert list(record.ledger_events.values_list("pk", flat=True)) == events
        hunt.gang.refresh_from_db()
        assert_reconciled(hunt.gang)

    @pytest.mark.parametrize("lifecycle", ["death", "unpaid_ransom"])
    def test_death_stashes_augmented_kit_without_allowing_its_transfer(
        self, client, hunt, lifecycle
    ):
        from n26.core.status import Status

        item = buy(hunt.fighter, thing=hunt.item.wargear, paid=10)
        record, _, _ = start(client, hunt, hunt.upgrade)
        with operation(hunt.gang, actor=hunt.owner) as op:
            record = op.review_action(
                record,
                outcome=hunt.upgrade,
                terms={
                    "item_assignment": str(item.pk),
                    "intended_pick": str(hunt.tiers[0].pk),
                },
            )
            record = op.complete_action(
                record,
                revision=record.revision,
                review=record.review,
                outcome=hunt.upgrade,
            )
            other = op.hire(hunt.fighter.membership.profile, "Other hunter", paid=100)
            if lifecycle == "unpaid_ransom":
                op.set_status(hunt.fighter, Status.RANSOMED)
        events = list(record.ledger_events.values_list("pk", flat=True))
        if lifecycle == "unpaid_ransom":
            url = reverse("n26-pay-ransom", args=[hunt.fighter.pk])
            payload = {"outcome": "unpaid"}
        else:
            url = reverse("n26-mark-fighter", args=[hunt.fighter.pk])
            payload = {"status": "dead", "kit": "stash"}
        response = client.post(url, payload, follow=True)
        assert response.status_code == 200
        hunt.fighter.refresh_from_db()
        item.refresh_from_db()
        assert hunt.fighter.status == Status.DEAD
        assert item.stash_root_id == hunt.gang.stash.pk
        assert f"reassign={item.pk}" not in response.content.decode()
        sheet = reverse("n26-gang", args=[hunt.gang.pk])
        assert (
            reverse("n26-reassign", args=[item.pk])
            not in client.get(f"{sheet}?reassign={item.pk}").content.decode()
        )
        refused = client.post(
            reverse("n26-reassign", args=[item.pk]),
            {"miniature": str(other.pk)},
            follow=True,
        )
        assert (
            "earned augmentations that cannot be transferred"
            in refused.content.decode()
        )
        item.refresh_from_db()
        assert item.stash_root_id == hunt.gang.stash.pk
        assert list(record.ledger_events.values_list("pk", flat=True)) == events
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
        assert revisit.context["payment_tallies"][0].facts[0].value == "7 Kill Count"
        fresh_token = revisit.context["form"]["review"].value()
        assert client.post(url, {"review": fresh_token}).status_code == 302
        hunt.kills.counter_value.refresh_from_db()
        assert hunt.kills.counter_value.value == 3
        hunt.gang.refresh_from_db()
        assert_reconciled(hunt.gang)

    def test_resuming_after_a_glitch_shows_current_state_without_rewriting_the_draft(
        self, client, hunt
    ):
        with operation(hunt.gang, actor=hunt.owner) as op:
            op.tally(hunt.glitches, -2)
        record, _, _ = start(client, hunt, hunt.clear)
        url = reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "review"])
        original_review = record.review
        old_token = client.get(url).context["form"]["review"].value()
        with operation(hunt.gang, actor=hunt.owner) as op:
            op.tally(hunt.glitches, 1)
            op.tally(hunt.kills, 1)

        resumed = client.get(
            reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "resume"]),
            follow=True,
        )
        assert "Glitch Count: 1 → 0" in resumed.content.decode()
        assert resumed.context["payment_tallies"][0].facts[0].value == "7 Kill Count"
        record.refresh_from_db()
        assert record.review == original_review
        fresh_token = resumed.context["form"]["review"].value()

        refused = client.post(url, {"review": old_token})
        assert refused.context["form"].non_field_errors()
        record.refresh_from_db()
        assert not record.payment_id
        assert client.post(url, {"review": fresh_token}).status_code == 302
        assert client.post(url, {"review": fresh_token}).status_code == 302
        hunt.glitches.counter_value.refresh_from_db()
        hunt.kills.counter_value.refresh_from_db()
        assert hunt.glitches.counter_value.value == 0
        assert hunt.kills.counter_value.value == 3
        record.refresh_from_db()
        assert record.review["target"][0]["before"] == 1
        assert (
            record.ledger_events.filter(
                kind=LedgerEvent.Kind.ACTION_USE_COMPLETED
            ).count()
            == 1
        )
        hunt.gang.refresh_from_db()
        assert_reconciled(hunt.gang)

    def test_clearing_no_glitches_explains_why_and_spends_nothing(self, client, hunt):
        with operation(hunt.gang, actor=hunt.owner) as op:
            op.tally(hunt.glitches, -2)
        record, _, _ = start(client, hunt, hunt.clear)
        url = reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "review"])
        token = client.get(url).context["form"]["review"].value()
        refused = client.post(url, {"review": token})
        assert "This model has no glitches to clear." in refused.content.decode()
        record.refresh_from_db()
        hunt.kills.counter_value.refresh_from_db()
        assert not record.payment_id
        assert record.state == ActionRecord.State.STARTED
        assert hunt.kills.counter_value.value == 6
        hunt.gang.refresh_from_db()
        assert_reconciled(hunt.gang)

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

    def test_a_missing_price_counter_is_shown_on_outcome_and_item_pages(
        self, client, hunt
    ):
        record, _, _ = start(client, hunt, hunt.upgrade)
        hunt.kills.archived = True
        hunt.kills.save(update_fields=["archived"])
        for step in ("outcome", "choose"):
            response = client.get(
                reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, step])
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

    def test_recent_history_shows_only_the_confirmed_augmentation_item(
        self, client, hunt
    ):
        spare = a.create_wargear("Spare rig", price=0)
        a.add_built_in(spare, hunt.item.caused.get(slot__isnull=False).slot)
        spare_item = buy(hunt.fighter, thing=spare, paid=0)
        record, _, _ = start(client, hunt, hunt.upgrade)
        choose = reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "choose"])
        review_url = client.post(
            choose, {"selection": f"{hunt.item.pk}|{hunt.tiers[0].pk}"}
        ).url
        reviewed = client.get(review_url)
        assert (
            client.post(
                review_url, {"review": reviewed.context["form"]["review"].value()}
            ).status_code
            == 302
        )

        def history_detail():
            page = client.get(reverse("n26-edit-fighter", args=[hunt.fighter.pk]))
            panel = next(
                panel
                for panel in page.context["action_history_panels"]
                if panel.action_id == str(hunt.action.pk)
            )
            return panel.completed[0].detail

        assert history_detail().startswith("Hunting rig: Tier 1. ")
        correction_url = client.post(
            reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "correct"]),
            {"selection": f"{spare_item.pk}|{hunt.tiers[0].pk}"},
        ).url
        correction = client.get(correction_url)
        assert history_detail() == "Hunting rig: Tier 1"

        assert (
            client.post(
                correction_url,
                {"review": correction.context["form"]["review"].value()},
            ).status_code
            == 302
        )
        assert history_detail() == "Spare rig: Tier 1"
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

    def test_an_outcome_less_draft_returns_to_selecting_its_result(self, client, hunt):
        with operation(hunt.gang, actor=hunt.owner) as op:
            record = op.start_action(hunt.fighter, hunt.action, uuid4())
        client.force_login(hunt.owner)
        outcome_url = reverse(
            "n26-action-flow", args=[hunt.fighter.pk, record.pk, "outcome"]
        )

        original = (record.state, record.revision, record.terms, record.review)
        for step, method in (("resume", "get"), ("roll", "get"), ("roll", "post")):
            url = reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, step])
            response = getattr(client, method)(url, follow=True)
            assert response.status_code == 200
            assert response.redirect_chain == [(outcome_url, 302)]
            assert response.context["stage"] == "start"
            record.refresh_from_db()
            assert (
                record.state,
                record.revision,
                record.terms,
                record.review,
            ) == original
            assert record.outcome_id is None
            assert record.payment_id is None
            assert not record.ledger_events.filter(
                kind=LedgerEvent.Kind.ROLLED
            ).exists()
        replay = client.post(
            reverse("n26-action-start", args=[hunt.fighter.pk, hunt.action.pk]),
            {"request_key": str(record.request_key)},
            follow=True,
        )
        assert replay.status_code == 200
        assert replay.context["stage"] == "start"
        chosen = client.post(outcome_url, {"outcome": str(hunt.upgrade.pk)})
        assert chosen.status_code == 302
        record.refresh_from_db()
        assert record.outcome_id == hunt.upgrade.pk
        assert ActionRecord.objects.filter(fighter=hunt.fighter).count() == 1

    @pytest.mark.parametrize("outcome_name", ["upgrade", "clear"])
    def test_the_roll_route_keeps_non_advancement_flows_in_their_own_forms(
        self, client, hunt, outcome_name
    ):
        record, _, _ = start(client, hunt, getattr(hunt, outcome_name))
        url = reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "roll"])

        original = (
            record.state,
            record.revision,
            record.terms,
            record.review,
            record.payment_id,
        )
        for method in ("get", "post"):
            response = getattr(client, method)(url, follow=True)
            assert response.status_code == 200
            assert response.redirect_chain[0] == (
                reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "choose"]),
                302,
            )
            assert response.context["stage"] == (
                "choose" if outcome_name == "upgrade" else "review"
            )
            record.refresh_from_db()
            assert (
                record.state,
                record.revision,
                record.terms,
                record.review,
                record.payment_id,
            ) == original
            assert not record.ledger_events.filter(
                kind=LedgerEvent.Kind.ROLLED
            ).exists()
