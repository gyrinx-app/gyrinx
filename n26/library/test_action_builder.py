"""The guided action form compiles into the same authored content as the verbs."""

import json

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse

from n26.library.action_builder import (
    create_from_draft,
    grant_to_profiles,
    set_use_limit,
)
from n26.library.models import (
    Action,
    Counter,
    DefaultAssignmentSet,
    Outcome,
    Picklist,
    Slot,
    SlotType,
    Subtype,
)

pytestmark = pytest.mark.django_db


def draft(**changes):
    value = {
        "name": "Suit Evolution",
        "timing": "post_cycle",
        "acquisitionPrice": "0",
        "useMode": "paid",
        "prices": [{"resource": "credits", "payer": "gang", "amount": "100"}],
        "outcomes": [],
    }
    value.update(changes)
    return json.dumps(value)


class TestCreatingAnAction:
    """The form's combined fields make one atomic authored action."""

    def test_a_paid_action_creates_its_outcome_without_granting_it(self, default_pack):
        tier = SlotType.objects.create(name="Augmentation")
        action = create_from_draft(
            draft(
                outcomes=[
                    {
                        "name": "Upgrade rig",
                        "operation": "augment",
                        "slotType": str(tier.pk),
                    }
                ]
            )
        )

        assert not action.staged
        assert action.use_price.get().amount == 100
        assert action.outcomes.get().outcome.name == "Upgrade rig"
        assert not action.outcomes.get().outcome.staged

    def test_an_existing_outcome_can_be_reused_without_copying_it(self, default_pack):
        tier = SlotType.objects.create(name="Augmentation")
        from n26.library import authoring

        existing = authoring.create_outcome(
            "Upgrade rig", authoring.augment_carried_item(tier)
        )
        action = create_from_draft(
            draft(
                outcomes=[{"existing": str(existing.pk)}],
                useMode="free",
                prices=[],
            )
        )
        assert action.outcomes.get().outcome == existing
        assert Outcome.objects.count() == 1

    def test_an_invalid_price_rolls_back_all_new_content(self, default_pack):
        tier = SlotType.objects.create(name="Augmentation")
        with pytest.raises(ValidationError, match="Price must be at least 1"):
            create_from_draft(
                draft(
                    prices=[{"resource": "credits", "amount": "0"}],
                    outcomes=[
                        {
                            "name": "Upgrade rig",
                            "operation": "augment",
                            "slotType": str(tier.pk),
                        }
                    ],
                )
            )
        assert not Action.objects.exists()
        assert not Outcome.objects.exists()

    def test_a_rank_allowance_uses_a_table_with_the_same_counter(self, default_pack):
        from n26.library import authoring

        xp = Counter.objects.create(name="XP")
        kill = Counter.objects.create(name="Kill Count")
        table = authoring.create_rank_table("XP ranks", xp)
        tier = SlotType.objects.create(name="Augmentation")
        with pytest.raises(ValidationError, match="must use the selected counter"):
            create_from_draft(
                draft(
                    useMode="rank",
                    prices=[],
                    rankCounter=str(kill.pk),
                    rankTable=str(table.pk),
                    outcomes=[
                        {
                            "name": "Upgrade rig",
                            "operation": "augment",
                            "slotType": str(tier.pk),
                        }
                    ],
                )
            )
        assert not Action.objects.exists()

    def test_an_advancement_action_uses_xp_ranks_and_resolves_a_slot(
        self, default_pack
    ):
        from n26.library import authoring

        xp = Counter.objects.create(name="XP")
        ranks = authoring.create_rank_table("Standard fighter ranks", xp)
        slot_type = SlotType.objects.create(name="Advancement")
        picklist = Picklist.objects.create(
            name="Fighter advancement table", slot_type=slot_type
        )
        slot = Slot.objects.create(
            name="Advancement", slot_type=slot_type, picklist=picklist
        )

        action = create_from_draft(
            draft(
                name="Local advancement",
                useMode="rank",
                prices=[],
                rankCounter=str(xp.pk),
                rankTable=str(ranks.pk),
                outcomes=[
                    {
                        "name": "Local advancement result",
                        "operation": "advancement",
                        "slot": str(slot.pk),
                    }
                ],
            )
        )

        assert action.rank_allowance_rule.counter == xp
        assert action.outcomes.get().outcome.resolve_advancement.slot == slot

    def test_an_owned_pack_outcome_cannot_enter_a_system_action(self, default_pack):
        from n26.library import authoring

        owner = User.objects.create_user("pack-author")
        owned_pack = authoring.create_pack("Private test rules", owner=owner)
        tier = SlotType.objects.create(name="Private tier", pack=owned_pack)
        with pytest.raises(ValidationError, match="valid tier slot type"):
            create_from_draft(
                draft(
                    outcomes=[
                        {
                            "name": "Private upgrade",
                            "operation": "augment",
                            "slotType": str(tier.pk),
                        }
                    ]
                )
            )
        assert not Action.objects.exists()

    def test_malformed_nested_drafts_are_refused_in_words(self, default_pack):
        with pytest.raises(ValidationError, match="valid price part"):
            create_from_draft(
                draft(prices=["not a price"], outcomes=[{"existing": "x"}])
            )
        with pytest.raises(ValidationError, match="valid outcome"):
            create_from_draft(draft(useMode="free", outcomes=["not an outcome"]))


class TestGrantingAnAction:
    """A grant is deliberate and cannot leak staged content through hiring."""

    def test_staged_actions_cannot_be_granted(self, default_pack, make_profile):
        action = Action.objects.create(name="Trial", timing="post_cycle", staged=True)
        profile = make_profile("Hunter")
        with pytest.raises(ValidationError, match="Put the action live"):
            grant_to_profiles(action, [str(profile.pk)])
        assert profile.built_ins_id is None

    def test_granting_twice_does_not_duplicate_a_built_in(
        self, default_pack, make_profile
    ):
        action = Action.objects.create(name="Trial", timing="post_cycle")
        profile = make_profile("Hunter")
        assert grant_to_profiles(action, [str(profile.pk)]) == 1
        assert grant_to_profiles(action, [str(profile.pk)]) == 0
        profile.refresh_from_db()
        assert profile.built_ins.members.filter(action=action).count() == 1
        assert profile.built_ins.pack_id == profile.pack_id

    def test_bulk_grant_creates_a_set_for_each_entry_without_built_ins(
        self, default_pack, make_profile
    ):
        action = Action.objects.create(name="Trial", timing="post_cycle")
        first = make_profile("Hunter one")
        second = make_profile("Hunter two")

        assert grant_to_profiles(action, [str(first.pk), str(second.pk)]) == 2

        first.refresh_from_db()
        second.refresh_from_db()
        assert first.built_ins_id != second.built_ins_id
        assert first.built_ins.members.filter(action=action).count() == 1
        assert second.built_ins.members.filter(action=action).count() == 1

    def test_shared_built_ins_cannot_grant_an_unselected_entry(
        self, default_pack, make_profile
    ):
        action = Action.objects.create(name="Trial", timing="post_cycle")
        shared = DefaultAssignmentSet.objects.create(name="Shared starter set")
        first = make_profile("Hunter one", built_ins=shared)
        second = make_profile("Hunter two", built_ins=shared)

        with pytest.raises(ValidationError, match="shares its built-ins"):
            grant_to_profiles(action, [str(first.pk)])
        assert not shared.members.filter(action=action).exists()

        assert grant_to_profiles(action, [str(first.pk), str(second.pk)]) == 2
        assert shared.members.filter(action=action).count() == 1

    def test_an_owned_action_cannot_be_granted_to_a_system_fighter_entry(
        self, default_pack, make_profile
    ):
        from n26.library import authoring

        owner = User.objects.create_user("pack-author")
        owned_pack = authoring.create_pack("Private test rules", owner=owner)
        action = Action.objects.create(
            name="Private action", timing="post_cycle", pack=owned_pack
        )
        profile = make_profile("Hunter")

        with pytest.raises(ValidationError, match="can only reference content"):
            grant_to_profiles(action, [str(profile.pk)])
        profile.refresh_from_db()
        assert profile.built_ins_id is None


class TestUseLimits:
    """An archived action cannot receive a new use limit."""

    def test_an_archived_action_keeps_its_existing_limit(self, default_pack):
        subtype = Subtype.objects.create(name="Spyrer")
        action = Action.objects.create(name="Trial", timing="post_cycle", archived=True)
        action.usable_by_subtypes.add(subtype)

        with pytest.raises(
            ValidationError, match="cannot change this action's use limit"
        ):
            set_use_limit(action, "any")
        assert list(action.usable_by_subtypes.all()) == [subtype]

    def test_an_action_in_an_archived_pack_keeps_its_limit(self, default_pack):
        action = Action.objects.create(name="Trial", timing="post_cycle")
        default_pack.archived = True
        default_pack.save(update_fields=["archived"])

        with pytest.raises(
            ValidationError, match="cannot change this action's use limit"
        ):
            set_use_limit(action, "any")


class TestAuthoringPages:
    """Staff can reach the builder and the next grant step."""

    def test_the_action_create_page_contains_the_builder(
        self, admin_client, default_pack
    ):
        page = admin_client.get(reverse("authoring-create", args=["action"]))
        assert page.status_code == 200
        assert b"An action takes a fighter through a sequence of steps" in page.content
        assert b"action-builder" in page.content

    def test_reusable_outcome_shows_its_configured_result(
        self, admin_client, default_pack
    ):
        from n26.library import authoring

        tier = SlotType.objects.create(name="Rig augmentation")
        authoring.create_outcome("Upgrade rig", authoring.augment_carried_item(tier))
        page = admin_client.get(reverse("authoring-create", args=["action"]))
        assert b"Upgrade rig" in page.content
        assert b"Advance a carried item in Rig augmentation" in page.content

    def test_creating_redirects_to_grant(self, admin_client, default_pack):
        tier = SlotType.objects.create(name="Augmentation")
        response = admin_client.post(
            reverse("authoring-create", args=["action"]),
            {
                "draft": draft(
                    outcomes=[
                        {
                            "name": "Upgrade rig",
                            "operation": "augment",
                            "slotType": str(tier.pk),
                        }
                    ]
                )
            },
        )
        action = Action.objects.get(name="Suit Evolution")
        assert response.status_code == 302
        assert response.url == reverse("authoring-action-grant", args=[action.pk])
        assert not action.staged

    def test_grant_page_selects_multiple_fighter_entries(
        self, admin_client, default_pack, make_profile
    ):
        action = Action.objects.create(name="Trial", timing="post_cycle")
        first = make_profile("Hunter one")
        second = make_profile("Hunter two")
        url = reverse("authoring-action-grant", args=[action.pk])
        page = admin_client.get(url)
        assert page.status_code == 200
        assert b"Hunter one" in page.content
        response = admin_client.post(url, {"profiles": [str(first.pk), str(second.pk)]})
        assert response.status_code == 302
        first.refresh_from_db()
        second.refresh_from_db()
        assert first.built_ins.members.filter(action=action).exists()
        assert second.built_ins.members.filter(action=action).exists()

    def test_owned_actions_do_not_offer_system_fighter_entries(
        self, admin_client, default_pack, make_profile
    ):
        from n26.library import authoring

        owner = User.objects.create_user("pack-author")
        owned_pack = authoring.create_pack("Private test rules", owner=owner)
        action = Action.objects.create(
            name="Private action", timing="post_cycle", pack=owned_pack
        )
        make_profile("System hunter")

        page = admin_client.get(reverse("authoring-action-grant", args=[action.pk]))

        assert page.status_code == 200
        assert page.context["rows"] == []
        assert b"No fighter entries yet" in page.content

    def test_optional_use_limit_does_not_grant_the_action(
        self, admin_client, default_pack, make_profile
    ):
        action = Action.objects.create(name="Trial", timing="post_cycle")
        spyrer = Subtype.objects.create(name="Spyrer")
        profile = make_profile("Hunter")
        url = reverse("authoring-action-grant", args=[action.pk])

        response = admin_client.post(
            url, {"act": "use_limit", "use_limit": f"subtype:{spyrer.pk}"}
        )
        assert response.status_code == 302
        assert list(action.usable_by_subtypes.all()) == [spyrer]
        assert profile.built_ins_id is None

        response = admin_client.post(url, {"act": "use_limit", "use_limit": "any"})
        assert response.status_code == 302
        assert not action.usable_by_subtypes.exists()

    def test_archived_actions_show_no_grant_or_use_limit_controls(
        self, admin_client, default_pack
    ):
        action = Action.objects.create(
            name="Retired trial", timing="post_cycle", archived=True
        )
        url = reverse("authoring-action-grant", args=[action.pk])

        page = admin_client.get(url)

        assert page.status_code == 200
        assert b"You cannot grant or change this action" in page.content
        assert b"Grant selected entries" not in page.content
        assert b"Save use limit" not in page.content

        response = admin_client.post(url, {"act": "use_limit", "use_limit": "any"})
        assert response.status_code == 200
        assert b"You cannot change this action&#x27;s use limit" in response.content
