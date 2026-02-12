from django import forms
from django.forms import CheckboxSelectMultiple

from gyrinx.core.models import ListFighter, PrintConfig


class PrintConfigForm(forms.ModelForm):
    """Form for creating and editing print configurations."""

    class Meta:
        model = PrintConfig
        fields = [
            "name",
            "include_assets",
            "include_attributes",
            "include_stash",
            "include_actions",
            "include_dead_fighters",
            "blank_fighter_cards",
            "blank_vehicle_cards",
            "fighter_selection_mode",
            "included_fighters",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "include_assets": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "include_attributes": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "include_stash": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "include_actions": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "include_dead_fighters": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "blank_fighter_cards": forms.NumberInput(
                attrs={"class": "form-control", "min": "0", "max": "20"}
            ),
            "blank_vehicle_cards": forms.NumberInput(
                attrs={"class": "form-control", "min": "0", "max": "20"}
            ),
            "fighter_selection_mode": forms.RadioSelect(
                attrs={"class": "form-check-input"}
            ),
            "included_fighters": CheckboxSelectMultiple(
                attrs={"class": "form-check-input"}
            ),
        }
        help_texts = {
            "name": "Give this print configuration a descriptive name.",
            "included_fighters": "Select which fighters to include in the print output.",
        }

    def __init__(self, *args, **kwargs):
        self.list_obj = kwargs.pop("list_obj", None)
        super().__init__(*args, **kwargs)

        if self.list_obj:
            # Filter fighters to only show those belonging to this list
            self.fields["included_fighters"].queryset = ListFighter.objects.filter(
                list=self.list_obj, archived=False, content_fighter__is_stash=False
            )

            # Customize the label for each fighter
            self.fields["included_fighters"].label_from_instance = lambda obj: (
                f"{obj.name} ({obj.get_injury_state_display()})"
            )

    def clean(self):
        """Validate fighter selection and clear included_fighters for non-specific modes."""
        cleaned_data = super().clean()
        mode = cleaned_data.get("fighter_selection_mode")

        if mode == PrintConfig.SPECIFIC_FIGHTERS:
            if not cleaned_data.get("included_fighters"):
                self.add_error(
                    "included_fighters",
                    "Select at least one Fighter, or use a different selection mode.",
                )
        else:
            cleaned_data["included_fighters"] = []

        return cleaned_data
