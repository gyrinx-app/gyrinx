"""JSON props for the announcement bar's dismiss control."""

from django import template

register = template.Library()


@register.simple_tag
def announcement_props(dismiss_url="", banner_id="", csrf=""):
    """Where a remembered dismissal posts, when the shell asks for one."""
    return {
        "dismissUrl": "" if dismiss_url is None else str(dismiss_url),
        "bannerId": "" if banner_id is None else str(banner_id),
        "csrfToken": "" if csrf is None else str(csrf),
    }
