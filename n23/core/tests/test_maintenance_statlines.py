"""Tests for #1861 C1 — format normalisation and statline materialisation."""

import pytest

from n23.content.models.statline import (
    ContentStat,
    ContentStatline,
    ContentStatlineType,
    ContentStatlineTypeStat,
)
from n23.core.maintenance.statlines import (
    STAT_FIELDS,
    apply_format_plan,
    apply_statline_plan,
    build_format_plan,
    build_statline_plan,
    run_materialise,
    run_normalise,
)
from n23.core.models import Backfill
from n23.core.models.list import ListFighter
from n23.models import FighterCategoryChoices

# Mirrors content.0156: position order, Ld..Int highlighted, Ld first of group.
_TYPE_META = {
    "leadership": (9, True, True),
    "cool": (10, True, False),
    "willpower": (11, True, False),
    "intelligence": (12, True, False),
}


@pytest.fixture
def fighter_type(db):
    """The "Fighter" statline type content.0156 guarantees in real databases.

    Tests run with --nomigrations, so the data migration never executes.
    """
    statline_type, _ = ContentStatlineType.objects.get_or_create(name="Fighter")
    for position, field_name in enumerate(STAT_FIELDS, start=1):
        stat = ContentStat.objects.get(field_name=field_name)
        pos, highlighted, first = _TYPE_META.get(field_name, (position, False, False))
        ContentStatlineTypeStat.objects.get_or_create(
            statline_type=statline_type,
            stat=stat,
            defaults={
                "position": pos,
                "is_highlighted": highlighted,
                "is_first_of_group": first,
            },
        )
    return statline_type


def make_cf(make_content_fighter, content_house, **overrides):
    values = dict(
        type=overrides.pop("type", "C1 Fighter"),
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
        movement='5"',
        weapon_skill="4+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="7+",
        cool="7+",
        willpower="7+",
        intelligence="7+",
    )
    values.update(overrides)
    return make_content_fighter(**values)


@pytest.mark.django_db
def test_format_plan_finds_only_the_two_bare_int_shapes(
    make_content_fighter, content_house
):
    cf = make_cf(
        make_content_fighter,
        content_house,
        weapon_skill="4",  # target-roll, bare -> 4+
        movement="5",  # inches, bare -> 5"
        strength="3",  # plain stat, bare is correct
        ballistic_skill="D6+1",  # dice expression: never touched
        toughness="-",
        wounds="",
    )
    fixes = {
        (f.stat, f.old, f.new) for f in build_format_plan() if f.cf_id == str(cf.id)
    }
    assert fixes == {("weapon_skill", "4", "4+"), ("movement", "5", '5"')}


@pytest.mark.django_db
def test_format_plan_skips_templates_that_already_have_a_statline(
    make_content_fighter, content_house, fighter_type
):
    cf = make_cf(make_content_fighter, content_house, weapon_skill="4")
    ContentStatline.objects.create(content_fighter=cf, statline_type=fighter_type)

    assert not [f for f in build_format_plan() if f.cf_id == str(cf.id)]


@pytest.mark.django_db
def test_format_apply_skips_a_value_edited_mid_run(make_content_fighter, content_house):
    cf = make_cf(make_content_fighter, content_house, weapon_skill="4")
    fixes = [f for f in build_format_plan() if f.cf_id == str(cf.id)]

    # An admin edits the template after the plan was built
    type(cf).objects.all_content().filter(pk=cf.pk).update(weapon_skill="3+")

    applied, skipped = apply_format_plan(fixes)
    assert applied == []
    assert len(skipped) == 1
    cf.refresh_from_db()
    assert cf.weapon_skill == "3+"


@pytest.mark.django_db
def test_materialise_preserves_the_rendered_statline_exactly(
    make_content_fighter, content_house, fighter_type
):
    """The whole point: both branches must render identical dicts.

    Includes a blank column (renders '-' in the legacy branch via `or "-"`)
    and a dash and a dice expression (copied verbatim).
    """
    cf = make_cf(
        make_content_fighter,
        content_house,
        ballistic_skill="",  # blank -> '-' row
        toughness="-",
        movement='D6+1"',  # legitimate dice value, verbatim
    )
    before = cf.statline()

    _, created, skipped = run_materialise()
    assert skipped == []
    assert str(cf.id) in {e.cf_id for e in created}

    cf = (
        type(cf).objects.all_content().get(pk=cf.pk)
    )  # fresh instance, statline attached
    assert hasattr(cf, "custom_statline")
    after = cf.statline()

    assert after == before


@pytest.mark.django_db
def test_materialise_covers_all_blank_templates_with_dashes(
    make_content_fighter, content_house, fighter_type
):
    """Stash-like templates get a statline of dashes, not skipped.

    The annotated fast path drops missing rows from the card entirely, so
    every stat needs a row for the three render paths to agree.
    """
    cf = make_cf(
        make_content_fighter,
        content_house,
        type="Stash-like",
        **{s: "" for s in STAT_FIELDS},
    )
    before = cf.statline()

    run_materialise()

    cf = type(cf).objects.all_content().get(pk=cf.pk)
    after = cf.statline()
    assert after == before
    assert all(entry["value"] == "-" for entry in after)
    assert len(after) == 12


@pytest.mark.django_db
def test_fighter_cards_are_unchanged_including_the_annotated_path(
    user, make_list, make_list_fighter, fighter_type
):
    """A real fighter's card, with a legacy override in play, through both
    the plain property and the with_related_data fast path."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Carded Fighter")
    fighter.weapon_skill_override = "2+"
    fighter.save()

    def card(pk):
        plain = ListFighter.objects.get(pk=pk)
        fast = ListFighter.objects.filter(pk=pk).with_related_data().get()
        return (
            [(s.field_name, s.name, s.value, s.highlight) for s in plain.statline],
            [(s.field_name, s.name, s.value, s.highlight) for s in fast.statline],
        )

    before_plain, before_fast = card(fighter.pk)
    assert before_plain == before_fast

    run_materialise()

    after_plain, after_fast = card(fighter.pk)
    assert after_plain == before_plain
    assert after_fast == before_fast
    # The override survives: no EAV override row exists, so the legacy
    # field is still the fallback
    assert any(x[0] == "weapon_skill" and x[2] == "2+" for x in after_plain)


@pytest.mark.django_db
def test_materialise_is_idempotent(make_content_fighter, content_house, fighter_type):
    make_cf(make_content_fighter, content_house)
    _, created_first, _ = run_materialise()
    assert created_first

    _, created_second, _ = run_materialise()
    assert created_second == []


@pytest.mark.django_db
def test_a_template_gaining_a_statline_mid_run_is_skipped(
    make_content_fighter, content_house, fighter_type
):
    cf = make_cf(make_content_fighter, content_house)
    entries = [e for e in build_statline_plan() if e.cf_id == str(cf.id)]

    # A statline appears between planning and applying (pack editor, admin)
    ContentStatline.objects.create(content_fighter=cf, statline_type=fighter_type)

    created, skipped = apply_statline_plan(entries)
    assert created == []
    assert len(skipped) == 1
    # The concurrent statline is untouched — no rows were force-written
    assert cf.custom_statline.stats.count() == 0


@pytest.mark.django_db
def test_runs_record_their_outcomes(make_content_fighter, content_house, fighter_type):
    make_cf(make_content_fighter, content_house, weapon_skill="4")

    record, applied, _ = run_normalise()
    assert record.operation == Backfill.Operation.NORMALISE_STAT_FORMATS
    assert record.status == Backfill.Status.DONE
    assert record.summary["applied"] == len(applied) >= 1
    ours = [c for c in record.summary["changes"] if c["stat"] == "weapon_skill"]
    assert ours and ours[0]["new"] == "4+"

    record, created, _ = run_materialise()
    assert record.operation == Backfill.Operation.MATERIALISE_STATLINES
    assert record.summary["created"] == len(created) >= 1


@pytest.mark.django_db
def test_values_are_copied_verbatim_including_whitespace(
    make_content_fighter, content_house, fighter_type
):
    """Verbatim means verbatim: stripping is only for deciding blankness."""
    cf = make_cf(make_content_fighter, content_house, weapon_skill="4+ ")

    run_materialise()

    cf = type(cf).objects.all_content().get(pk=cf.pk)
    row = cf.custom_statline.stats.get(
        statline_type_stat__stat__field_name="weapon_skill"
    )
    assert row.value == "4+ "


@pytest.mark.django_db
def test_a_failed_run_records_failed_and_raises(make_content_fighter, content_house):
    """No Fighter statline type -> the run fails loudly AND leaves a record."""
    make_cf(make_content_fighter, content_house)

    with pytest.raises(RuntimeError):
        run_materialise()

    record = Backfill.objects.get(operation=Backfill.Operation.MATERIALISE_STATLINES)
    assert record.status == Backfill.Status.FAILED
    # The exception and traceback are on the record, like every other
    # maintenance operation — a bare FAILED is undiagnosable after the fact
    assert "ContentStatlineType" in record.error
    assert "Traceback" in record.error


@pytest.mark.django_db
def test_runs_are_visible_as_running_while_in_flight(
    make_content_fighter, content_house, fighter_type, monkeypatch
):
    """The record exists as RUNNING during the apply, so the guard is real."""
    import n23.core.maintenance.statlines as mod

    make_cf(make_content_fighter, content_house)
    seen = {}

    real_apply = mod.apply_statline_plan

    def spying_apply(entries):
        seen["running"] = Backfill.objects.filter(
            operation=Backfill.Operation.MATERIALISE_STATLINES,
            status=Backfill.Status.RUNNING,
        ).exists()
        return real_apply(entries)

    monkeypatch.setattr(mod, "apply_statline_plan", spying_apply)
    run_materialise()
    assert seen["running"] is True


@pytest.mark.django_db
def test_a_content_edit_between_planning_and_applying_is_not_frozen(
    make_content_fighter, content_house, fighter_type
):
    """The statline outranks the columns the moment it exists, so it must be
    written from the values at write time, not planning time."""
    cf = make_cf(make_content_fighter, content_house)
    entries = [e for e in build_statline_plan() if e.cf_id == str(cf.id)]

    type(cf).objects.all_content().filter(pk=cf.pk).update(toughness="5")

    apply_statline_plan(entries)
    row = cf.custom_statline.stats.get(statline_type_stat__stat__field_name="toughness")
    assert row.value == "5"


@pytest.mark.django_db
def test_an_oversized_value_fails_the_run_loudly(
    make_content_fighter, content_house, fighter_type
):
    """Legacy columns allow 12 chars, statline rows 10 — never truncate."""
    cf = make_cf(make_content_fighter, content_house, movement="123456789012")
    entries = [e for e in build_statline_plan() if e.cf_id == str(cf.id)]

    with pytest.raises(RuntimeError, match="max_length"):
        apply_statline_plan(entries)
    cf = type(cf).objects.all_content().get(pk=cf.pk)
    assert not hasattr(cf, "custom_statline")


@pytest.mark.django_db
def test_an_orphan_eav_override_documents_why_the_preview_warns(
    user, make_list, make_list_fighter, fighter_type
):
    """An EAV override on a statline-less template flips from inert to
    outranking the legacy override when the statline appears. Zero such rows
    exist in prod; the materialise preview counts them so an operator sees
    any that appear before committing."""
    from n23.core.models.list import ListFighterStatOverride

    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Orphan EAV Fighter")
    fighter.weapon_skill_override = "2+"
    fighter.save()
    ws = fighter_type.stats.get(stat__field_name="weapon_skill")
    ListFighterStatOverride.objects.create(
        list_fighter=fighter, content_stat=ws, value="6+", owner=user
    )

    assert shown(fighter, "weapon_skill") == "2+"  # EAV row inert today

    run_materialise()

    assert shown(fighter, "weapon_skill") == "6+"  # now it outranks


def shown(fighter, stat):
    from n23.core.models.list import ListFighter

    fresh = ListFighter.objects.get(pk=fighter.pk)
    for entry in fresh.statline:
        if entry.field_name == stat:
            return entry.value
    raise AssertionError(f"{stat} missing")


@pytest.mark.django_db
def test_stats_form_shows_and_migrates_a_legacy_override(
    client, user, make_list, make_list_fighter, fighter_type
):
    """C1→C2 window: the owner must be able to see AND clear their override.

    Before: post-materialise the EAV form rendered empty while the card kept
    showing the legacy value, and blanking the form did not clear it.
    """
    from n23.core.models.list import ListFighterStatOverride

    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Windowed Fighter")
    fighter.weapon_skill_override = "2+"
    fighter.save()
    run_materialise()

    client.force_login(user)
    url = f"/n23/list/{lst.id}/fighter/{fighter.id}/stats"
    response = client.get(url)
    assert response.status_code == 200
    ws_field = [
        f
        for f in response.context["form"].fields.values()
        if getattr(f, "stat_def", None) is not None
        and f.stat_def.field_name == "weapon_skill"
    ]
    assert ws_field and ws_field[0].initial == "2+"

    # Saving with every field blank genuinely clears the override
    response = client.post(url, {})
    assert response.status_code == 302
    fighter.refresh_from_db()
    assert fighter.weapon_skill_override is None
    assert not ListFighterStatOverride.objects.filter(list_fighter=fighter).exists()
    assert shown(fighter, "weapon_skill") != "2+"


@pytest.mark.django_db
def test_normalise_skips_a_template_that_gained_a_statline_mid_run(
    make_content_fighter, content_house, fighter_type
):
    """The statline copied the old value; updating the dead column would
    silently diverge from what the card now shows."""
    cf = make_cf(make_content_fighter, content_house, weapon_skill="4")
    fixes = [f for f in build_format_plan() if f.cf_id == str(cf.id)]

    ContentStatline.objects.create(content_fighter=cf, statline_type=fighter_type)

    applied, skipped = apply_format_plan(fixes)
    assert applied == []
    assert len(skipped) == 1
    cf.refresh_from_db()
    assert cf.weapon_skill == "4"
