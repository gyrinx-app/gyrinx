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
    CREW_ALWAYS_INCLUDED,
    CREW_ELIGIBLE,
    CREW_NOT_ELIGIBLE,
    always_included_crew_fighters,
    crew_battle_spread,
    crew_eligibility,
    crew_spread_rating,
    crew_whole_gang_projection,
    eligible_crew_fighters,
    eligible_crew_fighters_for_loadouts,
    handle_crew_archive,
    handle_crew_lock,
    handle_crew_loadouts_save,
    handle_crew_recipe_save,
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
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
    ListFighterEquipmentSet,
)
from gyrinx.models import FighterCategoryChoices


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


# --- Vehicles and exotic beasts (linked child fighters) ---------------------
#
# A vehicle or exotic beast is bought as wargear and deploys alongside the
# fighter that owns it (rulebook p86). It is never selected in its own right,
# but it must still join the crew when its owner does — enrolled by
# handlers.crew.sync_linked_crew_members.


def _give_beast(
    crew_setup,
    owner,
    make_content_fighter,
    make_equipment,
    make_list_fighter,
    name="War Hound",
    beast_gear_cost=0,
):
    """Give ``owner`` a linked exotic beast (a child fighter), bought as 90¢ of
    wargear. Optionally arm the beast with its own ``beast_gear_cost``¢ of gear
    so it has a non-zero rating of its own."""
    beast_type = make_content_fighter(
        type=name,
        category=FighterCategoryChoices.EXOTIC_BEAST,
        house=owner.content_fighter.house,
        base_cost=0,
    )
    beast = make_list_fighter(crew_setup["gang"], name, content_fighter=beast_type)
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=owner,
        content_equipment=make_equipment(name=f"{name} (wargear)", cost=90),
        child_fighter=beast,
    )
    if beast_gear_cost:
        beast.assign(make_equipment(name=f"{name} claws", cost=beast_gear_cost))
    return beast


def _beast_line(crew, beast):
    return next(
        (line for _, line in crew._attendee_lines() if line["fighter_id"] == beast.id),
        None,
    )


@pytest.mark.django_db
def test_exotic_beast_is_not_selectable(
    crew_setup, make_content_fighter, make_equipment, make_list_fighter
):
    """A beast is wargear on its owner, so it never appears in the eligible pool
    — which is both the selection checkboxes and the random-draw pool."""
    owner = crew_setup["fighters"][0]
    beast = _give_beast(
        crew_setup, owner, make_content_fighter, make_equipment, make_list_fighter
    )
    assert beast.is_child_fighter is True

    eligible = set(eligible_crew_fighters(crew_setup["gang"]))
    assert owner in eligible
    assert beast not in eligible

    # Absent from the selection form's fighter checkboxes too.
    form = CrewForm(gang=crew_setup["gang"], method=Crew.CUSTOM)
    offered = {f.pk for f in form.fields["chosen_fighters"].queryset}
    assert beast.id not in offered
    assert owner.id in offered


@pytest.mark.django_db
def test_selecting_an_owner_brings_in_their_beast(
    crew_setup, make_content_fighter, make_equipment, make_list_fighter
):
    """Choosing the owner enrols its beast as a LINKED member, so the beast
    counts towards the rating and prints — without being chosen."""
    owner = crew_setup["fighters"][0]
    beast = _give_beast(
        crew_setup,
        owner,
        make_content_fighter,
        make_equipment,
        make_list_fighter,
        beast_gear_cost=30,
    )
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        custom_count=1,
    )
    handle_crew_recipe_save(
        user=crew_setup["user"],
        crew=crew,
        method=Crew.CUSTOM,
        custom_count=1,
        chosen_fighters=[owner],
    )

    assert list(
        crew.members.filter(source=CrewMember.LINKED).values_list(
            "list_fighter_id", flat=True
        )
    ) == [beast.id]
    assert crew.members.filter(source=CrewMember.CHOSEN, list_fighter=owner).exists()

    # The beast rides in with its own 30¢ of gear counted, and prints.
    line = _beast_line(crew, beast)
    assert line is not None
    assert line["is_random"] is False
    assert line["live_rating"] == 30
    assert beast.id in crew.print_fighter_ids()


@pytest.mark.django_db
def test_whole_gang_lock_enrols_owned_beasts(
    crew_setup, make_content_fighter, make_equipment, make_list_fighter
):
    """The whole-gang draw enrols every eligible fighter; their beasts come with
    them as linked members, but don't count towards the 'chosen' tally."""
    owner = crew_setup["fighters"][0]
    beast = _give_beast(
        crew_setup, owner, make_content_fighter, make_equipment, make_list_fighter
    )
    crew = Crew.objects.create(
        battle=crew_setup["battle"], list=crew_setup["gang"], owner=crew_setup["user"]
    )

    result = handle_crew_lock(user=crew_setup["user"], crew=crew)

    assert result.whole_gang is True
    assert result.chosen_count == 5  # the beast is extra, not a chosen fighter
    assert crew.members.filter(source=CrewMember.LINKED, list_fighter=beast).exists()
    assert crew.members.filter(source=CrewMember.LINKED).count() == 1
    assert beast.id in crew.print_fighter_ids()


@pytest.mark.django_db
def test_removing_the_owner_drops_the_beast(
    crew_setup, make_content_fighter, make_equipment, make_list_fighter
):
    """The beast follows its owner: cut the owner from the recipe and its beast
    leaves the crew too."""
    owner, other = crew_setup["fighters"][0], crew_setup["fighters"][1]
    beast = _give_beast(
        crew_setup, owner, make_content_fighter, make_equipment, make_list_fighter
    )
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        custom_count=2,
    )

    handle_crew_recipe_save(
        user=crew_setup["user"],
        crew=crew,
        method=Crew.CUSTOM,
        custom_count=2,
        chosen_fighters=[owner, other],
    )
    assert crew.members.filter(source=CrewMember.LINKED, list_fighter=beast).exists()

    handle_crew_recipe_save(
        user=crew_setup["user"],
        crew=crew,
        method=Crew.CUSTOM,
        custom_count=1,
        chosen_fighters=[other],
    )
    assert not crew.members.filter(list_fighter=beast).exists()
    assert not crew.members.filter(list_fighter=owner).exists()


@pytest.mark.django_db
def test_whole_gang_forecast_includes_beasts(
    crew_setup, make_content_fighter, make_equipment, make_list_fighter
):
    """The pre-lock whole-gang forecast counts owned beasts, so it matches what
    the lock will actually enrol."""
    owner = crew_setup["fighters"][0]
    _give_beast(
        crew_setup,
        owner,
        make_content_fighter,
        make_equipment,
        make_list_fighter,
        beast_gear_cost=40,
    )
    crew = Crew.objects.create(
        battle=crew_setup["battle"], list=crew_setup["gang"], owner=crew_setup["user"]
    )

    projection = crew_whole_gang_projection(crew)
    # Five gangers plus the one beast row.
    assert len(projection["rows"]) == 6
    beast_rows = [r for r in projection["rows"] if r["rating"] == 40]
    assert len(beast_rows) == 1


# --- Category eligibility (hangers-on, vehicle crew) ------------------------
#
# Hangers-on don't normally take part in a battle and vehicle crew are an
# Ash-Wastes thing, so both are excluded from selection by default. A crew opts
# a category back in per-crew (the player's choice). Brutes are NOT special —
# they field like any other fighter. The check is on the effective category, so
# a promotion's category_override wins.


def _fighter_of_category(
    crew_setup, make_content_fighter, make_list_fighter, category, name, base_cost=50
):
    """A standalone gang fighter of a given category."""
    cf = make_content_fighter(
        type=name,
        category=category,
        house=crew_setup["fighters"][0].content_fighter.house,
        base_cost=base_cost,
    )
    return make_list_fighter(crew_setup["gang"], name, content_fighter=cf)


def _give_vehicle(
    crew_setup,
    owner,
    make_content_fighter,
    make_equipment,
    make_list_fighter,
    name="Rig",
):
    """Give ``owner`` (a Crew fighter) a linked VEHICLE child."""
    vtype = make_content_fighter(
        type=name,
        category=FighterCategoryChoices.VEHICLE,
        house=owner.content_fighter.house,
        base_cost=0,
    )
    vehicle = make_list_fighter(crew_setup["gang"], name, content_fighter=vtype)
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=owner,
        content_equipment=make_equipment(name=f"{name} (vehicle)", cost=200),
        child_fighter=vehicle,
    )
    return vehicle


@pytest.mark.django_db
def test_eligible_crew_fighters_excludes_hangers_on_and_crew_by_default(
    crew_setup, make_content_fighter, make_list_fighter
):
    hanger = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HANGER_ON,
        "Rogue Doc",
    )
    driver = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.CREW,
        "Driver",
    )
    brute = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.BRUTE,
        "Ogryn",
    )

    eligible = set(eligible_crew_fighters(crew_setup["gang"]))
    assert hanger not in eligible
    assert driver not in eligible
    assert brute in eligible  # brutes field like anyone else
    assert crew_setup["fighters"][0] in eligible  # a normal ganger


@pytest.mark.django_db
def test_eligible_crew_fighters_opt_in_by_category(
    crew_setup, make_content_fighter, make_list_fighter
):
    hanger = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HANGER_ON,
        "Rogue Doc",
    )
    driver = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.CREW,
        "Driver",
    )
    gang = crew_setup["gang"]

    only_hangers = set(eligible_crew_fighters(gang, included=["HANGER_ON"]))
    assert hanger in only_hangers
    assert driver not in only_hangers  # opted hangers-on in, not crew

    both = set(eligible_crew_fighters(gang, included=["HANGER_ON", "CREW"]))
    assert hanger in both
    assert driver in both


@pytest.mark.django_db
def test_eligible_crew_fighters_uses_effective_category(
    crew_setup, make_content_fighter, make_list_fighter
):
    """The check is on the effective category. A valid category_override wins
    over the content fighter's category; an empty override counts as none."""
    # A content-Hanger-on relabelled to Ganger (a valid override) fields
    # normally — the override wins.
    promoted = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HANGER_ON,
        "Promoted",
    )
    promoted.category_override = FighterCategoryChoices.GANGER
    promoted.save()
    # An empty override is "no override", so the content category (hanger-on)
    # still excludes it.
    empty = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HANGER_ON,
        "Empty Override",
    )
    empty.category_override = ""
    empty.save()

    eligible = set(eligible_crew_fighters(crew_setup["gang"]))
    assert promoted in eligible
    assert empty not in eligible


@pytest.mark.django_db
def test_whole_gang_lock_excludes_hangers_on(
    crew_setup, make_content_fighter, make_list_fighter
):
    """A whole-gang crew enrols the fieldable roster; a hanger-on stays out and
    isn't counted."""
    _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HANGER_ON,
        "Rogue Doc",
    )
    crew = Crew.objects.create(
        battle=crew_setup["battle"], list=crew_setup["gang"], owner=crew_setup["user"]
    )

    result = handle_crew_lock(user=crew_setup["user"], crew=crew)

    assert result.chosen_count == 5  # the five gangers, not the hanger-on
    categories = {m.list_fighter.content_fighter.category for m in crew.members.all()}
    assert FighterCategoryChoices.HANGER_ON not in categories


@pytest.mark.django_db
def test_whole_gang_lock_includes_opted_in_hangers_on(
    crew_setup, make_content_fighter, make_list_fighter
):
    """A whole-gang crew that opts hangers-on in sweeps them up too."""
    hanger = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HANGER_ON,
        "Rogue Doc",
    )
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        included_categories=["HANGER_ON"],
    )

    result = handle_crew_lock(user=crew_setup["user"], crew=crew)

    assert result.chosen_count == 6  # five gangers + the hanger-on
    assert crew.members.filter(list_fighter=hanger).exists()


@pytest.mark.django_db
def test_included_crew_category_brings_in_the_vehicle_child(
    crew_setup, make_content_fighter, make_equipment, make_list_fighter
):
    """Ash-Wastes payoff: opt CREW in, pick the crew fighter, and its vehicle
    (a child) deploys with it via the linked-member enrolment."""
    driver = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.CREW,
        "Driver",
    )
    vehicle = _give_vehicle(
        crew_setup, driver, make_content_fighter, make_equipment, make_list_fighter
    )

    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        custom_count=1,
        included_categories=["CREW"],
    )
    handle_crew_recipe_save(
        user=crew_setup["user"],
        crew=crew,
        method=Crew.CUSTOM,
        custom_count=1,
        chosen_fighters=[driver],
    )

    assert crew.members.filter(source=CrewMember.CHOSEN, list_fighter=driver).exists()
    assert crew.members.filter(source=CrewMember.LINKED, list_fighter=vehicle).exists()


# --- Always-included fighters (hired guns, bounty hunters, …) ----------------
#
# "You Get What You Pay For": hired guns aren't counted during the choose step —
# they join the crew regardless of the selection method. So they're kept out of
# the pick/draw pool and auto-enrolled on top as INCLUDED members.


@pytest.mark.django_db
def test_hired_guns_are_excluded_from_the_pool_but_flagged_always_included(
    crew_setup, make_content_fighter, make_list_fighter
):
    hired = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HIRED_GUN,
        "Merc",
    )
    bounty = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.BOUNTY_HUNTER,
        "Kal Jerico",
    )

    eligible = set(eligible_crew_fighters(crew_setup["gang"]))
    always = set(always_included_crew_fighters(crew_setup["gang"]))
    # Never in the pick/draw pool...
    assert hired not in eligible
    assert bounty not in eligible
    assert crew_setup["fighters"][0] in eligible  # a normal ganger still is
    # ...but they are the always-included set.
    assert always == {hired, bounty}


@pytest.mark.django_db
def test_locking_enrols_always_included_fighters(
    crew_setup, make_content_fighter, make_list_fighter
):
    """A hired gun joins the crew regardless of the pick, and doesn't count as a
    chosen fighter."""
    hired = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HIRED_GUN,
        "Merc",
    )
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        custom_count=1,
    )
    add_chosen(crew, crew_setup["fighters"][:1])

    result = handle_crew_lock(user=crew_setup["user"], crew=crew)

    assert crew.members.filter(source=CrewMember.INCLUDED, list_fighter=hired).exists()
    assert result.chosen_count == 1  # the ganger, not the hired gun


@pytest.mark.django_db
def test_random_draw_never_picks_a_hired_gun(
    crew_setup, make_content_fighter, make_list_fighter
):
    """The random pool excludes hired guns, so a draw can't land on one — but it
    still joins the crew as always-included."""
    hired = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HIRED_GUN,
        "Merc",
    )
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        selection_method=Crew.RANDOM,
        random_spec="6",  # more than the 5 gangers, to drain the pool
    )

    handle_crew_lock(user=crew_setup["user"], crew=crew, rng=Random(0))

    # The hired gun was never drawn (it's not in the pool)...
    assert not crew.members.filter(source=CrewMember.DRAWN, list_fighter=hired).exists()
    # ...but it is on the crew as always-included; only the 5 gangers were drawn.
    assert crew.members.filter(source=CrewMember.INCLUDED, list_fighter=hired).exists()
    assert crew.members.filter(source=CrewMember.DRAWN).count() == 5


@pytest.mark.django_db
def test_whole_gang_forecast_includes_hired_guns(
    crew_setup, make_content_fighter, make_list_fighter
):
    _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HIRED_GUN,
        "Merc",
        base_cost=120,
    )
    crew = Crew.objects.create(
        battle=crew_setup["battle"], list=crew_setup["gang"], owner=crew_setup["user"]
    )

    projection = crew_whole_gang_projection(crew)
    # Five gangers plus the one hired gun.
    assert len(projection["rows"]) == 6
    assert any(r["rating"] == 120 for r in projection["rows"])


# --- Eligibility screen (per-fighter defaults + overrides) ------------------
#
# The eligibility step computes a default state per fighter (eligible /
# always-included / not-eligible) from its category and condition, which the
# screen then lets the player override per fighter.


@pytest.mark.django_db
def test_crew_eligibility_defaults_by_category(
    crew_setup, make_content_fighter, make_list_fighter
):
    hired = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HIRED_GUN,
        "Merc",
    )
    hanger = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HANGER_ON,
        "Rogue Doc",
    )
    crew = Crew.objects.create(
        battle=crew_setup["battle"], list=crew_setup["gang"], owner=crew_setup["user"]
    )

    states = {row["fighter"].id: row["effective"] for row in crew_eligibility(crew)}
    assert states[crew_setup["fighters"][0].id] == CREW_ELIGIBLE  # a normal ganger
    assert states[hired.id] == CREW_ALWAYS_INCLUDED
    assert states[hanger.id] == CREW_NOT_ELIGIBLE


@pytest.mark.django_db
def test_crew_eligibility_marks_injured_fighters_not_eligible(crew_setup):
    hurt = crew_setup["fighters"][0]
    hurt.injury_state = ListFighter.RECOVERY
    hurt.save()
    crew = Crew.objects.create(
        battle=crew_setup["battle"], list=crew_setup["gang"], owner=crew_setup["user"]
    )

    states = {row["fighter"].id: row["effective"] for row in crew_eligibility(crew)}
    assert states[hurt.id] == CREW_NOT_ELIGIBLE
    assert states[crew_setup["fighters"][1].id] == CREW_ELIGIBLE


@pytest.mark.django_db
def test_crew_eligibility_included_category_seeds_eligible(
    crew_setup, make_content_fighter, make_list_fighter
):
    """A hanger-on's category, opted in on the crew, flips its default to eligible."""
    hanger = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HANGER_ON,
        "Rogue Doc",
    )
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        included_categories=[FighterCategoryChoices.HANGER_ON.value],
    )

    states = {row["fighter"].id: row["effective"] for row in crew_eligibility(crew)}
    assert states[hanger.id] == CREW_ELIGIBLE


@pytest.mark.django_db
def test_crew_eligibility_override_supersedes_default(
    crew_setup, make_content_fighter, make_list_fighter
):
    """A per-fighter override on the crew wins over the category default, and the
    row still reports the underlying default."""
    hired = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HIRED_GUN,
        "Merc",
    )
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        eligibility_overrides={str(hired.id): CREW_NOT_ELIGIBLE},
    )

    row = next(r for r in crew_eligibility(crew) if r["fighter"].id == hired.id)
    assert row["default"] == CREW_ALWAYS_INCLUDED  # unchanged underlying default
    assert row["effective"] == CREW_NOT_ELIGIBLE  # the override wins


@pytest.mark.django_db
def test_crew_eligibility_excludes_child_fighters(
    crew_setup, make_content_fighter, make_equipment, make_list_fighter
):
    """Vehicles and beasts that ride in as equipment aren't independently
    selectable, so they don't get an eligibility row."""
    vehicle = _give_vehicle(
        crew_setup,
        crew_setup["fighters"][0],
        make_content_fighter,
        make_equipment,
        make_list_fighter,
    )
    crew = Crew.objects.create(
        battle=crew_setup["battle"], list=crew_setup["gang"], owner=crew_setup["user"]
    )

    ids = {row["fighter"].id for row in crew_eligibility(crew)}
    assert vehicle.id not in ids
    assert crew_setup["fighters"][0].id in ids  # its owner is still selectable


@pytest.mark.django_db
def test_override_drops_a_ganger_from_the_pool(crew_setup):
    """An 'excluded' override removes an otherwise-eligible fighter from the
    pick/draw pool."""
    dropped = crew_setup["fighters"][0]
    overrides = {str(dropped.id): CREW_NOT_ELIGIBLE}

    pool = set(eligible_crew_fighters(crew_setup["gang"], overrides=overrides))
    assert dropped not in pool
    assert crew_setup["fighters"][1] in pool  # an un-overridden ganger stays


@pytest.mark.django_db
def test_override_promotes_a_hanger_into_always_included(
    crew_setup, make_content_fighter, make_list_fighter
):
    """An 'included' override on a hanger-on (excluded by default) makes it join
    the crew on top, out of the pool."""
    hanger = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HANGER_ON,
        "Rogue Doc",
    )
    overrides = {str(hanger.id): CREW_ALWAYS_INCLUDED}

    pool = set(eligible_crew_fighters(crew_setup["gang"], overrides=overrides))
    always = set(always_included_crew_fighters(crew_setup["gang"], overrides=overrides))
    assert hanger not in pool
    assert hanger in always


@pytest.mark.django_db
def test_override_lets_a_hired_gun_into_the_pool(
    crew_setup, make_content_fighter, make_list_fighter
):
    """An 'eligible' override on a hired gun (always-included by default) moves it
    into the pick/draw pool and out of the always-included set."""
    hired = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HIRED_GUN,
        "Merc",
    )
    overrides = {str(hired.id): CREW_ELIGIBLE}

    pool = set(eligible_crew_fighters(crew_setup["gang"], overrides=overrides))
    always = set(always_included_crew_fighters(crew_setup["gang"], overrides=overrides))
    assert hired in pool
    assert hired not in always


@pytest.mark.django_db
def test_captured_fighter_is_not_in_the_pool(crew_setup, make_list):
    """A captured fighter can't take part, so it's out of the pool even though its
    injury_state is still active."""
    from gyrinx.core.models.list import CapturedFighter

    captured = crew_setup["fighters"][0]
    rivals = make_list(
        "Rivals", status=List.CAMPAIGN_MODE, campaign=crew_setup["campaign"]
    )
    CapturedFighter.objects.create(fighter=captured, capturing_list=rivals)

    assert ListFighter.objects.get(pk=captured.pk).is_captured
    pool = set(eligible_crew_fighters(crew_setup["gang"]))
    assert captured not in pool


# --- Eligibility screen (view + form) ---------------------------------------


def _eligibility_post_data(crew, changes=None):
    """POST payload for the eligibility form: every fighter at its current
    effective state, with ``changes`` (fighter_id -> state) applied on top."""
    changes = changes or {}
    data = {}
    for row in crew_eligibility(crew):
        fid = row["fighter"].id
        data[f"elig_{fid}"] = changes.get(fid, row["effective"])
    return data


@pytest.mark.django_db
def test_eligibility_screen_renders(client, crew_setup):
    crew = Crew.objects.create(
        battle=crew_setup["battle"], list=crew_setup["gang"], owner=crew_setup["user"]
    )
    client.force_login(crew_setup["user"])

    resp = client.get(reverse("core:crew-eligibility", args=[crew.battle_id, crew.id]))

    assert resp.status_code == 200
    # A row per selectable fighter (the five gangers), all at their default.
    rows = resp.context["form"].fighter_rows()
    assert len(rows) == 5
    assert all(r["effective"] == CREW_ELIGIBLE for r in rows)


@pytest.mark.django_db
def test_eligibility_screen_stores_only_changed_fighters(client, crew_setup):
    crew = Crew.objects.create(
        battle=crew_setup["battle"], list=crew_setup["gang"], owner=crew_setup["user"]
    )
    excluded = crew_setup["fighters"][0]
    client.force_login(crew_setup["user"])

    resp = client.post(
        reverse("core:crew-eligibility", args=[crew.battle_id, crew.id]),
        _eligibility_post_data(crew, {excluded.id: CREW_NOT_ELIGIBLE}),
    )

    assert resp.status_code == 302
    crew.refresh_from_db()
    # Only the fighter moved off their default is stored.
    assert crew.eligibility_overrides == {str(excluded.id): CREW_NOT_ELIGIBLE}


@pytest.mark.django_db
def test_eligibility_screen_stores_nothing_when_all_default(client, crew_setup):
    crew = Crew.objects.create(
        battle=crew_setup["battle"], list=crew_setup["gang"], owner=crew_setup["user"]
    )
    client.force_login(crew_setup["user"])

    client.post(
        reverse("core:crew-eligibility", args=[crew.battle_id, crew.id]),
        _eligibility_post_data(crew),
    )

    crew.refresh_from_db()
    assert crew.eligibility_overrides == {}


@pytest.mark.django_db
def test_eligibility_screen_change_drops_fighter_from_the_pool(client, crew_setup):
    """Excluding a fighter on the screen removes them from the selection pool."""
    crew = Crew.objects.create(
        battle=crew_setup["battle"], list=crew_setup["gang"], owner=crew_setup["user"]
    )
    excluded = crew_setup["fighters"][0]
    client.force_login(crew_setup["user"])

    client.post(
        reverse("core:crew-eligibility", args=[crew.battle_id, crew.id]),
        _eligibility_post_data(crew, {excluded.id: CREW_NOT_ELIGIBLE}),
    )

    crew.refresh_from_db()
    pool = set(eligible_crew_fighters(crew.list, overrides=crew.eligibility_overrides))
    assert excluded not in pool


@pytest.mark.django_db
def test_eligibility_screen_blocked_on_locked_crew(client, crew_setup):
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        status=Crew.LOCKED,
    )
    data = _eligibility_post_data(
        crew, {crew_setup["fighters"][0].id: CREW_NOT_ELIGIBLE}
    )
    client.force_login(crew_setup["user"])

    resp = client.post(
        reverse("core:crew-eligibility", args=[crew.battle_id, crew.id]), data
    )

    assert resp.status_code == 302
    crew.refresh_from_db()
    assert crew.eligibility_overrides == {}  # locked: no change


@pytest.mark.django_db
def test_eligibility_screen_requires_manage_permission(client, crew_setup, make_user):
    crew = Crew.objects.create(
        battle=crew_setup["battle"], list=crew_setup["gang"], owner=crew_setup["user"]
    )
    stranger = make_user("stranger", "pw")
    client.force_login(stranger)

    resp = client.get(reverse("core:crew-eligibility", args=[crew.battle_id, crew.id]))

    assert resp.status_code == 302  # redirected, not shown


@pytest.mark.django_db
def test_eligibility_form_diffs_hired_gun_override(
    crew_setup, make_content_fighter, make_list_fighter
):
    """The form stores only the changed fighter: a hired gun moved to eligible."""
    from gyrinx.core.forms.crew import CrewEligibilityForm

    hired = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HIRED_GUN,
        "Merc",
    )
    crew = Crew.objects.create(
        battle=crew_setup["battle"], list=crew_setup["gang"], owner=crew_setup["user"]
    )
    data = _eligibility_post_data(crew, {hired.id: CREW_ELIGIBLE})

    form = CrewEligibilityForm(data, crew=crew)
    assert form.is_valid(), form.errors
    form.save()

    assert crew.eligibility_overrides == {str(hired.id): CREW_ELIGIBLE}


# --- Category include set (seeded, carried through the selection form) ------
#
# Hangers-on and vehicle crew are hidden from the pool by default. The category
# opt-in still exists as the campaign-seeded `included_categories` (and a
# ?include= querystring that round-trips it) — the per-fighter eligibility screen
# supersedes the old per-category toggle UI for changing it.


def test_resolve_included_maps_slugs_and_normalises(rf):
    """The ?include= querystring uses slugs; resolving maps them to the canonical
    category values in display order, deduped, dropping anything unknown."""
    from gyrinx.core.views.crew import _resolve_included

    req = rf.get("/x", {"include": "crew,hangers-on,crew,bogus"})
    assert _resolve_included(req) == ["HANGER_ON", "CREW"]
    # Absent → the given default (e.g. a crew's stored opt-ins on edit).
    assert _resolve_included(rf.get("/x"), default=["CREW"]) == ["CREW"]
    # Explicit empty → empty, not the default.
    assert _resolve_included(rf.get("/x", {"include": ""}), default=["CREW"]) == []


@pytest.mark.django_db
def test_crew_form_offers_hangers_on_only_when_toggled(
    client, crew_setup, make_content_fighter, make_list_fighter
):
    hanger = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HANGER_ON,
        "Rogue Doc",
    )
    client.force_login(crew_setup["user"])
    url = reverse("core:crew-new", args=[crew_setup["battle"].id])
    params = {"list": str(crew_setup["gang"].id), "method": Crew.CUSTOM}

    off = client.get(url, params)
    assert hanger.id not in {f.id for f in off.context["form"].eligible_fighters}

    on = client.get(url, {**params, "include": "hangers-on"})
    assert hanger.id in {f.id for f in on.context["form"].eligible_fighters}
    assert 'aria-pressed="true"' in on.content.decode()  # the toggle reads "on"


@pytest.mark.django_db
def test_creating_a_crew_persists_included_categories(
    client, crew_setup, make_content_fighter, make_list_fighter
):
    hanger = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HANGER_ON,
        "Rogue Doc",
    )
    client.force_login(crew_setup["user"])
    resp = client.post(
        reverse("core:crew-new", args=[crew_setup["battle"].id]),
        {
            "list": str(crew_setup["gang"].id),
            "method": Crew.CUSTOM,
            "include": "hangers-on",
            "custom_count": "1",
            "chosen_fighters": [str(hanger.id)],
        },
    )
    assert resp.status_code == 302

    crew = Crew.objects.get(battle=crew_setup["battle"], list=crew_setup["gang"])
    assert crew.included_categories == ["HANGER_ON"]
    assert crew.members.filter(list_fighter=hanger).exists()


@pytest.mark.django_db
def test_editing_a_crew_keeps_its_included_categories(
    client, crew_setup, make_content_fighter, make_list_fighter
):
    """Opening the edit form with no ?include= keeps the crew's stored opt-ins,
    so the toggled-in fighters stay offered."""
    hanger = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HANGER_ON,
        "Rogue Doc",
    )
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        custom_count=1,
        included_categories=["HANGER_ON"],
    )

    client.force_login(crew_setup["user"])
    resp = client.get(reverse("core:crew-edit", args=[crew.battle_id, crew.id]))

    form = resp.context["form"]
    assert form.included_categories == ["HANGER_ON"]
    assert hanger.id in {f.id for f in form.eligible_fighters}


@pytest.mark.django_db
def test_editing_a_crew_can_clear_included_categories(
    client, crew_setup, make_content_fighter, make_list_fighter
):
    """Toggling the last category off is an explicit empty ``?include=``, which
    clears the crew's opt-ins rather than falling back to the stored value."""
    hanger = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HANGER_ON,
        "Rogue Doc",
    )
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        custom_count=1,
        included_categories=["HANGER_ON"],
    )

    client.force_login(crew_setup["user"])
    resp = client.get(
        reverse("core:crew-edit", args=[crew.battle_id, crew.id]), {"include": ""}
    )

    form = resp.context["form"]
    assert form.included_categories == []  # not the stored ["HANGER_ON"]
    assert hanger.id not in {f.id for f in form.eligible_fighters}


@pytest.mark.django_db
def test_campaign_default_seeds_the_crew_toggles(
    client, crew_setup, make_content_fighter, make_list_fighter
):
    """A new crew's toggles start from the campaign default (e.g. an Ash-Wastes
    campaign opting vehicle crew in for everyone)."""
    driver = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.CREW,
        "Driver",
    )
    crew_setup["campaign"].default_included_crew_categories = ["CREW"]
    crew_setup["campaign"].save()

    client.force_login(crew_setup["user"])
    resp = client.get(
        reverse("core:crew-new", args=[crew_setup["battle"].id]),
        {"list": str(crew_setup["gang"].id), "method": Crew.CUSTOM},
    )

    form = resp.context["form"]
    assert form.included_categories == ["CREW"]  # seeded from the campaign
    assert driver.id in {f.id for f in form.eligible_fighters}


@pytest.mark.django_db
def test_crew_toggle_overrides_the_campaign_default(
    client, crew_setup, make_content_fighter, make_list_fighter
):
    """The per-crew toggle wins: an explicit ?include= overrides the campaign
    default rather than being merged with it."""
    driver = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.CREW,
        "Driver",
    )
    hanger = _fighter_of_category(
        crew_setup,
        make_content_fighter,
        make_list_fighter,
        FighterCategoryChoices.HANGER_ON,
        "Rogue Doc",
    )
    crew_setup["campaign"].default_included_crew_categories = ["CREW"]
    crew_setup["campaign"].save()

    client.force_login(crew_setup["user"])
    resp = client.get(
        reverse("core:crew-new", args=[crew_setup["battle"].id]),
        {
            "list": str(crew_setup["gang"].id),
            "method": Crew.CUSTOM,
            "include": "hangers-on",
        },
    )

    form = resp.context["form"]
    assert form.included_categories == ["HANGER_ON"]  # the toggle, not the default
    assert hanger.id in {f.id for f in form.eligible_fighters}
    assert driver.id not in {f.id for f in form.eligible_fighters}


@pytest.mark.django_db
def test_edit_campaign_form_saves_default_crew_categories(campaign, user):
    """The campaign settings form persists the default opt-in categories."""
    from gyrinx.core.forms.campaign import EditCampaignForm

    form = EditCampaignForm(
        {
            "name": campaign.name,
            "budget": str(campaign.budget),
            "default_included_crew_categories": ["CREW"],
        },
        instance=campaign,
    )
    assert form.is_valid(), form.errors
    form.save(user=user)

    campaign.refresh_from_db()
    assert campaign.default_included_crew_categories == ["CREW"]


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

    # Extras can only be added once the crew is locked.
    Crew.objects.filter(pk=crew.pk).update(status=Crew.LOCKED)
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
def test_crew_archive_view(client, crew_setup):
    """Archiving keeps the crew (it's the record), flags it archived, redirects
    to the battle, and logs a battle-linked CampaignAction."""
    client.force_login(crew_setup["user"])
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(battle=battle, list=gang, owner=crew_setup["user"])

    resp = client.post(reverse("core:crew-archive", args=[battle.id, crew.id]))
    assert resp.status_code == 302
    assert resp.url == reverse("core:battle", args=[battle.id])

    crew.refresh_from_db()
    assert crew.archived is True
    assert crew.archived_at is not None

    action = CampaignAction.objects.get(battle=battle, list=gang)
    assert action.campaign_id == battle.campaign_id
    assert "archived" in action.description.lower()


@pytest.mark.django_db
def test_archived_crew_frees_the_gang_for_a_new_crew(crew_setup):
    """The unique constraint is conditional on archived=False: an archived crew
    must not block a fresh crew for the same gang and battle."""
    battle, gang, user = crew_setup["battle"], crew_setup["gang"], crew_setup["user"]

    first = Crew.objects.create(battle=battle, list=gang, owner=user)
    handle_crew_archive(user=user, crew=first)

    # Creating again for the same (battle, list) must succeed, not trip the
    # unique constraint.
    second = Crew.objects.create(battle=battle, list=gang, owner=user)
    assert second.pk != first.pk
    assert Crew.objects.filter(battle=battle, list=gang, archived=False).count() == 1


@pytest.mark.django_db
def test_archived_crew_hidden_from_battle_page(client, crew_setup):
    """An archived crew drops off the battle page: the gang shows the add-crew
    affordance again rather than a stale crew sub-row."""
    client.force_login(crew_setup["user"])
    battle, gang, user = crew_setup["battle"], crew_setup["gang"], crew_setup["user"]
    crew = Crew.objects.create(battle=battle, list=gang, owner=user)
    handle_crew_archive(user=user, crew=crew)

    content = client.get(reverse("core:battle", args=[battle.id])).content.decode()
    # The add-crew affordance carries ?list=<gang>; it's back because the gang
    # has no live crew.
    assert f"?list={gang.id}" in content


@pytest.mark.django_db
def test_archived_crew_page_renders_with_note_and_no_actions(client, crew_setup):
    """The archived crew's detail page still renders (it's the record), shows an
    'archived' note, and offers no manage actions."""
    client.force_login(crew_setup["user"])
    battle, gang, user = crew_setup["battle"], crew_setup["gang"], crew_setup["user"]
    crew = Crew.objects.create(battle=battle, list=gang, owner=user)
    handle_crew_archive(user=user, crew=crew)

    resp = client.get(reverse("core:crew", args=[battle.id, crew.id]))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert resp.context["can_manage"] is False
    assert "This crew is archived" in content
    # No manage affordances: no archive/edit/lock links.
    assert reverse("core:crew-archive", args=[battle.id, crew.id]) not in content
    assert reverse("core:crew-edit", args=[battle.id, crew.id]) not in content


@pytest.mark.django_db
def test_archived_crew_cannot_be_archived_again(client, crew_setup):
    """can_manage is False for an archived crew, so a repeat archive is refused
    rather than writing a second log line."""
    client.force_login(crew_setup["user"])
    battle, gang, user = crew_setup["battle"], crew_setup["gang"], crew_setup["user"]
    crew = Crew.objects.create(battle=battle, list=gang, owner=user)
    handle_crew_archive(user=user, crew=crew)
    before = CampaignAction.objects.filter(battle=battle).count()

    resp = client.post(reverse("core:crew-archive", args=[battle.id, crew.id]))
    assert resp.status_code == 302
    assert CampaignAction.objects.filter(battle=battle).count() == before


@pytest.mark.django_db
def test_non_manager_cannot_archive_crew(client, crew_setup, make_user):
    """A user who is neither the gang owner nor the battle's arbitrator can't
    archive the crew."""
    battle, gang, user = crew_setup["battle"], crew_setup["gang"], crew_setup["user"]
    crew = Crew.objects.create(battle=battle, list=gang, owner=user)

    stranger = make_user("stranger", "password")
    client.force_login(stranger)
    resp = client.post(reverse("core:crew-archive", args=[battle.id, crew.id]))
    assert resp.status_code == 302

    crew.refresh_from_db()
    assert crew.archived is False


@pytest.mark.django_db
def test_archived_crew_gets_no_played_rating_snapshot(crew_setup):
    """A crew archived (withdrawn) before the battle ends must not get a played
    snapshot — it fielded nothing."""
    user = crew_setup["user"]
    crew = _lock_one_fighter_crew(crew_setup)
    handle_crew_archive(user=user, crew=crew)

    _end_battle(crew_setup)

    crew.refresh_from_db()
    assert crew.rating_played is None


@pytest.mark.django_db
def test_crew_delete_url_is_gone():
    """The delete route has been replaced by archive."""
    with pytest.raises(NoReverseMatch):
        reverse("core:crew-delete", args=[uuid4(), uuid4()])


def test_post_lock_loadout_editing_is_gone():
    """A locked crew is frozen: equipment sets are chosen during selection, and
    there is no route to change one afterwards."""
    with pytest.raises(NoReverseMatch):
        reverse("core:crew-member-loadout", args=[uuid4(), uuid4(), uuid4()])


@pytest.mark.django_db
def test_crew_extra_add_edit_delete(client, crew_setup):
    client.force_login(crew_setup["user"])
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    # Extras are added once the crew is set, so it must be locked first.
    crew = Crew.objects.create(
        battle=battle, list=gang, owner=crew_setup["user"], status=Crew.LOCKED
    )

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
def test_extras_only_added_after_the_crew_is_locked(client, crew_setup):
    """Extras — hired guns, balancing credits — are worked out once the crew is
    set (the allowance is calculated after crew selection, and a random crew
    isn't even known until the draw), so a new extra can't be added to a draft."""
    client.force_login(crew_setup["user"])
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(battle=battle, list=gang, owner=crew_setup["user"])
    payload = {
        "label": "Hive Scum",
        "cost": "50",
        "payment": Crew.PAY_CREDITS,
        "reason": "",
    }

    # Draft: blocked, nothing created.
    client.post(reverse("core:crew-extra-new", args=[battle.id, crew.id]), payload)
    assert not crew.line_items.exists()

    # Locked: the extra is added.
    Crew.objects.filter(pk=crew.pk).update(status=Crew.LOCKED)
    client.post(reverse("core:crew-extra-new", args=[battle.id, crew.id]), payload)
    assert crew.line_items.count() == 1


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
def test_fighter_rows_carry_each_fighter_cost(crew_setup):
    """Each fighter row exposes its ``cost_int_cached`` so the running-total
    enhancement can sum the ticked fighters without a round-trip."""
    form = CrewForm(gang=crew_setup["gang"], method=Crew.CUSTOM)
    rows = form.fighter_rows()

    assert len(rows) == len(crew_setup["fighters"])
    # crew_setup fighters are base-cost 100 with no equipment.
    assert all(row["cost"] == 100 for row in rows)


@pytest.mark.django_db
def test_crew_form_renders_cost_data_and_hidden_running_total(client, crew_setup):
    """The per-fighter cost is a server-rendered data attribute and the running
    total starts hidden — nothing shows a stale "0 fighters" without JS."""
    client.force_login(crew_setup["user"])
    content = client.get(_crew_new_url(crew_setup, Crew.CUSTOM)).content.decode()

    assert 'data-cost="100"' in content
    assert "js-crew-fighter-row" in content
    # Hidden until the enhancement reveals it.
    assert "js-crew-total" in content
    assert "d-none" in content


@pytest.mark.django_db
def test_random_form_has_no_running_total(client, crew_setup):
    """Random Selection has no fighter checkboxes, so there is nothing to total
    and no total element is emitted."""
    client.force_login(crew_setup["user"])
    content = client.get(_crew_new_url(crew_setup, Crew.RANDOM)).content.decode()

    assert "js-crew-total" not in content
    assert "js-crew-fighter-row" not in content


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
def test_crew_recorded_after_the_battle_ends_freezes_what_fought_at_lock(
    crew_setup, make_equipment, make_weapon_profile
):
    """Recorded after the fact: players settled the crew at the table and only
    log it once the result is already in. There is no future battle-end to
    freeze what fought, so the lock has to be that moment — otherwise the record
    would drift with the gang's later spending."""
    battle = crew_setup["battle"]

    # Draft the crew but end the battle before it is confirmed — the normal
    # battle-end freeze finds nothing to snapshot (a draft never fielded).
    crew = Crew.objects.create(
        battle=battle,
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        custom_count=1,
    )
    add_chosen(crew, crew_setup["fighters"][:1])
    _end_battle(crew_setup)
    # handle_battle_end transitions a re-fetched instance, so reload ours.
    battle.refresh_from_db()
    assert battle.has_ended()

    # Now confirm the crew. Because the battle is over, the lock freezes played.
    crew = handle_crew_lock(user=crew_setup["user"], crew=crew).crew
    assert crew.rating_selected == 100
    assert crew.rating_played == 100
    assert crew.rating() == 100
    assert [m.rating_played for m in crew.members.all()] == [100]
    # One write per member, not two: selected and played were frozen together.
    assert crew.rating_note()["differs"] is False

    # The gang spends on: the crew that fought must not follow it.
    bolter = make_equipment(name="Late Bolter", cost=35, category="Basic Weapons")
    make_weapon_profile(bolter)
    crew_setup["fighters"][0].assign(bolter)

    crew.refresh_from_db()
    assert crew.rating() == 100
    assert crew.members.get().rating() == 100


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


@pytest.mark.django_db
def test_battle_page_forecasts_a_whole_gang_draft(client, crew_setup):
    """A whole-gang crew enrols nobody until it is confirmed, so its own rating
    is 0 — which on the battle page would read as "no fighters" rather than "the
    whole gang attends". The row must forecast instead."""
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    client.force_login(crew_setup["user"])
    crew = Crew.objects.create(
        battle=battle, list=gang, owner=crew_setup["user"], selection_method=Crew.CUSTOM
    )
    assert crew.is_whole_gang
    assert crew.rating() == 0  # nobody enrolled yet

    resp = client.get(reverse("core:battle", args=[battle.id]))
    summary = next(
        p["crew"]
        for group in resp.context["participant_groups"]
        for p in group["participants"]
        if p["crew"]
    )
    assert summary["is_forecast"] is True
    assert summary["rating"] == crew_whole_gang_projection(crew)["total"]
    assert summary["rating"] > 0
    assert "provisional" in resp.content.decode()


@pytest.mark.django_db
def test_no_template_comment_leaks_into_crew_pages(client, crew_setup):
    """Django's ``{# #}`` comment is single-line only: spread it over multiple
    lines and it renders as visible page text. That has now happened twice on
    crew templates, so pin it for the pages a player actually sees."""
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    client.force_login(crew_setup["user"])
    crew = Crew.objects.create(battle=battle, list=gang, owner=crew_setup["user"])

    urls = [
        reverse("core:battle", args=[battle.id]),
        reverse("core:crew", args=[battle.id, crew.id]),
        reverse("core:crew-new", args=[battle.id]) + f"?list={gang.id}",
    ]
    for url in urls:
        content = client.get(url).content.decode()
        assert "{#" not in content, url
        assert "#}" not in content, url


@pytest.mark.django_db
def test_double_archive_raises_and_logs_once(crew_setup):
    """The handler owns the guard: the loser of a concurrent double-archive
    raises rather than writing a second withdrawal to the campaign log."""
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    crew = Crew.objects.create(battle=battle, list=gang, owner=crew_setup["user"])

    handle_crew_archive(user=crew_setup["user"], crew=crew)
    with pytest.raises(ValidationError, match="already been archived"):
        handle_crew_archive(user=crew_setup["user"], crew=crew)

    assert (
        CampaignAction.objects.filter(
            battle=battle, description__startswith="Crew archived"
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_archive_page_says_already_archived(client, crew_setup):
    """An archived crew's archive URL explains itself rather than claiming the
    owner lacks permission (can_manage is False once archived)."""
    battle, gang = crew_setup["battle"], crew_setup["gang"]
    client.force_login(crew_setup["user"])
    crew = Crew.objects.create(battle=battle, list=gang, owner=crew_setup["user"])
    handle_crew_archive(user=crew_setup["user"], crew=crew)

    resp = client.get(
        reverse("core:crew-archive", args=[battle.id, crew.id]), follow=True
    )
    content = resp.content.decode()
    assert "already been archived" in content
    assert "permission" not in content


# --- crew_spread_rating: the shared comparison-rating cascade ---------------
#
# The single definition of what a crew is worth "right now" for spread/underdog
# comparison, extracted so the battle page and the crew-page spread can't drift.
# These pin the four cases; the battle-page render tests above exercise it in
# situ.


@pytest.mark.django_db
def test_crew_spread_rating_pending_roll_is_unknown(crew_setup):
    """A draft whose random draw hasn't happened has no comparable rating yet."""
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        selection_method=Crew.RANDOM,
        random_spec="D3",
    )
    assert crew.pending_roll is True
    assert crew_spread_rating(crew) == (None, False)


@pytest.mark.django_db
def test_crew_spread_rating_whole_gang_draft_is_a_forecast(crew_setup):
    """A whole-gang draft has enrolled nobody, so its comparison rating is the
    forecast of the currently-eligible roster, flagged provisional."""
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        selection_method=Crew.CUSTOM,
    )
    assert crew.is_whole_gang
    assert not crew.members.all()

    rating, provisional = crew_spread_rating(crew)
    assert provisional is True
    assert rating == crew_whole_gang_projection(crew)["total"]
    assert rating > 0  # five gangers at 100 each


@pytest.mark.django_db
def test_whole_gang_emptiness_check_reads_the_members_prefetch_cache(crew_setup):
    """The whole-gang draft's ``not crew.members.exists()`` check must read a
    caller's ``prefetch_related("members")`` cache, not the DB — otherwise the
    battle page, which prefetches members for every crew, would pay a query per
    crew. (Django's related-manager ``.exists()`` uses the prefetched cache.)"""
    Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        selection_method=Crew.CUSTOM,  # whole-gang draft, no members
    )
    crew = (
        Crew.objects.filter(battle=crew_setup["battle"])
        .prefetch_related("members")
        .get()
    )
    with CaptureQueriesContext(connection) as ctx:
        empty = not crew.members.exists()
    assert empty is True
    assert len(ctx) == 0


@pytest.mark.django_db
def test_crew_spread_rating_locked_unplayed_is_live(crew_setup):
    """A locked crew that hasn't fought reports its live rating — what the gang
    would field now — and is not provisional."""
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        status=Crew.LOCKED,
        custom_count=2,
    )
    add_chosen(crew, crew_setup["fighters"][:2])

    rating, provisional = crew_spread_rating(crew)
    assert provisional is False
    assert rating == crew.live_rating()
    assert rating == crew.rating()  # no played snapshot yet
    assert rating == 200


@pytest.mark.django_db
def test_crew_spread_rating_played_is_the_frozen_figure(crew_setup):
    """Once the battle has frozen what fought, that snapshot is the comparison
    rating — the live gang moving on afterwards must not change it."""
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=crew_setup["gang"],
        owner=crew_setup["user"],
        status=Crew.LOCKED,
        custom_count=2,
        rating_selected=280,
        rating_played=320,
    )
    add_chosen(crew, crew_setup["fighters"][:2])

    rating, provisional = crew_spread_rating(crew)
    assert provisional is False
    assert rating == 320  # the played snapshot, not the live 200
    assert rating == crew.rating()


# --- Battle-page underdog / spread block ------------------------------------
#
# The informational block under the participants table: it states the gap, the
# extra tactics it earns, and the conditional House-Patronage allowance, and
# points at the rules. It never asserts an entitlement. crew_setup's gang is
# "Riot Gang" with five 100¢ gangers; these add a second/third gang to the same
# battle and give crews controlled ratings (chosen members are 100¢ each).


def _spread_gang(crew_setup, make_list, make_list_fighter, name, n_fighters):
    """A further gang in crew_setup's campaign, with n_fighters 100¢ gangers."""
    gang = make_list(name, status=List.CAMPAIGN_MODE, campaign=crew_setup["campaign"])
    crew_setup["campaign"].lists.add(gang)
    fighters = [make_list_fighter(gang, f"{name} {i}") for i in range(n_fighters)]
    return gang, fighters


def _locked_crew(crew_setup, gang, members):
    """A LOCKED crew for gang with the given chosen members (100¢ each), so its
    comparison rating is 100 × len(members)."""
    crew = Crew.objects.create(
        battle=crew_setup["battle"],
        list=gang,
        owner=crew_setup["user"],
        status=Crew.LOCKED,
        custom_count=len(members) or None,
    )
    add_chosen(crew, members)
    return crew


def _pending_crew(crew_setup, gang):
    """A draft Random crew with an unrolled spec — pending, so no known rating."""
    return Crew.objects.create(
        battle=crew_setup["battle"],
        list=gang,
        owner=crew_setup["user"],
        selection_method=Crew.RANDOM,
        random_spec="D3",
    )


def _set_gang_rating(gang, value):
    """Force a gang's cached rating_current without recomputation."""
    List.objects.filter(pk=gang.pk).update(rating_current=value)


@pytest.mark.django_db
def test_crew_battle_spread_none_when_subject_pending(
    crew_setup, make_list, make_list_fighter
):
    """The subject crew has no rating yet (its draw is pending), so there is
    nothing to say about how far below the top it sits."""
    riot = crew_setup["gang"]
    iron, iron_fighters = _spread_gang(
        crew_setup, make_list, make_list_fighter, "Iron Skulls", 6
    )
    orlock, orlock_fighters = _spread_gang(
        crew_setup, make_list, make_list_fighter, "Orlock", 2
    )
    crew_setup["battle"].set_participants([riot, iron, orlock])

    subject = _pending_crew(crew_setup, riot)  # no known rating
    _locked_crew(crew_setup, iron, iron_fighters[:1])
    _locked_crew(crew_setup, orlock, orlock_fighters[:1])

    assert crew_battle_spread(subject) is None


@pytest.mark.django_db
def test_crew_battle_spread_is_the_gap_below_the_top(
    crew_setup, make_list, make_list_fighter
):
    """A below-top crew reports its gap; the top crew has nothing below it."""
    riot = crew_setup["gang"]
    iron, iron_fighters = _spread_gang(
        crew_setup, make_list, make_list_fighter, "Iron Skulls", 6
    )
    crew_setup["battle"].set_participants([riot, iron])
    riot_crew = _locked_crew(crew_setup, riot, crew_setup["fighters"][:1])  # 100
    iron_crew = _locked_crew(crew_setup, iron, iron_fighters[:6])  # 600 (top)

    assert crew_battle_spread(riot_crew) == 500
    assert crew_battle_spread(iron_crew) is None  # it is the top


def _battle_response(client, crew_setup):
    resp = client.get(reverse("core:battle", args=[crew_setup["battle"].id]))
    assert resp.status_code == 200
    return resp


def _participant_row(resp, gang_name):
    """The participant row for ``gang_name`` in the battle-page context."""
    for group in resp.context["participant_groups"]:
        for row in group["participants"]:
            if row["list"].name == gang_name:
                return row
    return None


@pytest.mark.django_db
def test_battle_table_shows_crew_and_gang_deltas(
    client, crew_setup, make_list, make_list_fighter
):
    """The participants table shows, beside each rating, how far it is below the
    top — for the crew (crew row) and the gang (gang row). Numbers only."""
    riot = crew_setup["gang"]
    iron, iron_fighters = _spread_gang(
        crew_setup, make_list, make_list_fighter, "Iron Skulls", 6
    )
    crew_setup["battle"].set_participants([riot, iron])
    _locked_crew(crew_setup, riot, crew_setup["fighters"][:1])  # crew 100
    _locked_crew(crew_setup, iron, iron_fighters[:6])  # crew 600 (top)
    _set_gang_rating(riot, 200)
    _set_gang_rating(iron, 600)  # top gang

    client.force_login(crew_setup["user"])
    resp = _battle_response(client, crew_setup)
    content = resp.content.decode()

    riot_row = _participant_row(resp, "Riot Gang")
    iron_row = _participant_row(resp, "Iron Skulls")
    # Gang deltas: Riot is 400¢ below the top gang; Iron is the top.
    assert riot_row["rating_delta"] == 400
    assert iron_row["rating_delta"] is None
    # Crew deltas: Riot's crew is 500¢ below the top crew; Iron's is the top.
    assert riot_row["crew"]["rating_delta"] == 500
    assert iron_row["crew"]["rating_delta"] is None

    assert "vs top" in content  # the column header
    assert "500¢" in content  # crew delta (only 500¢ on the page)
    assert "400¢" in content  # gang delta (only 400¢ on the page)
    # No rules read for the player.
    for word in ("underdog", "gang tactic", "House Patronage"):
        assert word not in content


@pytest.mark.django_db
def test_battle_table_no_crew_delta_with_fewer_than_two_crews(
    client, crew_setup, make_list, make_list_fighter
):
    """A crew delta needs two crews to compare; with one crew there is none,
    though the gang deltas still show."""
    riot = crew_setup["gang"]
    iron, _ = _spread_gang(crew_setup, make_list, make_list_fighter, "Iron Skulls", 3)
    crew_setup["battle"].set_participants([riot, iron])
    _locked_crew(crew_setup, riot, crew_setup["fighters"][:1])  # the only crew
    _set_gang_rating(riot, 200)
    _set_gang_rating(iron, 600)

    client.force_login(crew_setup["user"])
    resp = _battle_response(client, crew_setup)

    riot_row = _participant_row(resp, "Riot Gang")
    assert riot_row["crew"]["rating_delta"] is None  # only one crew
    assert riot_row["rating_delta"] == 400  # gang delta still shown


@pytest.mark.django_db
def test_battle_table_pending_crew_has_no_delta(
    client, crew_setup, make_list, make_list_fighter
):
    """A crew still to be drawn has no rating, so no delta."""
    riot = crew_setup["gang"]
    iron, iron_fighters = _spread_gang(
        crew_setup, make_list, make_list_fighter, "Iron Skulls", 6
    )
    crew_setup["battle"].set_participants([riot, iron])
    _pending_crew(crew_setup, riot)
    _locked_crew(crew_setup, iron, iron_fighters[:6])

    client.force_login(crew_setup["user"])
    resp = _battle_response(client, crew_setup)

    assert _participant_row(resp, "Riot Gang")["crew"]["rating_delta"] is None


@pytest.mark.django_db
def test_battle_table_every_crew_in_a_multi_gang_battle_has_a_delta(
    client, crew_setup, make_list, make_list_fighter
):
    """Three gangs: each trailing crew shows its own gap below the top — none is
    hidden."""
    riot = crew_setup["gang"]
    iron, iron_fighters = _spread_gang(
        crew_setup, make_list, make_list_fighter, "Iron Skulls", 6
    )
    orlock, orlock_fighters = _spread_gang(
        crew_setup, make_list, make_list_fighter, "Orlock", 5
    )
    crew_setup["battle"].set_participants([riot, iron, orlock])
    _locked_crew(crew_setup, iron, iron_fighters[:6])  # 600 (top)
    _locked_crew(crew_setup, orlock, orlock_fighters[:5])  # 500 — 100¢ below
    _locked_crew(crew_setup, riot, crew_setup["fighters"][:4])  # 400 — 200¢ below

    client.force_login(crew_setup["user"])
    resp = _battle_response(client, crew_setup)

    assert _participant_row(resp, "Iron Skulls")["crew"]["rating_delta"] is None
    assert _participant_row(resp, "Orlock")["crew"]["rating_delta"] == 100
    assert _participant_row(resp, "Riot Gang")["crew"]["rating_delta"] == 200


@pytest.mark.django_db
def test_battle_table_archived_crew_drops_out_of_the_deltas(
    client, crew_setup, make_list, make_list_fighter
):
    """Archiving (withdrawing) a crew removes it from the delta comparison."""
    riot = crew_setup["gang"]
    iron, iron_fighters = _spread_gang(
        crew_setup, make_list, make_list_fighter, "Iron Skulls", 6
    )
    crew_setup["battle"].set_participants([riot, iron])
    _locked_crew(crew_setup, riot, crew_setup["fighters"][:1])  # crew 100
    iron_crew = _locked_crew(crew_setup, iron, iron_fighters[:6])  # crew 600 (top)

    client.force_login(crew_setup["user"])
    before = _battle_response(client, crew_setup)
    assert _participant_row(before, "Riot Gang")["crew"]["rating_delta"] == 500

    # Withdraw Iron Skulls' crew — Riot's is now the only crew, so no delta.
    Crew.objects.filter(pk=iron_crew.pk).update(archived=True)

    after = _battle_response(client, crew_setup)
    riot_row = _participant_row(after, "Riot Gang")
    assert riot_row["crew"] is not None  # Riot still has its crew
    assert riot_row["crew"]["rating_delta"] is None  # nothing to compare now


@pytest.mark.django_db
def test_battle_table_hides_no_role_header_when_no_roles(
    client, crew_setup, make_list, make_list_fighter
):
    """With nobody assigned a role, the 'No role' group header is just noise, so
    it isn't shown."""
    iron, _ = _spread_gang(crew_setup, make_list, make_list_fighter, "Iron Skulls", 2)
    crew_setup["battle"].set_participants([crew_setup["gang"], iron])

    client.force_login(crew_setup["user"])
    resp = _battle_response(client, crew_setup)

    assert resp.context["roles_in_use"] is False
    assert "No role" not in resp.content.decode()


@pytest.mark.django_db
def test_battle_table_shows_role_headers_when_roles_assigned(
    client, crew_setup, make_list, make_list_fighter
):
    """Once any gang has a role, the role headers (including 'No role' for the
    rest) are shown to group the table."""
    from gyrinx.content.models import ContentBattleRole, ContentBattleRoleOption
    from gyrinx.core.models import BattleParticipant

    iron, _ = _spread_gang(crew_setup, make_list, make_list_fighter, "Iron Skulls", 2)
    battle = crew_setup["battle"]
    battle.set_participants([crew_setup["gang"], iron])

    role = ContentBattleRole.objects.create(name="Attacker/Defender")
    attacker = ContentBattleRoleOption.objects.create(role=role, name="Attacker")
    bp = BattleParticipant.objects.get(battle=battle, list=crew_setup["gang"])
    bp.role_option = attacker
    bp.save()

    client.force_login(crew_setup["user"])
    resp = _battle_response(client, crew_setup)
    content = resp.content.decode()

    assert resp.context["roles_in_use"] is True
    assert "Attacker" in content
    assert "No role" in content  # shown for the gang without a role


@pytest.mark.django_db
def test_battle_spread_third_gang_with_crew_adds_no_queries(
    client, crew_setup, make_list, make_list_fighter
):
    """The rating maps and spread are built from figures already in hand: a
    further participating gang with a crew must not add a query to the page.

    Uses pending crews so no per-crew fighter load is triggered (that batched
    cost is pre-existing crew-page behaviour, not the spread block's), and an
    anonymous viewer so no per-gang permission checks run — isolating the
    participants + maps + spread path this stage touches."""
    riot = crew_setup["gang"]
    iron, _ = _spread_gang(crew_setup, make_list, make_list_fighter, "Iron Skulls", 1)
    crew_setup["battle"].set_participants([riot, iron])
    _pending_crew(crew_setup, riot)
    _pending_crew(crew_setup, iron)

    url = reverse("core:battle", args=[crew_setup["battle"].id])

    def render_query_count():
        with CaptureQueriesContext(connection) as ctx:
            assert client.get(url).status_code == 200
        return len(ctx)

    render_query_count()  # warm per-process caches
    two_gangs = render_query_count()

    third, _ = _spread_gang(crew_setup, make_list, make_list_fighter, "Third Gang", 1)
    crew_setup["battle"].set_participants([riot, iron, third])
    _pending_crew(crew_setup, third)

    assert render_query_count() == two_gangs


# --- Crew-page rating-gap note ----------------------------------------------
#
# The crew sheet shows how far this crew sits below the highest crew in the
# battle — a plain number, no rules interpretation.


def _crew_response(client, crew):
    resp = client.get(reverse("core:crew", args=[crew.battle_id, crew.id]))
    assert resp.status_code == 200
    return resp


@pytest.mark.django_db
def test_crew_page_shows_the_rating_gap_below_the_top(
    client, crew_setup, make_list, make_list_fighter
):
    """A crew below the top shows how far below, in credits — numbers only."""
    riot = crew_setup["gang"]
    iron, iron_fighters = _spread_gang(
        crew_setup, make_list, make_list_fighter, "Iron Skulls", 6
    )
    crew_setup["battle"].set_participants([riot, iron])
    riot_crew = _locked_crew(crew_setup, riot, crew_setup["fighters"][:1])  # 100
    _locked_crew(crew_setup, iron, iron_fighters[:6])  # 600 (top)

    client.force_login(crew_setup["user"])
    resp = _crew_response(client, riot_crew)
    content = resp.content.decode()

    assert resp.context["rating_gap"] == 500
    assert "500¢ below" in content
    assert "the highest in the battle" in content
    # No rules interpretation.
    assert "House Patronage" not in content
    assert "This crew is the underdog" not in content


@pytest.mark.django_db
def test_crew_page_no_gap_note_for_the_top_crew(
    client, crew_setup, make_list, make_list_fighter
):
    """The top crew has nothing below it, so no gap note."""
    riot = crew_setup["gang"]
    iron, iron_fighters = _spread_gang(
        crew_setup, make_list, make_list_fighter, "Iron Skulls", 6
    )
    crew_setup["battle"].set_participants([riot, iron])
    _locked_crew(crew_setup, riot, crew_setup["fighters"][:1])  # 100
    iron_crew = _locked_crew(crew_setup, iron, iron_fighters[:6])  # 600 (top)

    client.force_login(crew_setup["user"])
    resp = _crew_response(client, iron_crew)

    assert resp.context["rating_gap"] is None
    assert "the highest in the battle" not in resp.content.decode()


@pytest.mark.django_db
def test_crew_page_no_gap_note_when_opponent_pending(
    client, crew_setup, make_list, make_list_fighter
):
    """When the opponent's crew is still to be drawn, the gap can't be worked
    out, so no note."""
    riot = crew_setup["gang"]
    iron, _ = _spread_gang(crew_setup, make_list, make_list_fighter, "Iron Skulls", 3)
    crew_setup["battle"].set_participants([riot, iron])
    riot_crew = _locked_crew(crew_setup, riot, crew_setup["fighters"][:1])
    _pending_crew(crew_setup, iron)  # opponent unresolved

    client.force_login(crew_setup["user"])
    resp = _crew_response(client, riot_crew)

    assert resp.context["rating_gap"] is None
    assert "the highest in the battle" not in resp.content.decode()


@pytest.mark.django_db
def test_crew_page_opponent_fighter_count_does_not_raise_query_count(
    client, crew_setup, make_list, make_list_fighter
):
    """The opponent crews load in a batch, so more fighters in an opposing crew
    must not add queries to the crew page — no N+1 per opposing fighter."""
    riot = crew_setup["gang"]
    iron, iron_fighters = _spread_gang(
        crew_setup, make_list, make_list_fighter, "Iron Skulls", 8
    )
    crew_setup["battle"].set_participants([riot, iron])
    riot_crew = _locked_crew(crew_setup, riot, crew_setup["fighters"][:1])
    iron_crew = _locked_crew(crew_setup, iron, iron_fighters[:2])
    CrewLineItem.objects.create(
        crew=riot_crew,
        owner=crew_setup["user"],
        label="Tactics card",
        cost=100,
        payment=Crew.PAY_ALLOWANCE,
    )

    client.force_login(crew_setup["user"])
    url = reverse("core:crew", args=[riot_crew.battle_id, riot_crew.id])

    def render_query_count():
        with CaptureQueriesContext(connection) as ctx:
            assert client.get(url).status_code == 200
        return len(ctx)

    render_query_count()  # warm per-process caches
    few = render_query_count()

    # Grow the opponent's crew; the batched opponent load must stay flat.
    add_chosen(iron_crew, iron_fighters[2:8])

    assert render_query_count() == few
