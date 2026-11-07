"""JSON props for the announcement bar's dismiss control."""

from django import template

register = template.Library()


@register.simple_tag
def announcement_props(dismiss_url="", banner_id="", csrf=""):
    """Serialise the dismissal URL, banner identity and CSRF token for the announcement control."""
    return {
        "dismissUrl": "" if dismiss_url is None else str(dismiss_url),
        "bannerId": "" if banner_id is None else str(banner_id),
        "csrfToken": "" if csrf is None else str(csrf),
    }
