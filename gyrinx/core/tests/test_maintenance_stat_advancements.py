"""Tests for the #2070 stat-advancement cleanup."""

import pytest

from gyrinx.core.models import ListFighter, ListFighterAdvancement
from gyrinx.core.models.notification import Notification
from gyrinx.core.maintenance.stat_advancements import (
    run,
    apply_plan,
    build_messages,
    build_plan,
    send_messages,
)
from gyrinx.models import FighterCategoryChoices


def advancement(fighter, user, stat, *, uses_mod_system):
    return ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased=stat,
        uses_mod_system=uses_mod_system,
        xp_cost=5,
        cost_increase=5,
        owner=user,
    )


def shown(fighter, stat):
    fresh = ListFighter.objects.get(pk=fighter.pk)
    for entry in fresh.statline:
        if entry.field_name == stat:
            return entry.value
    raise AssertionError(f"{stat} missing from statline")


def only_change(plan, fighter):
    matches = [c for c in plan.changes if c.fighter_id == str(fighter.id)]
    assert len(matches) == 1, matches
    return matches[0]


@pytest.fixture
def odd_base_fighter(make_content_fighter, content_house):
    """A fighter whose Movement base carries no inch mark."""
    return make_content_fighter(
        type="Odd Base Fighter",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
        movement="5",
        weapon_skill="4+",
        ballistic_skill="4+",
        strength="3",
        toughness="4",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="7",
        cool="7",
        willpower="7",
        intelligence="7",
    )


@pytest.mark.django_db
def test_manual_edit_is_back_computed_and_looks_identical(
    user, make_list, make_list_fighter
):
    """Situation 1: the card must not move, and the legacy row must go."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Typed Fighter")
    advancement(fighter, user, "weapon_skill", uses_mod_system=False)
    # Base is 5+; one advancement would give 4+. 2+ was typed by a person.
    fighter.weapon_skill_override = "2+"
    fighter.save()

    before = shown(fighter, "weapon_skill")
    change = only_change(build_plan(), fighter)
    assert change.situation == 1
    assert change.override_after == "3+"

    apply_plan(build_plan())

    fighter.refresh_from_db()
    assert fighter.weapon_skill_override == "3+"
    assert not ListFighterAdvancement.objects.filter(
        fighter=fighter, uses_mod_system=False
    ).exists()
    assert shown(fighter, "weapon_skill") == before


@pytest.mark.django_db
def test_old_format_value_is_cleared_keeping_the_same_number(
    user, make_list, make_list_fighter, odd_base_fighter
):
    """Situation 2: '6' and '6"' are the same value, differently written."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Format Fighter", content_fighter=odd_base_fighter)
    advancement(fighter, user, "movement", uses_mod_system=False)
    fighter.movement_override = "6"
    fighter.save()

    change = only_change(build_plan(), fighter)
    assert change.situation == 2

    apply_plan(build_plan())

    fighter.refresh_from_db()
    assert fighter.movement_override is None
    # Same number, now carrying the inch mark the mod system gives it
    assert shown(fighter, "movement") == '6"'


@pytest.mark.django_db
def test_inert_advancement_starts_applying(user, make_list, make_list_fighter):
    """Situation 3: bought, charged for, showing nothing — now it shows."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Erased Fighter")
    advancement(fighter, user, "toughness", uses_mod_system=False)
    # Base toughness is 3 and nothing was stored, so the advancement is inert.

    assert shown(fighter, "toughness") == "3"
    change = only_change(build_plan(), fighter)
    assert change.situation == 3
    assert change.displayed_before == "3"
    assert change.displayed_after == "4"
    assert change.visible_to_player
    assert change.direction == "gain"

    apply_plan(build_plan())
    assert shown(fighter, "toughness") == "4"


@pytest.mark.django_db
def test_format_disguised_duplicate_is_removed(
    user, make_list, make_list_fighter, odd_base_fighter
):
    """Situation 5: '5' against a '5"' expectation is still a duplicate."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Gallow", content_fighter=odd_base_fighter)
    advancement(fighter, user, "movement", uses_mod_system=True)
    fighter.movement_override = "6"
    fighter.save()

    # Base 5, one advancement gives 6" — but the stored 6 is improved again.
    assert shown(fighter, "movement") == '7"'
    change = only_change(build_plan(), fighter)
    assert change.situation == 5
    assert change.displayed_after == '6"'
    assert change.direction == "loss"

    apply_plan(build_plan())
    assert shown(fighter, "movement") == '6"'


@pytest.mark.django_db
def test_partial_count_duplicate_is_removed(user, make_list, make_list_fighter):
    """Situation 6: stored value matches fewer advancements than exist."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Jaxx")
    advancement(fighter, user, "toughness", uses_mod_system=True)
    advancement(fighter, user, "toughness", uses_mod_system=True)
    # Base 3, two advancements should give 5; the stored 4 is improved twice.
    fighter.toughness_override = "4"
    fighter.save()

    assert shown(fighter, "toughness") == "6"
    change = only_change(build_plan(), fighter)
    assert change.situation == 6
    assert change.displayed_after == "5"

    apply_plan(build_plan())
    assert shown(fighter, "toughness") == "5"


@pytest.mark.django_db
def test_genuine_manual_edit_alongside_working_advancement_is_untouched(
    user, make_list, make_list_fighter
):
    """Situation 7: legitimate, and nothing to retire."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Busa")
    advancement(fighter, user, "toughness", uses_mod_system=True)
    fighter.toughness_override = "9"
    fighter.save()

    change = only_change(build_plan(), fighter)
    assert change.situation == 7
    assert not change.acted_on

    apply_plan(build_plan())
    fighter.refresh_from_db()
    assert fighter.toughness_override == "9"


@pytest.mark.django_db
def test_unparseable_stat_is_left_alone(
    user, make_list, make_list_fighter, make_content_fighter, content_house
):
    """Situation 8: production really does hold values like '7_'."""
    cf = make_content_fighter(
        type="Broken Fighter",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
        movement='4"',
        weapon_skill="4+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="7_",
        cool="7",
        willpower="7",
        intelligence="7",
    )
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Czarn", content_fighter=cf)
    advancement(fighter, user, "leadership", uses_mod_system=False)
    fighter.leadership_override = "8"
    fighter.save()

    change = only_change(build_plan(), fighter)
    assert change.situation == 8
    assert not change.acted_on


@pytest.mark.django_db
def test_one_message_per_owner_with_losses_first(
    user, make_list, make_list_fighter, odd_base_fighter
):
    """The whole point of aggregating: one message, not one per fighter."""
    gang_a = make_list("Gang A")
    gang_b = make_list("Gang B")

    gainer = make_list_fighter(gang_a, "Feuer")
    advancement(gainer, user, "toughness", uses_mod_system=False)

    loser = make_list_fighter(gang_b, "Gallow", content_fighter=odd_base_fighter)
    advancement(loser, user, "movement", uses_mod_system=True)
    loser.movement_override = "6"
    loser.save()

    messages = build_messages(build_plan())
    assert len(messages) == 1

    owner_id, subject, content = messages[0]
    assert owner_id == user.id
    assert subject == "We've corrected some fighter stats"
    # Both gangs named, and the reduction appears before the improvement
    assert "Gang A" in content and "Gang B" in content
    assert content.index("too high") < content.index("weren't being applied")
    assert "ratings and credits haven't changed" in content
    assert "from their edit page" in content


@pytest.mark.django_db
def test_invisible_changes_generate_no_message(user, make_list, make_list_fighter):
    """Situation 1 leaves the card identical, so nobody is told."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Typed Fighter")
    advancement(fighter, user, "weapon_skill", uses_mod_system=False)
    fighter.weapon_skill_override = "2+"
    fighter.save()

    plan = build_plan()
    assert plan.acted_on
    assert build_messages(plan) == []


@pytest.mark.django_db
def test_messages_are_delivered_to_the_owner(user, make_list, make_list_fighter):
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Feuer")
    advancement(fighter, user, "toughness", uses_mod_system=False)

    sent = send_messages(build_messages(build_plan()))
    assert sent == 1

    notification = Notification.objects.get(owner=user)
    assert "weren't being applied" in notification.subject
    assert "Feuer" in notification.content


@pytest.mark.django_db
def test_applying_does_not_touch_the_gang_timestamp(user, make_list, make_list_fighter):
    """Saving fighters would reorder every affected player's gang list."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Typed Fighter")
    advancement(fighter, user, "weapon_skill", uses_mod_system=False)
    fighter.weapon_skill_override = "2+"
    fighter.save()

    lst.refresh_from_db()
    before = lst.modified

    apply_plan(build_plan())

    lst.refresh_from_db()
    assert lst.modified == before


@pytest.mark.django_db
def test_running_twice_changes_nothing_the_second_time(
    user, make_list, make_list_fighter
):
    """The back-computed value looks exactly like a duplicate improvement.

    A manual edit two steps better than base is stored one step lower so the
    advancement restores it — but that stored value is precisely what the
    advancement produces from base, which is the duplicate signature. Without
    a memory of what it already did, a second run undoes the first.
    """
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Mason Shade")
    advancement(fighter, user, "weapon_skill", uses_mod_system=False)
    # Base 5+, one advancement gives 4+; 3+ is two steps better — a manual edit.
    fighter.weapon_skill_override = "3+"
    fighter.save()

    before = shown(fighter, "weapon_skill")

    first = run(notify=False)
    assert first.changed == 1
    assert shown(fighter, "weapon_skill") == before

    second = run(notify=False)
    assert second.changed == 0, "second run must be a no-op"
    assert second.visible == 0
    assert shown(fighter, "weapon_skill") == before
