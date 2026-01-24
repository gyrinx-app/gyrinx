from django import forms
from django.forms import CheckboxSelectMultiple

from gyrinx.core.models import CrewTemplate, ListFighter


class CrewTemplateForm(forms.ModelForm):
    """Form for creating and editing crew templates."""

    class Meta:
        model = CrewTemplate
        fields = [
            "name",
            "chosen_fighters",
            "random_count",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "chosen_fighters": CheckboxSelectMultiple(
                attrs={"class": "form-check-input"}
            ),
            "random_count": forms.NumberInput(
                attrs={"class": "form-control", "min": "0", "max": "20"}
            ),
        }
        help_texts = {
            "name": "Give this crew template a descriptive name.",
            "chosen_fighters": "Select specific fighters to always include in the crew.",
            "random_count": "Number of additional fighters to randomly select from remaining active fighters.",
        }

    def __init__(self, *args, **kwargs):
        self.list_obj = kwargs.pop("list_obj", None)
        super().__init__(*args, **kwargs)

        if self.list_obj:
            # Filter fighters to only show active, non-stash fighters from this list
            self.fields["chosen_fighters"].queryset = ListFighter.objects.filter(
                list=self.list_obj,
                archived=False,
                content_fighter__is_stash=False,
                injury_state=ListFighter.ACTIVE,
            )

            # Customize the label for each fighter
            self.fields["chosen_fighters"].label_from_instance = (
                lambda obj: f"{obj.name}"
            )

    def clean(self):
        cleaned_data = super().clean()
        chosen_fighters = cleaned_data.get("chosen_fighters")
        random_count = cleaned_data.get("random_count", 0)

        if not chosen_fighters and not random_count:
            raise forms.ValidationError(
                "You must either choose specific fighters or set a random count."
            )

        return cleaned_data
