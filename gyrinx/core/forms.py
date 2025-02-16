from django import forms

from gyrinx.content.models import (
    ContentEquipment,
    ContentFighter,
    ContentHouse,
    ContentWeaponAccessory,
)
from gyrinx.core.models import List, ListFighter, ListFighterEquipmentAssignment
from gyrinx.forms import group_select


class NewListForm(forms.ModelForm):
    class Meta:
        model = List
        fields = ["name", "content_house", "public"]
        labels = {
            "name": "Name",
            "content_house": "House",
            "public": "Public",
        }
        help_texts = {
            "name": "The name you use to identify this List. This may be public.",
            "public": "If checked, this list will be visible to all users of Gyrinx. You can edit this later.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "content_house": forms.Select(attrs={"class": "form-select"}),
            "public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class CloneListForm(forms.ModelForm):
    class Meta:
        model = List
        fields = ["name", "public"]
        labels = {
            "name": "Name",
            "public": "Public",
        }
        help_texts = {
            "name": "The name you use to identify this List. This may be public.",
            "public": "If checked, this List will be visible to all users of Gyrinx. You can edit this later.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class EditListForm(forms.ModelForm):
    class Meta:
        model = List
        fields = ["name", "public"]
        labels = {
            "name": "Name",
            "public": "Public",
        }
        help_texts = {
            "name": "The name you use to identify this list. This may be public.",
            "public": "If checked, this list will be visible to all users.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ContentFighterChoiceField(forms.ModelChoiceField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", forms.Select(attrs={"class": "form-select"}))
        kwargs.setdefault("label", "Fighter")
        super().__init__(*args, **kwargs)

    def label_from_instance(self, obj):
        return f"{obj.name()}"


class NewListFighterForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = kwargs.get("instance", {})
        if inst:
            generic_houses = ContentHouse.objects.filter(generic=True).values_list(
                "id", flat=True
            )
            self.fields["content_fighter"].queryset = ContentFighter.objects.filter(
                house__in=[inst.list.content_house.id] + list(generic_houses)
            )

            if hasattr(inst, "content_fighter"):
                self.fields["cost_override"].placeholder = inst._base_cost_int()

        self.fields["content_fighter"] = ContentFighterChoiceField(
            queryset=self.fields["content_fighter"].queryset
        )

        group_select(self, "content_fighter", key=lambda x: x.house.name)

    class Meta:
        model = ListFighter
        fields = ["name", "content_fighter", "cost_override"]
        labels = {
            "name": "Name",
            "content_fighter": "Fighter",
            "cost_override": "Manually Set Cost",
        }
        help_texts = {
            "name": "The name you use to identify this Fighter. This may be public.",
            "cost_override": "Only change this if you want to override the default base cost of the Fighter.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "content_fighter": forms.Select(attrs={"class": "form-select"}),
            "cost_override": forms.NumberInput(
                attrs={"class": "form-control", "min": 0}
            ),
        }


class CloneListFighterForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        # user is passed in as a kwarg from the view but is not valid
        # for the ModelForm, so we pop it off before calling super()
        user = kwargs.pop("user", None)

        super().__init__(*args, **kwargs)

        inst = kwargs.get("instance", {})
        if inst:
            self.fields["content_fighter"].queryset = ContentFighter.objects.filter(
                house=inst.list.content_house
            )

        if user:
            self.fields["list"].queryset = List.objects.filter(
                owner=user,
                content_house=inst.list.content_house,
            )

        self.fields["content_fighter"] = ContentFighterChoiceField(
            queryset=self.fields["content_fighter"].queryset
        )

    class Meta:
        model = ListFighter
        fields = ["name", "content_fighter", "list"]
        labels = {
            "name": "Name",
            "content_fighter": "Fighter",
            "list": "List",
        }
        help_texts = {
            "name": "The name you use to identify this Fighter. This may be public.",
            "list": "The List into which this Fighter will be cloned.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "content_fighter": forms.Select(attrs={"class": "form-select"}),
            "list": forms.Select(attrs={"class": "form-select"}),
        }


class SkillsCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    template_name = "pages/forms/widgets/skills_checkbox_select.html"
    option_template_name = "pages/forms/widgets/skills_checkbox_option.html"


class ListFighterSkillsForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        group_select(self, "skills", key=lambda x: x.category)

    class Meta:
        model = ListFighter
        fields = ["skills"]
        labels = {
            "skills": "Skills",
        }
        widgets = {
            "skills": SkillsCheckboxSelectMultiple(
                attrs={"class": "form-check-input"},
            ),
        }


class ListFighterEquipmentField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        cost = (
            obj.cost_override
            if getattr(obj, "cost_override", None) is not None
            else obj.cost
        )
        unit = "¢" if str(cost).strip().isnumeric() else ""
        return f"{obj.name} ({cost}{unit})"


class ListFighterGearForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["equipment"].queryset = self.fields[
            "equipment"
        ].queryset.with_cost_for_fighter(self.instance.content_fighter)

    equipment = ListFighterEquipmentField(
        label="Gear",
        queryset=ContentEquipment.objects.non_weapons(),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check"}),
        help_text="Costs reflect the Fighter's Equipment List.",
        required=False,
    )

    class Meta:
        model = ListFighter
        fields = ["equipment"]


class ListFighterEquipmentAssignmentForm(forms.ModelForm):
    class Meta:
        model = ListFighterEquipmentAssignment
        fields = ["content_equipment", "weapon_profiles_field", "upgrade"]

    # TODO: Add a clean method to ensure that weapon profiles are assigned to the correct equipment


class ListFighterEquipmentAssignmentAccessoriesForm(forms.ModelForm):
    weapon_accessories_field = ListFighterEquipmentField(
        label="Accessories",
        queryset=ContentWeaponAccessory.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check"}),
        help_text="Costs reflect the Fighter's Equipment List.",
        required=False,
    )

    class Meta:
        model = ListFighterEquipmentAssignment
        fields = ["weapon_accessories_field"]
