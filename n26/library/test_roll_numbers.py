"""Numbered skills and powers share one D6 table within their category."""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from n26.library import authoring as a
from n26.library.forms import generate_form
from n26.library.models import Power, Skill
from n26.library.specs import specs

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("kind", [Skill, Power])
def test_authors_can_create_and_edit_numbered_results_and_clear_them(
    default_pack, kind
):
    category = a.create_category("Skills & Powers", "Numbered family")
    form_class = generate_form(specs()[f"create_{kind._meta.model_name}"])
    form = form_class(
        {"name": "Numbered result", "category": str(category.pk), "position": 6}
    )
    assert form.is_valid(), form.errors
    assert form.fields["position"].label == "D6 roll number"
    assert form.fields["position"].max_value == 6
    thing = form.compile()
    assert thing.position == 6
    payload = {
        "edit-name": thing.name,
        "edit-category": str(category.pk),
        "edit-position": 0,
    }
    edit = form_class.opened_on(thing, payload)
    assert edit.is_valid(), edit.errors
    edit.apply_to(thing)
    thing.refresh_from_db()
    assert thing.position == 0
    blank = form_class(
        {"name": "Unnumbered result", "category": str(category.pk), "position": ""}
    )
    assert blank.is_valid(), blank.errors
    assert blank.compile().position == 0


@pytest.mark.parametrize("kind", [Skill, Power])
@pytest.mark.parametrize("number", [-1, 7])
def test_forms_and_verbs_reject_results_outside_zero_to_six(default_pack, kind, number):
    form = generate_form(specs()[f"create_{kind._meta.model_name}"])(
        {"name": "Bad result", "position": number}
    )
    assert not form.is_valid()
    assert "position" in form.errors
    with pytest.raises(ValidationError):
        getattr(a, f"create_{kind._meta.model_name}")("Bad result", position=number)
    assert not kind.objects.filter(name="Bad result").exists()


@pytest.mark.parametrize(
    "first_kind, second_kind",
    [(Skill, Skill), (Power, Power), (Skill, Power), (Power, Skill)],
)
def test_a_number_can_have_only_one_active_result_across_both_kinds(
    default_pack, first_kind, second_kind
):
    category = a.create_category("Skills & Powers", "Shared family")
    first = getattr(a, f"create_{first_kind._meta.model_name}")(
        "First", category=category, position=2
    )
    create = getattr(a, f"create_{second_kind._meta.model_name}")
    with pytest.raises(ValidationError, match="already uses D6 result 2"):
        create("Second", category=category, position=2)
    second = create("Second", category=category)
    with pytest.raises(ValidationError, match="already uses D6 result 2"):
        a.revise(second, position=2)
    second.refresh_from_db()
    assert second.position == 0
    a.revise(first, archived=True)
    a.revise(second, position=2)
    assert second.position == 2


def test_multiple_non_rollable_results_and_gaps_are_preserved(default_pack):
    family = a.create_category("Powers", "Family")
    a.create_power("First", category=family)
    a.create_power("Second", category=family)
    a.create_power("Third", category=family, position=3)
    a.create_power(
        "Elsewhere", category=a.create_category("Powers", "Other"), position=3
    )
    with pytest.raises(ValidationError, match="Choose a category"):
        a.create_power("No family", position=1)


@pytest.mark.parametrize("kind", ["skill", "power"])
def test_authoring_pages_save_and_display_roll_numbers(
    client, admin_user, default_pack, kind
):
    client.force_login(admin_user)
    category = a.create_category("Skills & Powers", f"{kind} family")
    url = reverse("authoring-create", args=[kind])
    response = client.post(
        url, {"name": "Rollable", "category": str(category.pk), "position": 4}
    )
    assert response.status_code == 302, response.content.decode()
    model = Skill if kind == "skill" else Power
    thing = model.objects.get(name="Rollable")
    assert thing.position == 4
    page = client.get(response.url)
    assert 'name="edit-position"' in page.content.decode()
    listing = client.get(reverse("authoring-leaf", args=[kind]))
    assert "rolled on a 4" in listing.content.decode()
    duplicate = client.post(
        url, {"name": "Duplicate", "category": str(category.pk), "position": 4}
    )
    assert duplicate.status_code == 200
    assert "already uses D6 result 4" in duplicate.content.decode()
    assert not model.objects.filter(name="Duplicate").exists()
    other = getattr(a, f"create_{kind}")("Other", category=category)
    duplicate_edit = client.post(
        reverse("authoring-detail", args=[kind, other.pk]),
        {
            "act": "edit",
            "edit-name": other.name,
            "edit-category": str(category.pk),
            "edit-position": 4,
        },
    )
    assert duplicate_edit.status_code == 200
    assert "already uses D6 result 4" in duplicate_edit.content.decode()
    other.refresh_from_db()
    assert other.position == 0
