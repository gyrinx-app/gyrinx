"""A player resolves earned advancements through the whole browser flow."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import ActionAllowance, ActionRecord, Assignment, LedgerEvent
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.library import authoring as a
from n26.library.models import Dice, Skill
from n26.tests.sandbox.actions import found_gang, hire

pytestmark = pytest.mark.django_db


@pytest.fixture
def advancement(default_pack, gang_type, make_profile, make_statline):
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
        url, {"request_key": page.context["form"]["request_key"].value()}
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

    def test_crossing_xp_opens_one_paid_flow_and_the_roll_survives_resume(
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
        response = client.post(skill_url, {"skill_id": str(skill.pk)})
        assert response.status_code == 302
        assert ActionRecord.objects.get(pk=record.pk).terms["skill_id"] == str(skill.pk)

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
        retry = client.get(first.url)
        assert "already owned or unavailable" in retry.content.decode()
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

    def test_completion_and_correction_keep_one_payment_and_one_roll(
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
        reviewed = client.post(
            corrected_skill,
            {"skill_id": str(advancement.skills["secondary"].pk)},
        )
        correction_page = client.get(reviewed.url)
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
        for stage in ("choose", "skill", "review", "done", "correct", "cancel"):
            url = reverse(
                "n26-action-flow", args=[advancement.fighter.pk, record.pk, stage]
            )
            assert client.get(url).status_code == 404
            assert client.post(url, {}).status_code == 404
