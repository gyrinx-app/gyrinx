from allauth.account.forms import LoginForm, ResetPasswordForm, SignupForm
from django import forms
from django_recaptcha.fields import ReCaptchaField, ReCaptchaV3

from gyrinx.content.models import ContentFighter, ContentHouse, ContentWeaponAccessory
from gyrinx.core.models import List, ListFighter, ListFighterEquipmentAssignment
from gyrinx.forms import group_select
from gyrinx.models import FighterCategoryChoices


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
    content_house: ContentHouse | None = None

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", forms.Select(attrs={"class": "form-select"}))
        kwargs.setdefault("label", "Fighter")
        super().__init__(*args, **kwargs)

    def label_from_instance(self, obj: ContentFighter):
        cost_for_house = (
            obj.cost_for_house(self.content_house) if self.content_house else obj.cost
        )
        return f"{obj.name()} ({cost_for_house}¢)"


class NewListFighterForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = kwargs.get("instance", {})
        self.fields["content_fighter"] = ContentFighterChoiceField(
            queryset=self.fields["content_fighter"].queryset
        )

        overrides = [
            "movement_override",
            "weapon_skill_override",
            "ballistic_skill_override",
            "strength_override",
            "toughness_override",
            "wounds_override",
            "initiative_override",
            "attacks_override",
            "leadership_override",
            "cool_override",
            "willpower_override",
            "intelligence_override",
        ]

        if inst:
            # Fighters for the house and from generic houses, excluding Exotic Beasts
            # who are added via equipment
            generic_houses = ContentHouse.objects.filter(generic=True).values_list(
                "id", flat=True
            )
            self.fields["content_fighter"].content_house = inst.list.content_house
            self.fields["content_fighter"].queryset = ContentFighter.objects.filter(
                house__in=[inst.list.content_house.id] + list(generic_houses),
            ).exclude(category__in=[FighterCategoryChoices.EXOTIC_BEAST])

            # If the fighter is linked, don't allow the content_fighter to be changed
            if inst.has_linked_fighter:
                self.fields["content_fighter"].queryset = ContentFighter.objects.filter(
                    id=inst.content_fighter.id
                )
                self.fields["content_fighter"].disabled = True

            # The instance only has a content_fighter if it is being edited
            if hasattr(inst, "content_fighter"):
                self.fields["cost_override"].widget.attrs["placeholder"] = (
                    inst._base_cost_int
                )

                for field in overrides:
                    self.fields[field].widget.attrs["placeholder"] = getattr(
                        inst.content_fighter, field.replace("_override", "")
                    )
            else:
                # If no instance is provided, we are creating a new fighter
                # and we don't want to allow the user to override the stats
                for field in overrides:
                    self.fields.pop(field, None)

        group_select(self, "content_fighter", key=lambda x: x.house.name)

    class Meta:
        model = ListFighter
        fields = [
            "name",
            "content_fighter",
            "cost_override",
            "movement_override",
            "weapon_skill_override",
            "ballistic_skill_override",
            "strength_override",
            "toughness_override",
            "wounds_override",
            "initiative_override",
            "attacks_override",
            "leadership_override",
            "cool_override",
            "willpower_override",
            "intelligence_override",
        ]
        labels = {
            "name": "Name",
            "content_fighter": "Fighter",
            "cost_override": "Manually Set Cost",
            "movement_override": "Movement",
            "weapon_skill_override": "Weapon Skill",
            "ballistic_skill_override": "Ballistic Skill",
            "strength_override": "Strength",
            "toughness_override": "Toughness",
            "wounds_override": "Wounds",
            "initiative_override": "Initiative",
            "attacks_override": "Attacks",
            "leadership_override": "Leadership",
            "cool_override": "Cool",
            "willpower_override": "Willpower",
            "intelligence_override": "Intelligence",
        }
        help_texts = {
            "name": "The name you use to identify this Fighter. This may be public.",
            "cost_override": "Only change this if you want to override the default base cost of the Fighter.",
            "movement_override": "Override the default Movement for this fighter",
            "weapon_skill_override": "Override the default Weapon Skill for this fighter",
            "ballistic_skill_override": "Override the default Ballistic Skill for this fighter",
            "strength_override": "Override the default Strength for this fighter",
            "toughness_override": "Override the default Toughness for this fighter",
            "wounds_override": "Override the default Wounds for this fighter",
            "initiative_override": "Override the default Initiative for this fighter",
            "attacks_override": "Override the default Attacks for this fighter",
            "leadership_override": "Override the default Leadership for this fighter",
            "cool_override": "Override the default Cool for this fighter",
            "willpower_override": "Override the default Willpower for this fighter",
            "intelligence_override": "Override the default Intelligence for this fighter",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "content_fighter": forms.Select(attrs={"class": "form-select"}),
            "cost_override": forms.NumberInput(
                attrs={"class": "form-control", "min": 0}
            ),
            "movement_override": forms.TextInput(attrs={"class": "form-control"}),
            "weapon_skill_override": forms.TextInput(attrs={"class": "form-control"}),
            "ballistic_skill_override": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "strength_override": forms.TextInput(attrs={"class": "form-control"}),
            "toughness_override": forms.TextInput(attrs={"class": "form-control"}),
            "wounds_override": forms.TextInput(attrs={"class": "form-control"}),
            "initiative_override": forms.TextInput(attrs={"class": "form-control"}),
            "attacks_override": forms.TextInput(attrs={"class": "form-control"}),
            "leadership_override": forms.TextInput(attrs={"class": "form-control"}),
            "cool_override": forms.TextInput(attrs={"class": "form-control"}),
            "willpower_override": forms.TextInput(attrs={"class": "form-control"}),
            "intelligence_override": forms.TextInput(attrs={"class": "form-control"}),
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


class BsCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    template_name = "pages/forms/widgets/bs_checkbox_select.html"
    option_template_name = "pages/forms/widgets/bs_checkbox_option.html"


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
            "skills": BsCheckboxSelectMultiple(
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


class ListFighterEquipmentAssignmentForm(forms.ModelForm):
    class Meta:
        model = ListFighterEquipmentAssignment
        fields = ["content_equipment", "weapon_profiles_field", "upgrades_field"]

    # TODO: Add a clean method to ensure that weapon profiles are assigned to the correct equipment


class ListFighterEquipmentAssignmentCostForm(forms.ModelForm):
    class Meta:
        model = ListFighterEquipmentAssignment
        fields = ["total_cost_override"]
        labels = {
            "total_cost_override": "Manually Set Cost",
        }
        help_texts = {
            "total_cost_override": "Changing this manually sets the cost of the equipment including all accessories and upgrades. Use with caution.",
        }
        widgets = {
            "total_cost_override": forms.NumberInput(
                attrs={"class": "form-control", "min": 0}
            ),
        }


class ListFighterEquipmentAssignmentAccessoriesForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst: ListFighterEquipmentAssignment | None = kwargs.get("instance", None)
        if inst is not None:
            self.fields[
                "weapon_accessories_field"
            ].queryset = ContentWeaponAccessory.objects.with_cost_for_fighter(
                inst.list_fighter.content_fighter
            ).all()

    weapon_accessories_field = ListFighterEquipmentField(
        label="Accessories",
        queryset=ContentWeaponAccessory.objects.all(),
        widget=BsCheckboxSelectMultiple(
            attrs={"class": "form-check-input"},
        ),
        help_text="Costs reflect the Fighter's Equipment List.",
        required=False,
    )

    class Meta:
        model = ListFighterEquipmentAssignment
        fields = ["weapon_accessories_field"]


class ListFighterEquipmentAssignmentUpgradeForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["upgrades_field"].label = (
            self.instance.content_equipment.upgrade_stack_name or "Upgrade"
        )
        self.fields[
            "upgrades_field"
        ].queryset = self.instance.content_equipment.upgrades.all()

    class Meta:
        model = ListFighterEquipmentAssignment
        fields = ["upgrades_field"]
        labels = {
            "upgrades_field": "Upgrade",
        }
        widgets = {
            "upgrades_field": BsCheckboxSelectMultiple(
                attrs={"class": "form-check-input"},
            ),
        }


class ResetPasswordForm(ResetPasswordForm):
    captcha = ReCaptchaField(widget=ReCaptchaV3(action="reset_password"))


class LoginForm(LoginForm):
    captcha = ReCaptchaField(widget=ReCaptchaV3(action="login"))


class SignupForm(SignupForm):
    captcha = ReCaptchaField(widget=ReCaptchaV3(action="signup"))
