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
