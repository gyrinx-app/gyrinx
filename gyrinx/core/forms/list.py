from django import forms

from gyrinx.content.models import (
    ContentEquipmentUpgrade,
    ContentFighter,
    ContentHouse,
    ContentWeaponAccessory,
)
from gyrinx.core.forms import BsCheckboxSelectMultiple, BsClearableFileInput
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)
from gyrinx.core.widgets import TINYMCE_EXTRA_ATTRS, ColorRadioSelect, TinyMCEWithUpload
from gyrinx.forms import (
    fighter_group_key,
    group_select,
    group_sorter,
    template_form_with_terms,
)
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
            "public": "If checked, this list will be visible to all users of Gyrinx. If unchecked, it will be unlisted. You can edit this later.",
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
            "public": "If checked, this List will be visible to all users of Gyrinx. If unchecked, it will be unlisted. You can edit this later.",
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
            "public": "If checked, this list will be visible to all users. If unchecked, it will be unlisted.",
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

        if inst:
            # Fighters for the house and from generic houses, excluding Exotic Beasts and Vehicles
            # who are added via equipment
            self.fields["content_fighter"].content_house = inst.list.content_house

            # Use the available_for_house method to get available fighters
            self.fields[
                "content_fighter"
            ].queryset = ContentFighter.objects.available_for_house(
                inst.list.content_house
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

                # Disable legacy content fighter if the content fighter is not a legacy
                if not inst.content_fighter.can_take_legacy:
                    self.fields["legacy_content_fighter"].disabled = True
                    self.fields["legacy_content_fighter"].widget = forms.HiddenInput()

                group_select(self, "legacy_content_fighter", key=lambda x: x.house.name)
            else:
                # Don't allow the user to set a legacy content fighter on creation
                self.fields.pop("legacy_content_fighter", None)

        # Group and sort groups fighters so that the gang's own house is first
        group_select(
            self,
            "content_fighter",
            key=fighter_group_key,
            sort_groups_by=group_sorter(inst.list.content_house.name if inst else ""),
        )

        # Only pass the fighter to template_form_with_terms if it's a saved instance
        # with a content_fighter. New instances won't have content_fighter set yet.
        template_form_with_terms(
            self,
            fighter=inst if (inst and inst.pk and inst.content_fighter_id) else None,
        )

    class Meta:
        model = ListFighter
        fields = [
            "name",
            "content_fighter",
            "legacy_content_fighter",
            "category_override",
            "cost_override",
        ]
        labels = {
            "name": "Name",
            "content_fighter": "{term_singular} Type",
            "legacy_content_fighter": "Gang Legacy",
            "category_override": "Category Override",
            "cost_override": "Manually Set Cost",
        }
        help_texts = {
            "name": "The name you use to identify this {term_singular}. This may be public.",
            "legacy_content_fighter": "The Gang Legacy for this fighter.",
            "category_override": "Override the {term_singular}'s category without changing their type or special rules.",
            "cost_override": "Only change this if you want to override the default base cost of the {term_singular}.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "content_fighter": forms.Select(attrs={"class": "form-select"}),
            "legacy_content_fighter": forms.Select(
                attrs={"class": "form-select"},
            ),
            "category_override": forms.Select(
                attrs={"class": "form-select"},
                choices=[("", "-- No Override --")]
                + [
                    (
                        FighterCategoryChoices.LEADER,
                        FighterCategoryChoices.LEADER.label,
                    ),
                    (
                        FighterCategoryChoices.CHAMPION,
                        FighterCategoryChoices.CHAMPION.label,
                    ),
                    (
                        FighterCategoryChoices.GANGER,
                        FighterCategoryChoices.GANGER.label,
                    ),
                    (FighterCategoryChoices.JUVE, FighterCategoryChoices.JUVE.label),
                    (
                        FighterCategoryChoices.PROSPECT,
                        FighterCategoryChoices.PROSPECT.label,
                    ),
                    (
                        FighterCategoryChoices.SPECIALIST,
                        FighterCategoryChoices.SPECIALIST.label,
                    ),
                ],
            ),
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


class ListFighterWeaponAccessoryField(forms.ModelMultipleChoiceField):
    """Custom field for weapon accessories that shows calculated costs."""

    def __init__(self, *args, assignment=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.assignment = assignment

    def label_from_instance(self, obj):
        # Use the assignment's accessory cost calculation which includes expression support
        if self.assignment:
            cost = self.assignment._accessory_cost_with_override(obj)
        else:
            # Fallback: check for annotated cost_for_fighter first, then basic cost
            if hasattr(obj, "cost_for_fighter") and obj.cost_for_fighter is not None:
                cost = obj.cost_for_fighter
            else:
                cost = obj.cost
        unit = "¢" if str(cost).strip().isnumeric() else ""
        return f"{obj.name} ({cost}{unit})"


class ListFighterEquipmentAssignmentAccessoriesForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst: ListFighterEquipmentAssignment | None = kwargs.get("instance", None)
        if inst is not None:
            # Create new field with assignment instance
            self.fields["weapon_accessories_field"] = ListFighterWeaponAccessoryField(
                label="Accessories",
                queryset=ContentWeaponAccessory.objects.with_cost_for_fighter(
                    inst.list_fighter.content_fighter
                ).all(),
                widget=BsCheckboxSelectMultiple(
                    attrs={"class": "form-check-input"},
                ),
                help_text="Costs reflect the Fighter's Equipment List.",
                required=False,
                assignment=inst,
            )
            # Set initial value
            self.fields[
                "weapon_accessories_field"
            ].initial = inst.weapon_accessories_field.all()

    class Meta:
        model = ListFighterEquipmentAssignment
        fields = ["weapon_accessories_field"]


class ListFighterEquipmentAssignmentUpgradeForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[
            "upgrades_field"
        ].label = self.instance.content_equipment.upgrade_stack_name_display
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = kwargs.get("instance", None)
        template_form_with_terms(self, fighter=inst)

    class Meta:
        model = ListFighter
        fields = ["narrative"]
        labels = {
            "narrative": "About",
        }
        help_texts = {
            "narrative": "Narrative description of the {term_singular__lower}: their history and how to play them.",
        }
        widgets = {
            "narrative": TinyMCEWithUpload(
                attrs={"cols": 80, "rows": 20}, mce_attrs=TINYMCE_EXTRA_ATTRS
            ),
        }


class EditListFighterInfoForm(forms.ModelForm):
    """Form for editing fighter info section (image, save, private notes)"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = kwargs.get("instance", None)
        template_form_with_terms(self, fighter=inst)

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
            "save_roll": "{term_singular}'s typical save roll",
            "private_notes": "Notes about {term_proximal_demonstrative__lower} (only visible to you)",
        }
        widgets = {
            "save_roll": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. 5+"}
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
        label="Select {term_injury_singular}",
        help_text="Choose the {term_injury_singular__lower} to apply to this fighter.",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    fighter_state = forms.ChoiceField(
        choices=[],  # Will be set in __init__
        label="{term_singular} State",
        help_text="Select the state to put the fighter into.",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        required=False,
        label="Notes",
        help_text="Optional notes about how this {term_injury_singular__lower} was received (will be included in campaign log).",
    )

    def __init__(self, *args, **kwargs):
        # Extract fighter from kwargs if provided
        fighter = kwargs.pop("fighter", None)
        super().__init__(*args, **kwargs)
        # Import here to avoid circular imports
        from django.db.models import Q

        from gyrinx.content.models import ContentInjury, ContentInjuryGroup
        from gyrinx.forms import group_select

        # Filter injuries based on fighter category if fighter is provided
        if fighter:
            fighter_category = fighter.content_fighter.category
            fighter_house = fighter.equipment_list_fighter.house

            # Build query for injury groups available to this fighter
            # Start with groups that have no category restrictions or include this category
            group_query = (
                Q(restricted_to__isnull=True)
                | Q(restricted_to="")
                | Q(restricted_to__contains=fighter_category)
            )

            # Exclude groups that are unavailable to this category
            group_query &= ~Q(unavailable_to__contains=fighter_category)

            # Apply house restrictions if present
            if fighter_house:
                # Include groups with no house restrictions or those restricted to this house
                group_query &= Q(restricted_to_house__isnull=True) | Q(
                    restricted_to_house=fighter_house
                )

            available_groups = ContentInjuryGroup.objects.filter(group_query)

            # Filter injuries by available groups
            self.fields["injury"].queryset = ContentInjury.objects.select_related(
                "injury_group"
            ).filter(
                Q(injury_group__in=available_groups) | Q(injury_group__isnull=True)
            )
        else:
            # If no fighter, show all injuries
            self.fields["injury"].queryset = ContentInjury.objects.select_related(
                "injury_group"
            )

        # Group injuries by their injury_group field
        group_select(
            self,
            "injury",
            key=lambda x: x.injury_group.name if x.injury_group else "Other",
        )

        # Set fighter state choices including Active for injuries that don't affect availability
        # Add In Repair if the fighter is a vehicle
        choices = [
            (ListFighter.ACTIVE, "Active"),
            (ListFighter.RECOVERY, "Recovery"),
            (ListFighter.CONVALESCENCE, "Convalescence"),
            (ListFighter.DEAD, "Dead"),
        ]

        if (
            fighter
            and fighter.content_fighter.category == FighterCategoryChoices.VEHICLE
        ):
            choices = [
                (ListFighter.ACTIVE, "Active"),
                (ListFighter.IN_REPAIR, "In Repair"),
            ]

        self.fields["fighter_state"].choices = choices

        template_form_with_terms(self, fighter=fighter)

        # Set initial fighter state to the fighter's current state if provided
        if fighter and not self.is_bound:
            self.fields["fighter_state"].initial = fighter.injury_state


class EditFighterStateForm(forms.Form):
    fighter_state = forms.ChoiceField(
        choices=[],  # Will be set in __init__
        label="{term_singular} State",
        help_text="Select the new state for {term_proximal_demonstrative__lower}.",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        required=False,
        label="Reason",
        help_text="Optional reason for the state change (will be included in campaign log).",
    )

    def __init__(self, *args, **kwargs):
        fighter = kwargs.pop("fighter", None)
        super().__init__(*args, **kwargs)

        # Set all state choices
        self.fields["fighter_state"].choices = [
            (ListFighter.ACTIVE, "Active"),
            (ListFighter.RECOVERY, "Recovery"),
            (ListFighter.CONVALESCENCE, "Convalescence"),
            (ListFighter.DEAD, "Dead"),
        ]

        if (
            fighter
            and fighter.content_fighter.category == FighterCategoryChoices.VEHICLE
        ):
            # If the fighter is a vehicle, add In Repair state
            self.fields["fighter_state"].choices = [
                (ListFighter.ACTIVE, "Active"),
                (ListFighter.IN_REPAIR, "In Repair"),
            ]

        template_form_with_terms(self, fighter=fighter)

        # Set initial value to current state
        if fighter and fighter.injury_state:
            self.fields["fighter_state"].initial = fighter.injury_state


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


class EditListFighterStatsForm(forms.Form):
    """Form for editing fighter stat overrides in a table format."""

    def __init__(self, *args, **kwargs):
        fighter = kwargs.pop("fighter", None)
        super().__init__(*args, **kwargs)

        if not fighter:
            return

        # Check if the fighter has a custom statline
        has_custom_statline = hasattr(fighter.content_fighter, "custom_statline")

        if has_custom_statline:
            # Use the custom statline approach
            statline = fighter.content_fighter.custom_statline

            # Get existing overrides
            existing_overrides = {
                override.content_stat.id: override.value
                for override in fighter.stat_overrides.select_related("content_stat")
            }

            # Create fields for each stat in the statline
            for stat_def in statline.statline_type.stats.all():
                field_name = f"stat_{stat_def.id}"
                initial_value = existing_overrides.get(stat_def.id, "")

                # Get the base value from ContentStatline
                try:
                    base_stat = statline.stats.get(statline_type_stat=stat_def)
                    placeholder = base_stat.value
                except Exception:
                    placeholder = "-"

                self.fields[field_name] = forms.CharField(
                    required=False,
                    label=stat_def.full_name,
                    widget=forms.TextInput(
                        attrs={
                            "class": "form-control form-control-sm",
                            "data-stat-id": stat_def.id,
                            "data-short-name": stat_def.short_name,
                        }
                    ),
                    initial=initial_value,
                )

                # Store metadata for template rendering
                self.fields[field_name].stat_def = stat_def
                self.fields[field_name].is_first_of_group = stat_def.is_first_of_group
                self.fields[field_name].base_value = placeholder
        else:
            # Use legacy override fields
            legacy_stats = [
                ("movement", "M", "Movement"),
                ("weapon_skill", "WS", "Weapon Skill"),
                ("ballistic_skill", "BS", "Ballistic Skill"),
                ("strength", "S", "Strength"),
                ("toughness", "T", "Toughness"),
                ("wounds", "W", "Wounds"),
                ("initiative", "I", "Initiative"),
                ("attacks", "A", "Attacks"),
                ("leadership", "Ld", "Leadership"),
                ("cool", "Cl", "Cool"),
                ("willpower", "Wil", "Willpower"),
                ("intelligence", "Int", "Intelligence"),
            ]

            for field_name, short_name, full_name in legacy_stats:
                override_field = f"{field_name}_override"
                current_value = getattr(fighter, override_field) or ""
                base_value = getattr(fighter.content_fighter, field_name) or "-"

                self.fields[override_field] = forms.CharField(
                    required=False,
                    label=full_name,
                    widget=forms.TextInput(
                        attrs={
                            "class": "form-control form-control-sm",
                            "data-short-name": short_name,
                            "placeholder": "",
                        }
                    ),
                    initial=current_value,
                )

                # Store metadata for template rendering
                self.fields[override_field].is_first_of_group = field_name in [
                    "leadership"
                ]
                self.fields[override_field].short_name = short_name
                self.fields[override_field].full_name = full_name
                self.fields[override_field].base_value = base_value

        self.fighter = fighter
        self.has_custom_statline = has_custom_statline

    def clean(self):
        """Validate that no smart quotes are used in stat values."""
        cleaned_data = super().clean()

        # Smart quotes to check for
        smart_quotes = ['"', '"', """, """]

        for field_name, value in cleaned_data.items():
            if value and any(quote in value for quote in smart_quotes):
                # Get a more user-friendly field label
                if hasattr(self.fields[field_name], "full_name"):
                    field_label = self.fields[field_name].full_name
                elif hasattr(self.fields[field_name], "label"):
                    field_label = self.fields[field_name].label
                else:
                    field_label = field_name

                raise forms.ValidationError(
                    {
                        field_name: f'Smart quotes are not allowed in {field_label}. Please use simple quotes (") instead.'
                    }
                )

        return cleaned_data
