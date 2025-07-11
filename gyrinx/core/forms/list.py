from django import forms

from gyrinx.content.models import (
    ContentEquipmentUpgrade,
    ContentFighter,
    ContentHouse,
    ContentWeaponAccessory,
)
from gyrinx.core.forms import BsCheckboxSelectMultiple, BsClearableFileInput
from gyrinx.core.models.list import List, ListFighter, ListFighterEquipmentAssignment
from gyrinx.core.widgets import TINYMCE_EXTRA_ATTRS, ColorRadioSelect, TinyMCEWithUpload
from gyrinx.forms import group_select
from gyrinx.models import FighterCategoryChoices


class NewListForm(forms.ModelForm):
    show_stash = forms.BooleanField(
        required=False,
        initial=True,
        label="Show Stash for this list",
        help_text="If checked, a stash fighter will be created for this list.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter out generic houses that can't be selected as a primary house
        self.fields["content_house"].queryset = ContentHouse.objects.filter(
            generic=False
        )

        # Group houses by legacy status
        from gyrinx.forms import group_select

        group_select(
            self,
            "content_house",
            key=lambda x: "Legacy House" if x.legacy else "House",
            sort_groups_by=lambda group: 0 if group == "House" else 1,
        )

    class Meta:
        model = List
        fields = ["name", "content_house", "narrative", "public"]
        labels = {
            "name": "Name",
            "content_house": "House",
            "narrative": "About",
            "public": "Public",
        }
        help_texts = {
            "name": "The name you use to identify this List. This may be public.",
            "narrative": "Narrative description of the gang in this list: their history and how to play them.",
            "public": "If checked, this list will be visible to all users of Gyrinx. You can edit this later.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "content_house": forms.Select(attrs={"class": "form-select"}),
            "narrative": TinyMCEWithUpload(
                attrs={"cols": 80, "rows": 20}, mce_attrs=TINYMCE_EXTRA_ATTRS
            ),
            "public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class CloneListForm(forms.ModelForm):
    class Meta:
        model = List
        fields = ["name", "narrative", "public"]
        labels = {
            "name": "Name",
            "narrative": "About",
            "public": "Public",
        }
        help_texts = {
            "name": "The name you use to identify this List. This may be public.",
            "narrative": "Narrative description of the gang in this list: their history and how to play them.",
            "public": "If checked, this List will be visible to all users of Gyrinx. You can edit this later.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "narrative": TinyMCEWithUpload(
                attrs={"cols": 80, "rows": 20}, mce_attrs=TINYMCE_EXTRA_ATTRS
            ),
            "public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class EditListForm(forms.ModelForm):
    class Meta:
        model = List
        fields = ["name", "narrative", "public", "theme_color"]
        labels = {
            "name": "Name",
            "narrative": "About",
            "public": "Public",
            "theme_color": "Theme Color",
        }
        help_texts = {
            "name": "The name you use to identify this list. This may be public.",
            "narrative": "Narrative description of the gang in this list: their history and how to play them.",
            "public": "If checked, this list will be visible to all users.",
            "theme_color": "Select a theme color for your gang. Used in campaign views.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "narrative": TinyMCEWithUpload(
                attrs={"cols": 80, "rows": 20}, mce_attrs=TINYMCE_EXTRA_ATTRS
            ),
            "public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "theme_color": ColorRadioSelect(),
        }


class ContentFighterChoiceField(forms.ModelChoiceField):
    content_house: ContentHouse | None = None

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", forms.Select(attrs={"class": "form-select"}))
        kwargs.setdefault("label", "Fighter")
        super().__init__(*args, **kwargs)

    def label_from_instance(self, obj: ContentFighter):
        cost_for_house = (
            obj.cost_for_house(self.content_house) if self.content_house else obj.cost()
        )
        return f"{obj.name()} ({cost_for_house}¢)"


class ListFighterForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = kwargs.get("instance", {})
        self.fields["content_fighter"] = ContentFighterChoiceField(
            queryset=self.fields["content_fighter"].queryset,
            label=self.fields["content_fighter"].label,
            help_text=self.fields["content_fighter"].help_text,
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
            ).exclude(
                category__in=[
                    FighterCategoryChoices.EXOTIC_BEAST,
                    FighterCategoryChoices.STASH,
                ]
            )

            self.fields[
                "legacy_content_fighter"
            ].queryset = ContentFighter.objects.filter(can_be_legacy=True)

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

                # Disable legacy content fighter if the content fighter is not a legacy
                if not inst.content_fighter.can_take_legacy:
                    self.fields["legacy_content_fighter"].disabled = True
                    self.fields["legacy_content_fighter"].widget = forms.HiddenInput()

                group_select(self, "legacy_content_fighter", key=lambda x: x.house.name)
            else:
                # If no instance is provided, we are creating a new fighter
                # and we don't want to allow the user to override the stats
                for field in overrides:
                    self.fields.pop(field, None)

                # Don't allow the user to set a legacy content fighter on creation
                self.fields.pop("legacy_content_fighter")

        def fighter_group_key(fighter):
            # Group by house name
            return fighter.house.name

        def sort_groups_key(group_name):
            # Sort groups: gang's own house first, then alphabetically
            if group_name == inst.list.content_house.name:
                return (0, group_name)  # Gang's house comes first
            else:
                return (1, group_name)  # Other houses alphabetically

        # Group and sort groups fighters so that the gang's own house is first
        group_select(
            self,
            "content_fighter",
            key=fighter_group_key,
            sort_groups_by=sort_groups_key,
        )

    class Meta:
        model = ListFighter
        fields = [
            "name",
            "content_fighter",
            "legacy_content_fighter",
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
            "content_fighter": "Fighter Type",
            "legacy_content_fighter": "Gang Legacy",
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
            "legacy_content_fighter": "The Gang Legacy for this fighter.",
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
            "legacy_content_fighter": forms.Select(
                attrs={"class": "form-select"},
            ),
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
        if inst:
            self.fields["content_fighter"].content_house = inst.list.content_house

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
        ].queryset = ContentEquipmentUpgrade.objects.with_cost_for_fighter(
            self.instance.list_fighter.equipment_list_fighter
        ).filter(
            equipment=self.instance.content_equipment,
        )
        self.fields["upgrades_field"].label_from_instance = (
            lambda obj: f"{obj.name} ({self.instance.upgrade_cost_display(obj)})"
        )

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


class EditListFighterNarrativeForm(forms.ModelForm):
    class Meta:
        model = ListFighter
        fields = ["narrative"]
        labels = {
            "narrative": "About",
        }
        help_texts = {
            "narrative": "Narrative description of the Fighter: their history and how to play them.",
        }
        widgets = {
            "narrative": TinyMCEWithUpload(
                attrs={"cols": 80, "rows": 20}, mce_attrs=TINYMCE_EXTRA_ATTRS
            ),
        }


class EditListFighterInfoForm(forms.ModelForm):
    """Form for editing fighter info section (image, save, private notes)"""

    class Meta:
        model = ListFighter
        fields = ["image", "save_roll", "private_notes"]
        labels = {
            "image": "Image",
            "save_roll": "Save Roll",
            "private_notes": "Notes",
        }
        help_texts = {
            "image": "This image appears in Info section",
            "save_roll": "Fighter's typical save roll",
            "private_notes": "Notes about the fighter (only visible to you)",
        }
        widgets = {
            "save_roll": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. 5+ or 4+ inv"}
            ),
            "private_notes": TinyMCEWithUpload(
                attrs={"cols": 80, "rows": 10}, mce_attrs=TINYMCE_EXTRA_ATTRS
            ),
            "image": BsClearableFileInput(
                attrs={
                    "class": "form-control",
                    "accept": "image/*",
                },
            ),
        }


class AddInjuryForm(forms.Form):
    injury = forms.ModelChoiceField(
        queryset=None,  # Will be set in __init__
        label="Select Injury",
        help_text="Choose the lasting injury to apply to this fighter.",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    fighter_state = forms.ChoiceField(
        choices=[],  # Will be set in __init__
        label="Fighter State",
        help_text="Select the state to put the fighter into. Defaults to the injury's phase.",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        required=False,
        label="Notes",
        help_text="Optional notes about how this injury was received (will be included in campaign log).",
    )

    def __init__(self, *args, **kwargs):
        # Extract fighter from kwargs if provided
        fighter = kwargs.pop("fighter", None)
        super().__init__(*args, **kwargs)
        # Import here to avoid circular imports
        from gyrinx.content.models import ContentInjury
        from gyrinx.forms import group_select

        self.fields["injury"].queryset = ContentInjury.objects.select_related()

        # Group injuries by their group field if it exists
        group_select(self, "injury", key=lambda x: x.group if x.group else "Other")

        # Set fighter state choices including Active for injuries that don't affect availability
        self.fields["fighter_state"].choices = [
            (ListFighter.ACTIVE, "Active"),
            (ListFighter.RECOVERY, "Recovery"),
            (ListFighter.CONVALESCENCE, "Convalescence"),
            (ListFighter.DEAD, "Dead"),
        ]

        # Set initial fighter state to the fighter's current state if provided
        if fighter and not self.is_bound:
            self.fields["fighter_state"].initial = fighter.injury_state


class EditFighterStateForm(forms.Form):
    fighter_state = forms.ChoiceField(
        choices=[],  # Will be set in __init__
        label="Fighter State",
        help_text="Select the new state for this fighter.",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        required=False,
        label="Reason",
        help_text="Optional reason for the state change (will be included in campaign log).",
    )

    def __init__(self, *args, **kwargs):
        current_state = kwargs.pop("current_state", None)
        super().__init__(*args, **kwargs)

        # Set all state choices
        self.fields["fighter_state"].choices = ListFighter.INJURY_STATE_CHOICES

        # Set initial value to current state
        if current_state:
            self.fields["fighter_state"].initial = current_state


class EditFighterXPForm(forms.Form):
    """Form for modifying fighter XP in campaign mode."""

    XP_OPERATION_CHOICES = [
        ("add", "Add XP"),
        ("spend", "Spend XP"),
        ("reduce", "Reduce XP"),
    ]

    operation = forms.ChoiceField(
        choices=XP_OPERATION_CHOICES,
        label="Operation",
        help_text="Select what you want to do with XP",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    amount = forms.IntegerField(
        min_value=1,
        label="Amount",
        help_text="How much XP to add, spend, or reduce",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        required=False,
        label="Description",
        help_text="Optional description for this XP change (will be included in campaign log)",
    )

    def __init__(self, *args, **kwargs):
        fighter = kwargs.pop("fighter", None)
        super().__init__(*args, **kwargs)

        # Store fighter instance for use in clean method
        self.fighter = fighter

        # Add helpful hints based on current XP
        if fighter:
            self.fields["amount"].help_text = (
                f"How much XP to add, spend, or reduce. "
                f"Current: {fighter.xp_current} XP, Total earned: {fighter.xp_total} XP"
            )

    def clean(self):
        cleaned_data = super().clean()
        amount = cleaned_data.get("amount")

        if amount and amount <= 0:
            raise forms.ValidationError("Amount must be greater than 0.")

        # We'll do more validation in the view where we have access to the fighter
        return cleaned_data


class EditListCreditsForm(forms.Form):
    """Form for modifying list credits in campaign mode."""

    CREDIT_OPERATION_CHOICES = [
        ("add", "Add Credits"),
        ("spend", "Spend Credits"),
        ("reduce", "Reduce Credits"),
    ]

    operation = forms.ChoiceField(
        choices=CREDIT_OPERATION_CHOICES,
        label="Operation",
        help_text="Select what you want to do with credits",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    amount = forms.IntegerField(
        min_value=1,
        label="Amount",
        help_text="How many credits to add, spend, or reduce",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        required=False,
        label="Description",
        help_text="Optional description for this credit change (will be included in campaign log)",
    )

    def __init__(self, *args, **kwargs):
        lst = kwargs.pop("lst", None)
        super().__init__(*args, **kwargs)

        # Store list instance for use in clean method
        self.lst = lst

        # Add helpful hints based on current credits
        if lst:
            self.fields["amount"].help_text = (
                f"How many credits to add, spend, or reduce. "
                f"Current: {lst.credits_current}¢, Total earned: {lst.credits_earned}¢"
            )

    def clean(self):
        cleaned_data = super().clean()
        amount = cleaned_data.get("amount")

        if amount and amount <= 0:
            raise forms.ValidationError("Amount must be greater than 0.")

        # We'll do more validation in the view where we have access to the list
        return cleaned_data


class EquipmentReassignForm(forms.Form):
    """Form for reassigning equipment from one fighter to another."""

    target_fighter = forms.ModelChoiceField(
        queryset=ListFighter.objects.none(),
        label="Reassign to",
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Select the fighter to receive this equipment.",
    )

    def __init__(self, *args, **kwargs):
        fighters = kwargs.pop("fighters", ListFighter.objects.none())
        super().__init__(*args, **kwargs)
        self.fields["target_fighter"].queryset = fighters
        self.fields["target_fighter"].label_from_instance = (
            lambda obj: obj.fully_qualified_name
        )


class EquipmentSellSelectionForm(forms.Form):
    """Form for selecting equipment sale options (manual price vs dice roll)."""

    PRICE_CHOICES = [
        ("dice", "Cost minus D6×10"),
        ("manual", "Manual"),
    ]

    price_method = forms.ChoiceField(
        choices=PRICE_CHOICES,
        initial="dice",
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        label="Sale Price",
    )
    manual_price = forms.IntegerField(
        required=False,
        min_value=5,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        label="Manual Price",
        help_text="Enter price in credits (minimum 5¢)",
    )

    def clean(self):
        cleaned_data = super().clean()
        price_method = cleaned_data.get("price_method")
        manual_price = cleaned_data.get("manual_price")

        if price_method == "manual" and not manual_price:
            raise forms.ValidationError(
                "Manual price is required when manual pricing is selected."
            )

        return cleaned_data


class EquipmentSellForm(forms.Form):
    """Form for confirming equipment sale with calculated prices."""

    confirm = forms.BooleanField(
        required=True,
        widget=forms.HiddenInput(),
        initial=True,
    )
