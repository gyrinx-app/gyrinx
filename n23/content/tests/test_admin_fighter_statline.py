"""Editing a fighter type's stats on the fighter admin page (#1861)."""

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from gyrinx.models import SMART_QUOTES
from n23.content.admin import ContentFighterAdmin
from n23.content.models import (
    ContentFighter,
    ContentHouse,
    ContentStatline,
    ContentStatlineType,
)
from n23.core.models import List, ListFighter


@pytest.fixture
def house(db):
    return ContentHouse.objects.create(name="Statline House")


@pytest.fixture
def fighter(db, house, make_content_fighter):
    return make_content_fighter(
        type="Statline Ganger",
        category="GANGER",
        house=house,
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


def field_for(fighter, field_name):
    """The admin form's field name for one stat."""
    type_stat = fighter.custom_statline.statline_type.stats.get(
        stat__field_name=field_name
    )
    return f"stat_{type_stat.id}"


def admin_form(fighter, data=None):
    model_admin = ContentFighterAdmin(ContentFighter, AdminSite())
    form_class = model_admin.get_form(RequestFactory().get("/"), fighter, change=True)
    return (
        form_class(data=data, instance=fighter)
        if data
        else form_class(instance=fighter)
    )


def save_through_admin(fighter, data, user=None):
    """Run a bound admin form through the admin's save path.

    Mirrors ModelAdmin._changeform_view: save the instance without committing
    m2m, then save_model, then save_related — which is where the statline
    values are written.
    """
    model_admin = ContentFighterAdmin(ContentFighter, AdminSite())
    request = RequestFactory().post("/")
    request.user = user or AnonymousUser()
    form = admin_form(fighter, data=data)
    assert form.is_valid(), form.errors
    obj = form.save(commit=False)
    model_admin.save_model(request, obj, form, change=True)
    model_admin.save_related(request, form, [], change=True)
    return form


@pytest.mark.django_db
def test_saving_a_fighter_type_gives_it_a_statline(house):
    """Nothing asks for one — the save-time guarantee provides it."""
    fighter = ContentFighter.objects.create(
        type="Fresh Ganger", category="GANGER", house=house, base_cost=50
    )

    statline = ContentStatline.objects.get(content_fighter=fighter)
    assert statline.statline_type.name == "Fighter"
    # Every stat of the type gets a row, so the card can never be ragged
    assert statline.stats.count() == statline.statline_type.stats.count()
    # ...and every one is a dash: there is nowhere for values to come from at
    # creation any more, so they are filled in afterwards.
    assert {stat.value for stat in statline.stats.all()} == {"-"}


@pytest.mark.django_db
def test_the_stats_a_fighter_is_given_land_in_its_statline(fighter):
    """The stat columns are gone, so the statline is the only place the
    values a fighter was created with can be. It is of the type its category
    calls for, and it holds those values."""
    assert fighter.custom_statline.statline_type.name == "Fighter"
    values = {
        stat.statline_type_stat.field_name: stat.value
        for stat in fighter.custom_statline.stats.select_related(
            "statline_type_stat__stat"
        )
    }
    assert values["movement"] == '5"'
    assert values["weapon_skill"] == "4+"
    assert values["strength"] == "3"


@pytest.mark.django_db
def test_the_form_offers_one_field_per_stat_seeded_with_its_value(fighter):
    form = admin_form(fighter)

    assert len(form.stat_fields) == 12
    assert form.fields[field_for(fighter, "movement")].initial == '5"'
    assert form.fields[field_for(fighter, "weapon_skill")].initial == "4+"


@pytest.mark.django_db
def test_the_form_carries_no_bare_stat_name_fields(fighter):
    """Stats reach the form as statline fields, never as model columns.

    The 12 columns they used to live in are gone; a field named plainly after
    a stat would mean something had put them back.
    """
    form = admin_form(fighter)
    for name in ("movement", "weapon_skill", "toughness", "intelligence"):
        assert name not in form.fields


@pytest.mark.django_db
def test_saving_a_stat_formats_it(fighter):
    """A bare number gains the suffix its stat calls for."""
    data = _post_data(fighter, {"weapon_skill": "3", "movement": "6"})
    save_through_admin(fighter, data)

    statline = ContentStatline.objects.get(content_fighter=fighter)
    values = {
        stat.statline_type_stat.field_name: stat.value
        for stat in statline.stats.select_related("statline_type_stat__stat")
    }
    assert values["weapon_skill"] == "3+"
    assert values["movement"] == '6"'


@pytest.mark.django_db
def test_smart_quotes_are_rejected_naming_the_stat(fighter):
    data = _post_data(fighter, {"movement": f"6{SMART_QUOTES['RIGHT_DOUBLE']}"})
    form = admin_form(fighter, data=data)

    assert not form.is_valid()
    assert "Smart quotes are not allowed" in str(
        form.errors[field_for(fighter, "movement")]
    )


@pytest.mark.django_db
def test_an_edit_reaches_a_gang_fighter_card(fighter, house):
    """The point of the exercise: the number an admin types is the number
    players see."""
    lst = List.objects.create(name="Gang", content_house=house)
    list_fighter = ListFighter.objects.create(
        name="Recruit", content_fighter=fighter, list=lst
    )
    before = {stat.field_name: stat.value for stat in list_fighter.statline}
    assert before["weapon_skill"] == "4+"

    save_through_admin(fighter, _post_data(fighter, {"weapon_skill": "2+"}))

    fresh = ListFighter.objects.get(pk=list_fighter.pk)
    after = {stat.field_name: stat.value for stat in fresh.statline}
    assert after["weapon_skill"] == "2+"


@pytest.mark.django_db
def test_switching_statline_type_leaves_no_orphan_values(fighter):
    """Values are keyed to the old type's stats, so they cannot linger."""
    from n23.content.statlines import set_fighter_statline

    vehicle = ContentStatlineType.objects.create(name="Vehicle Type")
    stat = fighter.custom_statline.statline_type.stats.first()
    vehicle.stats.create(stat=stat.stat, position=1)

    set_fighter_statline(fighter, vehicle)

    statline = ContentStatline.objects.get(content_fighter=fighter)
    assert statline.statline_type == vehicle
    assert statline.stats.count() == 1
    # clean() insists on exactly the type's set; nothing left behind
    statline.clean()


def _post_data(fighter, stat_values):
    """A complete admin POST for this fighter, overriding some stats."""
    form = admin_form(fighter)
    data = {
        "type": fighter.type,
        "category": fighter.category,
        "house": str(fighter.house_id),
        "base_cost": str(fighter.base_cost),
    }
    for name in form.stat_fields:
        data[name] = form.fields[name].initial
    for field_name, value in stat_values.items():
        data[field_for(fighter, field_name)] = value
    return data
