import json
import logging

from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site

logger = logging.getLogger(__name__)


class CustomAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        """
        Whether to allow sign ups.
        """
        allow_signups = super(CustomAccountAdapter, self).is_open_for_signup(request)
        # Override with setting, otherwise default to super.
        return getattr(settings, "ACCOUNT_ALLOW_SIGNUPS", allow_signups)

    def get_reauthentication_methods(self, user):
        """Drop "use your password" when the destination is the Django admin.

        allauth's reauthentication normally accepts a password as proof of
        identity, which is the right trade-off for ordinary account changes. It
        is the wrong one here: the admin asks for reauthentication precisely
        because the session has not passed a second-factor challenge, so a
        password gets the user nowhere — allauth would record the wrong method
        and the admin would bounce them straight back to this page.

        See gyrinx/admin_site.py for the gate itself.
        """
        from allauth.core import context

        from gyrinx.admin_site import (
            admin_second_factor_required,
            is_admin_bound_request,
        )

        methods = super().get_reauthentication_methods(user)
        if not is_admin_bound_request(getattr(context, "request", None)):
            return methods
        if not admin_second_factor_required(user):
            return methods

        # Never return an empty list: that would deny reauthentication outright
        # rather than steer it.
        return [m for m in methods if m.get("id") != "reauthenticate"] or methods

    def send_mail(self, template_prefix, email, context):
        """
        Override send_mail to add custom headers from EMAIL_EXTRA_HEADERS setting.
        """

        # Parse extra headers from settings
        headers = {}
        try:
            extra_headers_str = getattr(settings, "EMAIL_EXTRA_HEADERS", "{}")
            extra_headers = json.loads(extra_headers_str)

            # Add extra headers
            for key, value in extra_headers.items():
                headers[key] = value

        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(f"Failed to parse EMAIL_EXTRA_HEADERS: {e}")

        if "current_site" not in context:
            context["current_site"] = get_current_site(self.request)

        if "email" not in context:
            context["email"] = email

        if "request" not in context:
            context["request"] = self.request

        msg = self.render_mail(template_prefix, email, context, headers=headers)
        msg.send()
