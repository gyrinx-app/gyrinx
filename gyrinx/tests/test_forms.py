"""Grouped choice fields, ordering and widget-specific empty choices."""

import pytest
from django import forms

from gyrinx.forms import group_select, group_sorter
from gyrinx.widgets import BsCheckboxSelectMultipleCompact
from n23.content.models import ContentFighter, ContentHouse
from n23.core.forms.terms import fighter_group_key
from n23.models import FighterCategoryChoices


@pytest.mark.django_db
def test_group_select_basic():

    house1 = ContentHouse.objects.create(name="House Goliath")
    house2 = ContentHouse.objects.create(name="House Escher")

    fighter1 = ContentFighter.objects.create(
        type="Ganger", category=FighterCategoryChoices.GANGER, house=house1
    )
    fighter2 = ContentFighter.objects.create(
        type="Champion", category=FighterCategoryChoices.CHAMPION, house=house1
    )
    fighter3 = ContentFighter.objects.create(
        type="Ganger", category=FighterCategoryChoices.GANGER, house=house2
    )

    class TestForm(forms.Form):
        fighter = forms.ModelChoiceField(
            queryset=ContentFighter.objects.all().order_by("house__name", "type")
        )

    form = TestForm()

    group_select(form, "fighter", key=lambda x: x.house.name)

    choices = form.fields["fighter"].widget.choices

    assert len(choices) == 3
    assert choices[0] == ("", "---------")

    assert choices[1][0] == "House Escher"
    assert len(choices[1][1]) == 1
    assert choices[1][1][0][0] == fighter3.id

    assert choices[2][0] == "House Goliath"
    assert len(choices[2][1]) == 2
    assert {item[0] for item in choices[2][1]} == {fighter1.id, fighter2.id}


@pytest.mark.django_db
def test_group_select_with_sorting():

    house1 = ContentHouse.objects.create(name="House Goliath")
    house2 = ContentHouse.objects.create(name="House Escher")
    house3 = ContentHouse.objects.create(name="House Orlock")

    ContentFighter.objects.create(
        type="Ganger", category=FighterCategoryChoices.GANGER, house=house1
    )
    ContentFighter.objects.create(
        type="Ganger", category=FighterCategoryChoices.GANGER, house=house2
    )
    ContentFighter.objects.create(
        type="Ganger", category=FighterCategoryChoices.GANGER, house=house3
    )

    class TestForm(forms.Form):
        fighter = forms.ModelChoiceField(queryset=ContentFighter.objects.all())

    form = TestForm()

    group_select(
        form,
        "fighter",
        key=lambda x: x.house.name,
        sort_groups_by=group_sorter("House Goliath"),
    )

    choices = form.fields["fighter"].widget.choices

    assert choices[1][0] == "House Goliath"
    assert choices[2][0] == "House Escher"
    assert choices[3][0] == "House Orlock"


@pytest.mark.django_db
def test_group_select_with_custom_label():

    house = ContentHouse.objects.create(name="House Goliath")
    ContentFighter.objects.create(
        type="Ganger", category=FighterCategoryChoices.GANGER, house=house, base_cost=50
    )

    class CustomField(forms.ModelChoiceField):
        def label_from_instance(self, obj):
            return f"{obj.type} - {obj.base_cost}¢"

    class TestForm(forms.Form):
        pass

    form = TestForm()
    form.fields["fighter"] = CustomField(queryset=ContentFighter.objects.all())

    group_select(form, "fighter", key=lambda x: x.house.name)

    choices = form.fields["fighter"].widget.choices
    assert choices[1][1][0][1] == "Ganger - 50¢"


@pytest.mark.django_db
def test_group_select_with_multiple_widget():

    house = ContentHouse.objects.create(name="House Goliath")
    ContentFighter.objects.create(
        type="Ganger", category=FighterCategoryChoices.GANGER, house=house
    )

    class TestForm(forms.Form):
        fighters = forms.ModelMultipleChoiceField(
            queryset=ContentFighter.objects.all(), widget=forms.CheckboxSelectMultiple()
        )

    form = TestForm()
    group_select(form, "fighters", key=lambda x: x.house.name)

    choices = form.fields["fighters"].widget.choices

    assert choices[0][0] == "House Goliath"
    assert len(choices) == 1


@pytest.mark.django_db
def test_group_select_with_compact_multiple_widget():
    """Do not add a single-choice empty option to a compact multiple-choice widget."""
    house = ContentHouse.objects.create(name="House Goliath")
    ContentFighter.objects.create(
        type="Ganger", category=FighterCategoryChoices.GANGER, house=house
    )

    class TestForm(forms.Form):
        fighters = forms.ModelMultipleChoiceField(
            queryset=ContentFighter.objects.all(),
            widget=BsCheckboxSelectMultipleCompact(attrs={"class": "form-check-input"}),
        )

    form = TestForm()
    group_select(form, "fighters", key=lambda x: x.house.name)

    choices = form.fields["fighters"].widget.choices

    assert choices[0][0] == "House Goliath"
    assert len(choices) == 1
    assert not any(key == "" for key, _ in choices)


@pytest.mark.django_db
def test_fighter_group_key():

    house = ContentHouse.objects.create(name="House Goliath")
    fighter = ContentFighter.objects.create(
        type="Ganger", category=FighterCategoryChoices.GANGER, house=house
    )

    assert fighter_group_key(fighter) == "House Goliath"


def test_group_sorter():

    sorter = group_sorter("House Goliath")

    assert sorter("House Goliath") == (0, "House Goliath")

    assert sorter("House Escher") == (1, "House Escher")
    assert sorter("House Orlock") == (1, "House Orlock")

    groups = ["House Orlock", "House Goliath", "House Escher"]
    sorted_groups = sorted(groups, key=sorter)

    assert sorted_groups == ["House Goliath", "House Escher", "House Orlock"]


@pytest.mark.django_db
def test_group_select_merge_adjacent_groups():

    house1 = ContentHouse.objects.create(name="House Goliath")
    house2 = ContentHouse.objects.create(name="House Escher")

    fighter1 = ContentFighter.objects.create(
        type="Ganger", category=FighterCategoryChoices.GANGER, house=house1
    )
    fighter2 = ContentFighter.objects.create(
        type="Champion", category=FighterCategoryChoices.CHAMPION, house=house1
    )
    fighter3 = ContentFighter.objects.create(
        type="Leader", category=FighterCategoryChoices.LEADER, house=house2
    )
    fighter4 = ContentFighter.objects.create(
        type="Specialist", category=FighterCategoryChoices.SPECIALIST, house=house2
    )

    class TestForm(forms.Form):
        fighter = forms.ModelChoiceField(
            # Interleave houses in the input so grouping must merge them after sorting.
            queryset=ContentFighter.objects.all().order_by("type")
        )

    form = TestForm()

    group_select(
        form,
        "fighter",
        key=lambda x: x.house.name,
        sort_groups_by=lambda x: x,  # Sort alphabetically
    )

    choices = form.fields["fighter"].widget.choices

    assert len(choices) == 3

    escher_group = next(g for g in choices if g[0] == "House Escher")
    goliath_group = next(g for g in choices if g[0] == "House Goliath")

    escher_ids = {item[0] for item in escher_group[1]}
    goliath_ids = {item[0] for item in goliath_group[1]}

    assert escher_ids == {fighter3.id, fighter4.id}
    assert goliath_ids == {fighter1.id, fighter2.id}


@pytest.mark.django_db
def test_group_select_empty_queryset():

    class TestForm(forms.Form):
        fighter = forms.ModelChoiceField(queryset=ContentFighter.objects.none())

    form = TestForm()
    group_select(form, "fighter", key=lambda x: x.house.name)

    choices = form.fields["fighter"].widget.choices

    assert len(choices) == 1
    assert choices[0] == ("", "---------")


@pytest.mark.django_db
def test_group_select_no_grouping():

    house = ContentHouse.objects.create(name="House Goliath")
    fighter1 = ContentFighter.objects.create(
        type="Ganger", category=FighterCategoryChoices.GANGER, house=house
    )
    fighter2 = ContentFighter.objects.create(
        type="Champion", category=FighterCategoryChoices.CHAMPION, house=house
    )

    class TestForm(forms.Form):
        fighter = forms.ModelChoiceField(
            queryset=ContentFighter.objects.all().order_by("type")
        )

    form = TestForm()

    group_select(form, "fighter")

    choices = form.fields["fighter"].widget.choices

    assert len(choices) == 3
    assert choices[0] == ("", "---------")

    choice_ids = {choices[1][1][0][0], choices[2][1][0][0]}
    assert choice_ids == {fighter1.id, fighter2.id}

    assert len(choices[1][1]) == 1
    assert len(choices[2][1]) == 1


@pytest.mark.django_db
def test_group_select_with_none_values():

    fighter1 = ContentFighter.objects.create(
        type="Mercenary", category=FighterCategoryChoices.GANGER, house=None
    )

    house = ContentHouse.objects.create(name="House Goliath")
    ContentFighter.objects.create(
        type="Ganger", category=FighterCategoryChoices.GANGER, house=house
    )

    class TestForm(forms.Form):
        fighter = forms.ModelChoiceField(
            queryset=ContentFighter.objects.all().order_by("type")
        )

    form = TestForm()

    group_select(form, "fighter", key=lambda x: x.house.name if x.house else "No House")

    choices = form.fields["fighter"].widget.choices

    assert len(choices) == 3

    no_house_group = next(g for g in choices if g[0] == "No House")
    assert len(no_house_group[1]) == 1
    assert no_house_group[1][0][0] == fighter1.id


def test_group_sorter_edge_cases():

    sorter = group_sorter("")

    assert sorter("") == (0, "")
    assert sorter("House Goliath") == (1, "House Goliath")

    sorter_case = group_sorter("house goliath")
    assert sorter_case("house goliath") == (0, "house goliath")
    assert sorter_case("House Goliath") == (1, "House Goliath")

    sorter_special = group_sorter("House-Goliath")
    assert sorter_special("House-Goliath") == (0, "House-Goliath")
    assert sorter_special("House Goliath") == (1, "House Goliath")
