from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from gyrinx.content.models import ContentAttributeValue
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import ListAttributeAssignment


class ListAttributeForm(forms.Form):
    """Form for managing list attribute assignments."""

    def __init__(self, *args, **kwargs):
        self.list_obj = kwargs.pop("list_obj")
        self.attribute = kwargs.pop("attribute")
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        # Get available values for this attribute
        values = ContentAttributeValue.objects.filter(
            attribute=self.attribute
        ).order_by("name")

        # Get current assignments
        current_assignments = ListAttributeAssignment.objects.filter(
            list=self.list_obj,
            attribute_value__attribute=self.attribute,
            archived=False,
        ).values_list("attribute_value_id", flat=True)

        if self.attribute.is_single_select:
            # Single select - use radio buttons
            # Note: empty_label doesn't work with RadioSelect, so we manually add None option
            self.fields["values"] = forms.ModelChoiceField(
                queryset=values,
                widget=forms.RadioSelect,
                required=False,
                initial=current_assignments.first() if current_assignments else None,
                label="",
                empty_label=None,
            )
            # Manually add a "None" option at the beginning of choices
            self.fields["values"].choices = [("", "None")] + list(
                self.fields["values"].choices
            )
        else:
            # Multi select - use checkboxes
            self.fields["values"] = forms.ModelMultipleChoiceField(
                queryset=values,
                widget=forms.CheckboxSelectMultiple,
                required=False,
                initial=list(current_assignments),
                label="",
            )

    def clean(self):
        cleaned_data = super().clean()

        # Check if list is archived
        if self.list_obj.archived:
            raise ValidationError("Cannot modify attributes for an archived list.")

        return cleaned_data

    def save(self):
        """Save the attribute assignments."""
        values = self.cleaned_data.get("values")

        with transaction.atomic():
            # Archive existing assignments for this attribute
            ListAttributeAssignment.objects.filter(
                list=self.list_obj,
                attribute_value__attribute=self.attribute,
                archived=False,
            ).update(archived=True)

            # Create new assignments
            if values:
                # Handle both single and multiple values
                if self.attribute.is_single_select:
                    values = [values] if values else []

                for value in values:
                    assignment, created = ListAttributeAssignment.objects.get_or_create(
                        list=self.list_obj,
                        attribute_value=value,
                        defaults={"archived": False},
                    )
                    if not created and assignment.archived:
                        assignment.archived = False
                        assignment.save()

            # Log campaign action if in campaign mode
            if (
                self.list_obj.is_campaign_mode
                and self.list_obj.campaign
                and self.request
            ):
                value_names = []
                if values:
                    # values is always a list at this point due to line 75
                    value_names = [v.name for v in values]

                action_text = f"Updated {self.attribute.name}: {', '.join(value_names) if value_names else 'None'}"

                CampaignAction.objects.create(
                    campaign=self.list_obj.campaign,
                    list=self.list_obj,
                    user=self.request.user,
                    description=action_text,
                )
