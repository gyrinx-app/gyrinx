"""Tests for the #2070 stat-advancement cleanup."""

import pytest

from n23.core.models import ListFighter, ListFighterAdvancement
from n23.core.models.notification import Notification
from n23.core.maintenance.stat_advancements import (
    run,
    apply_plan,
    build_messages,
    build_plan,
    send_messages,
)
from n23.models import FighterCategoryChoices


def make_simple_content_fighter(house):
    """A minimal content fighter for tests that cannot use the fixtures.

    Transactional tests get no data from the session fixtures, so they build
    their own.
    """
    from n23.content.models import ContentFighter
    from n23.models import FighterCategoryChoices

    return ContentFighter.objects.create(
        type="Commit Order Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
        movement='4"',
        weapon_skill="4+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="7",
        cool="7",
        willpower="7",
        intelligence="7",
    )


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


@pytest.mark.django_db
def test_user_supplied_names_are_escaped_in_messages(
    user, make_list, make_list_fighter
):
    """Gang and fighter names are user input and go into rendered HTML."""
    lst = make_list("<script>alert('gang')</script>")
    fighter = make_list_fighter(lst, "<img src=x onerror=alert(1)>")
    advancement(fighter, user, "toughness", uses_mod_system=False)

    _, _, content = build_messages(build_plan())[0]

    # The markup is neutered, so what remains is inert text rather than tags
    assert "<script>" not in content
    assert "<img" not in content
    assert "&lt;script&gt;" in content
    assert "&lt;img" in content


@pytest.mark.django_db
def test_an_interrupted_run_still_protects_the_repair(
    user, make_list, make_list_fighter
):
    """A run that dies partway must not let the next one undo its work.

    The record is written before the data changes, so even a run that never
    reached DONE names every pair it touched. Filtering the memory to
    successful runs would leave exactly this case unprotected.
    """
    from n23.core.models import Backfill

    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Typed Fighter")
    advancement(fighter, user, "weapon_skill", uses_mod_system=False)
    fighter.weapon_skill_override = "3+"
    fighter.save()

    before = shown(fighter, "weapon_skill")
    run(notify=False)
    assert shown(fighter, "weapon_skill") == before

    # Simulate the process dying after the data changed: the record exists,
    # naming what was touched, but never reached DONE.
    Backfill.objects.filter(operation=Backfill.Operation.FIX_STAT_ADVANCEMENTS).update(
        status=Backfill.Status.RUNNING
    )

    second = run(notify=False)
    assert second.changed == 0
    assert shown(fighter, "weapon_skill") == before


@pytest.mark.django_db
def test_an_advancement_a_set_would_swallow_is_left_alone(
    user, make_list, make_list_fighter
):
    """Re-resolution catches what arithmetic could not.

    Gear that fixes a stat discards the advancement, so switching it on
    changes nothing — and a change that does nothing should not be made, nor
    a player told about it. No special case for "set" is needed: the card
    simply does not move.
    """
    from n23.content.models import (
        ContentEquipment,
        ContentEquipmentCategory,
        ContentModFighterStat,
    )
    from n23.core.models.list import ListFighterEquipmentAssignment

    category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Set Gear", defaults={"group": "Vehicle & Mount"}
    )
    gear = ContentEquipment.objects.create(
        name="Ash Wheels", category=category, cost="0"
    )
    mod, _ = ContentModFighterStat.objects.get_or_create(
        stat="movement", mode="set", value='8"'
    )
    gear.modifiers.add(mod)

    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Ashwheel Drax")
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=gear
    )
    # An inert advancement — situation 3 would normally switch it on
    advancement(fighter, user, "movement", uses_mod_system=False)

    change = only_change(build_plan(), fighter)
    assert change.situation == 10
    assert not change.acted_on

    run(notify=False)
    assert shown(fighter, "movement") == '8"'
    assert ListFighterAdvancement.objects.filter(
        fighter=fighter, uses_mod_system=False
    ).exists()


@pytest.mark.django_db
def test_an_edit_made_during_the_run_is_not_overwritten(
    user, make_list, make_list_fighter
):
    """Building the plan takes long enough for a player to edit a stat.

    Writing blind would overwrite that edit with a decision made about the
    old value — losing a player's edit, which is the harm this whole
    operation exists to undo.
    """
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Busy Fighter")
    advancement(fighter, user, "toughness", uses_mod_system=False)
    fighter.toughness_override = "6"
    fighter.save()

    plan = build_plan()
    assert plan.acted_on

    # The player edits the same stat after the plan was built
    ListFighter.objects.filter(pk=fighter.pk).update(toughness_override="9")

    applied, skipped = apply_plan(plan)

    assert applied == []
    assert len(skipped) == 1
    fighter.refresh_from_db()
    assert fighter.toughness_override == "9"
    # And the advancement was not flipped, so the pair stays convertible
    assert ListFighterAdvancement.objects.filter(
        fighter=fighter, uses_mod_system=False
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_the_message_count_survives_the_record_being_finalised():
    """Real commit ordering, not captured callbacks.

    Delivery happens from on_commit, which fires as the write transaction
    exits — so anything written to the summary after that block would clobber
    the count. A test that captures the callbacks and runs them afterwards
    reverses that ordering and cannot catch it.
    """
    from django.contrib.auth import get_user_model

    from n23.content.models import ContentHouse
    from n23.core.models.list import List
    from n23.core.models.notification import Notification

    User = get_user_model()
    owner = User.objects.create_user(username="commitorder", password="pw")
    house = ContentHouse.objects.create(name="Commit Order House")
    cf = make_simple_content_fighter(house)
    lst = List.objects.create(name="Gang", owner=owner, content_house=house)
    fighter = ListFighter.objects.create(
        list=lst, name="Feuer", content_fighter=cf, owner=owner
    )
    advancement(fighter, owner, "toughness", uses_mod_system=False)

    result = run(notify=True)

    assert Notification.objects.filter(owner=owner).count() == 1
    result.backfill.refresh_from_db()
    assert result.backfill.summary["messages_sent"] == 1


@pytest.mark.django_db
def test_an_override_typed_during_the_run_blocks_the_advancement_flip(
    user, make_list, make_list_fighter
):
    """Situation 3 changes no field, but its decision still assumed one.

    The plan was built against the stat having no stored value. If someone
    types one meanwhile, switching the advancement on regardless would move
    their card — and the pair would be recorded as handled, so no later run
    would revisit it.
    """
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Erased Fighter")
    advancement(fighter, user, "toughness", uses_mod_system=False)

    plan = build_plan()
    assert only_change(plan, fighter).situation == 3

    # The player types a value after the plan was built
    ListFighter.objects.filter(pk=fighter.pk).update(toughness_override="5")

    applied, skipped = apply_plan(plan)

    assert applied == []
    assert len(skipped) == 1
    assert ListFighterAdvancement.objects.filter(
        fighter=fighter, uses_mod_system=False
    ).exists()
    fighter.refresh_from_db()
    assert fighter.toughness_override == "5"


@pytest.mark.django_db
def test_an_advancement_archived_mid_run_leaves_the_stat_alone(
    user, make_list, make_list_fighter
):
    """The conversion did not happen, so the field must not stay written.

    Lowering the stored value is only correct because the advancement makes
    the difference back up. If the advancement has gone, leaving the value
    lowered would drop the fighter's stat a step.
    """
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Vanishing Advancement")
    adv = advancement(fighter, user, "weapon_skill", uses_mod_system=False)
    fighter.weapon_skill_override = "2+"
    fighter.save()

    plan = build_plan()
    assert only_change(plan, fighter).situation == 1
    before = shown(fighter, "weapon_skill")

    # The advancement is archived after the plan was built
    ListFighterAdvancement.objects.filter(pk=adv.pk).update(archived=True)

    applied, skipped = apply_plan(plan)

    assert applied == []
    assert len(skipped) == 1
    fighter.refresh_from_db()
    assert fighter.weapon_skill_override == "2+"
    assert shown(fighter, "weapon_skill") == before


@pytest.mark.django_db
def test_a_summary_distinguishes_nothing_to_send_from_not_sent(
    user, make_list, make_list_fighter
):
    """ "sent 0" is ambiguous unless what was asked for is recorded too."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Erased Fighter")
    advancement(fighter, user, "toughness", uses_mod_system=False)

    result = run(notify=False)
    summary = result.backfill.summary

    assert summary["notify_requested"] is False
    assert summary["messages_expected"] == 0
    # There was a visible change — it just was not going to be announced
    assert summary["visible"] == 1


@pytest.mark.django_db(transaction=True)
def test_a_summary_records_what_notification_was_asked_for():
    """The requested count is what makes "0 sent" readable after the fact.

    Testing only the notify=False case would pass against code that never
    sets these at all, since False and 0 are their defaults.
    """
    from django.contrib.auth import get_user_model

    from n23.content.models import ContentHouse
    from n23.core.models.list import List

    User = get_user_model()
    owner = User.objects.create_user(username="intentrec", password="pw")
    house = ContentHouse.objects.create(name="Intent House")
    cf = make_simple_content_fighter(house)
    lst = List.objects.create(name="Gang", owner=owner, content_house=house)
    fighter = ListFighter.objects.create(
        list=lst, name="Feuer", content_fighter=cf, owner=owner
    )
    advancement(fighter, owner, "toughness", uses_mod_system=False)

    result = run(notify=True)
    result.backfill.refresh_from_db()
    summary = result.backfill.summary

    assert summary["notify_requested"] is True
    assert summary["messages_expected"] == 1
    assert summary["messages_sent"] == 1
