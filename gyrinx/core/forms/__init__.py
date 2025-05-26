from allauth.account.forms import LoginForm, ResetPasswordForm, SignupForm
from django import forms
from django_recaptcha.fields import ReCaptchaField, ReCaptchaV3


class BsCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    template_name = "pages/forms/widgets/bs_checkbox_select.html"
    option_template_name = "pages/forms/widgets/bs_checkbox_option.html"


class RequestContextMixin:
    def __init__(self, *args, **kwargs):
        if "request" not in kwargs or kwargs["request"] is None:
            raise ValueError(
                "RequestContextMixin requires a 'request' keyword argument."
            )
        super().__init__(*args, **kwargs)

        if hasattr(self, "fields") and "captcha" not in self.fields:
            raise ValueError(
                "RequestContextMixin requires a 'captcha' field in the form."
            )

        self.fields["captcha"].widget.request = self.request


class ReCaptchaV3WithRequest(ReCaptchaV3):
    """A ReCaptchaV3 widget that can pass the request context to the template."""

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)

        if not hasattr(self, "request") or self.request is None:
            raise ValueError("ReCaptchaV3WithRequest requires a 'request' attribute.")

        context.update(
            {
                "request": getattr(self, "request", None),
            }
        )

        return context


class ResetPasswordForm(ResetPasswordForm):
    captcha = ReCaptchaField(widget=ReCaptchaV3WithRequest(action="reset_password"))


class LoginForm(RequestContextMixin, LoginForm):
    captcha = ReCaptchaField(widget=ReCaptchaV3WithRequest(action="login"))


class SignupForm(SignupForm):
    captcha = ReCaptchaField(widget=ReCaptchaV3WithRequest(action="signup"))
