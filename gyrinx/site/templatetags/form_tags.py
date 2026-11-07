"""Template tags for the shared Cotton form components.

require_bound_field rejects stringified widgets before labels or errors can
be lost. field_label calls Django's label methods with optional text and CSS.
submit_variant validates semantic submit intents. space_before controls
attribute whitespace while preserving existing SafeData status.
"""

import logging

from django import template
from django.conf import settings
from django.utils.html import format_html
from django.utils.safestring import SafeData, mark_safe

logger = logging.getLogger(__name__)

register = template.Library()


# Semantic form-submit intents and their Bootstrap colours. Unknown intents are invalid.
SUBMIT_INTENTS = {
    # creation / confirmation
    "save": "success",
    "create": "success",
    "confirm": "success",
    "apply": "success",
    "add": "success",
    "update": "success",
    "send": "success",
    "generate": "success",
    "restore": "success",
    "unarchive": "success",
    "resurrect": "success",
    # destructive
    "delete": "danger",
    "archive": "danger",
    "remove": "danger",
    "discard": "danger",
    "destroy": "danger",
    "reset": "danger",
    "clear": "danger",
    "revert": "danger",
    "kill": "danger",
    "sell": "danger",
    "deactivate": "danger",
    # navigation
    "next": "primary",
    "continue": "primary",
    "search": "primary",
    "filter": "primary",
    "select": "primary",
    "go": "primary",
    # cautionary state changes (the amber lifecycle actions: capture, ransom)
    "capture": "warning",
    "warn": "warning",
    # deliberately muted
    "secondary": "secondary",
}


def _loud(message):
    """Raise TemplateSyntaxError in strict mode; otherwise log the component error.

    Use COTTON_STRICT_COMPONENTS, falling back to DEBUG only when unset.
    Development settings enable strict mode independently of pytest's DEBUG.
    """
    if getattr(settings, "COTTON_STRICT_COMPONENTS", settings.DEBUG):
        raise template.TemplateSyntaxError(message)
    logger.error("cotton form component: %s", message)


@register.simple_tag(name="require_bound_field")
def require_bound_field(field, component):
    """Check that field supplies the BoundField label API; render nothing.

    Call unconditionally before testing field.label: a stringified widget
    has no label and would otherwise bypass validation.
    """
    if not hasattr(field, "label_tag"):
        _loud(
            f"<c-{component}> needs a BoundField. Got "
            f"{type(field).__name__!r}"
            + (" (empty — the prop was never passed)" if not field else "")
            + '. Use the colon form: :field="form.name". The quoted form '
            'field="{{ form.name }}" stringifies the widget, and the label, '
            "help text and ERRORS are then all silently dropped (#2001)."
        )
    return ""


@register.simple_tag(name="field_label")
def field_label(field, text="", css_class="", suffix="", tag="label", note=""):
    """Render the field's label or legend with optional replacement text and CSS.

    An empty text uses the field label. suffix defaults to no colon; pass
    None to use the form's suffix. tag="legend" selects Django's legend_tag.
    The optional note is escaped and added in a secondary span. Return an
    empty string when the BoundField API is unavailable.
    """
    if not hasattr(field, "label_tag"):
        return ""
    contents = text or field.label
    if note:
        contents = format_html(
            '{} <span class="text-secondary">{}</span>', contents, note
        )
    render = field.legend_tag if tag == "legend" else field.label_tag
    return render(
        contents=contents or None,
        attrs={"class": css_class} if css_class else None,
        label_suffix=suffix,
    )


@register.simple_tag(name="submit_variant")
def submit_variant(intent):
    """Return the Bootstrap colour for a normalised submit intent.

    Unknown intents raise in strict mode. Otherwise log the error and use
    secondary, avoiding a success colour for an unrecognised destructive action.
    """
    key = str(intent or "").strip().lower()
    if key in SUBMIT_INTENTS:
        return SUBMIT_INTENTS[key]
    _loud(
        f"submit intent {intent!r} is not in the design-system vocabulary. "
        f"Known intents: {', '.join(sorted(SUBMIT_INTENTS))}. Add the verb to "
        "SUBMIT_INTENTS in gyrinx/site/templatetags/form_tags.py with a "
        "deliberate colour — do not let it default."
    )
    return "secondary"


@register.filter(name="space_before")
def space_before(value):
    """Strip a value and prepend one space, or return an empty string.

    Use for optional attributes and appended classes to avoid surplus spaces
    and template formatter newlines inside class values. Preserve SafeData
    status for Cotton attributes; ordinary strings remain subject to escaping.
    """
    if value is None or value is False:
        return ""
    rendered = value if isinstance(value, str) else str(value)
    text = rendered.strip()
    if not text:
        return ""
    out = f" {text}"
    # Preserve existing SafeData status without marking ordinary strings safe.
    # Bandit cannot infer this guard. Keep its suppression on the return statement;
    # placing the directive keyword in prose makes Bandit parse the following words as IDs.
    return mark_safe(out) if isinstance(rendered, SafeData) else out  # nosec
