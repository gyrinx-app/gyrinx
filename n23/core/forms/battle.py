from django import forms

from n23.content.models import ContentBattleRoleOption
from gyrinx.widgets import BsRadioSelect
from n23.core.models import Battle, BattleNote
from n23.core.models.list import List
from gyrinx.widgets import TINYMCE_EXTRA_ATTRS, TinyMCEWithUpload


def validate_result_and_winners(result, winners, add_error):
    """Cross-field rule shared by the end-battle and edit-battle forms.

    The result radio and the winners checkboxes are always both visible, so the
    radio changes what counts as valid rather than what is on screen.
    """
    if result == Battle.RESULT_WINNERS and not winners:
        add_error("winners", "Select at least one winning gang, or choose Draw.")
    elif result == Battle.RESULT_DRAW and winners:
        add_error(
            "winners",
            "A draw has no winners. Clear the selection, or choose "
            "'One or more gangs won'.",
        )


def result_field(
    required_error="Choose a result before ending the battle.", widget=None
):
    """The 'how did it finish' radio, shared by the end and edit forms.

    The edit form passes its own ``required_error``: it records a result for a
    battle that has *already* ended, so telling the user to choose one "before
    ending the battle" would be nonsense there.
    """
    return forms.ChoiceField(
        choices=[
            (Battle.RESULT_WINNERS, "One or more gangs won"),
            (Battle.RESULT_DRAW, "Draw — no winner"),
        ],
        # form-check-input is what gives the control Bootstrap's 1em box and its
        # 0.25em top margin; without it the browser default sits high against
        # the first line of the label in the widget's align-items-start row.
        widget=widget or BsRadioSelect(attrs={"class": "form-check-input"}),
        label="Result",
        error_messages={"required": required_error},
    )


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

        # An ended battle must say how it finished — a blank result means
        # "nobody recorded one", which is not something an editor should be
        # able to leave behind. Battles that have not been fought yet are
        # unaffected.
        self.include_result = (
            include_winners and self.instance.status == Battle.POST_BATTLE
        )
        if self.include_result:
            self.fields["result"] = result_field(
                required_error="Choose how this battle finished."
            )
            self.fields["result"].initial = self.instance.result

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

        if self.include_result:
            validate_result_and_winners(
                cleaned_data.get("result"), winners, self.add_error
            )

        return cleaned_data


class BattleEndForm(forms.Form):
    """Record the result when a battle ends.

    Both fields always render: the radio decides which shape of answer is
    valid, never which fields are on screen. No JavaScript, no hidden fields.
    """

    # Plain widgets, not the Bs* ones: this form renders through
    # <c-form.choices>, which emits its own .form-check wrapper and label. The
    # Bs* option templates bake a label in as well, so pairing them shows every
    # option twice. The edit form still renders via {{ form }} and keeps Bs*.
    winners = forms.ModelMultipleChoiceField(
        queryset=List.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        label="Winner(s)",
        help_text="Only gangs taking part in this battle can be selected",
    )

    def __init__(self, *args, battle=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.battle = battle
        # `result` is declared here rather than as a class attribute so the
        # edit form can share the same field definition.
        # Passed in, not assigned afterwards: a widget swapped onto a built
        # field never receives its choices, and renders an empty control.
        self.fields["result"] = result_field(
            widget=forms.RadioSelect(attrs={"class": "form-check-input"})
        )
        # Most battles have a winner, so open on that rather than making every
        # player state the common case. A plain Form, so field.initial is read
        # directly — no self.initial seeded from an instance to shadow it.
        self.fields["result"].initial = Battle.RESULT_WINNERS
        self.order_fields(["result", "winners"])

        if battle is not None:
            self.fields["winners"].queryset = battle.participants.all()
            # Someone may have already set winners via the edit form; carry
            # that through rather than making them pick again.
            existing_winners = battle.winners.all()
            if existing_winners:
                self.fields["winners"].initial = existing_winners
                self.fields["result"].initial = Battle.RESULT_WINNERS

    def clean(self):
        cleaned_data = super().clean()
        validate_result_and_winners(
            cleaned_data.get("result"), cleaned_data.get("winners"), self.add_error
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
            "content": "Report",
        }
        widgets = {
            "content": TinyMCEWithUpload(
                attrs={"cols": 80, "rows": 20},
                mce_attrs={"min_height": "250px", **TINYMCE_EXTRA_ATTRS},
            ),
        }
