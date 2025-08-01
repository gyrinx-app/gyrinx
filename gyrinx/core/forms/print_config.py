from django import forms
from django.forms import CheckboxSelectMultiple

from gyrinx.core.models import ListFighter, PrintConfig


class PrintConfigForm(forms.ModelForm):
    """Form for creating and editing print configurations."""

    select_all_fighters = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = PrintConfig
        fields = [
            "name",
            "include_assets",
            "include_attributes",
            "include_stash",
            "include_actions",
            "include_dead_fighters",
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
            self.fields["included_fighters"].label_from_instance = (
                lambda obj: f"{obj.name} ({obj.get_injury_state_display()})"
            )

            # Set the initial state of select_all_fighters based on whether fighters are selected
            if self.instance.pk:
                # Editing existing config - check if any fighters are selected
                self.fields[
                    "select_all_fighters"
                ].initial = not self.instance.included_fighters.exists()
            else:
                # New config - default to all fighters
                self.fields["select_all_fighters"].initial = True

    def save_m2m(self):
        """Override save_m2m to handle the select_all_fighters logic."""
        if not self.cleaned_data.get("select_all_fighters"):
            # Only save selected fighters if "all fighters" is not checked
            super().save_m2m()
        # If "all fighters" is checked, we don't save any specific fighters
