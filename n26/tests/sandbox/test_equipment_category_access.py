"""Profiles narrow their equipment list by category while exceptions stay available."""

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.access import hidden_categories_for
from n26.core.card import build_card, build_modifier_index, carriers
from n26.core.effects import compute
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.core.views.equip import ALL_SCOPE, _screen
from n26.library import authoring as a
from n26.library.forms import ModifierComposerForm, generate_form
from n26.library.specs import specs
from n26.tests.sandbox.actions import buy, found_gang, hire

pytestmark = pytest.mark.django_db


@pytest.fixture
def equipment(default_pack, person_type, make_statline):
    owner = User.objects.create_user("category-player")
    house = a.create_gang_type("Hunters", starting_credits=1000)
    collection = a.create_collection("Hunting equipment")
    alternative = a.create_collection("Other equipment")
    categories = [a.create_category("Equipment", name) for name in ("Rigs", "Blades")]
    same_name = a.create_category("Other equipment", "Blades")
    gear = [
        a.create_wargear(name, price=20, category=category)
        for name, category in zip(
            ("Hunting rig", "Naga blade", "Other blade"),
            (*categories, same_name),
            strict=True,
        )
    ]
    for item in gear:
        a.add_entry(collection, item)
        a.add_entry(alternative, item)
    a.add_built_in(house, collection)
    a.add_built_in(house, alternative)
    profile = a.create_profile("Hunter", person_type, house, price=100)
    other_profile = a.create_profile("Other hunter", person_type, house, price=100)
    make_statline(profile)
    make_statline(other_profile)
    a.modifier(
        "Hunter hides blades",
        a.targets_model(),
        a.ef_hides_categories(collection, [categories[1]]),
        attach_to=profile,
    )
    gang = found_gang("The Hunt", house, owner=owner, budget=1000)
    model = hire(gang, profile, "Vex")
    other = hire(gang, other_profile, "Ash")
    return SimpleNamespace(
        owner=owner,
        gang=gang,
        profile=profile,
        model=model,
        other=other,
        collection=collection,
        alternative=alternative,
        categories=categories,
        gear=gear,
    )


def offered(equipment, *, model=None, collection=None):
    screen = _screen(
        equipment.gang,
        miniature=model or equipment.model,
        list_param=str((collection or equipment.collection).pk),
        budgets=False,
    )
    return {line.thing.pk for line in screen.view.all_lines()}


class TestEquipmentCategoryAccess:
    """A profile narrows one list without changing ownership or other lists."""

    def test_the_restriction_is_for_one_model_and_one_list(self, equipment):
        e = equipment
        assert offered(e) == {e.gear[0].pk, e.gear[2].pk}
        assert offered(e, model=e.other) == {item.pk for item in e.gear}
        assert offered(e, collection=e.alternative) == {item.pk for item in e.gear}

    def test_unrestricted_and_stash_browsing_still_offer_the_hidden_category(
        self, equipment
    ):
        e = equipment
        unrestricted = _screen(
            e.gang, miniature=e.model, list_param=ALL_SCOPE, budgets=False
        )
        stash = _screen(e.gang, list_param=str(e.collection.pk), budgets=False)
        for screen in (unrestricted, stash):
            assert e.gear[1].pk in {line.thing.pk for line in screen.view.all_lines()}

    def test_reading_the_effect_and_its_provenance_never_queries(
        self, equipment, django_assert_num_queries
    ):
        e = equipment
        card = build_card(e.model)
        index = build_modifier_index(carriers(card))
        with django_assert_num_queries(0):
            computed = compute(card, index)
            assert hidden_categories_for(e.collection, computed) == {e.categories[1]}
            assert computed.hidden_categories[0].source == "Hunter"
            assert "hides Blades from Hunting equipment" in str(computed.plan[0])

    def test_removing_a_carrier_restores_only_its_hidden_categories(self, equipment):
        e = equipment
        carrier = a.create_wargear("Rig restriction")
        a.modifier(
            "Hide rigs",
            a.targets_model(),
            a.ef_hides_categories(e.collection, [e.categories[0]]),
            attach_to=carrier,
        )
        held = buy(e.model, thing=carrier, paid=0)
        assert offered(e) == {e.gear[2].pk}
        with operation(e.gang, actor=e.owner) as op:
            op.remove(held)
        assert offered(e) == {e.gear[0].pk, e.gear[2].pk}
        assert_reconciled(e.gang)

    def test_a_computed_carrier_can_supply_and_retract_the_restriction(self, equipment):
        e = equipment
        hidden = a.create_hidden("Restricted rig access")
        a.modifier(
            "Hidden rig restriction",
            a.targets_model(),
            a.ef_hides_categories(e.collection, [e.categories[0]]),
            attach_to=hidden,
        )
        carrier = a.create_wargear("Restriction source")
        a.modifier(
            "Give rig restriction",
            a.targets_model(),
            a.ef_adds(hidden),
            attach_to=carrier,
        )
        remover = a.create_wargear("Restriction exception")
        a.modifier(
            "Remove rig restriction",
            a.targets_model(),
            a.ef_removes(hidden),
            attach_to=remover,
        )
        buy(e.model, thing=carrier, paid=0)
        assert offered(e) == {e.gear[2].pk}
        buy(e.model, thing=remover, paid=0)
        assert offered(e) == {e.gear[0].pk, e.gear[2].pk}
        assert_reconciled(e.gang)

    def test_equipment_already_owned_keeps_its_assignment_and_rating(
        self, equipment, client
    ):
        e = equipment
        held = buy(e.model, thing=e.gear[1], paid=20)
        e.gang.refresh_from_db()
        before = (e.gang.rating, e.gang.credits)
        client.force_login(e.owner)
        response = client.get(
            reverse("n26-equip", args=[e.model.pk]), {"list": str(e.collection.pk)}
        )
        assert response.status_code == 200
        assert {row.name for row in response.context["catalogue"].all_rows()} == {
            e.gear[0].name,
            e.gear[2].name,
        }
        held.refresh_from_db()
        e.gang.refresh_from_db()
        assert not held.archived
        assert held.miniature_root_id == e.model.pk
        assert (e.gang.rating, e.gang.credits) == before
        assert_reconciled(e.gang)

    def test_a_purchase_uses_the_selected_list_and_allows_an_unrestricted_exception(
        self, equipment, client
    ):
        e = equipment
        client.force_login(e.owner)
        url = reverse("n26-equip", args=[e.model.pk])
        key = f"{e.gear[1]._meta.label_lower}:{e.gear[1].pk}"
        before = e.model.assignments.count()
        response = client.post(f"{url}?list={e.collection.pk}", {"thing": key})
        assert response.status_code == 302
        assert e.model.assignments.count() == before
        response = client.post(f"{url}?list={ALL_SCOPE}", {"thing": key})
        assert response.status_code == 302
        assert e.model.assignments.filter(wargear=e.gear[1], archived=False).exists()
        e.gang.refresh_from_db()
        assert_reconciled(e.gang)

    def test_more_restrictions_do_not_add_per_modifier_queries(self, equipment, client):
        e = equipment
        client.force_login(e.owner)
        url = reverse("n26-equip", args=[e.model.pk])

        def measure():
            with CaptureQueriesContext(connection) as queries:
                response = client.get(url, {"list": str(e.collection.pk)})
                assert response.status_code == 200
            return len(queries)

        measure()
        before = measure()
        for i in range(4):
            a.modifier(
                f"Extra restriction {i}",
                a.targets_model(),
                a.ef_hides_categories(e.collection, [e.categories[1]]),
                attach_to=e.profile,
            )
        assert measure() == before


class TestAuthoringCategoryRestrictions:
    """Authors can create and reopen the effect through the modifier composer."""

    def test_the_effect_form_requires_categories_and_reopens_its_selections(
        self, equipment
    ):
        e = equipment
        form_type = generate_form(specs()["ef_hides_categories"])
        blank = form_type({"collection": str(e.collection.pk), "categories": []})
        assert not blank.is_valid()
        assert "categories" in blank.errors
        form = form_type(
            {
                "collection": str(e.collection.pk),
                "categories": [str(category.pk) for category in e.categories],
            }
        )
        assert form.is_valid(), form.errors
        effect = form.compile()
        reopened = form_type.opened_on(effect)
        assert set(reopened.initial["categories"]) == set(e.categories)
        assert reopened.initial["collection"] == e.collection

    def test_the_modifier_composer_attaches_a_restriction_to_a_profile(self, equipment):
        e = equipment
        form = ModifierComposerForm(
            {
                "scope_kind": "targets_model",
                "effect_kind": "ef_hides_categories",
                "what-collection": str(e.collection.pk),
                "what-categories": [str(e.categories[0].pk)],
                "conditions-TOTAL_FORMS": "0",
                "conditions-INITIAL_FORMS": "0",
            },
            attach_to=e.profile,
        )
        assert form.is_valid(), form.errors
        modifier = form.save()
        assert modifier in e.profile.modifiers.all()
        assert offered(e) == {e.gear[2].pk}

    def test_the_authoring_page_describes_and_edits_the_hidden_categories(
        self, equipment, client
    ):
        e = equipment
        e.owner.is_staff = True
        e.owner.save(update_fields=["is_staff"])
        client.force_login(e.owner)
        modifier = e.profile.modifiers.get()
        url = reverse("authoring-modifier", args=[modifier.pk])
        response = client.get(url)
        assert response.status_code == 200
        assert (
            "Blades equipment is hidden from Hunting equipment"
            in response.content.decode()
        )
        response = client.post(
            url,
            {
                "scope_kind": "targets_model",
                "effect_kind": "ef_hides_categories",
                "what-collection": str(e.collection.pk),
                "what-categories": [str(e.categories[0].pk)],
                "conditions-TOTAL_FORMS": "0",
                "conditions-INITIAL_FORMS": "0",
            },
        )
        assert response.status_code == 302
        assert offered(e) == {e.gear[1].pk, e.gear[2].pk}

    def test_authoring_descriptions_load_categories_in_a_batch(
        self, equipment, django_assert_num_queries
    ):
        from n26.library.references import reading_sentences

        modifiers = list(reading_sentences(equipment.profile.modifiers.all()))
        with django_assert_num_queries(0):
            assert str(modifiers[0].effect) == "hides Blades from Hunting equipment"
