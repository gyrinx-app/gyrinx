from allauth.account.forms import LoginForm, ResetPasswordForm, SignupForm
from django import forms
from django.contrib.auth import get_user_model
from django.core import validators
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django_recaptcha.fields import ReCaptchaField, ReCaptchaV3


class BsCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    template_name = "pages/forms/widgets/bs_checkbox_select.html"
    option_template_name = "pages/forms/widgets/bs_checkbox_option.html"


class BsClearableFileInput(forms.ClearableFileInput):
    template_name = "pages/forms/widgets/bs_clearable_file_input.html"
    clear_checkbox_label = _("Clear image")
    clear_checkbox_help_text = _("Check and click Save to clear the image.")
    input_text = _("Replace image")

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["clear_checkbox_help_text"] = self.clear_checkbox_help_text
        return context


class ResetPasswordForm(ResetPasswordForm):
    captcha = ReCaptchaField(widget=ReCaptchaV3(action="reset_password"))


class LoginForm(LoginForm):
    captcha = ReCaptchaField(widget=ReCaptchaV3(action="login"))


class SignupForm(SignupForm):
    captcha = ReCaptchaField(widget=ReCaptchaV3(action="signup"))
    tos_agreement = forms.BooleanField(
        required=True,
        label="Agree to the Terms of Use",
        help_text=mark_safe(  # nosec B308 - HTML content required for TOS link
            'By signing up, you acknowledge that you have read and agree to be bound by our <a href="/terms/" target="_blank">Terms of Use</a>'
        ),
        error_messages={
            "required": "You must agree to the Terms of Use to create an account."
        },
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Update username field help text and add validation
        if "username" in self.fields:
            self.fields["username"].help_text = (
                "This is the name you'll use to log in to Gyrinx. "
                "It can only contain letters, numbers, and underscores. "
                "Please pick a username, not an email address."
            )
            # Add validator to check for @ symbol
            from django.core import validators

            self.fields["username"].validators.insert(
                0,
                validators.RegexValidator(
                    regex=r"^[^@]+$",
                    message="Username cannot be an email address. Please choose a username without @ symbol.",
                ),
            )

        if "email" in self.fields:
            self.fields["email"].help_text = (
                "We are having difficulty sending automated emails to Microsoft email addresses "
                "(live.com, hotmail.com, hotmail.co.uk etc.). "
                "Please use a different address if you can."
            )

        # Move tos_agreement to the end of the form
        if "tos_agreement" in self.fields:
            tos_field = self.fields.pop("tos_agreement")
            self.fields["tos_agreement"] = tos_field


class UsernameChangeForm(forms.Form):
    """Form for users to change their username (only for users with @ in username)."""

    new_username = forms.CharField(
        max_length=150,
        label="New Username",
        help_text=(
            "Choose a new username. "
            "It can only contain letters, numbers, and underscores. "
            "Please pick a username, not an email address."
        ),
        validators=[
            validators.RegexValidator(
                regex=r"^[^@]+$",
                message="Username cannot be an email address. Please choose a username without @ symbol.",
            ),
            validators.RegexValidator(
                regex=r"^[a-zA-Z0-9_]+$",
                message="Username can only contain letters, numbers, and underscores.",
            ),
        ],
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    captcha = ReCaptchaField(widget=ReCaptchaV3(action="change_username"))

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def clean_new_username(self):
        new_username = self.cleaned_data["new_username"]
        User = get_user_model()

        # Check if username is already taken
        if (
            User.objects.filter(username__iexact=new_username)
            .exclude(pk=self.user.pk)
            .exists()
        ):
            raise forms.ValidationError("This username is already taken.")

        # Check against blacklist (matching settings configuration)
        blacklist = ["admin", "superuser", "staff", "user", "gyrinx"]
        if new_username.lower() in blacklist:
            raise forms.ValidationError("This username is not allowed.")

        return new_username

    def save(self):
        """Save the new username to the user."""
        if self.user:
            self.user.username = self.cleaned_data["new_username"]
            self.user.save()
            return self.user
