from django import forms

from gyrinx.core.models import Battle, BattleNote
from gyrinx.core.widgets import TINYMCE_EXTRA_ATTRS, TinyMCEWithUpload


class BattleForm(forms.ModelForm):
    """Form for creating and editing battles"""

    class Meta:
        model = Battle
        fields = ["date", "mission", "participants", "winners"]
        labels = {
            "date": "Date",
            "mission": "Mission",
            "participants": "Participants",
            "winners": "Winner(s)",
        }
        help_texts = {
            "date": "The date that the battle took place",
            "mission": "Mission name or type",
            "participants": "Select all gangs that participated in the battle",
            "winners": "Select the winners (leave empty for a draw)",
        }
        widgets = {
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "mission": forms.TextInput(attrs={"class": "form-control"}),
            "participants": forms.CheckboxSelectMultiple(),
            "winners": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        campaign = kwargs.pop("campaign", None)
        super().__init__(*args, **kwargs)

        # If we have a campaign, limit participants to lists in that campaign
        if campaign:
            self.instance.campaign = campaign
            campaign_lists = campaign.lists.filter(archived_at__isnull=True)
            self.fields["participants"].queryset = campaign_lists
            self.fields["winners"].queryset = campaign_lists

        # If editing existing battle, limit winners to current participants
        if self.instance.pk:
            self.fields["winners"].queryset = self.instance.participants.all()

    def clean(self):
        cleaned_data = super().clean()
        participants = cleaned_data.get("participants")
        winners = cleaned_data.get("winners")

        if winners and participants:
            # Ensure all winners are also participants
            for winner in winners:
                if winner not in participants:
                    raise forms.ValidationError(
                        f"{winner} cannot be a winner without being a participant."
                    )

        return cleaned_data


class BattleNoteForm(forms.ModelForm):
    """Form for adding notes to a battle"""

    class Meta:
        model = BattleNote
        fields = ["content"]
        labels = {
            "content": "Notes",
        }
        widgets = {
            "content": TinyMCEWithUpload(
                attrs={"cols": 80, "rows": 10}, mce_attrs=TINYMCE_EXTRA_ATTRS
            ),
        }
