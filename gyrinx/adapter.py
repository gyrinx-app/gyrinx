import json
import logging
from io import BytesIO

from allauth.account.adapter import DefaultAccountAdapter
from allauth.mfa.adapter import DefaultMFAAdapter
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import PermissionDenied

from gyrinx.client_ip import get_client_ip

logger = logging.getLogger(__name__)


class CustomAccountAdapter(DefaultAccountAdapter):
    def get_client_ip(self, request):
        """Use the same trusted proxy boundary as application audit events."""
        ip = get_client_ip(request)
        if ip is None:
            raise PermissionDenied("Unable to determine client IP address")
        return ip

    def is_open_for_signup(self, request):
        """Use ACCOUNT_ALLOW_SIGNUPS when configured, otherwise retain allauth's decision."""
        allow_signups = super().is_open_for_signup(request)
        return getattr(settings, "ACCOUNT_ALLOW_SIGNUPS", allow_signups)

    def get_reauthentication_methods(self, user):
        """Prefer second-factor methods when an admin-bound session requires another challenge.

        A password alone cannot satisfy the admin gate in gyrinx/admin_site.py.
        Retain the original methods if filtering would leave none available.
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

        # Keep available methods when filtering would otherwise block all reauthentication.
        return [m for m in methods if m.get("id") != "reauthenticate"] or methods

    def send_mail(self, template_prefix, email, context):
        """Send allauth mail with headers from EMAIL_EXTRA_HEADERS and required template context."""

        headers = {}
        try:
            extra_headers_str = getattr(settings, "EMAIL_EXTRA_HEADERS", "{}")
            extra_headers = json.loads(extra_headers_str)

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


class CustomMFAAdapter(DefaultMFAAdapter):
    def build_totp_svg(self, url: str) -> str:
        """Render the authenticator QR with a white background so dark pages preserve contrast."""
        import qrcode
        from qrcode.image.svg import SvgPathFillImage

        img = qrcode.make(url, image_factory=SvgPathFillImage)
        buf = BytesIO()
        img.save(buf)
        return buf.getvalue().decode("utf8")
