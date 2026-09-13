"""Forms for starting, selecting and confirming a fighter action."""

from django import forms


class StartActionForm(forms.Form):
    request_key = forms.UUIDField(widget=forms.HiddenInput)
    outcome = forms.ChoiceField(label="Choose an outcome")
    allowance = forms.ChoiceField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, outcomes, allowances, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["outcome"].choices = [
            (str(item.pk), str(item)) for item in outcomes
        ]
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
    request_key = forms.UUIDField(widget=forms.HiddenInput)


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
    skill_set_id = forms.ChoiceField(label="Select a Skill Set")

    def __init__(self, *args, groups, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["skill_set_id"].choices = [
            (str(group.pk), str(group)) for group in groups
        ]


class EmptyActionForm(forms.Form):
    pass
