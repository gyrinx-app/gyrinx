from django import forms

from gyrinx.content.models import ContentBattleRoleOption
from gyrinx.core.models import Battle, BattleNote
from gyrinx.core.models.list import List
from gyrinx.core.widgets import TINYMCE_EXTRA_ATTRS, TinyMCEWithUpload


class BattleForm(forms.ModelForm):
    """Form for creating and editing battles.

    ``participants`` is a plain choice field rather than a model field because
    the ``Battle.participants`` M2M uses a through model (``BattleParticipant``)
    and cannot be edited directly via a ModelForm. The view syncs the selection
    onto the through model. ``winners`` is only shown when ``include_winners``
    is set (i.e. when editing), so the create form does not assume the battle
    has already happened.
    """

    participants = forms.ModelMultipleChoiceField(
        queryset=List.objects.none(),
        widget=forms.CheckboxSelectMultiple(),
        label="Participants",
        help_text="Select the gangs taking part",
    )

    class Meta:
        model = Battle
        fields = ["date", "mission"]
        labels = {
            "date": "Date",
            "mission": "Mission",
        }
        help_texts = {
            "date": "Optional — leave blank until the battle is scheduled or played",
            "mission": "Mission name or type",
        }
        widgets = {
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "mission": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, campaign=None, include_winners=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.include_winners = include_winners

        if campaign is not None:
            self.instance.campaign = campaign

        # Restrict participant/winner choices to the campaign's active gangs.
        # active_lists() excludes CLONING_IN_PROGRESS stubs (#1222) — a gang still
        # joining in the background isn't a valid battle participant.
        campaign = campaign or getattr(self.instance, "campaign", None)
        campaign_lists = (
            campaign.active_lists().filter(archived_at__isnull=True)
            if campaign
            else List.objects.none()
        )
        self.fields["participants"].queryset = campaign_lists

        if include_winners:
            self.fields["winners"] = forms.ModelMultipleChoiceField(
                queryset=campaign_lists,
                required=False,
                widget=forms.CheckboxSelectMultiple(),
                label="Winner(s)",
                help_text="Select the winners (leave empty for a draw)",
            )

        # Pre-fill selections when editing an existing battle.
        if self.instance and self.instance.pk:
            self.fields["participants"].initial = self.instance.participants.all()
            if include_winners:
                self.fields["winners"].initial = self.instance.winners.all()

    def clean(self):
        cleaned_data = super().clean()
        participants = cleaned_data.get("participants")
        winners = cleaned_data.get("winners")

        if winners and participants:
            for winner in winners:
                if winner not in participants:
                    raise forms.ValidationError(
                        f"{winner} cannot be a winner without being a participant."
                    )

        return cleaned_data


class BattleRolesForm(forms.Form):
    """Assign a role (e.g. Attacker or Defender) to each battle participant."""

    def __init__(self, *args, battle=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.battle = battle

        options = ContentBattleRoleOption.objects.select_related("role")
        self.participant_entries = list(
            battle.participant_entries.select_related("list", "role_option")
        )
        for entry in self.participant_entries:
            self.fields[f"role_{entry.pk}"] = forms.ModelChoiceField(
                queryset=options,
                required=False,
                initial=entry.role_option_id,
                label=entry.list.name,
                empty_label="No role",
                widget=forms.Select(attrs={"class": "form-select"}),
            )

    def save(self):
        for entry in self.participant_entries:
            field_name = f"role_{entry.pk}"
            if field_name not in self.cleaned_data:
                continue
            new_option = self.cleaned_data[field_name]
            new_option_id = new_option.pk if new_option else None
            if entry.role_option_id != new_option_id:
                entry.role_option = new_option
                entry.save(update_fields=["role_option", "modified"])


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
                attrs={"cols": 80, "rows": 20},
                mce_attrs={"min_height": "250px", **TINYMCE_EXTRA_ATTRS},
            ),
        }
