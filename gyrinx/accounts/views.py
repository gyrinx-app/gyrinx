"""Combined platform account screens; allauth owns authentication operations."""

from base64 import b64encode

from allauth.account.internal.flows import manage_email
from allauth.account.views import EmailView, PasswordChangeView, PasswordSetView
from allauth.mfa.base.views import IndexView
from allauth.usersessions.views import ListUserSessionsView
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.html import strip_tags

from gyrinx.account_forms import AccountSettingsForm
from gyrinx.accounts.models import UserProfile


def _flat_choices(choices):
    for value, label in choices:
        if isinstance(label, (list, tuple)):
            yield from label
        else:
            yield value, label


def _field_props(form):
    badge_images = {}
    for badge in form.badge_form.profile.available_badges:
        svg = badge.inline_svg()
        badge_images[badge.slug] = (
            f"data:image/svg+xml;base64,{b64encode(svg.encode()).decode()}"
            if svg
            else ""
        )
    return [
        {
            "name": field.name,
            "label": field.label,
            "value": str(field.value() or ""),
            "help": str(field.help_text),
            "errors": list(field.errors),
            "choices": [
                {
                    "value": str(value),
                    "label": str(label),
                    **(
                        {"imageUrl": badge_images.get(value, "")}
                        if field.name == "selected_badge"
                        else {}
                    ),
                }
                for value, label in _flat_choices(field.field.choices)
            ]
            if hasattr(field.field, "choices")
            else [],
        }
        for field in form
    ]


class SettingsView(EmailView):
    template_name = "account/settings.html"
    success_url = reverse_lazy("account-settings")

    def get_form_class(self):
        return AccountSettingsForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        UserProfile.objects.get_or_create(user=self.request.user)
        return kwargs

    def post(self, request, *args, **kwargs):
        if "action_save" in request.POST:
            form = self.get_form()
            if form.is_valid():
                return self.form_valid(form)
            return self.form_invalid(form)
        # Resending and cancelling a pending email retain allauth's contracts.
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        with transaction.atomic():
            if form.email_changed:
                manage_email.add_email(self.request, form.email_form)
                self._did_send_verification_email = True
            form.save_preferences()
        messages.success(self.request, "Account settings saved.")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["account_tab"] = "settings"
        context["settings_form"] = {
            "actionUrl": reverse("account-settings"),
            "csrfToken": get_token(self.request),
            "fields": _field_props(context["form"]),
            "errors": list(context["form"].non_field_errors()),
        }
        return context


def security_context(request, password_form=None):
    password_view = (
        PasswordChangeView()
        if request.user.has_usable_password()
        else PasswordSetView()
    )
    password_view.setup(request)
    password_form = password_form or password_view.get_form()
    mfa_view = IndexView()
    mfa_view.setup(request)
    session_view = ListUserSessionsView()
    session_view.setup(request)
    context = mfa_view.get_context_data()
    context.update(session_view.get_context_data())
    context.update(
        {
            "account_tab": "security",
            "password_form": {
                "actionUrl": reverse(
                    "account_change_password"
                    if request.user.has_usable_password()
                    else "account_set_password"
                ),
                "csrfToken": get_token(request),
                "fields": [
                    {
                        "name": f.name,
                        "label": f.label,
                        "autocomplete": f.field.widget.attrs.get(
                            "autocomplete", "new-password"
                        ),
                        "errors": list(f.errors),
                        "help": str(
                            strip_tags(str(f.help_text).replace("</li>", "</li> "))
                        ),
                    }
                    for f in password_form
                ],
                "returnUrl": reverse("account-security"),
                "resetUrl": reverse("account_reset_password"),
                "errors": list(password_form.non_field_errors()),
            },
        }
    )
    return context


@login_required
def security(request):
    return render(request, "account/security.html", security_context(request))


class CombinedPasswordChangeView(PasswordChangeView):
    def form_invalid(self, form):
        return render(
            self.request, "account/security.html", security_context(self.request, form)
        )


class CombinedPasswordSetView(PasswordSetView):
    def get(self, request, *args, **kwargs):
        return redirect("account-security")

    def form_invalid(self, form):
        return render(
            self.request, "account/security.html", security_context(self.request, form)
        )


@login_required
def legacy_security(request):
    return redirect(reverse("account-security"))


@login_required
def legacy_settings(request):
    return redirect(reverse("account-settings"))


def legacy_password(request):
    if request.method == "GET":
        return legacy_security(request)
    return CombinedPasswordChangeView.as_view()(request)


def legacy_email(request):
    if request.method == "GET":
        return legacy_settings(request)
    return EmailView.as_view()(request)


def legacy_sessions(request):
    if request.method == "GET":
        return legacy_security(request)
    return ListUserSessionsView.as_view()(request)
