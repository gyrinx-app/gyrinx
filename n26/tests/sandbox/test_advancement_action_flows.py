"""A player resolves earned advancements through the whole browser flow."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import (
    ActionAllowance,
    ActionRecord,
    Assignment,
    LedgerEvent,
    SkillSelection,
)
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.library import authoring as a
from n26.library.models import Dice, Skill
from n26.tests.sandbox.actions import found_gang, hire

pytestmark = pytest.mark.django_db


@pytest.fixture
def advancement(default_pack, gang_type, make_profile, make_statline, counter_tracking):
    owner = User.objects.create_user("advancement-player")
    gang = found_gang("The Climbers", gang_type, owner=owner, budget=1000)
    profile = make_profile("Prospect", price=100)
    make_statline(profile)

    agility = a.create_category("Skills", "Agility", position=0)
    brawn = a.create_category("Skills", "Brawn", position=1)
    skills = {
        "owned": a.create_skill("Catfall", category=agility, position=1),
        "primary": a.create_skill("Dodge", category=agility, position=2),
        "secondary": a.create_skill("Bull Charge", category=brawn, position=1),
    }
    catalogue = a.create_collection("Skills", contains=[Skill])
    primary = a.section_of(catalogue, "Primary", 0)
    secondary = a.section_of(catalogue, "Secondary", 1)
    a.section_of(catalogue, "Other", 2, is_default=True)
    for category, section in ((agility, primary), (brawn, secondary)):
        a.modifier(
            f"Prospect: {category} is {section}",
            a.targets_model(),
            a.ef_places(category, section),
            attach_to=profile,
        )

    kind = a.create_slot_type("Advancement")
    results = {}
    for position, (key, label, section, mode) in enumerate(
        (
            ("primary", "Select Primary skill", primary, "select"),
            ("secondary", "Select Secondary skill", secondary, "select"),
            ("any", "Select any skill", None, "select"),
            ("random", "Random Primary skill", primary, "random"),
        )
    ):
        results[key] = a.create_pickable(
            label,
            kind,
            rating_contribution=5 + position,
            effects=[
                (
                    a.targets_model(),
                    a.ef_offers_choice(
                        Skill,
                        from_section=section,
                        label=label,
                        mode=mode,
                    ),
                )
            ],
        )
    table = a.create_picklist(
        "Prospect advancement results", kind, dice="2d6", roll_selects="threshold"
    )
    for position, result in enumerate(results.values()):
        a.add_picklist_member(table, result, position=position, roll_low=2 + position)
    slot = a.create_slot("Prospect advancement", kind, table)
    outcome = a.create_outcome("Advancement", a.resolve_advancement(slot))
    xp = a.create_counter("XP")
    ranks = a.create_rank_table("Prospect ranks", xp, thresholds=[4])
    action = a.create_action(
        "Advance",
        "post_cycle",
        outcomes=[outcome],
        allowance_rule=a.rank_allowance_rule(xp),
    )
    fighter = hire(gang, profile, "Kara")
    with operation(gang, actor=owner) as op:
        op.assign(action, miniature=fighter)
        op.assign(ranks, miniature=fighter)
        counter = op.assign(xp, miniature=fighter)
        op.open_counter(counter, 0)
        op.assign(skills["owned"], miniature=fighter)
        op.tally(counter, 4)
    allowance = ActionAllowance.objects.get(fighter=fighter, threshold=4)
    return SimpleNamespace(
        owner=owner,
        gang=gang,
        fighter=fighter,
        action=action,
        outcome=outcome,
        results=results,
        skills=skills,
        primary=primary,
        secondary=secondary,
        allowance=allowance,
        xp=counter,
    )


def _load_rolls(monkeypatch, *rolls):
    rolled = iter(rolls)
    monkeypatch.setattr(
        Dice, "roll", classmethod(lambda cls, dice, rng=None: next(rolled))
    )


def _start(client, advancement):
    client.force_login(advancement.owner)
    url = reverse(
        "n26-action-start", args=[advancement.fighter.pk, advancement.action.pk]
    )
    response = client.post(
        url,
        {
            "request_key": str(uuid4()),
            "outcome": str(advancement.outcome.pk),
            "allowance": str(advancement.allowance.pk),
        },
    )
    assert response.status_code == 302
    return ActionRecord.objects.get(fighter=advancement.fighter)


def _post_roll(client, advancement, record):
    url = reverse("n26-action-flow", args=[advancement.fighter.pk, record.pk, "choose"])
    page = client.get(url)
    assert page.context["stage"] == "roll"
    response = client.post(
        url,
        {
            "request_key": page.context["form"]["request_key"].value(),
            "roll_mode": "roll",
        },
    )
    assert response.status_code == 302
    return response.url


def _choose_result(client, advancement, record, result, *, stage="choose"):
    url = reverse("n26-action-flow", args=[advancement.fighter.pk, record.pk, stage])
    response = client.post(url, {"pickable_id": str(result.pk)})
    assert response.status_code == 302
    return response.url


class TestAnEarnedAdvancementStartsAndResumes:
    """XP remains held while its earned use keeps one saved 2D6 result."""

    def test_crossing_xp_opens_one_earned_flow_and_the_roll_survives_resume(
        self, client, monkeypatch, advancement
    ):
        _load_rolls(monkeypatch, 12)
        record = _start(client, advancement)
        choose_url = _post_roll(client, advancement, record)
        assert client.get(choose_url).context["roll_value"] == 12
        resume = reverse(
            "n26-action-flow", args=[advancement.fighter.pk, record.pk, "resume"]
        )
        resumed = client.get(resume, follow=True)
        assert resumed.context["roll_value"] == 12
        advancement.xp.counter_value.refresh_from_db()
        assert advancement.xp.counter_value.value == 4
        assert (
            LedgerEvent.objects.filter(
                action_record=record, kind=LedgerEvent.Kind.ROLLED
            ).count()
            == 1
        )

    def test_a_roll_removes_the_cancel_route(self, client, monkeypatch, advancement):
        _load_rolls(monkeypatch, 12)
        record = _start(client, advancement)
        _post_roll(client, advancement, record)
        cancel = reverse(
            "n26-action-flow", args=[advancement.fighter.pk, record.pk, "cancel"]
        )
        response = client.post(cancel)
        record.refresh_from_db()
        assert response.status_code == 302
        assert record.state == ActionRecord.State.STARTED

    def test_an_earned_use_reserved_in_another_tab_resumes_the_same_flow(
        self, client, advancement
    ):
        record = _start(client, advancement)
        response = client.post(
            reverse(
                "n26-action-start", args=[advancement.fighter.pk, advancement.action.pk]
            ),
            {
                "request_key": str(uuid4()),
                "outcome": str(advancement.outcome.pk),
                "allowance": str(advancement.allowance.pk),
            },
        )
        assert response.status_code == 302
        assert response.url == reverse(
            "n26-action-flow", args=[advancement.fighter.pk, record.pk, "resume"]
        )
        assert (
            ActionRecord.objects.filter(fighter=advancement.fighter).get().pk
            == record.pk
        )

    def test_a_recorded_roll_is_durable_and_the_highest_available_results_come_first(
        self, client, monkeypatch, advancement
    ):
        _load_rolls(monkeypatch)
        record = _start(client, advancement)
        url = reverse(
            "n26-action-flow", args=[advancement.fighter.pk, record.pk, "choose"]
        )
        page = client.get(url)
        payload = {
            "request_key": page.context["form"]["request_key"].value(),
            "roll_mode": "record",
            "rolled": "4",
        }
        response = client.post(url, payload)
        assert response.status_code == 302
        page = client.get(response.url)
        assert page.context["roll_value"] == 4
        assert [
            item["option"].name for item in page.context["advancement_options"]
        ] == ["Select any skill", "Select Secondary skill", "Select Primary skill"]
        html = page.content.decode()
        assert "Choose any result at or below your roll." in html
        assert "It asks" not in html
        assert "Roll 4+" in html
        back = client.get(page.context["back_href"])
        assert back.context["advancement_roll"]["previousRoll"] == 4
        client.post(page.context["back_href"], {**payload, "rolled": "12"})
        record.refresh_from_db()
        assert record.advancement_selection.roll_event.roll == 4
        assert (
            LedgerEvent.objects.filter(
                action_record=record, kind=LedgerEvent.Kind.ROLLED
            ).count()
            == 1
        )

    @pytest.mark.parametrize("rolled", ["", "0", "1", "13", "not a number"])
    def test_invalid_recorded_totals_do_not_generate_a_roll(
        self, client, monkeypatch, advancement, rolled
    ):
        _load_rolls(monkeypatch)
        record = _start(client, advancement)
        url = reverse(
            "n26-action-flow", args=[advancement.fighter.pk, record.pk, "choose"]
        )
        page = client.get(url)
        response = client.post(
            url,
            {
                "request_key": page.context["form"]["request_key"].value(),
                "roll_mode": "record",
                "rolled": rolled,
            },
        )
        assert response.status_code == 200
        assert "rolled" in response.context["form"].errors
        assert response.context["advancement_roll"]["rolled"] == rolled
        assert not LedgerEvent.objects.filter(
            action_record=record, kind=LedgerEvent.Kind.ROLLED
        ).exists()

    def test_missing_roll_controls_do_not_generate_a_roll(
        self, client, monkeypatch, advancement
    ):
        _load_rolls(monkeypatch)
        record = _start(client, advancement)
        url = reverse(
            "n26-action-flow", args=[advancement.fighter.pk, record.pk, "choose"]
        )
        page = client.get(url)
        response = client.post(
            url, {"request_key": page.context["form"]["request_key"].value()}
        )
        assert response.status_code == 200
        assert response.context["form"].errors["roll_mode"] == ["Choose how to roll."]
        assert response.context["advancement_roll"]["mode"] == ""
        assert not LedgerEvent.objects.filter(
            action_record=record, kind=LedgerEvent.Kind.ROLLED
        ).exists()

    def test_generated_roll_ignores_the_disabled_total(
        self, client, monkeypatch, advancement
    ):
        _load_rolls(monkeypatch, 6)
        record = _start(client, advancement)
        url = reverse(
            "n26-action-flow", args=[advancement.fighter.pk, record.pk, "choose"]
        )
        page = client.get(url)
        response = client.post(
            url,
            {
                "request_key": page.context["form"]["request_key"].value(),
                "roll_mode": "roll",
                "rolled": "8",
            },
        )
        assert response.status_code == 302
        assert (
            LedgerEvent.objects.get(
                action_record=record, kind=LedgerEvent.Kind.ROLLED
            ).roll
            == 6
        )


class TestChangingTheRoll:
    def test_correcting_2d6_preserves_the_skill_roll_but_clears_the_pending_choice(
        self, client, monkeypatch, advancement
    ):
        _load_rolls(monkeypatch, 12, 2)
        record = _start(client, advancement)
        _post_roll(client, advancement, record)
        skill_url = _choose_result(
            client, advancement, record, advancement.results["random"]
        )
        page = client.get(skill_url)
        category = page.context["skill_groups"][0]["key"]
        assert (
            client.post(
                skill_url,
                {
                    "request_key": page.context["form"]["request_key"].value(),
                    "skill_set_id": category,
                },
            ).status_code
            == 302
        )
        old_selection = SkillSelection.objects.get(action_record=record)
        assert old_selection.selected_skill == advancement.skills["primary"]
        old_event = old_selection.random_attempts[-1]["event_id"]
        roll_url = reverse(
            "n26-action-flow", args=[advancement.fighter.pk, record.pk, "roll"]
        )
        page = client.get(roll_url)
        payload = {
            "request_key": page.context["form"]["request_key"].value(),
            "previous_roll": page.context["form"]["previous_roll"].value(),
            "roll_mode": "record",
            "rolled": "12",
        }
        assert client.post(roll_url, payload).status_code == 302
        assert SkillSelection.objects.filter(pk=old_selection.pk).exists()

        payload["rolled"] = "11"
        assert client.post(roll_url, payload).status_code == 302
        record.refresh_from_db()
        assert "pickable_id" not in record.terms
        assert record.review == {}
        assert LedgerEvent.objects.filter(pk=old_event, action_record=record).exists()
        skill_url = _choose_result(
            client, advancement, record, advancement.results["random"]
        )
        page = client.get(skill_url)
        assert page.context["stage"] == "skill"
        assert page.context["skill_resolved"] is True
        assert page.context["submit_label"] == "Review"
        assert client.post(skill_url, {"review_skill": "1"}).status_code == 302
        selection = SkillSelection.objects.get(action_record=record)
        assert selection.selected_skill == advancement.skills["primary"]
        assert selection.random_attempts == old_selection.random_attempts
        assert client.post(roll_url, payload).status_code == 302
        assert SkillSelection.objects.filter(pk=selection.pk).exists()
        assert sorted(
            LedgerEvent.objects.filter(
                action_record=record, kind=LedgerEvent.Kind.ROLLED
            ).values_list("roll", flat=True)
        ) == [2, 11, 12]
        assert_reconciled(advancement.gang)

    def test_back_allows_a_correction_and_invalidates_the_old_review(
        self, client, monkeypatch, advancement
    ):
        _load_rolls(monkeypatch, 12)
        record = _start(client, advancement)
        _post_roll(client, advancement, record)
        skill_url = _choose_result(
            client, advancement, record, advancement.results["primary"]
        )
        reviewed = client.post(
            skill_url, {"skill_id": str(advancement.skills["primary"].pk)}
        )
        review_page = client.get(reviewed.url)
        token = review_page.context["form"]["review"].value()
        skill_page = client.get(review_page.context["back_href"])
        choices = client.get(skill_page.context["back_href"])
        roll_url = choices.context["back_href"]
        page = client.get(roll_url)
        payload = {
            "request_key": page.context["form"]["request_key"].value(),
            "previous_roll": page.context["form"]["previous_roll"].value(),
            "roll_mode": "record",
            "rolled": "3",
        }
        response = client.post(roll_url, payload)
        assert response.status_code == 302, response.context["form"].errors
        record.refresh_from_db()
        assert record.advancement_selection.roll_event.roll == 3
        assert record.review == {}
        assert "pickable_id" not in record.terms
        assert "skill_id" not in record.terms
        choices = client.get(response.url)
        assert choices.context["roll_value"] == 3
        assert [
            item["option"].name for item in choices.context["advancement_options"]
        ] == ["Select Secondary skill", "Select Primary skill"]
        assert client.post(roll_url, payload).status_code == 302
        stale = client.post(
            roll_url, {**payload, "request_key": str(uuid4()), "rolled": "5"}
        )
        assert stale.status_code == 200
        assert "This roll has changed" in stale.content.decode()
        client.post(reviewed.url, {"review": token})
        record.refresh_from_db()
        assert record.state == ActionRecord.State.STARTED
        assert sorted(
            LedgerEvent.objects.filter(
                action_record=record, kind=LedgerEvent.Kind.ROLLED
            ).values_list("roll", flat=True)
        ) == [3, 12]
        assert_reconciled(advancement.gang)


class TestSelectingSkills:
    """The same saved roll can resolve each authored skill access tier."""

    @pytest.mark.parametrize(
        ("result_key", "skill_key"),
        (("primary", "primary"), ("secondary", "secondary"), ("any", "secondary")),
    )
    def test_primary_secondary_and_any_each_show_and_save_an_allowed_skill(
        self, client, monkeypatch, advancement, result_key, skill_key
    ):
        _load_rolls(monkeypatch, 12)
        record = _start(client, advancement)
        _post_roll(client, advancement, record)
        skill_url = _choose_result(
            client, advancement, record, advancement.results[result_key]
        )
        skill = advancement.skills[skill_key]
        page = client.get(skill_url)
        assert str(skill) in page.content.decode()
        assert page.context["back_href"] == reverse(
            "n26-action-flow", args=[advancement.fighter.pk, record.pk, "choose"]
        )
        assert client.get(page.context["back_href"]).context["roll_value"] == 12
        response = client.post(skill_url, {"skill_id": str(skill.pk)})
        assert response.status_code == 302
        assert ActionRecord.objects.get(pk=record.pk).terms["skill_id"] == str(skill.pk)
        review = client.get(response.url)
        assert review.context["back_href"] == skill_url
        assert review.context["show_outcome"] is False
        assert review.context["review_choice"]["description"] == str(skill)

    def test_random_skill_rerolls_an_unavailable_result_and_keeps_the_success(
        self, client, monkeypatch, advancement
    ):
        _load_rolls(monkeypatch, 12, 1, 2)
        record = _start(client, advancement)
        _post_roll(client, advancement, record)
        skill_url = _choose_result(
            client, advancement, record, advancement.results["random"]
        )
        page = client.get(skill_url)
        category = next(iter(page.context["skill_groups"]))
        first = client.post(
            skill_url,
            {
                "request_key": page.context["form"]["request_key"].value(),
                "skill_set_id": category["key"],
            },
        )
        assert first.status_code == 302
        assert (
            client.post(
                skill_url,
                {
                    "request_key": page.context["form"]["request_key"].value(),
                    "skill_set_id": category["key"],
                },
            ).status_code
            == 302
        )
        resume = reverse(
            "n26-action-flow", args=[advancement.fighter.pk, record.pk, "resume"]
        )
        retry = client.get(resume, follow=True)
        assert retry.context["stage"] == "skill"
        assert "No available skill was rolled." in retry.content.decode()
        second = client.post(
            first.url,
            {
                "request_key": retry.context["form"]["request_key"].value(),
                "skill_set_id": category["key"],
            },
        )
        resolved = client.get(second.url)
        assert str(advancement.skills["primary"]) in resolved.content.decode()
        record.refresh_from_db()
        assert [
            attempt["roll"] for attempt in record.skill_selection.random_attempts
        ] == [1, 2]


class TestCompletingAndCorrecting:
    """Confirmation settles once; correction changes the pick around that receipt."""

    def test_recent_history_shows_only_the_confirmed_skill_selection(
        self, client, monkeypatch, advancement
    ):
        _load_rolls(monkeypatch, 12)
        record = _start(client, advancement)
        _post_roll(client, advancement, record)
        skill_url = _choose_result(
            client, advancement, record, advancement.results["primary"]
        )
        review_url = client.post(
            skill_url, {"skill_id": str(advancement.skills["primary"].pk)}
        ).url
        reviewed = client.get(review_url)
        assert (
            client.post(
                review_url, {"review": reviewed.context["form"]["review"].value()}
            ).status_code
            == 302
        )

        def history_detail():
            page = client.get(
                reverse("n26-edit-fighter", args=[advancement.fighter.pk])
            )
            panel = next(
                panel
                for panel in page.context["action_history_panels"]
                if panel.action_id == str(advancement.action.pk)
            )
            return panel.completed[0].detail

        assert history_detail() == "Select Primary skill: Dodge"
        corrected_skill = _choose_result(
            client,
            advancement,
            record,
            advancement.results["secondary"],
            stage="correct",
        )
        correction_url = client.post(
            corrected_skill, {"skill_id": str(advancement.skills["secondary"].pk)}
        ).url
        correction = client.get(correction_url)
        assert history_detail() == "Select Primary skill: Dodge"

        assert (
            client.post(
                correction_url,
                {"review": correction.context["form"]["review"].value()},
            ).status_code
            == 302
        )
        assert history_detail() == "Select Secondary skill: Bull Charge"
        advancement.gang.refresh_from_db()
        assert_reconciled(advancement.gang)

    def test_completion_and_correction_keep_one_use_and_one_roll(
        self, client, monkeypatch, advancement
    ):
        credits = advancement.gang.recompute_credits()
        _load_rolls(monkeypatch, 12)
        record = _start(client, advancement)
        _post_roll(client, advancement, record)
        skill_url = _choose_result(
            client, advancement, record, advancement.results["primary"]
        )
        review = client.post(
            skill_url, {"skill_id": str(advancement.skills["primary"].pk)}
        )
        review_page = client.get(review.url)
        token = review_page.context["form"]["review"].value()
        completed = client.post(review.url, {"review": token})
        assert completed.status_code == 302
        assert client.post(review.url, {"review": token}).status_code == 302
        record.refresh_from_db()
        payment = record.payment_id
        assert record.state == ActionRecord.State.COMPLETED
        assert advancement.gang.recompute_credits() == credits

        from n26.core.rating import read_rating_receipt

        receipt = read_rating_receipt(advancement.fighter)
        assert ("Advancements", 5) in [
            (line.label, line.rating) for line in receipt.contributions
        ]
        advancement.fighter.refresh_from_db()
        assert receipt.total == advancement.fighter.rating

        corrected_skill = _choose_result(
            client,
            advancement,
            record,
            advancement.results["secondary"],
            stage="correct",
        )
        assert corrected_skill.startswith(
            reverse(
                "n26-action-flow", args=[advancement.fighter.pk, record.pk, "skill"]
            )
        )
        skill_page = client.get(corrected_skill)
        choices = client.get(skill_page.context["back_href"])
        assert choices.context["form"]["pickable_id"].value() == str(
            advancement.results["secondary"].pk
        )
        record.refresh_from_db()
        assert record.terms["pickable_id"] == str(advancement.results["primary"].pk)
        reviewed = client.post(
            corrected_skill,
            {"skill_id": str(advancement.skills["secondary"].pk)},
        )
        correction_page = client.get(reviewed.url)
        skill_page = client.get(correction_page.context["back_href"])
        assert skill_page.context["form"]["skill_id"].value() == str(
            advancement.skills["secondary"].pk
        )
        choices = client.get(skill_page.context["back_href"])
        assert choices.context["form"]["pickable_id"].value() == str(
            advancement.results["secondary"].pk
        )
        record.refresh_from_db()
        assert record.terms["skill_id"] == str(advancement.skills["primary"].pk)
        corrected = client.post(
            reviewed.url,
            {"review": correction_page.context["form"]["review"].value()},
        )
        assert corrected.status_code == 302
        record.refresh_from_db()
        assert record.payment_id == payment
        assert advancement.gang.recompute_credits() == credits
        assert (
            LedgerEvent.objects.filter(
                action_record=record, kind=LedgerEvent.Kind.ROLLED
            ).count()
            == 1
        )
        assert Assignment.objects.filter(
            miniature_root=advancement.fighter,
            skill=advancement.skills["secondary"],
            archived=False,
        ).exists()
        advancement.gang.refresh_from_db()
        assert_reconciled(advancement.gang)

    def test_another_owner_cannot_read_or_post_any_stage(
        self, client, monkeypatch, advancement
    ):
        _load_rolls(monkeypatch, 12)
        record = _start(client, advancement)
        stranger = User.objects.create_user("advancement-stranger")
        client.force_login(stranger)
        for stage in (
            "choose",
            "skill",
            "review",
            "done",
            "correct",
            "cancel",
            "by-hand",
            "reopen",
        ):
            url = reverse(
                "n26-action-flow", args=[advancement.fighter.pk, record.pk, stage]
            )
            assert client.get(url).status_code == 404
            assert client.post(url, {}).status_code == 404


def _waiting(advancement):
    from n26.core.action_flow import available_action_names

    card = SimpleNamespace(id=str(advancement.fighter.pk), action_ids=())
    return available_action_names(advancement.gang, [card]).get(card.id, ())


def _edit_page(client, advancement):
    return client.get(
        reverse("n26-edit-fighter", args=[advancement.fighter.pk])
    ).content.decode()


def _mark_unused_by_hand(client, advancement, request_key=None):
    client.force_login(advancement.owner)
    url = (
        reverse(
            "n26-action-by-hand",
            args=[advancement.fighter.pk, advancement.action.pk],
        )
        + f"?allowance={advancement.allowance.pk}"
    )
    response = client.post(url, {"request_key": str(request_key or uuid4())})
    assert response.status_code == 302
    return response


def _flow(client, advancement, record, step):
    return client.post(
        reverse("n26-action-flow", args=[advancement.fighter.pk, record.pk, step])
    )


def _story(advancement):
    from n26.core import history

    return [
        "".join(span.text for span in act.spans)
        for act in history.build(advancement.gang)
    ]


class TestApplyingByHand:
    """A player who gave the result outside Gyrinx clears the waiting mark."""

    def test_an_unused_earned_use_is_cleared_without_touching_the_fighter(
        self, client, advancement
    ):
        with operation(advancement.gang, actor=advancement.owner) as op:
            by_hand = op.assign(
                advancement.skills["secondary"], miniature=advancement.fighter
            )
        assert _waiting(advancement) == ("Advance",)
        client.force_login(advancement.owner)
        assert "Mark as applied" in _edit_page(client, advancement)

        _mark_unused_by_hand(client, advancement)

        record = ActionRecord.objects.get(fighter=advancement.fighter)
        assert record.state == ActionRecord.State.APPLIED_BY_HAND
        assert record.allowance == advancement.allowance
        assert _waiting(advancement) == ()
        assert not ActionAllowance.objects.filter(fighter=advancement.fighter).unused()
        by_hand.refresh_from_db()
        assert not by_hand.archived
        assert "applied Advance by hand for Kara" in _story(advancement)
        page = _edit_page(client, advancement)
        assert "Applied by hand" in page
        assert "Undo" in page
        assert "Mark as applied" not in page
        assert_reconciled(advancement.gang)

    def test_the_cleared_rank_cannot_be_taken_again_through_the_flow(
        self, client, advancement
    ):
        _mark_unused_by_hand(client, advancement)
        client.post(
            reverse(
                "n26-action-start",
                args=[advancement.fighter.pk, advancement.action.pk],
            ),
            {
                "request_key": str(uuid4()),
                "outcome": str(advancement.outcome.pk),
                "allowance": str(advancement.allowance.pk),
            },
        )
        assert not ActionRecord.objects.filter(
            fighter=advancement.fighter, state=ActionRecord.State.STARTED
        ).exists()

    def test_a_repeated_request_marks_one_use(self, client, advancement):
        key = uuid4()
        _mark_unused_by_hand(client, advancement, key)
        _mark_unused_by_hand(client, advancement, key)
        assert ActionRecord.objects.filter(fighter=advancement.fighter).count() == 1
        assert (
            LedgerEvent.objects.filter(
                kind=LedgerEvent.Kind.ACTION_USE_APPLIED_BY_HAND
            ).count()
            == 1
        )

    def test_a_started_flow_with_a_roll_is_cleared_and_keeps_its_roll(
        self, client, monkeypatch, advancement
    ):
        _load_rolls(monkeypatch, 12)
        record = _start(client, advancement)
        _post_roll(client, advancement, record)
        assert _waiting(advancement) == ("Advance",)
        assert "Mark as applied" in _edit_page(client, advancement)

        assert _flow(client, advancement, record, "by-hand").status_code == 302

        record.refresh_from_db()
        assert record.state == ActionRecord.State.APPLIED_BY_HAND
        assert _waiting(advancement) == ()
        assert LedgerEvent.objects.filter(
            action_record=record, kind=LedgerEvent.Kind.ROLLED
        ).exists()
        resumed = client.get(
            reverse(
                "n26-action-flow", args=[advancement.fighter.pk, record.pk, "resume"]
            )
        )
        assert resumed.url == reverse("n26-edit-fighter", args=[advancement.fighter.pk])

    def test_undo_frees_an_unused_earned_use(self, client, advancement):
        _mark_unused_by_hand(client, advancement)
        record = ActionRecord.objects.get(fighter=advancement.fighter)

        _flow(client, advancement, record, "reopen")

        record.refresh_from_db()
        assert record.state == ActionRecord.State.CANCELLED
        assert _waiting(advancement) == ("Advance",)
        assert list(
            ActionAllowance.objects.filter(fighter=advancement.fighter).unused()
        ) == [advancement.allowance]
        assert "reopened Advance for Kara" in _story(advancement)

    def test_undo_returns_a_started_flow_with_its_roll(
        self, client, monkeypatch, advancement
    ):
        _load_rolls(monkeypatch, 12)
        record = _start(client, advancement)
        _post_roll(client, advancement, record)
        _flow(client, advancement, record, "by-hand")

        _flow(client, advancement, record, "reopen")

        record.refresh_from_db()
        assert record.state == ActionRecord.State.STARTED
        assert _waiting(advancement) == ("Advance",)
        resumed = client.get(
            reverse(
                "n26-action-flow", args=[advancement.fighter.pk, record.pk, "resume"]
            ),
            follow=True,
        )
        assert resumed.context["roll_value"] == 12

    def test_the_rank_history_names_the_state(self, client, advancement):
        from n26.core.progression import progression_for

        _mark_unused_by_hand(client, advancement)

        [rank] = progression_for(advancement.fighter).history
        assert rank.state_label == "Applied by hand"

    def test_another_owner_cannot_mark_an_unused_use(self, client, advancement):
        client.force_login(User.objects.create_user("by-hand-stranger"))
        url = reverse(
            "n26-action-by-hand", args=[advancement.fighter.pk, advancement.action.pk]
        )
        assert client.post(url, {"request_key": str(uuid4())}).status_code == 404
        assert not ActionRecord.objects.filter(fighter=advancement.fighter).exists()

    def test_marking_needs_a_post(self, client, advancement):
        client.force_login(advancement.owner)
        url = reverse(
            "n26-action-by-hand", args=[advancement.fighter.pk, advancement.action.pk]
        )
        assert client.get(url).status_code == 405

    def test_a_rolled_flow_loses_its_empty_slot_and_undo_lets_it_finish(
        self, client, monkeypatch, advancement
    ):
        _load_rolls(monkeypatch, 12)
        record = _start(client, advancement)
        _post_roll(client, advancement, record)
        rolled_slot = record.advancement_selection.slot_assignment

        _flow(client, advancement, record, "by-hand")

        rolled_slot.refresh_from_db()
        assert rolled_slot.archived

        _flow(client, advancement, record, "reopen")

        record.refresh_from_db()
        record.advancement_selection.refresh_from_db()
        rebound = record.advancement_selection.slot_assignment
        assert not rebound.archived
        assert rebound.slot_id == rolled_slot.slot_id
        skill_url = _choose_result(
            client, advancement, record, advancement.results["primary"]
        )
        review = client.post(
            skill_url, {"skill_id": str(advancement.skills["primary"].pk)}
        )
        token = client.get(review.url).context["form"]["review"].value()
        assert client.post(review.url, {"review": token}).status_code == 302
        record.refresh_from_db()
        assert record.state == ActionRecord.State.COMPLETED
        advancement.gang.refresh_from_db()
        assert_reconciled(advancement.gang)

    def test_an_older_flow_marked_now_keeps_its_undo_above_newer_results(
        self, client, monkeypatch, advancement
    ):
        _load_rolls(monkeypatch, 12)
        record = _start(client, advancement)
        for _ in range(3):
            ActionRecord.objects.create(
                gang=advancement.gang,
                fighter=advancement.fighter,
                action=advancement.action,
                outcome=advancement.outcome,
                request_key=uuid4(),
                state=ActionRecord.State.COMPLETED,
            )

        _flow(client, advancement, record, "by-hand")

        assert "Undo marking Advance as applied by hand" in _edit_page(
            client, advancement
        )
