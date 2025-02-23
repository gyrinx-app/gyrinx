from django import forms
from django.core import validators
from django_recaptcha.fields import ReCaptchaField, ReCaptchaV3

from gyrinx.core.forms import BsCheckboxSelectMultiple
from gyrinx.pages.models import WaitingListEntry, WaitingListSkill


class InviteUserForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)


class JoinWaitingListForm(forms.ModelForm):
    class Meta:
        model = WaitingListEntry
        fields = [
            "email",
            "desired_username",
            "yaktribe_username",
            "skills",
            "notes",
        ]
        read_only_fields = ["referred_by_code"]

    email = forms.EmailField(
        label="What's your email address?",
        help_text="If you support Gyrinx on Patreon, please use the email address associated with your Patreon account.",
        required=True,
        widget=forms.EmailInput(
            attrs={"placeholder": "you@example.com", "class": "form-control"}
        ),
    )
    desired_username = forms.CharField(
        label="What would you ideally like your Gyrinx username to be?",
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "lord_helmawr", "class": "form-control"}
        ),
        help_text="This is the name you'll use to log in to Gyrinx. It can only contain letters, numbers, and underscores.",
        validators=[
            validators.RegexValidator(
                regex=r"^[a-zA-Z0-9_]+$",
                message="Username can only contain alphanumeric characters and underscores.",
            ),
            validators.MinLengthValidator(3),
            validators.MaxLengthValidator(30),
        ],
    )
    yaktribe_username = forms.CharField(
        label="YakTribe user? Tell us your username…",
        label_suffix="",
        help_text="We're working on ways to import your YakTribe data, so this will help us match you up.",
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "lord_helmawr", "class": "form-control"}
        ),
    )
    skills = forms.ModelMultipleChoiceField(
        queryset=WaitingListSkill.objects.all(),
        label="Interested in helping out? Tell us what you'd bring to the table…",
        label_suffix="",
        required=False,
        widget=BsCheckboxSelectMultiple(
            attrs={"class": "form-check-input"},
        ),
    )
    notes = forms.CharField(
        label="Anything else you'd like to tell us?",
        required=False,
        widget=forms.Textarea(attrs={"placeholder": "", "class": "form-control"}),
    )
    referred_by_code = forms.UUIDField(
        widget=forms.HiddenInput(),
        required=False,
    )

    captcha = ReCaptchaField(
        widget=ReCaptchaV3(
            action="sign_up_for_waiting_list",
        )
    )
