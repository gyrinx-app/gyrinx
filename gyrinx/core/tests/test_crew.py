"""Tests for battle crews (#1346).

Covers the selection-spec parser, the Crew/CrewMember/CrewLineItem models
(method label, live rating for draft vs locked, extras, deltas, permissions),
the set-scoped fighter cost that feeds crew rating, the lock/draw handler, and
the crew lifecycle views.
"""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from random import Random

from gyrinx.core.handlers.crew import eligible_crew_fighters, handle_crew_lock
from gyrinx.core.models import Battle
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.crew import (
    Crew,
    CrewLineItem,
    CrewMember,
    build_selection_spec,
    roll_selection_spec,
    split_selection_spec,
    validate_selection_spec,
)
from gyrinx.core.models.list import List, ListFighter, ListFighterEquipmentSet


# --- Selection-spec parser --------------------------------------------------


@pytest.mark.parametrize("spec", ["", "6", "D3", "d3", "D6+2", "D66"])
def test_validate_selection_spec_accepts_valid(spec):
    validate_selection_spec(spec)  # must not raise


@pytest.mark.parametrize("spec", ["x", "D", "3+D3", "-1", "D0", "D3+", "+2", "D-1"])
def test_validate_selection_spec_rejects_invalid(spec):
    with pytest.raises(ValidationError):
        validate_selection_spec(spec)


def test_roll_selection_spec_empty_and_flat():
    assert roll_selection_spec("") == (0, "")
    assert roll_selection_spec("6") == (6, "")


def test_roll_selection_spec_die_is_bounded_and_described():
    count, detail = roll_selection_spec("D3", rng=Random(0))
    assert 1 <= count <= 3
    assert detail.startswith("D3: rolled ")


def test_roll_selection_spec_die_plus_constant():
    count, detail = roll_selection_spec("D3+4", rng=Random(0))
    assert 5 <= count <= 7  # (1..3) + 4
    assert "→" in detail and detail.startswith("D3+4:")


def test_roll_selection_spec_invalid_raises():
    with pytest.raises(ValidationError):
        roll_selection_spec("nope")


@pytest.mark.parametrize(
    "spec,dice,number",
    [
        ("", "", None),
        ("6", "", 6),
        ("D3", "D3", None),
        ("D6+2", "D6", 2),
        ("nonsense", "", None),
    ],
)
def test_split_selection_spec(spec, dice, number):
    assert split_selection_spec(spec) == (dice, number)


@pytest.mark.parametrize(
    "dice,number,spec",
    [
        ("", None, ""),
        ("", 0, ""),
        ("", 6, "6"),
        ("D3", None, "D3"),
        ("D3", 0, "D3"),
        ("D6", 2, "D6+2"),
    ],
)
def test_build_selection_spec(dice, number, spec):
    assert build_selection_spec(dice, number) == spec


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture
def crew_setup(user, campaign, make_list, make_list_fighter):
    """A campaign battle with one participating gang of five active fighters."""
    gang = make_list("Riot Gang", status=List.CAMPAIGN_MODE, campaign=campaign)
    campaign.lists.add(gang)
    fighters = [make_list_fighter(gang, f"Ganger {i}") for i in range(5)]
    battle = Battle.objects.create(campaign=campaign, mission="Ambush", owner=user)
    battle.set_participants([gang])
    return {
        "user": user,
        "campaign": campaign,
        "gang": gang,
        "fighters": fighters,
        "battle": battle,
    }


@pytest.fixture
def equipped_fighter(make_list_fighter, make_equipment, make_weapon_profile):
    """Build a fighter (in a given gang) with two weapons + gear and a set."""

    def build(gang):
        fighter = make_list_fighter(gang, "Specialist")
        lasgun = make_equipment(name="Lasgun", cost=30, category="Basic Weapons")
        make_weapon_profile(lasgun)
        plasma = make_equipment(name="Plasma Gun", cost=50, category="Special Weapons")
        make_weapon_profile(plasma)
        armour = make_equipment(name="Flak Armour", cost=15, category="Armour")
        a_lasgun = fighter.assign(lasgun)
        fighter.assign(plasma)
        a_armour = fighter.assign(armour)
        card = ListFighterEquipmentSet.objects.create(
            list_fighter=fighter, name="Light kit", owner=fighter.owner
        )
        card.assignments.set([a_lasgun, a_armour])
        return fighter, card

    return build


# --- Set-scoped fighter cost (crew rating input) ----------------------------


@pytest.mark.django_db
def test_cost_int_for_equipment_set(crew_setup, equipped_fighter):
    fighter, card = equipped_fighter(crew_setup["gang"])
    fighter = ListFighter.objects.with_related_data().get(id=fighter.id)

    # Full kit: base 100 + 30 + 50 + 15 = 195.
    assert fighter.cost_int_for_equipment_set(None) == 195
    assert fighter.cost_int_for_equipment_set(None) == fighter.cost_int_cached
    # Set scopes out the plasma gun (50): base 100 + 30 + 15 = 145.
    assert fighter.cost_int_for_equipment_set(card) == 145


@pytest.mark.django_db
def test_cost_int_for_full_coverage_set_equals_full_kit(
    crew_setup, make_list_fighter, make_equipment, make_weapon_profile
):
    """A set that includes every assignment costs the same as the full kit."""
    fighter = make_list_fighter(crew_setup["gang"], "Trooper")
    lasgun = make_equipment(name="Lasgun 2", cost=30, category="Basic Weapons")
    make_weapon_profile(lasgun)
    armour = make_equipment(name="Flak 2", cost=15, category="Armour")
    a1 = fighter.assign(lasgun)
    a2 = fighter.assign(armour)
    full_card = ListFighterEquipmentSet.objects.create(
        list_fighter=fighter, name="Everything", owner=fighter.owner
    )
    full_card.assignments.set([a1, a2])

    fighter = ListFighter.objects.with_related_data().get(id=fighter.id)
    assert fighter.cost_int_for_equipment_set(full_card) == fighter.cost_int_cached


# --- Crew model -------------------------------------------------------------


@pytest.mark.django_db
def test_method_label(crew_setup):
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(battle=battle, list=gang, owner=crew_setup["user"])

    assert crew.method_label() == "Whole gang"

    crew.random_spec = "D3"
    crew.save()
    assert crew.method_label() == "D3 random"

    crew.chosen_fighters.set(crew_setup["fighters"][:2])
    assert crew.method_label() == "2 chosen + D3 random"

    crew.random_spec = ""
    crew.save()
    assert crew.method_label() == "2 chosen"


@pytest.mark.django_db
def test_draft_rating_sums_chosen_full_cost(crew_setup):
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(battle=battle, list=gang, owner=crew_setup["user"])
    crew.chosen_fighters.set(crew_setup["fighters"][:3])

    # Three fighters at base 100 each.
    assert crew.rating() == 300
    assert crew.credits_value() == 300


@pytest.mark.django_db
def test_locked_rating_uses_member_loadout(crew_setup, equipped_fighter):
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    fighter, card = equipped_fighter(gang)
    crew = Crew.objects.create(
        battle=battle, list=gang, owner=crew_setup["user"], status=Crew.LOCKED
    )
    member = CrewMember.objects.create(
        crew=crew, list_fighter=fighter, equipment_set=card, owner=crew_setup["user"]
    )

    # Member scoped to the light kit: 145 (see set-scoped cost test).
    assert member.rating() == 145
    assert crew.rating() == 145


@pytest.mark.django_db
def test_extras_and_credits_value(crew_setup):
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(
        battle=battle, list=gang, owner=crew_setup["user"], status=Crew.LOCKED
    )
    CrewMember.objects.create(
        crew=crew, list_fighter=crew_setup["fighters"][0], owner=crew_setup["user"]
    )
    CrewLineItem.objects.create(
        crew=crew, label="Tactics card", cost=20, owner=crew_setup["user"]
    )
    CrewLineItem.objects.create(
        crew=crew,
        label="Hired gun",
        cost=55,
        payment=Crew.PAY_FREE,
        owner=crew_setup["user"],
    )

    assert crew.rating() == 100
    assert crew.extras_total() == 75
    assert crew.credits_value() == 175


@pytest.mark.django_db
def test_receipt_totals(crew_setup):
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(
        battle=battle, list=gang, owner=crew_setup["user"], status=Crew.LOCKED
    )
    CrewMember.objects.create(
        crew=crew, list_fighter=crew_setup["fighters"][0], owner=crew_setup["user"]
    )
    CrewLineItem.objects.create(
        crew=crew, label="Tactics card", cost=20, owner=crew_setup["user"]
    )
    CrewLineItem.objects.create(
        crew=crew,
        label="Free favour",
        cost=30,
        payment=Crew.PAY_FREE,
        owner=crew_setup["user"],
    )

    receipt = crew.receipt()
    assert receipt["fighters_total"] == 100
    assert [a["name"] for a in receipt["attendees"]] == ["Ganger 0"]
    # Each attendee carries its fighter category for the bold "name · category".
    assert all(a["category"] for a in receipt["attendees"])
    assert receipt["has_extras"] is True
    # Extras land in the column for how they're paid.
    assert receipt["credits_total"] == 20
    assert receipt["free_total"] == 30
    assert receipt["allowance_total"] == 0
    assert receipt["has_free"] is True
    # Grand total = fighters + all extras (the crew's credits value).
    assert receipt["total"] == 150
    assert receipt["total"] == crew.credits_value()


@pytest.mark.django_db
def test_can_manage(crew_setup, make_user):
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(battle=battle, list=gang, owner=crew_setup["user"])

    # Gang owner / battle owner (same user here) can manage.
    assert crew.can_manage(crew_setup["user"]) is True
    # A stranger cannot.
    stranger = make_user("stranger", "pw")
    assert crew.can_manage(stranger) is False

    # Not while archived.
    battle.archive()
    assert crew.can_manage(crew_setup["user"]) is False


# --- Eligibility ------------------------------------------------------------


@pytest.mark.django_db
def test_eligible_crew_fighters_excludes_non_active(crew_setup, make_list_fighter):
    gang = crew_setup["gang"]
    fighters = crew_setup["fighters"]
    # Injure, archive fighters — they should drop out of the pool.
    fighters[0].injury_state = ListFighter.DEAD
    fighters[0].save()
    fighters[1].archived = True
    fighters[1].save()

    eligible = set(eligible_crew_fighters(gang))
    assert fighters[0] not in eligible
    assert fighters[1] not in eligible
    assert fighters[2] in eligible


# --- Lock / draw handler ----------------------------------------------------


@pytest.mark.django_db
def test_lock_freezes_chosen_and_draws_random(crew_setup):
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    fighters = crew_setup["fighters"]
    crew = Crew.objects.create(
        battle=battle, list=gang, owner=crew_setup["user"], random_spec="2"
    )
    crew.chosen_fighters.set(fighters[:1])

    result = handle_crew_lock(user=crew_setup["user"], crew=crew, rng=Random(1))

    crew.refresh_from_db()
    assert crew.status == Crew.LOCKED
    assert result.chosen_count == 1
    assert result.random_count == 2

    members = list(crew.members.all())
    assert len(members) == 3
    chosen_members = [m for m in members if not m.was_random]
    random_members = [m for m in members if m.was_random]
    assert [m.list_fighter_id for m in chosen_members] == [fighters[0].id]
    assert len(random_members) == 2
    # Random draws never re-pick a chosen fighter.
    assert fighters[0].id not in {m.list_fighter_id for m in random_members}


@pytest.mark.django_db
def test_lock_writes_campaign_action(crew_setup):
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(
        battle=battle, list=gang, owner=crew_setup["user"], random_spec="D3"
    )
    crew.chosen_fighters.set(crew_setup["fighters"][:2])

    result = handle_crew_lock(user=crew_setup["user"], crew=crew, rng=Random(0))

    action = CampaignAction.objects.filter(battle=battle).first()
    assert action is not None
    assert action == result.campaign_action
    assert "Crew locked" in action.description


@pytest.mark.django_db
def test_lock_whole_gang_enrols_all_eligible(crew_setup):
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    # No chosen fighters and no random spec = "Whole gang".
    crew = Crew.objects.create(battle=battle, list=gang, owner=crew_setup["user"])
    assert crew.method_label() == "Whole gang"

    result = handle_crew_lock(user=crew_setup["user"], crew=crew)

    crew.refresh_from_db()
    assert crew.status == Crew.LOCKED
    # All five eligible fighters attend, none marked random.
    members = list(crew.members.all())
    assert len(members) == 5
    assert all(not m.was_random for m in members)
    assert result.chosen_count == 5
    assert result.random_count == 0
    assert result.whole_gang is True
    action = CampaignAction.objects.filter(battle=battle).first()
    assert "whole gang" in action.outcome


@pytest.mark.django_db
def test_lock_is_idempotent(crew_setup):
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(
        battle=battle, list=gang, owner=crew_setup["user"], status=Crew.LOCKED
    )
    with pytest.raises(ValidationError):
        handle_crew_lock(user=crew_setup["user"], crew=crew)


@pytest.mark.django_db
def test_lock_random_pool_excludes_ineligible(crew_setup):
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    fighters = crew_setup["fighters"]
    # Only two active, non-chosen fighters remain eligible.
    for f in fighters[2:]:
        f.injury_state = ListFighter.DEAD
        f.save()
    crew = Crew.objects.create(
        battle=battle, list=gang, owner=crew_setup["user"], random_spec="10"
    )
    crew.chosen_fighters.set(fighters[:1])

    result = handle_crew_lock(user=crew_setup["user"], crew=crew, rng=Random(0))

    # Asked for 10, only fighters[1] is eligible-and-not-chosen.
    assert result.random_count == 1
    random_ids = {m.list_fighter_id for m in crew.members.filter(was_random=True)}
    assert random_ids == {fighters[1].id}


# --- Views ------------------------------------------------------------------


@pytest.mark.django_db
def test_crew_new_creates_crew(client, crew_setup):
    client.force_login(crew_setup["user"])
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    url = reverse("core:crew-new", args=[battle.id])

    # The form renders with the gang chosen via query string.
    assert client.get(url, {"list": str(gang.id)}).status_code == 200

    resp = client.post(
        url,
        {
            "list": str(gang.id),
            "name": "A Team",
            "random_dice": "D3",
            "random_number": "",
            "chosen_fighters": [str(crew_setup["fighters"][0].id)],
        },
    )
    assert resp.status_code == 302
    crew = Crew.objects.get(battle=battle, list=gang)
    assert crew.name == "A Team"
    assert crew.random_spec == "D3"
    assert list(crew.chosen_fighters.all()) == [crew_setup["fighters"][0]]


@pytest.mark.django_db
def test_crew_new_permission_denied_for_stranger(client, crew_setup, make_user):
    stranger = make_user("stranger", "pw")
    client.force_login(stranger)
    battle, gang = crew_setup["battle"], crew_setup["gang"]

    resp = client.post(
        reverse("core:crew-new", args=[battle.id]),
        {"list": str(gang.id), "name": "Nope", "random_dice": "", "random_number": ""},
    )
    assert resp.status_code == 302
    assert not Crew.objects.filter(battle=battle).exists()


@pytest.mark.django_db
def test_crew_and_extra_owned_by_gang_owner(
    client, crew_setup, make_user, make_list, make_list_fighter
):
    """An arbitrator creating a crew for another player's gang: the crew and its
    extras are owned by the gang's player, not the acting arbitrator."""
    arbiter = crew_setup["user"]  # owns the campaign and the battle
    campaign, battle = crew_setup["campaign"], crew_setup["battle"]
    player = make_user("player2", "pw")
    other_gang = make_list(
        "Other Gang", owner=player, status=List.CAMPAIGN_MODE, campaign=campaign
    )
    campaign.lists.add(other_gang)
    make_list_fighter(other_gang, "Their Ganger", owner=player)
    battle.set_participants(list(battle.participants.all()) + [other_gang])

    client.force_login(arbiter)
    resp = client.post(
        reverse("core:crew-new", args=[battle.id]),
        {
            "list": str(other_gang.id),
            "name": "For player",
            "random_dice": "",
            "random_number": "",
        },
    )
    assert resp.status_code == 302
    crew = Crew.objects.get(battle=battle, list=other_gang)
    assert crew.owner == player

    client.post(
        reverse("core:crew-extra-new", args=[battle.id, crew.id]),
        {"label": "Card", "cost": "10", "payment": Crew.PAY_CREDITS, "reason": ""},
    )
    assert CrewLineItem.objects.get(crew=crew).owner == player


@pytest.mark.django_db
def test_crew_detail_and_edit(client, crew_setup):
    client.force_login(crew_setup["user"])
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(battle=battle, list=gang, owner=crew_setup["user"])
    crew.chosen_fighters.set(crew_setup["fighters"][:1])

    assert (
        client.get(reverse("core:crew", args=[battle.id, crew.id])).status_code == 200
    )

    resp = client.post(
        reverse("core:crew-edit", args=[battle.id, crew.id]),
        {
            "name": "Renamed",
            "random_dice": "D6",
            "random_number": "2",
            "chosen_fighters": [str(f.id) for f in crew_setup["fighters"][:3]],
        },
    )
    assert resp.status_code == 302
    crew.refresh_from_db()
    assert crew.name == "Renamed"
    assert crew.random_spec == "D6+2"
    assert crew.chosen_fighters.count() == 3


@pytest.mark.django_db
def test_crew_edit_blocked_when_locked(client, crew_setup):
    client.force_login(crew_setup["user"])
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(
        battle=battle, list=gang, owner=crew_setup["user"], status=Crew.LOCKED
    )
    resp = client.get(reverse("core:crew-edit", args=[battle.id, crew.id]))
    # Redirected back to the crew rather than serving the edit form.
    assert resp.status_code == 302


@pytest.mark.django_db
def test_crew_lock_view(client, crew_setup):
    client.force_login(crew_setup["user"])
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(
        battle=battle, list=gang, owner=crew_setup["user"], random_spec="1"
    )
    crew.chosen_fighters.set(crew_setup["fighters"][:1])

    assert (
        client.get(reverse("core:crew-lock", args=[battle.id, crew.id])).status_code
        == 200
    )
    resp = client.post(reverse("core:crew-lock", args=[battle.id, crew.id]))
    assert resp.status_code == 302
    crew.refresh_from_db()
    assert crew.status == Crew.LOCKED
    assert crew.members.count() == 2


@pytest.mark.django_db
def test_crew_delete_view(client, crew_setup):
    client.force_login(crew_setup["user"])
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(battle=battle, list=gang, owner=crew_setup["user"])

    resp = client.post(reverse("core:crew-delete", args=[battle.id, crew.id]))
    assert resp.status_code == 302
    assert not Crew.objects.filter(id=crew.id).exists()


@pytest.mark.django_db
def test_crew_member_loadout_view(client, crew_setup, equipped_fighter):
    client.force_login(crew_setup["user"])
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    fighter, card = equipped_fighter(gang)
    crew = Crew.objects.create(
        battle=battle, list=gang, owner=crew_setup["user"], status=Crew.LOCKED
    )
    member = CrewMember.objects.create(
        crew=crew, list_fighter=fighter, owner=crew_setup["user"]
    )

    resp = client.post(
        reverse("core:crew-member-loadout", args=[battle.id, crew.id, member.id]),
        {"equipment_set": str(card.id)},
    )
    assert resp.status_code == 302
    member.refresh_from_db()
    assert member.equipment_set_id == card.id


@pytest.mark.django_db
def test_crew_extra_add_edit_delete(client, crew_setup):
    client.force_login(crew_setup["user"])
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(battle=battle, list=gang, owner=crew_setup["user"])

    # Add.
    resp = client.post(
        reverse("core:crew-extra-new", args=[battle.id, crew.id]),
        {
            "label": "Tactics card",
            "cost": "20",
            "payment": Crew.PAY_CREDITS,
            "reason": "",
        },
    )
    assert resp.status_code == 302
    item = CrewLineItem.objects.get(crew=crew)
    assert item.cost == 20

    # Edit.
    client.post(
        reverse("core:crew-extra-edit", args=[battle.id, crew.id, item.id]),
        {
            "label": "Tactics card",
            "cost": "35",
            "payment": Crew.PAY_CREDITS,
            "reason": "",
        },
    )
    item.refresh_from_db()
    assert item.cost == 35

    # Delete.
    client.post(reverse("core:crew-extra-delete", args=[battle.id, crew.id, item.id]))
    assert not CrewLineItem.objects.filter(id=item.id).exists()


@pytest.mark.django_db
def test_battle_page_shows_crew_section(client, crew_setup):
    client.force_login(crew_setup["user"])
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    resp = client.get(reverse("core:battle", args=[battle.id]))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "Crews" in content
    # Add-crew affordance for the manageable gang with no crew yet.
    assert f"?list={gang.id}" in content
