"""Forms for starting, selecting and confirming a fighter action."""

from django import forms


class ActionOutcomeForm(forms.Form):
    outcome = forms.ChoiceField(label="Choose a result")

    def __init__(self, *args, outcomes, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["outcome"].choices = [
            (str(item.pk), str(item)) for item in outcomes
        ]


class StartActionForm(ActionOutcomeForm):
    request_key = forms.UUIDField(
        widget=forms.HiddenInput,
        error_messages={
            "invalid": "This form is not recognised. Reload this page and try again.",
            "required": "Reload this page before continuing.",
        },
    )
    allowance = forms.ChoiceField(
        required=False,
        widget=forms.HiddenInput,
        error_messages={
            "invalid_choice": "That earned use is no longer available. Return to the model to resume it or choose another.",
        },
    )

    def __init__(self, *args, outcomes, allowances, **kwargs):
        super().__init__(*args, outcomes=outcomes, **kwargs)
        self.fields["allowance"].choices = [
            (str(item.pk), str(item.threshold or "Recruitment")) for item in allowances
        ]


class ActionSelectionForm(forms.Form):
    selection = forms.ChoiceField(label="Choose tier")

    def __init__(self, *args, choices, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["selection"].choices = choices


class ConfirmActionForm(forms.Form):
    review = forms.CharField(widget=forms.HiddenInput)


class ActionRollForm(forms.Form):
    request_key = forms.UUIDField(
        widget=forms.HiddenInput,
        error_messages={
            "invalid": "This form is not recognised. Reload this page and try again.",
            "required": "Reload this page before rolling.",
        },
    )


class AdvancementRollForm(ActionRollForm):
    roll_mode = forms.ChoiceField(
        label="How would you like to roll?",
        choices=[("roll", "Roll in Gyrinx"), ("record", "Record my roll")],
        required=False,
    )
    rolled = forms.IntegerField(
        label="Your 2D6 total", min_value=2, max_value=12, required=False
    )

    def clean(self):
        data = super().clean()
        if data.get("roll_mode") == "record" and data.get("rolled") is None:
            if "rolled" not in self.errors:
                self.add_error("rolled", "Enter the total of your two dice.")
        elif data.get("roll_mode") != "record" and data.get("rolled") is not None:
            self.add_error("roll_mode", "Select Record my roll to use this total.")
        return data


class AdvancementForm(forms.Form):
    pickable_id = forms.ChoiceField(label="Choose an advancement")

    def __init__(self, *args, options, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pickable_id"].choices = [
            (option.id, option.name) for option in options
        ]


class SkillSelectionForm(forms.Form):
    skill_id = forms.ChoiceField(label="Select a skill")

    def __init__(self, *args, groups, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["skill_id"].choices = [
            (str(skill.pk), str(skill))
            for skills in groups.values()
            for skill in skills
        ]


class SkillRollForm(ActionRollForm):
    skill_set_id = forms.ChoiceField(label="Select a skill set")

    def __init__(self, *args, groups, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["skill_set_id"].choices = [
            (str(group.pk), str(group)) for group in groups
        ]


class EmptyActionForm(forms.Form):
    pass
