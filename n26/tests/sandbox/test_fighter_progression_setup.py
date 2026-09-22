"""Foundation setup is opt-in, repeatable, and resolves promotions at earned ranks."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.card import build_card, build_modifier_index, carriers
from n26.core.effects import compute
from n26.core.models import ActionAllowance, ActionRecord, Assignment, LedgerEvent
from n26.core.operations import Refusal, operation
from n26.library import authoring as a
from n26.library.fighter_action_setup import (
    attach_fighter_progression,
    prepare_fighter_progression,
    progression_plan,
)
from n26.library.models import (
    Action,
    AdvancementPromotion,
    Counter,
    Dice,
    Modifier,
    Pickable,
    Subtype,
    Trait,
)
from n26.tests.sandbox.actions import found_gang, give_weapon, hire

pytestmark = pytest.mark.django_db


def _errors(response):
    return (
        response.context["form"].errors
        if response.context and "form" in response.context
        else response.content.decode()[:800]
    )


@pytest.fixture
def progression(
    default_pack, make_profile, make_statline, gang_type, counter_tracking, request
):
    profile = make_profile("Test prospect", staged=True, price=100)
    make_statline(profile)
    prepare_fighter_progression()
    a.add_built_in(
        profile, Counter.objects.get(name="XP"), amount=getattr(request, "param", 12)
    )
    prospect = Subtype.objects.get(name="Prospect")
    a.modifier(
        "Prospect rank", a.targets_model(), a.ef_adds(prospect), attach_to=profile
    )
    attach_fighter_progression()
    profile.refresh_from_db()
    owner = User.objects.create_user("progression-player")
    gang = found_gang("The Climbers", gang_type, owner=owner, budget=1000)
    fighter = hire(gang, profile, "Kara")
    xp = Assignment.objects.get(miniature_root=fighter, counter__name="XP")
    action = Action.objects.get(name="Advancement")
    outcome = action.outcomes.get().outcome
    return SimpleNamespace(
        profile=profile,
        owner=owner,
        gang=gang,
        fighter=fighter,
        xp=xp,
        action=action,
        outcome=outcome,
    )


def _computed(fighter):
    card = build_card(fighter)
    return compute(card, build_modifier_index(carriers(card)))


def _earned(progression, threshold):
    with operation(progression.gang, actor=progression.owner) as op:
        # Opening XP is not earned XP: only this crossing grants an allowance.
        assert progression.xp.counter_value.value == threshold - 1
        op.tally(progression.xp, 1)
    return ActionAllowance.objects.get(fighter=progression.fighter, threshold=threshold)


def _start(client, progression, allowance):
    client.force_login(progression.owner)
    response = client.post(
        reverse(
            "n26-action-start", args=[progression.fighter.pk, progression.action.pk]
        ),
        {
            "request_key": str(uuid4()),
            "outcome": str(progression.outcome.pk),
            "allowance": str(allowance.pk),
        },
    )
    assert response.status_code == 302, _errors(response)
    record = ActionRecord.objects.get(allowance=allowance)
    return record, reverse(
        "n26-action-flow", args=[progression.fighter.pk, record.pk, "choose"]
    )


class TestFoundationSetup:
    """Test preparation cannot attach progression to an existing live profile."""

    def test_preparation_is_repeatable_and_live_profiles_are_untouched(
        self, default_pack, make_profile
    ):
        profile = make_profile("Live ganger")
        rule = prepare_fighter_progression()
        counts = Modifier.objects.count(), Pickable.objects.count()
        assert prepare_fighter_progression() == rule
        assert counts == (Modifier.objects.count(), Pickable.objects.count())
        assert not profile.modifiers.exists()
        assert attach_fighter_progression() == 0
        profile.refresh_from_db()
        assert profile.built_ins_id is None

    def test_live_setup_preserves_starting_xp_and_excludes_hired_guns_and_delegations(
        self, default_pack, make_profile
    ):
        ordinary = make_profile("Ganger")
        hired = make_profile(
            "Mercenary",
            category=a.create_category("Supplementary profiles", "Hired Guns"),
        )
        ally = make_profile("Envoy", category=a.create_category("Allies", "Delegation"))
        persona = make_profile(
            "Named mercenary", category=a.create_category("Dramatis Personae", "Named")
        )
        prepare_fighter_progression()
        xp = Counter.objects.get(name="XP")
        a.add_built_in(ordinary, xp, amount=7)
        assert attach_fighter_progression(staged_only=False) == 1
        assert attach_fighter_progression(staged_only=False) == 0
        ordinary.refresh_from_db()
        assert ordinary.built_ins.members.get(counter=xp).amount == 7
        for profile in (hired, ally, persona):
            assert not profile.modifiers.exists()
        assert sum(bool(row.excluded) for row in progression_plan()) == 3

    def test_preparing_content_does_not_invalidate_a_pending_review(
        self, client, progression
    ):
        record, url = _start(client, progression, _earned(progression, 13))
        pick = Pickable.objects.get(name="Ganger specialist: Scout")
        response = client.post(url, {"pickable_id": str(pick.pk)})
        page = client.get(response.url)
        token = page.context["form"]["review"].value()
        prepare_fighter_progression()
        response = client.post(response.url, {"review": token})
        assert response.status_code == 302, _errors(response)
        record.refresh_from_db()
        assert record.state == ActionRecord.State.COMPLETED

    def test_the_live_rollout_requires_a_current_signed_preview(
        self, client, progression, make_profile
    ):
        progression.owner.is_staff = True
        progression.owner.save()
        client.force_login(progression.owner)
        live = make_profile("Live recruit")
        address = reverse("authoring-foundations")
        assert client.post(address, {"progression": "live"}).status_code == 302
        assert not live.modifiers.exists()
        page = client.get(address + "?progression=live")
        token = page.context["progression_token"]
        new = make_profile("Imported after review")
        assert (
            client.post(address, {"progression": "live", "plan": token}).status_code
            == 302
        )
        assert not live.modifiers.exists()
        page = client.get(address + "?progression=live")
        assert (
            client.post(
                address,
                {"progression": "live", "plan": page.context["progression_token"]},
            ).status_code
            == 302
        )
        assert live.modifiers.exists()
        assert new.modifiers.exists()

    def test_only_the_elevated_leader_gets_the_outcast_exception(
        self, client, progression, make_profile, make_statline, monkeypatch
    ):
        from n26.core.access import actions_for

        outcast = a.create_gang_type("Outcast")
        profile = make_profile(
            "Hired gun", category=a.create_category("Dramatis Personae", "Named")
        )
        make_statline(profile, strength=3, toughness=3)
        attach_fighter_progression(staged_only=False)
        gang = found_gang("Elevated", outcast, owner=progression.owner, budget=1000)
        leader = hire(gang, profile, "Leader")
        guest = hire(gang, profile, "Guest")
        with operation(gang, actor=progression.owner) as op:
            op.assign(Subtype.objects.get(name="Leader"), miniature=leader)
        assert progression.action.pk in {row.action.pk for row in actions_for(leader)}
        assert not actions_for(guest)
        client.force_login(progression.owner)
        address = reverse("n26-edit-fighter", args=[leader.pk])
        assert "Track XP" in client.get(address).content.decode()
        xp = Counter.objects.get(name="XP")
        assert (
            client.post(
                address, {"act": "track-progression", "counter": str(xp.pk)}
            ).status_code
            == 302
        )
        counter = Assignment.objects.get(miniature_root=leader, counter=xp)
        assert counter.counter_value.value == 0
        assert (
            client.post(
                address, {"act": "track-progression", "counter": str(xp.pk)}
            ).status_code
            == 302
        )
        assert Assignment.objects.filter(miniature_root=leader, counter=xp).count() == 1
        guest_address = reverse("n26-edit-fighter", args=[guest.pk])
        assert "Track XP" not in client.get(guest_address).content.decode()
        client.post(guest_address, {"act": "track-progression", "counter": str(xp.pk)})
        assert not Assignment.objects.filter(miniature_root=guest, counter=xp).exists()
        with operation(gang, actor=progression.owner) as op:
            op.tally(counter, 4)
        test = SimpleNamespace(
            **{**vars(progression), "gang": gang, "fighter": leader, "xp": counter}
        )
        allowance = ActionAllowance.objects.get(fighter=leader, threshold=4)
        record, url = _start(client, test, allowance)
        monkeypatch.setattr(Dice, "roll", classmethod(lambda cls, dice, rng=None: 10))
        page = client.get(url)
        client.post(url, {"request_key": page.context["form"]["request_key"].value()})
        page = client.get(url)
        pick = next(
            row["option"]
            for row in page.context["advancement_options"]
            if not row["option"].needs_skill
        )
        response = client.post(url, {"pickable_id": pick.id})
        page = client.get(response.url)
        response = client.post(
            response.url, {"review": page.context["form"]["review"].value()}
        )
        assert response.status_code == 302, _errors(response)
        record.refresh_from_db()
        assert record.state == ActionRecord.State.COMPLETED

    def test_the_imported_initiate_name_receives_both_exceptions(
        self, progression, make_profile
    ):
        cults = a.create_gang_type("Corpse Grinder Cults")
        initiate = make_profile(
            "Initiate", gang_type=cults, qualifier="Corpse Grinder Cults"
        )
        prepare_fighter_progression()
        promotion = AdvancementPromotion.objects.get(threshold=13)
        assert promotion.optional_profiles.filter(pk=initiate.pk).exists()
        assert promotion.stash_weapons_for.filter(pk=initiate.pk).exists()

    @pytest.mark.parametrize("subtype", ["Champion", "Leader"])
    def test_starting_skills_remain_available_without_a_promotion_pick(
        self, progression, subtype
    ):
        from n26.library.models import Skill

        offer = a.modifier(
            "Offer Primary Skill to Leader/Champion",
            a.targets_model(a.has_subtypes(Subtype.objects.get(name=subtype))),
            a.ef_offers_choice(Skill),
            attach_to=progression.profile,
        )
        prepare_fighter_progression()
        with operation(progression.gang, actor=progression.owner) as op:
            op.assign(Subtype.objects.get(name=subtype), miniature=progression.fighter)
        assert any(
            choice.offer == offer.offers_choice
            for choice in _computed(progression.fighter).choices
        )

    @pytest.mark.parametrize("case", ["archived", "departed", "inactive", "invalid"])
    def test_tracking_refuses_unavailable_counters_without_writes(
        self, progression, counter_tracking, case
    ):
        counter_id = progression.xp.counter_id
        # Retain the caller's cached membership while changing its stored state.
        membership = progression.fighter.membership
        if case == "departed":
            Assignment.objects.filter(pk=membership.pk).update(archived=True)
        elif case == "inactive":
            counter_tracking.activated_at = None
            counter_tracking.activation_run = None
            counter_tracking.save()
        elif case == "archived":
            Assignment.objects.filter(pk=progression.xp.pk).update(archived=True)
        else:
            counter_id = "not-a-counter"
        before = Assignment.objects.count(), LedgerEvent.objects.count()
        with pytest.raises(Refusal):
            with operation(progression.gang, actor=progression.owner) as op:
                op.track_progression_counter(progression.fighter, counter_id)
        assert before == (Assignment.objects.count(), LedgerEvent.objects.count())

    def test_a_broken_shared_binding_is_reported_and_repaired(self, progression):
        modifier = Modifier.objects.get(name="Fighter progression: Advancement")
        modifier.targets_miniature.reach = "every_model"
        modifier.targets_miniature.save()
        assert not next(
            row for row in progression_plan() if row.target == progression.profile
        ).attached
        attach_fighter_progression()
        assert next(
            row for row in progression_plan() if row.target == progression.profile
        ).attached

    def test_profile_count_does_not_grow_foundation_queries(
        self, client, progression, make_profile
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        progression.owner.is_staff = True
        progression.owner.save()
        client.force_login(progression.owner)
        address = reverse("authoring-foundations") + "?progression=live"

        def queries():
            client.get(address)
            with CaptureQueriesContext(connection) as captured:
                assert client.get(address).status_code == 200
            return len(captured)

        small = queries()
        for index in range(12):
            make_profile(f"Extra prospect {index}", staged=True)
        attach_fighter_progression()
        assert queries() <= small


class TestPromotionAuthoring:
    def test_an_author_can_add_and_edit_a_promotion(self, client, progression):
        progression.owner.is_staff = True
        progression.owner.save()
        client.force_login(progression.owner)
        original = AdvancementPromotion.objects.get(threshold=13)
        address = reverse(
            "authoring-detail", args=["resolve-advancement", original.advancement_id]
        )
        page = client.get(address)
        assert page.status_code == 200
        payload = {
            "from_subtype": str(original.from_subtype_id),
            "threshold": "61",
            "slot": str(original.slot_id),
            "replaces_advancement": "on",
            "optional_profiles": [str(progression.profile.pk)],
            "requires_rule": str(original.requires_rule_id),
            "stash_weapons_for": [str(progression.profile.pk)],
            "keep_weapon_trait": str(original.keep_weapon_trait_id),
        }
        added = client.post(address, payload)
        assert added.status_code == 302, added.context["part_sections"][0][
            "form"
        ].errors
        promotion = AdvancementPromotion.objects.get(threshold=61)
        assert list(promotion.optional_profiles.all()) == [progression.profile]
        payload["threshold"] = "85"
        payload["optional_profiles"] = []
        edited = client.post(
            address,
            {
                "act": "edit-part",
                "part": str(promotion.pk),
                **{
                    f"part-{promotion.pk}-{key}": value
                    for key, value in payload.items()
                },
            },
        )
        assert edited.status_code == 302, edited.content.decode()[:800]
        promotion.refresh_from_db()
        assert promotion.threshold == 85
        assert not promotion.optional_profiles.exists()
        assert promotion.stash_weapons_for.filter(pk=progression.profile.pk).exists()

        payload["keep_weapon_trait"] = ""
        refused = client.post(
            address,
            {
                "act": "edit-part",
                "part": str(promotion.pk),
                **{
                    f"part-{promotion.pk}-{key}": value
                    for key, value in payload.items()
                },
            },
        )
        assert refused.status_code == 200
        assert "Choose the trait" in refused.content.decode()
        promotion.refresh_from_db()
        assert promotion.keep_weapon_trait_id == original.keep_weapon_trait_id


class TestPromotions:
    """A promotion is part of its earned advancement, not an additional use."""

    @pytest.mark.parametrize("field", ["staged", "archived"])
    def test_withdrawn_results_preserve_the_earned_use_until_a_result_is_restored(
        self, client, progression, field
    ):
        promotion = AdvancementPromotion.objects.get(threshold=13)
        members = list(promotion.slot.picklist.members.all())
        for member in members:
            a.revise(member, **{field: True})
        record, url = _start(client, progression, _earned(progression, 13))
        for response in (
            client.get(url),
            client.post(url, {"pickable_id": str(members[0].pickable_id)}),
        ):
            assert response.status_code == 200
            assert "must make a result available" in response.content.decode()
            assert response.context["cancel_href"]
        record.refresh_from_db()
        assert record.state == ActionRecord.State.STARTED
        assert not hasattr(record, "advancement_selection")
        assert not LedgerEvent.objects.filter(
            action_record=record, kind=LedgerEvent.Kind.ROLLED
        ).exists()

        a.revise(members[0], **{field: False})
        assert len(client.get(url).context["advancement_options"]) == 1
        response = client.post(url, {"pickable_id": str(members[0].pickable_id)})
        assert response.status_code == 302, _errors(response)
        review = client.get(response.url)
        response = client.post(
            response.url, {"review": review.context["form"]["review"].value()}
        )
        assert response.status_code == 302, _errors(response)
        record.refresh_from_db()
        assert record.state == ActionRecord.State.COMPLETED
        assert ActionAllowance.objects.filter(fighter=progression.fighter).count() == 1

    @pytest.mark.parametrize("field", ["staged", "archived"])
    def test_unavailable_promotions_are_not_discovered(
        self, client, progression, field
    ):
        promotion = AdvancementPromotion.objects.get(threshold=13)
        setattr(promotion, field, True)
        promotion.save()
        record, url = _start(client, progression, _earned(progression, 13))
        assert client.get(url).context["stage"] == "roll"

    @pytest.mark.parametrize("field", ["staged", "archived"])
    def test_recorded_promotions_survive_content_withdrawal(
        self, client, progression, field
    ):
        from n26.core.promotions import promotion_for

        record, url = _start(client, progression, _earned(progression, 13))
        pick = Pickable.objects.get(name="Ganger specialist: Scout")
        assert client.post(url, {"pickable_id": str(pick.pk)}).status_code == 302
        promotion = AdvancementPromotion.objects.get(threshold=13)
        setattr(promotion, field, True)
        promotion.save()
        record.refresh_from_db()
        assert promotion_for(record, progression.outcome.operation) == promotion
        assert client.get(url).context["stage"] == "advancement"

    def test_a_stored_subtype_qualifies_for_promotion(self, client, progression):
        progression.profile.modifiers.remove(
            progression.profile.modifiers.get(name="Prospect rank")
        )
        with operation(progression.gang, actor=progression.owner) as op:
            op.assign(
                Subtype.objects.get(name="Prospect"), miniature=progression.fighter
            )
        record, url = _start(client, progression, _earned(progression, 13))
        assert client.get(url).context["stage"] == "advancement"

    def test_a_gang_only_rule_does_not_satisfy_a_model_gate(self, progression):
        from n26.core.promotions import promotion_for

        gate = AdvancementPromotion.objects.get(threshold=13).requires_rule
        progression.profile.modifiers.remove(
            progression.profile.modifiers.get(name="Fighter progression: Promotion")
        )
        with operation(progression.gang, actor=progression.owner) as op:
            op.assign(gate, gang=progression.gang)
        allowance = _earned(progression, 13)
        with operation(progression.gang, actor=progression.owner) as op:
            record = op.start_action(
                progression.fighter, progression.action, uuid4(), allowance=allowance
            )
        assert promotion_for(record, progression.outcome.operation) is None
        a.modifier(
            "Grant model promotion gate",
            a.targets_every_model(),
            a.ef_adds(gate),
            attach_to=gate,
        )
        assert promotion_for(record, progression.outcome.operation) is not None

    @pytest.mark.parametrize("decline", [False, True])
    def test_leaving_a_prepared_promotion_removes_its_unpicked_slot(
        self, client, progression, decline
    ):
        promotion = AdvancementPromotion.objects.get(threshold=13)
        promotion.optional_profiles.add(progression.profile)
        allowance = _earned(progression, 13)
        record, url = _start(client, progression, allowance)
        pick = Pickable.objects.get(name="Ganger specialist: Scout")
        assert client.post(url, {"pickable_id": str(pick.pk)}).status_code == 302
        record.refresh_from_db()
        anchor = record.advancement_selection.slot_assignment
        with operation(progression.gang, actor=progression.owner) as op:
            if decline:
                op.record_action_roll(
                    record,
                    progression.outcome.operation,
                    uuid4(),
                    decline_promotion=True,
                    rolled=12,
                )
            else:
                op.cancel_action(record)
        anchor.refresh_from_db()
        assert anchor.archived
        assert not Assignment.objects.filter(
            miniature_root=progression.fighter, slot=promotion.slot, archived=False
        ).exists()

    def test_a_prospect_chooses_a_specialisation_instead_of_rolling(
        self, client, progression
    ):
        allowance = _earned(progression, 13)
        record, choose_url = _start(client, progression, allowance)
        page = client.get(choose_url)
        assert page.context["stage"] == "advancement"
        assert "Choose a promotion" in page.content.decode()
        assert len(page.context["advancement_options"]) == 8
        pick = Pickable.objects.get(name="Ganger specialist: Scout")
        response = client.post(choose_url, {"pickable_id": str(pick.pk)})
        assert response.status_code == 302, _errors(response)
        review = client.get(response.url)
        assert review.status_code == 200
        record.refresh_from_db()
        response = client.post(
            response.url, {"review": review.context["form"]["review"].value()}
        )
        assert response.status_code == 302, _errors(response)
        record.refresh_from_db()
        assert record.state == ActionRecord.State.COMPLETED
        computed = _computed(progression.fighter)
        assert {str(row.thing) for row in computed.subtypes} >= {"Ganger", "Specialist"}
        assert "Prospect" not in {str(row.thing) for row in computed.subtypes}
        assert "Clamber" in {str(row.thing) for row in computed.skills}
        assert not LedgerEvent.objects.filter(
            action_record=record, kind=LedgerEvent.Kind.ROLLED
        ).exists()
        assert record.advancement_selection.pick_assignment.rating == 15
        assert ActionAllowance.objects.filter(fighter=progression.fighter).count() == 1

        correction_url = reverse(
            "n26-action-flow", args=[progression.fighter.pk, record.pk, "correct"]
        )
        replacement = Pickable.objects.get(name="Ganger specialist: Medic")
        changed = client.post(correction_url, {"pickable_id": str(replacement.pk)})
        assert changed.status_code == 302, _errors(changed)
        review = client.get(changed.url)
        changed = client.post(
            changed.url, {"review": review.context["form"]["review"].value()}
        )
        assert changed.status_code == 302, _errors(changed)
        skills = {str(row.thing) for row in _computed(progression.fighter).skills}
        assert "Medicate" in skills
        assert "Clamber" not in skills

    def test_promotion_resolves_the_imported_specialist_choice_once(
        self, client, progression
    ):
        from n26.library.models import SlotType

        kind = SlotType.objects.get(name="Specialisation")
        table = a.create_picklist("Specialisations", kind)
        slot = a.create_slot("Specialisation", kind, table)
        specialist = Subtype.objects.get(name="Specialist")
        a.modifier(
            "Specialist asks its specialisation",
            a.targets_model(),
            a.ef_adds(slot),
            attach_to=specialist,
        )
        independent = a.create_slot("Independent specialisation", kind, table)
        a.modifier(
            "Another choice",
            a.targets_model(),
            a.ef_adds(independent),
            attach_to=specialist,
        )
        canonical = Pickable.objects.get(name="Scout", slot_type=kind)
        marker = a.create_rule("Scout promotion marker")
        a.modifier(
            "Scout identity",
            a.targets_model(a.has_pickable(canonical)),
            a.ef_adds(marker),
            attach_to=progression.profile,
        )
        prepare_fighter_progression()
        record, url = _start(client, progression, _earned(progression, 13))
        pick = Pickable.objects.get(name="Ganger specialist: Scout")
        response = client.post(url, {"pickable_id": str(pick.pk)})
        page = client.get(response.url)
        response = client.post(
            response.url, {"review": page.context["form"]["review"].value()}
        )
        assert response.status_code == 302, _errors(response)
        computed = _computed(progression.fighter)
        assert "Clamber" in {str(row.thing) for row in computed.skills}
        assert not any(choice.slot == slot for choice in computed.choices)
        assert any(choice.slot == independent for choice in computed.choices)
        assert marker in {row.thing for row in computed.rules}

    @pytest.mark.parametrize("withdrawn_field", [None, "staged", "archived"])
    def test_an_initiate_can_keep_its_subtype_and_roll(
        self, client, monkeypatch, progression, withdrawn_field
    ):
        promotion = AdvancementPromotion.objects.get(threshold=13)
        promotion.optional_profiles.add(progression.profile)
        if withdrawn_field:
            for member in promotion.slot.picklist.members.all():
                a.revise(member, **{withdrawn_field: True})
        record, url = _start(client, progression, _earned(progression, 13))
        monkeypatch.setattr(Dice, "roll", classmethod(lambda cls, dice, rng=None: 12))
        page = client.get(url)
        assert page.context["decline_promotion"]
        response = client.post(
            url,
            {
                "decline_promotion": "1",
                "request_key": page.context["promotion_request_key"],
            },
        )
        assert response.status_code == 302
        page = client.get(url)
        assert page.context["roll_value"] == 12
        pick = next(
            item["option"]
            for item in page.context["advancement_options"]
            if not item["option"].needs_skill
        )
        response = client.post(url, {"pickable_id": pick.id})
        review = client.get(response.url)
        response = client.post(
            response.url, {"review": review.context["form"]["review"].value()}
        )
        assert response.status_code == 302, _errors(response)
        assert {str(row.thing) for row in _computed(progression.fighter).subtypes} == {
            "Prospect"
        }

    @pytest.mark.parametrize("progression", [36], indirect=True)
    @pytest.mark.parametrize(
        "retired_result",
        [
            None,
            "member_archived",
            "member_staged",
            "pickable_archived",
            "pickable_staged",
        ],
    )
    def test_a_ganger_gets_the_advancement_and_champion_promotion(
        self, client, monkeypatch, progression, retired_result
    ):
        from n26.library.models import Skill

        offer = a.modifier(
            "Offer Primary Skill to Leader/Champion",
            a.targets_model(a.has_subtypes(Subtype.objects.get(name="Champion"))),
            a.ef_offers_choice(Skill),
            attach_to=progression.profile,
        )
        prepare_fighter_progression()
        promotion = AdvancementPromotion.objects.get(threshold=37)
        if retired_result:
            extra = a.create_pickable(
                "Other promotion result", promotion.slot.slot_type
            )
            member = a.add_picklist_member(promotion.slot.picklist, extra)
            target, field = retired_result.split("_")
            row = member if target == "member" else extra
            setattr(row, field, True)
            row.save()
        promotion.full_clean()
        existing_skill = Skill.objects.get(name="Clamber")
        with operation(progression.gang, actor=progression.owner) as op:
            held_skill = op.assign(existing_skill, miniature=progression.fighter)
        effect = progression.profile.modifiers.get(name="Prospect rank").adds_assignable
        effect.subtype = Subtype.objects.get(name="Ganger")
        effect.save()
        record, url = _start(client, progression, _earned(progression, 37))
        monkeypatch.setattr(Dice, "roll", classmethod(lambda cls, dice, rng=None: 12))
        page = client.get(url)
        assert page.context["stage"] == "roll"
        response = client.post(
            url, {"request_key": page.context["form"]["request_key"].value()}
        )
        page = client.get(response.url)
        pick = next(
            item["option"]
            for item in page.context["advancement_options"]
            if not item["option"].needs_skill
        )
        response = client.post(url, {"pickable_id": pick.id})
        review = client.get(response.url)
        response = client.post(
            response.url, {"review": review.context["form"]["review"].value()}
        )
        assert response.status_code == 302, _errors(response)
        assert {str(row.thing) for row in _computed(progression.fighter).subtypes} == {
            "Champion"
        }
        record.refresh_from_db()
        assert record.advancement_selection.promotion_assignment_id
        assert "Inspiring" in {
            str(row.thing) for row in _computed(progression.fighter).skills
        }
        assert not any(
            choice.offer == offer.offers_choice
            for choice in _computed(progression.fighter).choices
        )
        held_skill.refresh_from_db()
        assert not held_skill.archived
        assert any(
            node.assignable == existing_skill and not node.suppressed
            for node in build_card(progression.fighter).all_nodes()
        )

        url = reverse(
            "n26-action-flow", args=[progression.fighter.pk, record.pk, "correct"]
        )
        response = client.post(url, {"pickable_id": pick.id})
        assert response.status_code == 302, _errors(response)
        page = client.get(response.url)
        response = client.post(
            response.url, {"review": page.context["form"]["review"].value()}
        )
        assert response.status_code == 302, _errors(response)
        assert {str(row.thing) for row in _computed(progression.fighter).subtypes} == {
            "Champion"
        }

    def test_promoting_an_initiate_stashes_the_gun_but_keeps_the_melee_weapon(
        self, client, progression
    ):
        promotion = AdvancementPromotion.objects.get(threshold=13)
        promotion.stash_weapons_for.add(progression.profile)
        melee = Trait.objects.get(name="Melee")
        gun = give_weapon(
            progression.fighter, a.create_weapon("Autopistol", profiles=[("", 0)])
        )
        blade = give_weapon(
            progression.fighter, a.create_weapon("Cleaver", profiles=[("", 0, [melee])])
        )
        record, url = _start(client, progression, _earned(progression, 13))
        pick = Pickable.objects.get(name="Ganger specialist: Scout")
        response = client.post(url, {"pickable_id": str(pick.pk)})
        page = client.get(response.url)
        assert "Move to stash: Autopistol" in page.content.decode()
        response = client.post(
            response.url, {"review": page.context["form"]["review"].value()}
        )
        assert response.status_code == 302, _errors(response)
        gun.refresh_from_db()
        blade.refresh_from_db()
        assert gun.stash_root == progression.gang.stash
        assert blade.miniature_root == progression.fighter
        assert (
            LedgerEvent.objects.filter(
                assignment=gun, action_record=record, kind=LedgerEvent.Kind.MOVED
            ).count()
            == 1
        )

    @pytest.mark.parametrize("promotion_enabled", [True, False])
    def test_rank_order_is_required_only_for_a_promotion(
        self, progression, promotion_enabled
    ):
        if not promotion_enabled:
            progression.profile.modifiers.remove(
                progression.profile.modifiers.get(name="Fighter progression: Promotion")
            )
        with operation(progression.gang, actor=progression.owner) as op:
            op.tally(progression.xp, 7)
        later = ActionAllowance.objects.get(fighter=progression.fighter, threshold=19)
        if not promotion_enabled:
            with operation(progression.gang, actor=progression.owner) as op:
                record = op.start_action(
                    progression.fighter, progression.action, uuid4(), allowance=later
                )
            assert record.state == ActionRecord.State.STARTED
            return
        with pytest.raises(Refusal, match="earlier"):
            with operation(progression.gang, actor=progression.owner) as op:
                op.start_action(
                    progression.fighter, progression.action, uuid4(), allowance=later
                )

    def test_prepared_promotions_do_not_change_an_existing_manual_binding(
        self, progression
    ):
        from n26.core.promotions import promotion_for

        progression.profile.modifiers.filter(
            name="Fighter progression: Promotion"
        ).delete()
        allowance = _earned(progression, 13)
        with operation(progression.gang, actor=progression.owner) as op:
            record = op.start_action(
                progression.fighter, progression.action, uuid4(), allowance=allowance
            )
        assert promotion_for(record, progression.outcome.operation) is None

    def test_a_mandatory_promotion_cannot_be_declined_by_posting_a_hidden_field(
        self, client, progression
    ):
        record, url = _start(client, progression, _earned(progression, 13))
        response = client.post(
            url, {"decline_promotion": "1", "request_key": str(uuid4())}
        )
        assert response.status_code == 200
        assert "Choose a promotion instead" in response.content.decode()
        assert not LedgerEvent.objects.filter(
            action_record=record, kind=LedgerEvent.Kind.ROLLED
        ).exists()

    def test_a_prepared_promotion_cannot_be_moved_to_another_outcome(
        self, client, progression
    ):
        record, url = _start(client, progression, _earned(progression, 13))
        pick = Pickable.objects.get(name="Ganger specialist: Scout")
        assert client.post(url, {"pickable_id": str(pick.pk)}).status_code == 302
        other = a.create_outcome(
            "Another advancement",
            a.resolve_advancement(progression.outcome.operation.slot),
        )
        a.add_action_outcome(progression.action, other)
        with pytest.raises(Refusal, match="cannot change the outcome"):
            with operation(progression.gang, actor=progression.owner) as op:
                op.save_action_choices(record, outcome=other, terms={})

    def test_changed_promotion_content_requires_a_new_review(self, client, progression):
        record, url = _start(client, progression, _earned(progression, 13))
        pick = Pickable.objects.get(name="Ganger specialist: Scout")
        selected = client.post(url, {"pickable_id": str(pick.pk)})
        page = client.get(selected.url)
        token = page.context["form"]["review"].value()
        pick.rating_contribution = 20
        pick.save()
        response = client.post(selected.url, {"review": token})
        assert response.status_code == 200
        record.refresh_from_db()
        assert record.state == ActionRecord.State.STARTED
        assert record.advancement_selection.pick_assignment_id is None

    @pytest.mark.parametrize("mode", ["select", "random"])
    def test_an_authored_promotion_can_offer_a_skill(
        self, client, monkeypatch, progression, mode
    ):
        from n26.library.models import Skill

        promotion = AdvancementPromotion.objects.get(threshold=13)
        category = a.create_category("Test skills", "Promotion skills")
        skill = a.create_skill("Test skill", category=category, position=1)
        pick = a.create_pickable(
            "Custom promotion",
            promotion.slot.slot_type,
            effects=[
                (a.targets_model(), a.ef_offers_choice(Skill, mode=mode)),
            ],
        )
        a.add_picklist_member(promotion.slot.picklist, pick)
        record, url = _start(client, progression, _earned(progression, 13))
        response = client.post(url, {"pickable_id": str(pick.pk)})
        assert response.status_code == 302, _errors(response)
        assert response.url.endswith("/skill/")
        page = client.get(response.url)
        if mode == "random":
            monkeypatch.setattr(
                Dice, "roll", classmethod(lambda cls, dice, rng=None: 1)
            )
            rolled = client.post(
                response.url,
                {
                    "request_key": page.context["form"]["request_key"].value(),
                    "skill_set_id": str(category.pk),
                },
            )
            assert rolled.status_code == 302, _errors(rolled)
            with pytest.raises(Refusal, match="must be resumed"):
                with operation(progression.gang, actor=progression.owner) as op:
                    op.cancel_action(record)
            response = client.post(response.url, {"review_skill": "1"})
        else:
            response = client.post(response.url, {"skill_id": str(skill.pk)})
        assert response.status_code == 302, _errors(response)
        page = client.get(response.url)
        completed = client.post(
            response.url, {"review": page.context["form"]["review"].value()}
        )
        assert completed.status_code == 302, _errors(completed)
        assert Assignment.objects.filter(
            miniature_root=progression.fighter, skill=skill, archived=False
        ).exists()
