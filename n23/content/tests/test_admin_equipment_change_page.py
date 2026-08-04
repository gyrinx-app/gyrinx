"""Tests for the ContentEquipment admin change page.

The page renders several selects over the whole content library — every
fighter, every modification — once per inline row. Building those option lists
per row made the page issue thousands of queries; these tests pin the flat
behaviour down.
"""

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from n23.content.admin import ContentEquipmentAdmin
from n23.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentFighterProfile,
    ContentEquipmentUpgrade,
    ContentMod,
    ContentModFighterRule,
    ContentModFighterStat,
    ContentModStat,
    ContentModTrait,
    ContentRule,
    ContentStat,
    ContentWeaponTrait,
)
from gyrinx.query import capture_queries

User = get_user_model()


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="admin", email="admin@test.com", password="testpass"
    )


@pytest.fixture
def equipment_category(db):
    return ContentEquipmentCategory.objects.create(name="Test Gear", group="Gear")


@pytest.fixture
def equipment(equipment_category):
    return ContentEquipment.objects.create(
        name="Test Equipment", category=equipment_category, cost="10"
    )


def _equipment_form_class(admin_user, equipment):
    """The model form the admin actually builds (ContentEquipmentAdminForm is a
    mixin over a generated ModelForm, so it has no model of its own)."""
    request = RequestFactory().get("/")
    request.user = admin_user
    admin = ContentEquipmentAdmin(ContentEquipment, AdminSite())
    return admin.get_form(request, equipment)


def _render_change_page(admin_user, equipment):
    request = RequestFactory().get(
        f"/admin/content/contentequipment/{equipment.pk}/change/"
    )
    request.user = admin_user

    admin = ContentEquipmentAdmin(ContentEquipment, AdminSite())
    response = admin.change_view(request, str(equipment.pk))
    if hasattr(response, "render"):
        response.render()
    return response


def _make_fighter_mods(count):
    """A handful of fighter-affecting modifications of assorted types."""
    ContentStat.objects.get_or_create(
        field_name="movement",
        defaults={"short_name": "M", "full_name": "Movement"},
    )
    mods = []
    for i in range(count):
        mods.append(
            ContentModFighterStat.objects.create(
                stat="movement", mode="improve", value=str(i + 1)
            )
        )
        rule = ContentRule.objects.create(name=f"Rule {i}")
        mods.append(ContentModFighterRule.objects.create(rule=rule, mode="add"))
    return mods


@pytest.mark.django_db
def test_change_page_query_count_does_not_scale_with_rows(
    admin_user, equipment_category, content_house, make_content_fighter
):
    """Regression: the page must not rebuild its option lists per inline row.

    Fighter selects, and the modifications select on every upgrade row, used to
    be assembled inside each row's form — one pass over every fighter (with an
    N+1 on house) and every modification (with an N+1 on each modification's
    related objects) for each row on the page. Rendering the same content with
    more rows should therefore cost the same number of queries.
    """
    fighters = [
        make_content_fighter(
            type=f"Fighter {i}",
            category="GANGER",
            house=content_house,
            base_cost=50,
        )
        for i in range(30)
    ]
    mods = _make_fighter_mods(10)

    def build(name, rows):
        equipment = ContentEquipment.objects.create(
            name=name, category=equipment_category, cost="10"
        )
        for fighter in fighters[:rows]:
            ContentEquipmentFighterProfile.objects.create(
                equipment=equipment, content_fighter=fighter
            )
        for i in range(rows):
            upgrade = ContentEquipmentUpgrade.objects.create(
                equipment=equipment, name=f"Upgrade {i}", position=i, cost=5
            )
            upgrade.modifiers.set(mods[:4])
        equipment.modifiers.set(mods[:3])
        return equipment

    small = build("Few Rows", 2)
    large = build("Many Rows", 8)

    _, small_info = capture_queries(lambda: _render_change_page(admin_user, small))
    _, large_info = capture_queries(lambda: _render_change_page(admin_user, large))

    # Four times the rows must not mean four times the queries: the option
    # lists are built once, and the rows themselves are select_related /
    # prefetched, so the count should be flat but for a little slack.
    assert large_info.count <= small_info.count + 2, (
        f"queries scale with rows: {small_info.count} at 2 rows, "
        f"{large_info.count} at 8 rows"
    )
    assert large_info.count < 100, f"too many queries: {large_info.count}"


@pytest.mark.django_db
def test_change_page_renders_grouped_and_preselected_fighter(
    admin_user, equipment, content_house, make_content_fighter
):
    """Sharing one option list across rows must not lose grouping or selection."""
    fighter = make_content_fighter(
        type="Profile Fighter",
        category="GANGER",
        house=content_house,
        base_cost=50,
    )
    ContentEquipmentFighterProfile.objects.create(
        equipment=equipment, content_fighter=fighter
    )

    response = _render_change_page(admin_user, equipment)
    assert response.status_code == 200

    html = response.content.decode()
    assert f'<optgroup label="{content_house.name}">' in html
    assert f'value="{fighter.pk}" selected' in html


@pytest.mark.django_db
def test_change_page_preselects_modifiers(admin_user, equipment):
    """The modifications already on the equipment render as selected options."""
    mods = _make_fighter_mods(2)
    equipment.modifiers.set(mods)

    html = _render_change_page(admin_user, equipment).content.decode()
    for mod in mods:
        assert f'value="{mod.pk}" selected' in html


@pytest.mark.django_db
def test_modifiers_field_offers_only_fighter_modifications(admin_user, equipment):
    """Weapon-only modification types stay out of the equipment's list."""
    fighter_mod = ContentModFighterStat.objects.create(
        stat="movement", mode="improve", value="1"
    )
    weapon_mod = ContentModStat.objects.create(
        stat="strength", mode="improve", value="1"
    )

    form = _equipment_form_class(admin_user, equipment)(instance=equipment)
    offered = {str(pk) for pk, _label in form.fields["modifiers"].widget.choices}

    assert str(fighter_mod.pk) in offered
    assert str(weapon_mod.pk) not in offered
    # The queryset backs validation, so it must agree with what is offered.
    assert form.fields["modifiers"].queryset.filter(pk=weapon_mod.pk).count() == 0


@pytest.mark.django_db
def test_modifiers_can_still_be_saved(admin_user, equipment, equipment_category):
    """Overriding the widget's choices must not break validation or saving."""
    mods = _make_fighter_mods(2)

    form = _equipment_form_class(admin_user, equipment)(
        data={
            "name": equipment.name,
            "category": str(equipment_category.pk),
            "cost": "10",
            "rarity": "C",
            "modifiers": [str(mod.pk) for mod in mods],
            "upgrade_mode": ContentEquipment.UpgradeMode.SINGLE,
        },
        instance=equipment,
    )

    assert form.is_valid(), form.errors
    form.save()
    assert set(equipment.modifiers.all()) == set(mods)


@pytest.mark.django_db
def test_prime_stat_definitions_avoids_a_query_per_modification():
    """Labelling many fighter stat modifications costs one stat query, not N."""
    _make_fighter_mods(5)
    mods = list(ContentModFighterStat.objects.all())

    def label_all():
        ContentModFighterStat.prime_stat_definitions(mods)
        return [str(mod) for mod in mods]

    labels, info = capture_queries(label_all)

    assert len(labels) == 5
    assert all("Movement" in label for label in labels)
    assert info.count == 1, f"expected a single stat query, got {info.count}"


@pytest.mark.django_db
def test_every_modification_type_gets_an_option():
    """A modification with no <option> would be silently cleared on save.

    ``MODIFIER_LABEL_LOADERS`` is an optimisation, so the choice builder must
    cover every concrete type in the queryset — including any added later that
    nobody remembered to list there.
    """
    from django import forms

    from n23.content.admin import MODIFIER_LABEL_LOADERS, modifier_choices

    _make_fighter_mods(2)
    ContentModStat.objects.create(stat="strength", mode="improve", value="1")
    ContentModTrait.objects.create(
        trait=ContentWeaponTrait.objects.create(name="Unwieldy"), mode="add"
    )

    field = forms.ModelMultipleChoiceField(queryset=ContentMod.objects.all())
    offered = {str(pk) for pk, _label in modifier_choices(field)}
    everything = {str(pk) for pk in ContentMod.objects.values_list("pk", flat=True)}

    assert offered == everything

    # And the loader map itself should stay in step with the model hierarchy,
    # so the common path keeps its select_related.
    def concrete_subclasses(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from concrete_subclasses(sub)

    assert set(concrete_subclasses(ContentMod)) == set(MODIFIER_LABEL_LOADERS)
