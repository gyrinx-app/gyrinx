"""JSON props for the announcement bar React draws over the fallback."""

from django import template

register = template.Library()

TONES = ("info", "success", "warning", "danger", "neutral")


def _flag(value):
    """A cotton boolean. Empty and the string false are off."""
    if isinstance(value, bool):
        return value
    if value is None:
        return True
    text = str(value).strip().lower()
    if text == "":
        return False
    return text not in {"false", "0", "off", "no"}


@register.simple_tag
def announcement_props(
    tone="info",
    icon="",
    message="",
    slot="",
    cta_text="",
    cta_url="",
    dismissible="1",
    dismiss_url="",
    banner_id="",
    csrf_token="",
    element_id="",
    css_class="",
):
    """The bar's words and, when a banner is remembered, where dismiss posts."""
    text = str(message or "").strip() or str(slot or "").strip()
    chosen = tone if tone in TONES else "info"
    return {
        "tone": chosen,
        "icon": "" if icon is None else str(icon),
        "message": text,
        "ctaText": "" if cta_text is None else str(cta_text),
        "ctaUrl": "" if cta_url is None else str(cta_url),
        "dismissible": _flag(dismissible),
        "dismissUrl": "" if dismiss_url is None else str(dismiss_url),
        "bannerId": "" if banner_id is None else str(banner_id),
        "csrfToken": "" if csrf_token is None else str(csrf_token),
        "id": "" if element_id is None else str(element_id),
        "className": "" if css_class is None else str(css_class),
    }
