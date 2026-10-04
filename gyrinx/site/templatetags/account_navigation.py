"""Navigation shared by platform account pages and allauth subpages."""

from django import template
from django.urls import reverse

register = template.Library()


@register.simple_tag(takes_context=True)
def account_tabs(context):
    request = context["request"]
    name = request.resolver_match.url_name
    current = context.get("account_tab")
    if not current:
        if name == "account_home":
            current = "overview"
        elif name == "notifications":
            current = "notifications"
        elif name in {
            "account_email",
            "account-settings",
            "badge-settings",
            "timezone-settings",
            "change-username",
        }:
            current = "settings"
        else:
            current = "security"
    return [
        {"label": label, "href": reverse(url), "current": key == current}
        for key, label, url in [
            ("overview", "Overview", "core:account_home"),
            ("notifications", "Notifications", "core:notifications"),
            ("settings", "Settings", "account-settings"),
            ("security", "Security", "account-security"),
        ]
    ]
