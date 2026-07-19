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

from itertools import count
from random import Random
from uuid import uuid4

from gyrinx.core.forms.crew import CrewForm, equipment_set_field_name
from gyrinx.core.handlers.battle import handle_battle_end
from gyrinx.core.handlers.crew import (
    crew_whole_gang_projection,
    eligible_crew_fighters,
    eligible_crew_fighters_for_loadouts,
    handle_crew_lock,
    handle_crew_loadouts_save,
)
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
def test_lock_whole_gang_brings_each_fighters_own_set(crew_setup, equipped_fighter):
    """Nobody is asked which card a whole-gang crew brings, so each model brings
    the set already active on its fighter card rather than the Default."""
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    fighter, card = equipped_fighter(gang)
    fighter.active_equipment_set = card
    fighter.save()

    crew = Crew.objects.create(battle=battle, list=gang, owner=crew_setup["user"])
    handle_crew_lock(user=crew_setup["user"], crew=crew)

    member = crew.members.get(list_fighter=fighter)
    assert member.equipment_set_id == card.id
    # Fighters with no active set still come as Default.
    others = crew.members.exclude(list_fighter=fighter)
    assert all(m.equipment_set_id is None for m in others)


@pytest.mark.django_db
def test_crew_form_preselects_the_fighters_active_set(crew_setup, equipped_fighter):
    """The per-fighter select starts on the set the fighter is already using, so
    leaving it alone brings what the player set up on the fighter."""
    gang = crew_setup["gang"]
    fighter, card = equipped_fighter(gang)
    fighter.active_equipment_set = card
    fighter.save()

    form = CrewForm(gang=gang, method=Crew.CUSTOM)
    field = form.fields[equipment_set_field_name(fighter.pk)]
    assert field.initial == card.id


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


# --- Selected / live / played ratings ---------------------------------------
#
# Three values, three questions: what did I pick (selected, frozen at lock),
# what would I field now (live, computed), what actually fought (played, frozen
# when the battle ends). A locked crew reports *live* until the battle ends,
# because that is what the gang would really put on the table.


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


def _arm_first_fighter(crew_setup, make_equipment, make_weapon_profile, name):
    """Give the crew's fighter a 35¢ bolter, moving them from 100¢ to 135¢."""
    bolter = make_equipment(name=name, cost=35, category="Basic Weapons")
    make_weapon_profile(bolter)
    crew_setup["fighters"][0].assign(bolter)


def _end_battle(crew_setup):
    """Run the battle to its end, which is what freezes what each crew fought
    at."""
    battle = crew_setup["battle"]
    battle.states.transition_to(Battle.IN_PROGRESS)
    handle_battle_end(user=crew_setup["user"], battle=battle, winners=[], is_draw=True)
    return battle


@pytest.mark.django_db
def test_locked_crew_reports_live_rating_until_the_battle_is_played(
    crew_setup, make_equipment, make_weapon_profile
):
    """Locking records what was picked, but the crew goes on reporting what the
    gang would field: come battle night you print the roster and field the
    fighters as they are *then*, so a weapon bought since selection really is
    on the table."""
    crew = _lock_one_fighter_crew(crew_setup)
    assert crew.rating() == 100
    assert crew.rating_selected == 100
    assert crew.rating_played is None
    assert [m.rating_selected for m in crew.members.all()] == [100]

    _arm_first_fighter(crew_setup, make_equipment, make_weapon_profile, "Bolter")

    crew.refresh_from_db()
    assert crew.rating() == 135
    assert crew.members.get().rating() == 135
    assert crew.receipt()["fighters_total"] == 135
    # What was picked is remembered, it just isn't the headline number.
    assert crew.rating_selected == 100


@pytest.mark.django_db
def test_locked_crew_notes_what_it_was_picked_at(
    client, crew_setup, make_equipment, make_weapon_profile
):
    crew = _lock_one_fighter_crew(crew_setup)
    _arm_first_fighter(crew_setup, make_equipment, make_weapon_profile, "Bolter 2")
    crew.refresh_from_db()

    assert crew.rating_note() == {
        "selected": 100,
        "current": 135,
        "is_played": False,
        "differs": True,
    }

    client.force_login(crew_setup["user"])
    battle = crew_setup["battle"]
    resp = client.get(reverse("core:crew", args=[battle.id, crew.id]))
    assert resp.context["show_rating_note"] is True
    assert "was 100¢ when you picked it" in resp.content.decode()

    # The arbitrator sees it on the battle page too.
    resp = client.get(reverse("core:battle", args=[battle.id]))
    crew_row = resp.context["participant_groups"][0]["participants"][0]["crew"]
    assert crew_row["show_rating_note"] is True
    assert crew_row["rating"] == 135
    assert crew_row["rating_note"]["selected"] == 100
    assert "picked at 100¢" in resp.content.decode()


@pytest.mark.django_db
def test_ending_the_battle_freezes_what_fought(
    crew_setup, make_equipment, make_weapon_profile
):
    """Once the fight is over the record must stop moving: later purchases
    can't rewrite what was fielded."""
    crew = _lock_one_fighter_crew(crew_setup)
    _arm_first_fighter(crew_setup, make_equipment, make_weapon_profile, "Bolter 3")
    _end_battle(crew_setup)

    crew.refresh_from_db()
    assert crew.rating_played == 135
    assert crew.rating() == 135
    # Per-member too, so the receipt's rows stop moving with the crew's total.
    assert [m.rating_played for m in crew.members.all()] == [135]
    assert crew.members.get().rating() == 135

    # The gang carries on spending; the crew that fought does not follow it.
    chainsword = make_equipment(name="Chainsword", cost=25, category="Close Combat")
    make_weapon_profile(chainsword)
    crew_setup["fighters"][0].assign(chainsword)

    crew.refresh_from_db()
    assert crew.rating() == 135
    assert crew.members.get().rating() == 135
    assert crew.receipt()["fighters_total"] == 135
    assert crew.live_rating() == 160


@pytest.mark.django_db
def test_played_crew_notes_what_it_was_picked_at(
    client, crew_setup, make_equipment, make_weapon_profile
):
    """After the battle the note preserves the gap between selection and play —
    and says nothing about the gang having moved on since."""
    crew = _lock_one_fighter_crew(crew_setup)
    _arm_first_fighter(crew_setup, make_equipment, make_weapon_profile, "Bolter 4")
    battle = _end_battle(crew_setup)

    # More spending after the battle: irrelevant, and must not show up as a
    # discrepancy.
    knife = make_equipment(name="Knife", cost=10, category="Close Combat")
    make_weapon_profile(knife)
    crew_setup["fighters"][0].assign(knife)
    crew.refresh_from_db()

    assert crew.rating_note() == {
        "selected": 100,
        "current": 135,
        "is_played": True,
        "differs": True,
    }

    client.force_login(crew_setup["user"])
    resp = client.get(reverse("core:crew", args=[battle.id, crew.id]))
    content = resp.content.decode()
    assert resp.context["show_rating_note"] is True
    assert "picked at 100¢" in content
    # What it fought at is the headline; the live figure (145¢ with the knife)
    # is not part of the story any more. Match the rendered figure rather than
    # the bare digits: the page is full of random UUIDs, and "145" turns up
    # inside one often enough to make a looser assertion flaky.
    assert "135¢" in content
    assert "145¢" not in content


@pytest.mark.django_db
def test_unchanged_crew_says_nothing(crew_setup):
    """A crew that hasn't moved between selection and play has no note — the
    number speaks for itself."""
    crew = _lock_one_fighter_crew(crew_setup)
    assert crew.rating_note()["differs"] is False

    _end_battle(crew_setup)
    crew.refresh_from_db()
    note = crew.rating_note()
    assert note["differs"] is False
    assert note["is_played"] is True
    assert crew.receipt()["note"]["differs"] is False


@pytest.mark.django_db
def test_draft_crew_has_no_note(crew_setup):
    """Nothing has been committed to yet, so there is nothing to compare."""
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        custom_count=2,
    )
    add_chosen(crew, crew_setup["fighters"][:2])

    assert crew.rating() == 200
    assert crew.rating_note() is None
    assert crew.receipt()["note"] is None


@pytest.mark.django_db
def test_only_locked_crews_are_frozen_when_the_battle_ends(crew_setup):
    """A crew that was never confirmed didn't field anything, so there is no
    fact to freeze — inventing one would claim a battle it never fought."""
    draft = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        custom_count=1,
    )
    add_chosen(draft, crew_setup["fighters"][:1])

    _end_battle(crew_setup)

    draft.refresh_from_db()
    assert draft.rating_played is None
    assert draft.rating() == 100


@pytest.mark.django_db
def test_crew_locked_before_snapshots_computes_live_and_says_nothing(crew_setup):
    """Crews locked before snapshotting shipped keep ``rating_selected`` NULL —
    inventing one now would be inventing a moment. They compute live, and have
    nothing to compare against, so they carry no note."""
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        status=Crew.LOCKED,
    )
    add_chosen(crew, crew_setup["fighters"][:2])

    assert crew.rating_selected is None
    assert crew.rating_played is None
    assert crew.rating() == 200
    assert crew.rating() == crew.live_rating()
    assert crew.rating_note() is None
    assert crew.receipt()["note"] is None


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


# --- Pre-lock loadout overrides (whole-gang crews) --------------------------
#
# A whole-gang crew has no members until the lock enrols the roster, so the
# equipment set each model will bring is recorded on the crew as advisory
# intent. Every read goes through Crew.resolve_loadout, which the forecast on
# the crew page and the enrolment at lock both use — so the two cannot
# disagree — and which falls back to the fighter's own kit whenever the stored
# entry no longer makes sense.


@pytest.fixture
def carded_fighter(make_list_fighter, make_equipment, make_weapon_profile):
    """Build a fighter with a weapon, some gear, and a set holding the weapon
    only. Unlike ``equipped_fighter`` this can be called several times in one
    test — each call makes its own equipment, so nothing collides on
    ``unique(name, category)``."""
    made = count()

    def build(gang):
        i = next(made)
        fighter = make_list_fighter(gang, f"Carrier {i}")
        gun = make_equipment(name=f"Crew Gun {i}", cost=30, category="Basic Weapons")
        make_weapon_profile(gun)
        gear = make_equipment(name=f"Crew Gear {i}", cost=20, category="Armour")
        a_gun = fighter.assign(gun)
        fighter.assign(gear)
        card = ListFighterEquipmentSet.objects.create(
            list_fighter=fighter, name=f"Kit {i}", owner=fighter.owner
        )
        card.assignments.set([a_gun])
        return fighter, card

    return build


def _loadout_crew(crew_setup, **kwargs):
    """A draft whole-gang crew: Custom Selection, no number, nobody chosen."""
    return Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        **kwargs,
    )


def _override(fighter, equipment_set):
    """The stored shape for one fighter (``None`` = explicitly Default)."""
    return {
        str(fighter.pk): {
            "equipment_set": str(equipment_set.pk) if equipment_set else None
        }
    }


def _loaded(fighter):
    """The fighter as the resolver sees it — sets read from the prefetch."""
    return ListFighter.objects.with_related_data().get(pk=fighter.pk)


@pytest.mark.django_db
def test_resolve_loadout_falls_back_to_the_fighters_own_set(
    crew_setup, equipped_fighter
):
    fighter, card = equipped_fighter(crew_setup["gang"])
    fighter.active_equipment_set = card
    fighter.save()
    crew = _loadout_crew(crew_setup)

    assert crew.resolve_loadout(_loaded(fighter)) == card


@pytest.mark.django_db
def test_resolve_loadout_override_wins(crew_setup, equipped_fighter):
    fighter, card = equipped_fighter(crew_setup["gang"])
    # The fighter's own card is Default; the override says otherwise.
    crew = _loadout_crew(crew_setup, loadout_overrides=_override(fighter, card))

    assert crew.resolve_loadout(_loaded(fighter)) == card


@pytest.mark.django_db
def test_resolve_loadout_stored_null_is_an_explicit_default(
    crew_setup, equipped_fighter
):
    """An explicit Default sticks even though the fighter's own card is a set —
    that is the point of a per-battle override."""
    fighter, card = equipped_fighter(crew_setup["gang"])
    fighter.active_equipment_set = card
    fighter.save()
    crew = _loadout_crew(crew_setup, loadout_overrides=_override(fighter, None))

    assert crew.resolve_loadout(_loaded(fighter)) is None


@pytest.mark.django_db
def test_resolve_loadout_falls_back_when_the_set_was_deleted(
    crew_setup, equipped_fighter
):
    fighter, card = equipped_fighter(crew_setup["gang"])
    other = ListFighterEquipmentSet.objects.create(
        list_fighter=fighter, name="Heavy kit", owner=fighter.owner
    )
    fighter.active_equipment_set = other
    fighter.save()
    crew = _loadout_crew(crew_setup, loadout_overrides=_override(fighter, card))
    card.delete()

    # No error: the intent can't be honoured, so the fighter's own kit stands.
    assert crew.resolve_loadout(_loaded(fighter)) == other


@pytest.mark.django_db
def test_resolve_loadout_rejects_another_fighters_set(crew_setup, equipped_fighter):
    """A stale or forged id pointing at someone else's card is not honoured."""
    gang = crew_setup["gang"]
    fighter, card = equipped_fighter(gang)
    intruder = crew_setup["fighters"][0]
    crew = _loadout_crew(crew_setup, loadout_overrides=_override(intruder, card))

    assert crew.resolve_loadout(_loaded(intruder)) is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "overrides",
    [
        None,
        [],
        "nonsense",
        {"not-a-uuid": {"equipment_set": "also-not-a-uuid"}},
        {"FIGHTER": "a bare string"},
        {"FIGHTER": []},
        {"FIGHTER": {"something_else": 1}},
        {"FIGHTER": {"equipment_set": "not-a-uuid"}},
        {"FIGHTER": {"equipment_set": 42}},
    ],
)
def test_resolve_loadout_tolerates_malformed_overrides(
    crew_setup, equipped_fighter, overrides
):
    """Whatever the JSON column holds, resolving must not raise: it falls back
    to the fighter's own kit."""
    fighter, card = equipped_fighter(crew_setup["gang"])
    fighter.active_equipment_set = card
    fighter.save()
    if isinstance(overrides, dict):
        overrides = {
            (str(fighter.pk) if k == "FIGHTER" else k): v for k, v in overrides.items()
        }
    crew = _loadout_crew(crew_setup)
    # Assigned rather than saved: the column is NOT NULL, so a None can only
    # arrive in memory — but the resolver must survive it either way.
    crew.loadout_overrides = overrides

    assert crew.resolve_loadout(_loaded(fighter)) == card


@pytest.mark.django_db
def test_ineligible_fighters_override_is_never_read(crew_setup, equipped_fighter):
    """An entry for someone who can no longer take part simply never comes up:
    they aren't in the eligible roster the forecast and the lock work from."""
    fighter, card = equipped_fighter(crew_setup["gang"])
    crew = _loadout_crew(crew_setup, loadout_overrides=_override(fighter, card))
    fighter.archived = True
    fighter.save()

    projection = crew_whole_gang_projection(crew)
    assert fighter.id not in [row["fighter_id"] for row in projection["rows"]]

    handle_crew_lock(user=crew_setup["user"], crew=crew)
    assert not crew.members.filter(list_fighter=fighter).exists()


@pytest.mark.django_db
def test_pruned_loadout_overrides_drops_stale_entries(crew_setup, carded_fighter):
    gang = crew_setup["gang"]
    keeper, keeper_card = carded_fighter(gang)
    defaulted = crew_setup["fighters"][0]
    gone, gone_card = carded_fighter(gang)

    crew = _loadout_crew(
        crew_setup,
        loadout_overrides={
            **_override(keeper, keeper_card),
            # Explicit Default: kept.
            **_override(defaulted, None),
            # Set deleted below: dropped.
            **_override(gone, gone_card),
            # A fighter who has left the roster: dropped.
            **_override(crew_setup["fighters"][1], None),
            # Junk: dropped.
            "not-a-fighter": {"equipment_set": None},
        },
    )
    gone_card.delete()
    crew_setup["fighters"][1].delete()

    roster = list(eligible_crew_fighters_for_loadouts(gang))
    pruned = crew.pruned_loadout_overrides(roster)

    assert pruned == {
        str(keeper.pk): {"equipment_set": str(keeper_card.pk)},
        str(defaulted.pk): {"equipment_set": None},
    }


@pytest.mark.django_db
def test_lock_prunes_the_overrides(crew_setup, equipped_fighter):
    fighter, card = equipped_fighter(crew_setup["gang"])
    crew = _loadout_crew(
        crew_setup,
        loadout_overrides={
            **_override(fighter, card),
            "not-a-fighter": {"equipment_set": None},
        },
    )

    handle_crew_lock(user=crew_setup["user"], crew=crew)

    crew.refresh_from_db()
    assert crew.loadout_overrides == {str(fighter.pk): {"equipment_set": str(card.pk)}}


@pytest.mark.django_db
def test_lock_enrols_exactly_what_the_forecast_showed(crew_setup, carded_fighter):
    """The forecast and the lock run the same resolver, so what the crew page
    promised is what the confirmed crew gets."""
    gang = crew_setup["gang"]
    overridden, overridden_card = carded_fighter(gang)
    own_kit, own_card = carded_fighter(gang)
    own_kit.active_equipment_set = own_card
    own_kit.save()
    explicit_default, explicit_card = carded_fighter(gang)
    explicit_default.active_equipment_set = explicit_card
    explicit_default.save()

    crew = _loadout_crew(
        crew_setup,
        loadout_overrides={
            **_override(overridden, overridden_card),
            **_override(explicit_default, None),
        },
    )

    forecast = {
        row["fighter_id"]: row["loadout"]
        for row in crew_whole_gang_projection(crew)["rows"]
    }
    assert forecast[overridden.id] == overridden_card.name
    assert forecast[own_kit.id] == own_card.name
    assert forecast[explicit_default.id] is None

    handle_crew_lock(user=crew_setup["user"], crew=crew)

    enrolled = {
        m.list_fighter_id: (m.equipment_set.name if m.equipment_set else None)
        for m in crew.members.select_related("equipment_set")
    }
    assert enrolled == forecast


@pytest.mark.django_db
def test_crew_page_forecasts_the_whole_gang(client, crew_setup, equipped_fighter):
    client.force_login(crew_setup["user"])
    battle = crew_setup["battle"]
    fighter, card = equipped_fighter(crew_setup["gang"])
    crew = _loadout_crew(crew_setup, loadout_overrides=_override(fighter, card))

    resp = client.get(reverse("core:crew", args=[battle.id, crew.id]))
    assert resp.status_code == 200
    projection = resp.context["projection"]
    content = resp.content.decode()

    # Every eligible fighter is forecast, with the resolved set and its cost.
    assert len(projection["rows"]) == 6  # five plain gangers plus the specialist
    assert projection["total"] == 5 * 100 + 145  # the light kit, not the 195 full kit
    assert resp.context["provisional_total"] == projection["total"]
    assert card.name in content
    assert "645¢" in content
    # Labelled as a forecast, not as the crew's rating.
    assert "Provisional" in content
    assert crew.rating() == 0
    # And the way to change it.
    assert reverse("core:crew-loadouts", args=[battle.id, crew.id]) in content


@pytest.mark.django_db
def test_crew_page_forecast_costs_no_per_fighter_query(
    client, crew_setup, equipped_fighter, make_list_fighter
):
    """The forecast reads sets and assignments from ``with_related_data()``'s
    prefetch: more fighters must not mean more queries."""
    gang = crew_setup["gang"]
    client.force_login(crew_setup["user"])
    crew = _loadout_crew(crew_setup)
    url = reverse("core:crew", args=[crew_setup["battle"].id, crew.id])

    def render_query_count():
        with CaptureQueriesContext(connection) as ctx:
            assert client.get(url).status_code == 200
        return len(ctx)

    equipped_fighter(gang)
    render_query_count()  # warm anything cached per process
    baseline = render_query_count()

    for i in range(2):
        extra = make_list_fighter(gang, f"Carrier {i}")
        ListFighterEquipmentSet.objects.create(
            list_fighter=extra, name=f"Kit {i}", owner=extra.owner
        )
    assert render_query_count() == baseline


@pytest.mark.django_db
def test_draft_crews_note_costs_no_queries(crew_setup):
    """A draft has nothing to compare against, so asking for its note must
    answer ``None`` outright.

    Computing the live rating first would batch-load every attendee and then
    throw the answer away — and the battle page asks each crew for its note, so
    that load would be paid per draft crew on the page.
    """
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        selection_method=Crew.CUSTOM,
        custom_count=3,
    )
    # Members are what make the wasted load expensive; an empty crew would be
    # cheap either way and this guard would pass without proving anything.
    for fighter in crew_setup["fighters"][:3]:
        CrewMember.objects.create(
            crew=crew,
            list_fighter=fighter,
            owner=crew_setup["user"],
            source=CrewMember.CHOSEN,
        )
    assert crew.rating_selected is None

    with CaptureQueriesContext(connection) as ctx:
        assert crew.rating_note() is None
    assert len(ctx) == 0


@pytest.mark.django_db
def test_played_crews_note_costs_no_queries(crew_setup):
    """A crew whose battle is over compares its own two snapshots, so it must
    not batch-load the roster to answer either — the same guard the draft case
    has, extended to the state the battle page will mostly be showing."""
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        status=Crew.LOCKED,
        rating_selected=300,
        rating_played=320,
    )
    for fighter in crew_setup["fighters"][:3]:
        CrewMember.objects.create(
            crew=crew,
            list_fighter=fighter,
            owner=crew_setup["user"],
            source=CrewMember.CHOSEN,
            rating_selected=100,
            rating_played=100,
        )

    with CaptureQueriesContext(connection) as ctx:
        note = crew.rating_note()
    assert note == {
        "selected": 300,
        "current": 320,
        "is_played": True,
        "differs": True,
    }
    assert len(ctx) == 0


@pytest.mark.django_db
def test_loadouts_page_prefills_from_the_resolver(client, crew_setup, equipped_fighter):
    client.force_login(crew_setup["user"])
    battle = crew_setup["battle"]
    fighter, card = equipped_fighter(crew_setup["gang"])
    crew = _loadout_crew(crew_setup, loadout_overrides=_override(fighter, card))

    resp = client.get(reverse("core:crew-loadouts", args=[battle.id, crew.id]))
    assert resp.status_code == 200
    content = resp.content.decode()
    # The stored choice is selected; fighters with no sets have no select.
    assert f'value="{card.id}" selected' in content
    assert f'name="{equipment_set_field_name(fighter.id)}"' in content
    for plain in crew_setup["fighters"]:
        assert f'name="{equipment_set_field_name(plain.id)}"' not in content


@pytest.mark.django_db
def test_loadouts_page_saves_choices(client, crew_setup, equipped_fighter):
    client.force_login(crew_setup["user"])
    battle = crew_setup["battle"]
    fighter, card = equipped_fighter(crew_setup["gang"])
    crew = _loadout_crew(crew_setup)
    url = reverse("core:crew-loadouts", args=[battle.id, crew.id])

    resp = client.post(url, {equipment_set_field_name(fighter.id): str(card.id)})
    assert resp.status_code == 302
    crew.refresh_from_db()
    assert crew.loadout_overrides == {str(fighter.id): {"equipment_set": str(card.id)}}

    # Choosing Default is recorded as an explicit choice, not as "no answer":
    # it must survive the fighter's own card changing afterwards.
    resp = client.post(url, {equipment_set_field_name(fighter.id): ""})
    assert resp.status_code == 302
    crew.refresh_from_db()
    assert crew.loadout_overrides == {str(fighter.id): {"equipment_set": None}}
    fighter.active_equipment_set = card
    fighter.save()
    assert crew.resolve_loadout(_loaded(fighter)) is None


@pytest.mark.django_db
def test_loadouts_page_rejects_another_fighters_set(client, crew_setup, carded_fighter):
    client.force_login(crew_setup["user"])
    battle = crew_setup["battle"]
    fighter, card = carded_fighter(crew_setup["gang"])
    other, other_card = carded_fighter(crew_setup["gang"])
    crew = _loadout_crew(crew_setup)

    resp = client.post(
        reverse("core:crew-loadouts", args=[battle.id, crew.id]),
        {equipment_set_field_name(fighter.id): str(other_card.id)},
    )
    # The field's queryset is the fighter's own sets, so this can't validate.
    assert resp.status_code == 200
    crew.refresh_from_db()
    assert crew.loadout_overrides == {}


@pytest.mark.django_db
def test_loadouts_page_refused_when_locked(client, crew_setup, equipped_fighter):
    client.force_login(crew_setup["user"])
    battle = crew_setup["battle"]
    fighter, card = equipped_fighter(crew_setup["gang"])
    crew = _loadout_crew(crew_setup, status=Crew.LOCKED)

    url = reverse("core:crew-loadouts", args=[battle.id, crew.id])
    assert client.get(url).status_code == 302
    resp = client.post(url, {equipment_set_field_name(fighter.id): str(card.id)})
    assert resp.status_code == 302
    crew.refresh_from_db()
    assert crew.loadout_overrides == {}


@pytest.mark.django_db
def test_loadouts_page_refused_for_non_manager(
    client, crew_setup, equipped_fighter, make_user
):
    stranger = make_user("interloper", "pw")
    client.force_login(stranger)
    battle = crew_setup["battle"]
    fighter, card = equipped_fighter(crew_setup["gang"])
    crew = _loadout_crew(crew_setup)

    url = reverse("core:crew-loadouts", args=[battle.id, crew.id])
    assert client.get(url).status_code == 302
    assert (
        client.post(
            url, {equipment_set_field_name(fighter.id): str(card.id)}
        ).status_code
        == 302
    )
    crew.refresh_from_db()
    assert crew.loadout_overrides == {}


@pytest.mark.django_db
def test_loadouts_page_sends_chosen_crews_to_the_recipe(client, crew_setup):
    """Chosen fighters pick their card on the crew form itself, and drawn ones
    get theirs at random — so only whole-gang crews need this screen."""
    client.force_login(crew_setup["user"])
    battle = crew_setup["battle"]
    crew = _loadout_crew(crew_setup, custom_count=1)
    add_chosen(crew, crew_setup["fighters"][:1])

    resp = client.get(reverse("core:crew-loadouts", args=[battle.id, crew.id]))
    assert resp.status_code == 302
    assert resp.url == reverse("core:crew", args=[battle.id, crew.id])


@pytest.mark.django_db
def test_pending_roll_needs_a_spec_that_actually_draws(crew_setup):
    """Random/Hybrid with a blank spec draws nobody, so it must not advertise an
    unknown rating. The form requires a spec; the column allows a blank."""
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        selection_method=Crew.RANDOM,
        random_spec="",
    )
    assert crew.pending_roll is False

    crew.random_spec = "D3"
    assert crew.pending_roll is True


# --- Saving loadouts keeps choices the form couldn't offer -------------------
#
# The form only lists currently *eligible* fighters, so rebuilding the stored
# map from its answers would quietly delete the choice made for anyone who
# happens to be in recovery on the day someone re-saves the page.


@pytest.mark.django_db
def test_saving_loadouts_keeps_a_recovering_fighters_choice(crew_setup, carded_fighter):
    """A fighter in recovery isn't offered by the form, but may well be back by
    battle start — their choice is a decision the player made and must survive
    a re-save."""
    gang = crew_setup["gang"]
    recovering, recovering_card = carded_fighter(gang)
    other, other_card = carded_fighter(gang)
    crew = _loadout_crew(
        crew_setup, loadout_overrides=_override(recovering, recovering_card)
    )

    recovering.injury_state = ListFighter.RECOVERY
    recovering.save()
    offered = list(eligible_crew_fighters_for_loadouts(gang))
    assert recovering.id not in [f.id for f in offered]

    handle_crew_loadouts_save(
        user=crew_setup["user"], crew=crew, choices={other.pk: other_card}
    )

    crew.refresh_from_db()
    assert crew.loadout_overrides == {
        str(recovering.pk): {"equipment_set": str(recovering_card.pk)},
        str(other.pk): {"equipment_set": str(other_card.pk)},
    }

    # And when they recover before the lock, they turn up on the chosen kit.
    recovering.injury_state = ListFighter.ACTIVE
    recovering.save()
    handle_crew_lock(user=crew_setup["user"], crew=crew)
    member = crew.members.get(list_fighter=recovering)
    assert member.equipment_set_id == recovering_card.id


@pytest.mark.django_db
def test_saving_loadouts_prunes_entries_that_no_longer_mean_anything(
    crew_setup, carded_fighter
):
    """Merging is not hoarding: an entry whose set has gone, or whose fighter
    has left the gang, is dropped."""
    gang = crew_setup["gang"]
    gone_set, gone_card = carded_fighter(gang)
    departed, departed_card = carded_fighter(gang)
    keeper, keeper_card = carded_fighter(gang)

    crew = _loadout_crew(
        crew_setup,
        loadout_overrides={
            **_override(gone_set, gone_card),
            **_override(departed, departed_card),
            **_override(keeper, keeper_card),
            "not-a-fighter": {"equipment_set": None},
        },
    )
    gone_card.delete()
    departed.delete()

    handle_crew_loadouts_save(user=crew_setup["user"], crew=crew, choices={})

    crew.refresh_from_db()
    assert crew.loadout_overrides == {
        str(keeper.pk): {"equipment_set": str(keeper_card.pk)}
    }


@pytest.mark.django_db
def test_saving_loadouts_overwrites_the_fighters_the_form_did_offer(
    crew_setup, carded_fighter
):
    """Merging must not make a choice sticky: an eligible fighter's answer
    replaces whatever was stored, including a switch back to Default."""
    gang = crew_setup["gang"]
    fighter, card = carded_fighter(gang)
    crew = _loadout_crew(crew_setup, loadout_overrides=_override(fighter, card))

    handle_crew_loadouts_save(
        user=crew_setup["user"], crew=crew, choices={fighter.pk: None}
    )

    crew.refresh_from_db()
    assert crew.loadout_overrides == {str(fighter.pk): {"equipment_set": None}}
