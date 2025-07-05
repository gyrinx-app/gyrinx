from allauth.account.forms import LoginForm, ResetPasswordForm, SignupForm
from django import forms
from django_recaptcha.fields import ReCaptchaField, ReCaptchaV3


class BsCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    template_name = "pages/forms/widgets/bs_checkbox_select.html"
    option_template_name = "pages/forms/widgets/bs_checkbox_option.html"


class ResetPasswordForm(ResetPasswordForm):
    captcha = ReCaptchaField(widget=ReCaptchaV3(action="reset_password"))


class LoginForm(LoginForm):
    captcha = ReCaptchaField(widget=ReCaptchaV3(action="login"))


class SignupForm(SignupForm):
    captcha = ReCaptchaField(widget=ReCaptchaV3(action="signup"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Update username field help text and add validation
        print(self.fields.keys())
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
