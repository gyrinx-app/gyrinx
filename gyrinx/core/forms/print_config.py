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
            "included_fighters",
            "is_default",
        ]
        widgets = {
            "included_fighters": CheckboxSelectMultiple(),
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
                list=self.list_obj, archived=False
            ).order_by("order")

            # Customize the label for each fighter
            self.fields["included_fighters"].label_from_instance = (
                lambda obj: f"{obj.name} ({obj.get_state_display()})"
            )
