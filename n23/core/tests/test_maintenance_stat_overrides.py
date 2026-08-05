"""Tests for #1861 C2 — migrating fighter stat overrides to the EAV store."""

import pytest

from n23.content.models.statline import (
    ContentStat,
    ContentStatline,
    ContentStatlineStat,
    ContentStatlineType,
    ContentStatlineTypeStat,
)
from n23.core.maintenance.stat_overrides import (
    CONFLICT,
    DROP_REDUNDANT,
    INERT,
    MIGRATE,
    NO_STATLINE,
    STAT_FIELDS,
    UNMIGRATABLE,
    apply_plan,
    build_plan,
    run,
)
from n23.core.models import Backfill
from n23.core.models.list import ListFighter, ListFighterStatOverride

_HIGHLIGHTED = {"leadership", "cool", "willpower", "intelligence"}


def statline_for(content_fighter, fields=STAT_FIELDS, name="Fighter"):
    """Give a template a statline, mirroring what C1 produced."""
    statline_type, _ = ContentStatlineType.objects.get_or_create(name=name)
    statline = ContentStatline.objects.create(
        content_fighter=content_fighter, statline_type=statline_type
    )
    for position, field_name in enumerate(fields, start=1):
        type_stat, _ = ContentStatlineTypeStat.objects.get_or_create(
            statline_type=statline_type,
            stat=ContentStat.objects.get(field_name=field_name),
            defaults={
                "position": position,
                "is_highlighted": field_name in _HIGHLIGHTED,
                "is_first_of_group": field_name == "leadership",
            },
        )
        ContentStatlineStat.objects.create(
            statline=statline,
            statline_type_stat=type_stat,
            value=getattr(content_fighter, field_name) or "-",
        )
    return statline


def card(pk):
    """The rendered statline, through both the plain and annotated paths."""
    plain = ListFighter.objects.get(pk=pk)
    fast = ListFighter.objects.filter(pk=pk).with_related_data().get()
    render = [(s.field_name, s.name, s.value, s.highlight) for s in plain.statline]
    render_fast = [(s.field_name, s.name, s.value, s.highlight) for s in fast.statline]
    assert render == render_fast, "render paths disagree"
    return render


def only_move(plan, fighter, stat):
    matches = [
        m for m in plan.moves if m.fighter_id == str(fighter.id) and m.stat == stat
    ]
    assert len(matches) == 1, matches
    return matches[0]


@pytest.mark.django_db
def test_a_legacy_override_migrates_without_changing_the_card(
    user, make_list, make_list_fighter, content_fighter
):
    statline_for(content_fighter)
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Overridden Fighter")
    fighter.weapon_skill_override = "2+"
    fighter.save()

    assert only_move(build_plan(), fighter, "weapon_skill").action == MIGRATE
    run()

    fighter.refresh_from_db()
    assert fighter.weapon_skill_override is None
    assert ListFighterStatOverride.objects.get(list_fighter=fighter).value == "2+"
    # The value now reaches the card through the override store. When this
    # migration ran, the column reached it too and the card was unchanged
    # across the move; Track C3 has since cut the column out entirely, so the
    # store is the only way the value can show at all.
    assert ("weapon_skill", "WS", "2+", False) in card(fighter.pk)


@pytest.mark.django_db
def test_a_redundant_column_is_cleared_silently(
    user, make_list, make_list_fighter, content_fighter
):
    """An EAV row already outranks the column, so clearing it changes nothing."""
    statline = statline_for(content_fighter)
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Doubled Fighter")
    fighter.toughness_override = "5"
    fighter.save()
    ListFighterStatOverride.objects.create(
        list_fighter=fighter,
        content_stat=statline.statline_type.stats.get(stat__field_name="toughness"),
        value="5",
        owner=user,
    )

    before = card(fighter.pk)
    assert only_move(build_plan(), fighter, "toughness").action == DROP_REDUNDANT

    run()

    fighter.refresh_from_db()
    assert fighter.toughness_override is None
    assert ListFighterStatOverride.objects.filter(list_fighter=fighter).count() == 1
    assert card(fighter.pk) == before


@pytest.mark.django_db
def test_a_conflict_keeps_what_the_card_shows(
    user, make_list, make_list_fighter, content_fighter
):
    """Both stores hold a value; the EAV one is displayed, so it wins."""
    statline = statline_for(content_fighter)
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Conflicted Fighter")
    fighter.toughness_override = "5"
    fighter.save()
    ListFighterStatOverride.objects.create(
        list_fighter=fighter,
        content_stat=statline.statline_type.stats.get(stat__field_name="toughness"),
        value="6",
        owner=user,
    )

    before = card(fighter.pk)
    assert ("toughness", "T", "6", False) in before

    move = only_move(build_plan(), fighter, "toughness")
    assert move.action == CONFLICT
    assert (move.legacy_value, move.eav_value) == ("5", "6")

    record, _, _ = run()

    fighter.refresh_from_db()
    assert fighter.toughness_override is None
    assert card(fighter.pk) == before
    # The discarded edit is named individually on the record
    conflict = record.summary["conflicts"][0]
    assert conflict["discarded_column_value"] == "5"
    assert conflict["kept_override_value"] == "6"


@pytest.mark.django_db
def test_an_inert_value_is_cleared_and_reported(
    user, make_list, make_list_fighter, content_fighter
):
    """A stat absent from the statline type rendered nothing anyway."""
    statline_for(content_fighter, fields=["movement", "toughness"], name="Crew")
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Crew Fighter")
    fighter.weapon_skill_override = "2+"
    fighter.save()

    before = card(fighter.pk)
    assert not [s for s in before if s[0] == "weapon_skill"]

    assert only_move(build_plan(), fighter, "weapon_skill").action == INERT
    run()

    fighter.refresh_from_db()
    assert fighter.weapon_skill_override is None
    assert not ListFighterStatOverride.objects.filter(list_fighter=fighter).exists()
    assert card(fighter.pk) == before


@pytest.mark.django_db
def test_an_oversized_value_is_left_alone(
    user, make_list, make_list_fighter, content_fighter
):
    """Legacy columns hold 12 chars, override rows 10 — never truncate."""
    statline_for(content_fighter)
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Long Value Fighter")
    fighter.movement_override = "123456789012"
    fighter.save()

    move = only_move(build_plan(), fighter, "movement")
    assert move.action == UNMIGRATABLE
    assert not move.writes

    record, _, _ = run()

    fighter.refresh_from_db()
    assert fighter.movement_override == "123456789012"
    assert record.summary["unmigratable"][0]["value"] == "123456789012"


@pytest.mark.django_db
def test_an_edit_during_the_run_is_not_overwritten(
    user, make_list, make_list_fighter, content_fighter
):
    statline_for(content_fighter)
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Busy Fighter")
    fighter.weapon_skill_override = "2+"
    fighter.save()

    plan = build_plan()
    ListFighter.objects.filter(pk=fighter.pk).update(weapon_skill_override="1+")

    applied, skipped = apply_plan(plan)
    assert applied == []
    assert len(skipped) == 1
    fighter.refresh_from_db()
    assert fighter.weapon_skill_override == "1+"
    assert not ListFighterStatOverride.objects.filter(list_fighter=fighter).exists()


@pytest.mark.django_db
def test_the_run_is_idempotent(user, make_list, make_list_fighter, content_fighter):
    statline_for(content_fighter)
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Once Fighter")
    fighter.weapon_skill_override = "2+"
    fighter.save()

    _, first, _ = run()
    assert first
    before = card(fighter.pk)

    _, second, _ = run()
    assert second == []
    assert card(fighter.pk) == before


@pytest.mark.django_db
def test_values_copy_verbatim_including_dice_and_garbage(
    user, make_list, make_list_fighter, content_fighter
):
    """Cards show these strings as-is, so copying verbatim preserves display."""
    statline_for(content_fighter)
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Odd Values Fighter")
    fighter.movement_override = 'D6"'
    fighter.toughness_override = "3banans"
    fighter.save()

    run()

    stored = {
        o.content_stat.field_name: o.value
        for o in ListFighterStatOverride.objects.filter(list_fighter=fighter)
    }
    assert stored == {"movement": 'D6"', "toughness": "3banans"}
    # Unparseable values must survive the round trip to the card untouched —
    # no coercion, no dropping to the base value.
    shown = {field_name: value for field_name, _, value, _ in card(fighter.pk)}
    assert shown["movement"] == 'D6"'
    assert shown["toughness"] == "3banans"


@pytest.mark.django_db
def test_a_failed_run_records_the_traceback(
    user, make_list, make_list_fighter, content_fighter, monkeypatch
):
    import n23.core.maintenance.stat_overrides as mod

    statline_for(content_fighter)
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Doomed Fighter")
    fighter.weapon_skill_override = "2+"
    fighter.save()

    def boom(plan):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(mod, "apply_plan", boom)
    with pytest.raises(RuntimeError):
        run()

    record = Backfill.objects.get(operation=Backfill.Operation.MIGRATE_STAT_OVERRIDES)
    assert record.status == Backfill.Status.FAILED
    assert "kaboom" in record.error
    assert "Traceback" in record.error


@pytest.mark.django_db
def test_a_statline_less_template_is_never_touched(
    user, make_list, make_list_fighter, content_fighter
):
    """Without a statline there is nowhere to put the value.

    An override is a row keyed to one of a statline's stats, so a template
    without one cannot hold the column's value. Clearing it anyway would
    destroy it outright — distinct from a stat merely absent from an existing
    statline. The column is kept so the value can still be migrated once the
    template gains a statline.
    """
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "No Statline Fighter")
    fighter.weapon_skill_override = "2+"
    fighter.save()
    assert not hasattr(content_fighter, "custom_statline")

    move = only_move(build_plan(), fighter, "weapon_skill")
    assert move.action == NO_STATLINE
    assert not move.writes

    run()

    fighter.refresh_from_db()
    assert fighter.weapon_skill_override == "2+"
    assert not ListFighterStatOverride.objects.filter(list_fighter=fighter).exists()


@pytest.mark.django_db
def test_migrating_does_not_touch_the_gang_timestamp_or_spawn_anything(
    user, make_list, make_list_fighter, content_fighter
):
    """save() fires receivers that bump every gang's modified timestamp —
    reordering owners' gang lists — and materialise child fighter defaults.
    A stats migration must do neither."""
    statline_for(content_fighter)
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Quiet Fighter")
    fighter.weapon_skill_override = "2+"
    fighter.save()

    lst.refresh_from_db()
    before_modified = lst.modified
    before_fighters = ListFighter.objects.count()

    run()

    lst.refresh_from_db()
    assert lst.modified == before_modified
    assert ListFighter.objects.count() == before_fighters


@pytest.mark.django_db
def test_a_concurrent_override_row_skips_only_that_fighter(
    user, make_list, make_list_fighter, content_fighter
):
    """The owner's stats form recreates rows without touching the column, so
    a racing edit can trip unique_together. One racing owner must not abort
    the remaining fifteen hundred fighters."""
    statline = statline_for(content_fighter)
    lst = make_list("Gang")
    racer = make_list_fighter(lst, "Racing Fighter")
    racer.weapon_skill_override = "2+"
    racer.save()
    bystander = make_list_fighter(lst, "Bystander Fighter")
    bystander.toughness_override = "5"
    bystander.save()

    plan = build_plan()
    # A row appears for the racer between planning and applying
    ListFighterStatOverride.objects.create(
        list_fighter=racer,
        content_stat=statline.statline_type.stats.get(stat__field_name="weapon_skill"),
        value="1+",
        owner=user,
    )

    applied, skipped = apply_plan(plan)

    assert [m.fighter_id for m in applied] == [str(bystander.id)]
    assert {m.fighter_id for m in skipped} == {str(racer.id)}
    racer.refresh_from_db()
    assert racer.weapon_skill_override == "2+"


@pytest.mark.django_db
def test_created_rows_are_owned_by_the_fighters_owner(
    user, make_list, make_list_fighter, content_fighter
):
    statline_for(content_fighter)
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Owned Fighter")
    fighter.toughness_override = "5"
    fighter.save()

    run()

    row = ListFighterStatOverride.objects.get(list_fighter=fighter)
    assert row.owner_id == fighter.owner_id
