"""Tests for battle crews (#1346).

Covers the selection-spec parser, the Crew/CrewMember/CrewLineItem models
(method label, live rating for draft vs locked, extras, deltas, permissions),
the set-scoped fighter cost that feeds crew rating, the lock/draw handler, the
URL-driven selection-method picker with its per-method validation, and the crew
lifecycle views.
"""

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import NoReverseMatch, reverse

from random import Random
from uuid import uuid4

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


@pytest.mark.parametrize(
    "spec", ["x", "D", "3+D3", "-1", "D0", "D3+", "+2", "D-1", "0", "D6+0"]
)
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


def add_chosen(crew, fighters):
    """Add ``fighters`` to ``crew`` as chosen members — what saving a recipe
    does. Members exist from selection time, so a draft crew has them too."""
    return [
        CrewMember.objects.create(
            crew=crew,
            list_fighter=fighter,
            source=CrewMember.CHOSEN,
            owner=crew.owner,
        )
        for fighter in fighters
    ]


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
def test_method_label_uses_rulebook_notation(crew_setup):
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(battle=battle, list=gang, owner=crew_setup["user"])

    # Custom Selection with no number in brackets: the whole gang may take part.
    assert crew.method_label() == "Custom Selection"

    crew.custom_count = 4
    assert crew.method_label() == "Custom Selection (4)"

    crew.selection_method = Crew.RANDOM
    crew.custom_count = None
    crew.random_spec = "D6+2"
    assert crew.method_label() == "Random Selection (D6+2)"

    crew.selection_method = Crew.HYBRID
    crew.custom_count = 2
    assert crew.method_label() == "Hybrid Selection (2+D6+2)"


@pytest.mark.django_db
def test_pending_roll_by_method(crew_setup):
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(battle=battle, list=gang, owner=crew_setup["user"])

    # Custom has nothing to roll, whatever the recipe says.
    assert crew.pending_roll is False
    crew.custom_count = 3
    assert crew.pending_roll is False

    for method in (Crew.RANDOM, Crew.HYBRID):
        crew.selection_method = method
        crew.random_spec = "D3"
        assert crew.pending_roll is True

    # A locked crew has already been drawn.
    crew.status = Crew.LOCKED
    assert crew.pending_roll is False


@pytest.mark.django_db
def test_draft_rating_sums_chosen_full_cost(crew_setup):
    """Rating neutrality: a draft crew's rating is the sum of its chosen members
    at full kit — the same number the chosen-fighters M2M used to produce."""
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(
        battle=battle, list=gang, owner=crew_setup["user"], custom_count=3
    )
    add_chosen(crew, crew_setup["fighters"][:3])

    # Three fighters at base 100 each, all with no equipment set (full kit).
    assert all(m.equipment_set_id is None for m in crew.members.all())
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
        battle=battle,
        list=gang,
        owner=crew_setup["user"],
        selection_method=Crew.HYBRID,
        custom_count=1,
        random_spec="2",
    )
    add_chosen(crew, fighters[:1])

    result = handle_crew_lock(user=crew_setup["user"], crew=crew, rng=Random(1))

    crew.refresh_from_db()
    assert crew.status == Crew.LOCKED
    assert result.chosen_count == 1
    assert result.random_count == 2

    members = list(crew.members.all())
    assert len(members) == 3
    chosen_members = [m for m in members if m.source == CrewMember.CHOSEN]
    random_members = [m for m in members if m.source == CrewMember.DRAWN]
    assert [m.list_fighter_id for m in chosen_members] == [fighters[0].id]
    assert len(random_members) == 2
    # Random draws never re-pick a chosen fighter.
    assert fighters[0].id not in {m.list_fighter_id for m in random_members}


@pytest.mark.django_db
def test_lock_does_not_duplicate_chosen_members(crew_setup):
    """The chosen members already exist when the lock runs, so the draw must
    exclude them: re-drawing one would trip unique(crew, list_fighter)."""
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    fighters = crew_setup["fighters"]
    # Ask for more random fighters than the gang has left, so the pool would
    # certainly include a chosen fighter if it weren't excluded.
    crew = Crew.objects.create(
        battle=battle,
        list=gang,
        owner=crew_setup["user"],
        selection_method=Crew.HYBRID,
        custom_count=2,
        random_spec="10",
    )
    add_chosen(crew, fighters[:2])

    handle_crew_lock(user=crew_setup["user"], crew=crew, rng=Random(3))

    member_fighter_ids = [m.list_fighter_id for m in crew.members.all()]
    # Everyone attends, exactly once.
    assert len(member_fighter_ids) == len(set(member_fighter_ids)) == 5
    chosen = crew.members.filter(source=CrewMember.CHOSEN)
    assert {m.list_fighter_id for m in chosen} == {fighters[0].id, fighters[1].id}


@pytest.mark.django_db
def test_lock_writes_campaign_action(crew_setup):
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(
        battle=battle,
        list=gang,
        owner=crew_setup["user"],
        selection_method=Crew.HYBRID,
        custom_count=2,
        random_spec="D3",
    )
    add_chosen(crew, crew_setup["fighters"][:2])

    result = handle_crew_lock(user=crew_setup["user"], crew=crew, rng=Random(0))

    action = CampaignAction.objects.filter(battle=battle).first()
    assert action is not None
    assert action == result.campaign_action
    assert "Crew selected" in action.description


@pytest.mark.django_db
def test_lock_whole_gang_enrols_all_eligible(crew_setup):
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    # Custom Selection with no number in brackets and nobody chosen: the whole
    # gang takes part.
    crew = Crew.objects.create(battle=battle, list=gang, owner=crew_setup["user"])
    assert crew.method_label() == "Custom Selection"

    result = handle_crew_lock(user=crew_setup["user"], crew=crew)

    crew.refresh_from_db()
    assert crew.status == Crew.LOCKED
    # All five eligible fighters attend, none marked random.
    members = list(crew.members.all())
    assert len(members) == 5
    assert all(m.source == CrewMember.CHOSEN for m in members)
    assert result.chosen_count == 5
    assert result.random_count == 0
    assert result.whole_gang is True
    action = CampaignAction.objects.filter(battle=battle).first()
    assert "whole gang" in action.outcome


@pytest.mark.django_db
def test_lock_skips_chosen_now_ineligible(crew_setup):
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    fighters = crew_setup["fighters"]
    crew = Crew.objects.create(
        battle=battle, list=gang, owner=crew_setup["user"], custom_count=2
    )
    add_chosen(crew, fighters[:2])
    # A chosen fighter becomes ineligible between the recipe and the lock.
    fighters[1].archived = True
    fighters[1].save()

    result = handle_crew_lock(user=crew_setup["user"], crew=crew)

    # Only the still-eligible pick is enrolled; the archived one is dropped.
    members = list(crew.members.all())
    assert [m.list_fighter_id for m in members] == [fighters[0].id]
    assert result.chosen_count == 1
    assert result.skipped_ineligible == 1
    # Picks were named, so it's a custom crew (now short one), not a whole-gang one.
    assert result.whole_gang is False


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
        battle=battle,
        list=gang,
        owner=crew_setup["user"],
        selection_method=Crew.HYBRID,
        custom_count=1,
        random_spec="10",
    )
    add_chosen(crew, fighters[:1])

    result = handle_crew_lock(user=crew_setup["user"], crew=crew, rng=Random(0))

    # Asked for 10, only fighters[1] is eligible-and-not-chosen.
    assert result.random_count == 1
    random_ids = {
        m.list_fighter_id for m in crew.members.filter(source=CrewMember.DRAWN)
    }
    assert random_ids == {fighters[1].id}


@pytest.mark.django_db
def test_locked_crew_preserves_member_source(crew_setup):
    """Once locked, how each attendee joined is still on the record."""
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(
        battle=battle,
        list=gang,
        owner=crew_setup["user"],
        selection_method=Crew.HYBRID,
        custom_count=1,
        random_spec="1",
    )
    add_chosen(crew, crew_setup["fighters"][:1])

    handle_crew_lock(user=crew_setup["user"], crew=crew, rng=Random(2))

    sources = sorted(m.source for m in crew.members.all())
    assert sources == [CrewMember.CHOSEN, CrewMember.DRAWN]
    # The receipt flags the drawn one for the "Random" badge.
    flags = sorted(a["is_random"] for a in crew.receipt()["attendees"])
    assert flags == [False, True]


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
            "method": Crew.HYBRID,
            "name": "A Team",
            "custom_count": "1",
            "random_dice": "D3",
            "random_number": "",
            "chosen_fighters": [str(crew_setup["fighters"][0].id)],
        },
    )
    assert resp.status_code == 302
    crew = Crew.objects.get(battle=battle, list=gang)
    assert crew.name == "A Team"
    assert crew.selection_method == Crew.HYBRID
    assert crew.custom_count == 1
    assert crew.random_spec == "D3"
    assert [m.list_fighter_id for m in crew.members.all()] == [
        crew_setup["fighters"][0].id
    ]


@pytest.mark.django_db
def test_crew_new_permission_denied_for_stranger(client, crew_setup, make_user):
    stranger = make_user("stranger", "pw")
    client.force_login(stranger)
    battle, gang = crew_setup["battle"], crew_setup["gang"]

    resp = client.post(
        reverse("core:crew-new", args=[battle.id]),
        {"list": str(gang.id), "method": Crew.CUSTOM, "name": "Nope"},
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
            "method": Crew.CUSTOM,
            "name": "For player",
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
    crew = Crew.objects.create(
        battle=battle, list=gang, owner=crew_setup["user"], custom_count=1
    )
    add_chosen(crew, crew_setup["fighters"][:1])

    assert (
        client.get(reverse("core:crew", args=[battle.id, crew.id])).status_code == 200
    )

    resp = client.post(
        reverse("core:crew-edit", args=[battle.id, crew.id]),
        {
            "method": Crew.HYBRID,
            "name": "Renamed",
            "custom_count": "3",
            "random_dice": "D6",
            "random_number": "2",
            "chosen_fighters": [str(f.id) for f in crew_setup["fighters"][:3]],
        },
    )
    assert resp.status_code == 302
    crew.refresh_from_db()
    assert crew.name == "Renamed"
    assert crew.selection_method == Crew.HYBRID
    assert crew.random_spec == "D6+2"
    assert crew.members.filter(source=CrewMember.CHOSEN).count() == 3


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
        battle=battle,
        list=gang,
        owner=crew_setup["user"],
        selection_method=Crew.HYBRID,
        custom_count=1,
        random_spec="1",
    )
    add_chosen(crew, crew_setup["fighters"][:1])

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


def test_post_lock_loadout_editing_is_gone():
    """A locked crew is frozen: equipment sets are chosen during selection, and
    there is no route to change one afterwards."""
    with pytest.raises(NoReverseMatch):
        reverse("core:crew-member-loadout", args=[uuid4(), uuid4(), uuid4()])


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
    # The participants table lists the gang; the add-crew affordance appears
    # for a manageable gang with no crew yet.
    assert "Participants" in content
    assert gang.name in content
    assert f"?list={gang.id}" in content


@pytest.mark.django_db
def test_print_fighter_ids_by_state(crew_setup):
    gang, fighters, battle = (
        crew_setup["gang"],
        crew_setup["fighters"],
        crew_setup["battle"],
    )
    user = crew_setup["user"]
    crew = Crew.objects.create(battle=battle, list=gang, owner=user)

    # Whole-gang draft (no picks, no random) -> None: print the whole gang.
    assert crew.print_fighter_ids() is None

    # Draft with picks -> exactly the chosen fighters.
    add_chosen(crew, [fighters[0], fighters[2]])
    assert set(crew.print_fighter_ids()) == {fighters[0].id, fighters[2].id}

    # Locked -> the frozen members (here, the two chosen, no random draw).
    handle_crew_lock(user=user, crew=crew)
    crew.refresh_from_db()
    assert set(crew.print_fighter_ids()) == {fighters[0].id, fighters[2].id}


@pytest.mark.django_db
def test_crew_print_link_filters_to_crew_fighters(client, crew_setup):
    client.force_login(crew_setup["user"])
    gang, fighters, battle = (
        crew_setup["gang"],
        crew_setup["fighters"],
        crew_setup["battle"],
    )
    crew = Crew.objects.create(
        battle=battle,
        list=gang,
        owner=crew_setup["user"],
        name="Alpha",
        custom_count=2,
    )
    add_chosen(crew, [fighters[0], fighters[1]])

    resp = client.get(reverse("core:list-print", args=[gang.id]) + f"?crew={crew.id}")
    assert resp.status_code == 200
    content = resp.content.decode()
    assert fighters[0].name in content
    assert fighters[1].name in content
    # A gang fighter that isn't in the crew is filtered out of the print.
    assert fighters[2].name not in content


@pytest.mark.django_db
def test_print_ignores_malformed_crew_param(client, crew_setup):
    client.force_login(crew_setup["user"])
    gang = crew_setup["gang"]
    # A non-UUID ?crew= fails closed (whole gang), not a 500.
    resp = client.get(reverse("core:list-print", args=[gang.id]) + "?crew=not-a-uuid")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_crew_new_rejects_malformed_list_param(client, crew_setup):
    client.force_login(crew_setup["user"])
    battle = crew_setup["battle"]
    # A non-UUID ?list= redirects to the battle rather than 500ing.
    resp = client.get(reverse("core:crew-new", args=[battle.id]) + "?list=not-a-uuid")
    assert resp.status_code == 302
    assert reverse("core:battle", args=[battle.id]) in resp.url


# --- Selection-method backfill (migration 0170) -----------------------------


def _load_migration(name):
    """Import a migration module by name — its filename isn't an identifier."""
    import importlib

    return importlib.import_module(f"gyrinx.core.migrations.{name}")


@pytest.mark.django_db
def test_migration_derives_selection_method(crew_setup):
    """The 0170 backfill must leave every existing crew meaning what it meant
    when the method was derived rather than stored. Exercises the migration's
    own function against the four shapes historical data can take."""
    battle, gang, fighters = (
        crew_setup["battle"],
        crew_setup["gang"],
        crew_setup["fighters"],
    )
    user = crew_setup["user"]

    def make(name, *, picks, spec):
        other = List.objects.create(
            name=name, content_house=gang.content_house, owner=user
        )
        battle.set_participants(list(battle.participants.all()) + [other])
        crew = Crew.objects.create(
            battle=battle, list=other, owner=user, random_spec=spec
        )
        crew.chosen_fighters.set(picks)
        # Simulate pre-migration data: the columns hadn't been populated yet.
        Crew.objects.filter(pk=crew.pk).update(
            selection_method=Crew.CUSTOM, custom_count=None
        )
        return crew

    hybrid = make("Hybrid gang", picks=fighters[:2], spec="D3")
    random_only = make("Random gang", picks=[], spec="D6+1")
    custom = make("Custom gang", picks=fighters[:3], spec="")
    whole = make("Whole gang", picks=[], spec="")

    derive = _load_migration("0170_crew_selection_method").derive_selection_method
    derive(apps, None)

    for crew in (hybrid, random_only, custom, whole):
        crew.refresh_from_db()

    assert (hybrid.selection_method, hybrid.custom_count) == (Crew.HYBRID, 2)
    assert (random_only.selection_method, random_only.custom_count) == (
        Crew.RANDOM,
        None,
    )
    assert (custom.selection_method, custom.custom_count) == (Crew.CUSTOM, 3)
    # Neither picks nor a spec: Custom Selection with no number = whole gang.
    assert (whole.selection_method, whole.custom_count) == (Crew.CUSTOM, None)
    # Labels still read as they did before the method was stored.
    assert hybrid.method_label() == "Hybrid Selection (2+D3)"
    assert random_only.method_label() == "Random Selection (D6+1)"
    assert custom.method_label() == "Custom Selection (3)"
    assert whole.method_label() == "Custom Selection"


# --- URL-driven method picker ----------------------------------------------


def _crew_new_url(crew_setup, method=None):
    url = reverse("core:crew-new", args=[crew_setup["battle"].id])
    query = f"?list={crew_setup['gang'].id}"
    if method is not None:
        query += f"&method={method}"
    return url + query


@pytest.mark.django_db
@pytest.mark.parametrize("method", [Crew.CUSTOM, Crew.RANDOM, Crew.HYBRID])
def test_method_picker_links_to_the_other_methods(client, crew_setup, method):
    client.force_login(crew_setup["user"])
    resp = client.get(_crew_new_url(crew_setup, method))
    assert resp.status_code == 200
    content = resp.content.decode()

    # Every method is offered, and each link carries the gang so switching
    # method doesn't lose it.
    for other, label in Crew.SELECTION_METHOD_CHOICES:
        assert label in content
        if other != method:
            assert f"method={other}" in content
    assert f"list={crew_setup['gang'].id}" in content


@pytest.mark.django_db
def test_random_form_has_no_fighter_checkboxes(client, crew_setup):
    """The invalid state is unrepresentable: with no chosen_fighters field on
    the Random form, a user cannot tick fighters for an all-random selection."""
    client.force_login(crew_setup["user"])
    resp = client.get(_crew_new_url(crew_setup, Crew.RANDOM))
    form = resp.context["form"]

    assert "chosen_fighters" not in form.fields
    assert "custom_count" not in form.fields
    assert "random_dice" in form.fields
    assert 'name="chosen_fighters"' not in resp.content.decode()


@pytest.mark.django_db
def test_custom_form_has_no_random_fields(client, crew_setup):
    client.force_login(crew_setup["user"])
    form = client.get(_crew_new_url(crew_setup, Crew.CUSTOM)).context["form"]

    assert "random_dice" not in form.fields
    assert "random_number" not in form.fields
    assert "chosen_fighters" in form.fields


@pytest.mark.django_db
def test_nonsense_method_coerces_to_a_valid_variant(client, crew_setup):
    client.force_login(crew_setup["user"])

    # On create, an unrecognised ?method= falls back to Custom Selection.
    resp = client.get(_crew_new_url(crew_setup, "nonsense"))
    assert resp.status_code == 200
    assert resp.context["method"] == Crew.CUSTOM

    # On edit, it falls back to whatever the crew was saved with.
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        selection_method=Crew.RANDOM,
        random_spec="D3",
    )
    resp = client.get(
        reverse("core:crew-edit", args=[crew_setup["battle"].id, crew.id])
        + "?method=nonsense"
    )
    assert resp.status_code == 200
    assert resp.context["method"] == Crew.RANDOM


@pytest.mark.django_db
def test_edit_without_method_keeps_the_stored_one(client, crew_setup):
    """The plain "Edit" link carries no ?method=, so it must open the crew on
    the method it was saved with."""
    client.force_login(crew_setup["user"])
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        selection_method=Crew.HYBRID,
        custom_count=1,
        random_spec="D6",
    )
    add_chosen(crew, crew_setup["fighters"][:1])

    resp = client.get(
        reverse("core:crew-edit", args=[crew_setup["battle"].id, crew.id])
    )
    assert resp.context["method"] == Crew.HYBRID
    form = resp.context["form"]
    assert form.fields["custom_count"].initial == 1
    assert form.fields["chosen_fighters"].initial == [crew_setup["fighters"][0].id]


# --- Per-method validation --------------------------------------------------


@pytest.mark.django_db
def test_custom_requires_exactly_the_bracket_number(client, crew_setup):
    client.force_login(crew_setup["user"])
    fighters = crew_setup["fighters"]

    resp = client.post(
        _crew_new_url(crew_setup, Crew.CUSTOM),
        {
            "list": str(crew_setup["gang"].id),
            "method": Crew.CUSTOM,
            "name": "",
            "custom_count": "3",
            "chosen_fighters": [str(fighters[0].id)],
        },
    )
    # Re-rendered with the error, nothing saved.
    assert resp.status_code == 200
    assert resp.context["form"].errors["chosen_fighters"] == [
        "Choose exactly 3 fighters — you've chosen 1."
    ]
    assert not Crew.objects.filter(battle=crew_setup["battle"]).exists()

    resp = client.post(
        _crew_new_url(crew_setup, Crew.CUSTOM),
        {
            "list": str(crew_setup["gang"].id),
            "method": Crew.CUSTOM,
            "name": "",
            "custom_count": "3",
            "chosen_fighters": [str(f.id) for f in fighters[:3]],
        },
    )
    assert resp.status_code == 302
    crew = Crew.objects.get(battle=crew_setup["battle"])
    assert crew.custom_count == 3
    assert crew.members.count() == 3


@pytest.mark.django_db
def test_custom_blank_count_allows_any_number_of_picks(client, crew_setup):
    """Custom Selection with no number in brackets is unbounded."""
    client.force_login(crew_setup["user"])
    resp = client.post(
        _crew_new_url(crew_setup, Crew.CUSTOM),
        {
            "list": str(crew_setup["gang"].id),
            "method": Crew.CUSTOM,
            "name": "",
            "custom_count": "",
            "chosen_fighters": [str(f.id) for f in crew_setup["fighters"][:2]],
        },
    )
    assert resp.status_code == 302
    crew = Crew.objects.get(battle=crew_setup["battle"])
    assert crew.custom_count is None
    assert crew.members.count() == 2


@pytest.mark.django_db
def test_custom_blank_count_with_no_picks_is_the_whole_gang(client, crew_setup):
    client.force_login(crew_setup["user"])
    resp = client.post(
        _crew_new_url(crew_setup, Crew.CUSTOM),
        {
            "list": str(crew_setup["gang"].id),
            "method": Crew.CUSTOM,
            "name": "",
            "custom_count": "",
        },
    )
    assert resp.status_code == 302
    crew = Crew.objects.get(battle=crew_setup["battle"])
    assert crew.is_whole_gang is True
    assert crew.members.count() == 0
    assert crew.method_label() == "Custom Selection"

    # And locking it enrols the whole eligible roster.
    result = handle_crew_lock(user=crew_setup["user"], crew=crew)
    assert result.whole_gang is True
    assert crew.members.count() == 5


@pytest.mark.django_db
def test_count_over_roster_requires_every_eligible_fighter(client, crew_setup):
    client.force_login(crew_setup["user"])
    fighters = crew_setup["fighters"]

    resp = client.post(
        _crew_new_url(crew_setup, Crew.CUSTOM),
        {
            "list": str(crew_setup["gang"].id),
            "method": Crew.CUSTOM,
            "name": "",
            "custom_count": "8",
            "chosen_fighters": [str(f.id) for f in fighters[:3]],
        },
    )
    assert resp.status_code == 200
    assert resp.context["form"].errors["chosen_fighters"] == [
        "Choose exactly 5 fighters — you've chosen 3. "
        "This gang only has 5 fighters available."
    ]

    # Sending everyone is accepted, even though the scenario asked for more.
    resp = client.post(
        _crew_new_url(crew_setup, Crew.CUSTOM),
        {
            "list": str(crew_setup["gang"].id),
            "method": Crew.CUSTOM,
            "name": "",
            "custom_count": "8",
            "chosen_fighters": [str(f.id) for f in fighters],
        },
    )
    assert resp.status_code == 302
    assert Crew.objects.get(battle=crew_setup["battle"]).members.count() == 5


@pytest.mark.django_db
def test_random_requires_a_spec(client, crew_setup):
    client.force_login(crew_setup["user"])
    resp = client.post(
        _crew_new_url(crew_setup, Crew.RANDOM),
        {
            "list": str(crew_setup["gang"].id),
            "method": Crew.RANDOM,
            "name": "",
            "random_dice": "",
            "random_number": "",
        },
    )
    assert resp.status_code == 200
    assert "Random Selection always shows a number in brackets." in (
        resp.content.decode()
    )
    assert not Crew.objects.filter(battle=crew_setup["battle"]).exists()


@pytest.mark.django_db
def test_hybrid_requires_both_numbers(client, crew_setup):
    client.force_login(crew_setup["user"])
    resp = client.post(
        _crew_new_url(crew_setup, Crew.HYBRID),
        {
            "list": str(crew_setup["gang"].id),
            "method": Crew.HYBRID,
            "name": "",
            "custom_count": "",
            "random_dice": "",
            "random_number": "",
        },
    )
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "the first number in brackets." in content
    assert "the second number in brackets." in content
    assert not Crew.objects.filter(battle=crew_setup["battle"]).exists()


@pytest.mark.django_db
def test_method_round_trips_through_a_validation_error(client, crew_setup):
    """A failed POST must re-render the same variant, not fall back to Custom."""
    client.force_login(crew_setup["user"])
    resp = client.post(
        reverse("core:crew-new", args=[crew_setup["battle"].id]),
        {
            "list": str(crew_setup["gang"].id),
            "method": Crew.RANDOM,
            "name": "",
            "random_dice": "",
            "random_number": "",
        },
    )
    assert resp.status_code == 200
    assert resp.context["method"] == Crew.RANDOM
    assert "chosen_fighters" not in resp.context["form"].fields
    assert 'value="random"' in resp.content.decode()


@pytest.mark.django_db
def test_switching_method_clears_the_other_methods_fields(client, crew_setup):
    """Hybrid → Random must null the custom count and drop the chosen members;
    → Custom must blank the random spec."""
    client.force_login(crew_setup["user"])
    battle, gang, fighters = (
        crew_setup["battle"],
        crew_setup["gang"],
        crew_setup["fighters"],
    )
    crew = Crew.objects.create(
        battle=battle,
        list=gang,
        owner=crew_setup["user"],
        selection_method=Crew.HYBRID,
        custom_count=2,
        random_spec="D3",
    )
    add_chosen(crew, fighters[:2])

    edit_url = reverse("core:crew-edit", args=[battle.id, crew.id])
    resp = client.post(
        edit_url + f"?method={Crew.RANDOM}",
        {"method": Crew.RANDOM, "name": "", "random_dice": "D6", "random_number": "2"},
    )
    assert resp.status_code == 302
    crew.refresh_from_db()
    assert crew.selection_method == Crew.RANDOM
    assert crew.custom_count is None
    assert crew.random_spec == "D6+2"
    assert crew.members.count() == 0

    resp = client.post(
        edit_url + f"?method={Crew.CUSTOM}",
        {
            "method": Crew.CUSTOM,
            "name": "",
            "custom_count": "1",
            "chosen_fighters": [str(fighters[0].id)],
        },
    )
    assert resp.status_code == 302
    crew.refresh_from_db()
    assert crew.selection_method == Crew.CUSTOM
    assert crew.random_spec == ""
    assert crew.custom_count == 1
    assert [m.list_fighter_id for m in crew.members.all()] == [fighters[0].id]


# --- Equipment sets during selection ----------------------------------------


@pytest.mark.django_db
def test_chosen_fighter_brings_the_selected_equipment_set(
    client, crew_setup, equipped_fighter
):
    """Custom Selection lets the player choose which card each model uses, and
    that scopes the model's contribution to the crew's rating."""
    client.force_login(crew_setup["user"])
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    fighter, card = equipped_fighter(gang)

    resp = client.post(
        _crew_new_url(crew_setup, Crew.CUSTOM),
        {
            "method": Crew.CUSTOM,
            "list": str(gang.id),
            "name": "",
            "custom_count": "1",
            "chosen_fighters": [str(fighter.id)],
            f"equipment_set_{fighter.id}": str(card.id),
        },
    )
    assert resp.status_code == 302

    crew = Crew.objects.get(battle=battle, list=gang)
    assert crew.members.get().equipment_set_id == card.id
    # The light kit (145), not the 195 full kit — see the set-scoped cost test.
    assert crew.rating() == 145

    # Re-opening the recipe shows the card that was chosen.
    edit_page = client.get(reverse("core:crew-edit", args=[battle.id, crew.id]))
    assert f'value="{card.id}" selected' in edit_page.content.decode()

    # Switching back to the Default card clears the choice.
    resp = client.post(
        reverse("core:crew-edit", args=[battle.id, crew.id]),
        {
            "method": Crew.CUSTOM,
            "name": "",
            "custom_count": "1",
            "chosen_fighters": [str(fighter.id)],
            f"equipment_set_{fighter.id}": "",
        },
    )
    assert resp.status_code == 302
    assert crew.members.get().equipment_set_id is None
    assert crew.rating() == 195


@pytest.mark.django_db
def test_set_select_rendered_only_for_fighters_with_sets(
    client, crew_setup, equipped_fighter
):
    """A fighter with one card has nothing to choose, so gets no select."""
    client.force_login(crew_setup["user"])
    fighter, card = equipped_fighter(crew_setup["gang"])

    resp = client.get(_crew_new_url(crew_setup, Crew.CUSTOM))
    form = resp.context["form"]
    content = resp.content.decode()

    assert f"equipment_set_{fighter.id}" in form.fields
    assert f'name="equipment_set_{fighter.id}"' in content
    assert card.name in content
    for plain in crew_setup["fighters"]:
        assert f"equipment_set_{plain.id}" not in form.fields


@pytest.mark.django_db
def test_selection_form_issues_no_per_fighter_set_query(
    client, crew_setup, equipped_fighter, make_list_fighter
):
    """The sets come from ``with_related_data()``'s prefetch: more fighters with
    sets must not mean more queries."""
    gang = crew_setup["gang"]
    client.force_login(crew_setup["user"])
    url = _crew_new_url(crew_setup, Crew.CUSTOM)

    def render_query_count():
        with CaptureQueriesContext(connection) as ctx:
            assert client.get(url).status_code == 200
        return len(ctx)

    equipped_fighter(gang)
    render_query_count()  # warm anything cached per process
    one_fighter_with_sets = render_query_count()

    for i in range(2):
        fighter = make_list_fighter(gang, f"Carrier {i}")
        ListFighterEquipmentSet.objects.create(
            list_fighter=fighter, name=f"Kit {i}", owner=fighter.owner
        )
    assert render_query_count() == one_fighter_with_sets


@pytest.mark.django_db
def test_random_draw_also_draws_the_card(crew_setup, equipped_fighter):
    """Random Selection determines the card at random too — the deck holds one
    card per model, chosen at random for models with several."""
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    fighter, card = equipped_fighter(gang)
    crew = Crew.objects.create(
        battle=battle,
        list=gang,
        owner=crew_setup["user"],
        selection_method=Crew.RANDOM,
        # Six: the five plain gangers plus the specialist, so the fighter with
        # cards is certain to be drawn.
        random_spec="6",
    )

    handle_crew_lock(user=crew_setup["user"], crew=crew, rng=Random(0))

    member = crew.members.get(list_fighter=fighter)
    assert member.equipment_set_id in (None, card.id)
    # What was drawn is in the campaign log, so the draw can be audited.
    outcome = CampaignAction.objects.get(battle=battle).outcome
    drawn_card = card.name if member.equipment_set_id else "Default"
    assert f"{fighter.name} ({drawn_card})" in outcome


# --- Locked rating snapshot and drift ---------------------------------------


def _lock_one_fighter_crew(crew_setup):
    """A locked crew of a single 100¢ fighter."""
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        custom_count=1,
    )
    add_chosen(crew, crew_setup["fighters"][:1])
    return handle_crew_lock(user=crew_setup["user"], crew=crew).crew


@pytest.mark.django_db
def test_locked_rating_stable_when_fighter_gains_equipment(
    crew_setup, make_equipment, make_weapon_profile
):
    """The crew is a historical record: the gang carrying on buying gear must
    not move the rating of a battle already fought."""
    crew = _lock_one_fighter_crew(crew_setup)
    assert crew.rating() == 100
    assert crew.rating_locked == 100
    assert [m.rating_locked for m in crew.members.all()] == [100]

    bolter = make_equipment(name="Bolter", cost=35, category="Basic Weapons")
    make_weapon_profile(bolter)
    crew_setup["fighters"][0].assign(bolter)

    crew.refresh_from_db()
    assert crew.rating() == 100
    assert crew.members.get().rating() == 100
    assert crew.receipt()["fighters_total"] == 100
    # The live figure has moved — the snapshot simply doesn't follow it.
    assert crew.live_rating() == 135


@pytest.mark.django_db
def test_rating_drift_is_detected_and_surfaced(
    client, crew_setup, make_equipment, make_weapon_profile
):
    crew = _lock_one_fighter_crew(crew_setup)
    bolter = make_equipment(name="Bolter 2", cost=35, category="Basic Weapons")
    make_weapon_profile(bolter)
    crew_setup["fighters"][0].assign(bolter)
    crew.refresh_from_db()

    drift = crew.rating_drift()
    assert drift == {"locked": 100, "live": 135, "has_drifted": True}

    client.force_login(crew_setup["user"])
    battle = crew_setup["battle"]
    resp = client.get(reverse("core:crew", args=[battle.id, crew.id]))
    assert resp.context["has_drifted"] is True
    assert "have changed since it was locked" in resp.content.decode()

    # The arbitrator sees it on the battle page too.
    resp = client.get(reverse("core:battle", args=[battle.id]))
    crew_row = resp.context["participant_groups"][0]["participants"][0]["crew"]
    assert crew_row["has_drifted"] is True
    assert crew_row["rating"] == 100
    assert crew_row["live_rating"] == 135
    assert "changed since it was locked" in resp.content.decode()


@pytest.mark.django_db
def test_crew_locked_before_snapshots_computes_live_and_reports_no_drift(crew_setup):
    """Crews locked before snapshotting shipped keep ``rating_locked`` NULL —
    inventing one now would be inventing a moment. They compute live, and have
    nothing to compare against, so they report no drift."""
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        status=Crew.LOCKED,
    )
    add_chosen(crew, crew_setup["fighters"][:2])

    assert crew.rating_locked is None
    assert crew.rating() == 200
    assert crew.rating() == crew.live_rating()
    assert crew.rating_drift() is None
    assert crew.receipt()["drift"] is None


# --- Wording ----------------------------------------------------------------


@pytest.mark.django_db
def test_crew_pages_use_rulebook_vocabulary(client, crew_setup):
    """The rulebook never says "hand-pick" — it says Custom Selection."""
    client.force_login(crew_setup["user"])
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(
        battle=battle, list=gang, owner=crew_setup["user"], custom_count=1
    )
    add_chosen(crew, crew_setup["fighters"][:1])

    pages = [
        _crew_new_url(crew_setup, Crew.CUSTOM),
        _crew_new_url(crew_setup, Crew.RANDOM),
        _crew_new_url(crew_setup, Crew.HYBRID),
        reverse("core:crew", args=[battle.id, crew.id]),
        reverse("core:crew-edit", args=[battle.id, crew.id]),
        reverse("core:crew-lock", args=[battle.id, crew.id]),
    ]
    for url in pages:
        content = client.get(url).content.decode().lower()
        assert "hand-pick" not in content, url
        assert "hand pick" not in content, url
