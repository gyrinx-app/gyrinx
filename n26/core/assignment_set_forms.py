"""Owner-facing forms for named model cards."""

from django import forms

from n26.core.assignment_sets import equipment_for
from n26.core.models import Assignment


class EquipmentChoices(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return str(obj.weapon or obj.wargear)


class ModelCardForm(forms.Form):
    name = forms.CharField(
        label="Card name", max_length=200, help_text='For example, "Long range".'
    )
    assignments = EquipmentChoices(
        label="Equipment",
        queryset=Assignment.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        error_messages={
            "invalid_choice": "Choose equipment currently on this model.",
            "invalid_pk_value": "Choose equipment currently on this model.",
        },
    )
    revision = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, miniature, assignment_set=None, **kwargs):
        super().__init__(*args, **kwargs)
        equipment = equipment_for(miniature)
        self.fields["assignments"].queryset = equipment
        if assignment_set is None:
            self.initial["assignments"] = list(equipment.values_list("pk", flat=True))
        else:
            self.fields["revision"].required = True
            self.initial.update(
                name=assignment_set.name,
                assignments=list(
                    assignment_set.assignments.values_list("pk", flat=True)
                ),
                revision=assignment_set.modified.isoformat(),
            )


class RemoveModelCardForm(forms.Form):
    revision = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, *args, assignment_set, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["revision"] = assignment_set.modified.isoformat()
