"""Template tags for the cotton form components (``gyrinx/templates/cotton/form/``).

Four symbols, each of which exists because a Django template cannot do the job:

``require_bound_field``
    The load-bearing safety guard. ``<c-form.field field="{{ form.name }}" />``
    (no colon) stringifies the widget; every ``field.*`` lookup then resolves to
    nothing and the component renders a plausible-looking wrapper with NO label,
    NO help text and — the part that matters — NO ERRORS. That is a verbatim
    reintroduction of the #2001 hidden-form-errors bug inside the component
    built to make it impossible. This tag is called UNCONDITIONALLY, at the top
    of every field component, outside every ``{% if %}``, so the mistake raises
    instead of rendering.

``field_label``
    Templates cannot call a method with arguments, so ``{{ field.label_tag }}``
    can never carry a CSS class or replacement text. That single limitation is
    why 101 sites in the estate hand-write

        <label class="form-label" for="{{ f.id_for_label }}">{{ f.label }}</label>

    and in doing so throw away Django's ``for`` resolution (which knows about
    multi-widget fields, where ``id_for_label`` is not ``auto_id``) and the
    ``required``/``aria`` handling that comes with it. One tag keeps ONE label
    code path in the components: overriding the text does not silently switch
    the component to a different, hand-built ``<label>`` with different margins.

``submit_variant``
    Maps the submit row's semantic ``intent`` to a Bootstrap colour, and FAILS
    on an unknown intent rather than defaulting. A dictionary lookup with
    ``|default:'success'`` turns ``intent="destroy"`` into a green button on a
    delete page — the exact failure the colour vocabulary exists to prevent.

``space_before``
    Whitespace-exact attribute emission. See its docstring.
"""

import logging

from django import template
from django.conf import settings
from django.utils.html import format_html
from django.utils.safestring import SafeData, mark_safe

logger = logging.getLogger(__name__)

register = template.Library()


# Semantic verb -> Bootstrap button colour for a FORM SUBMIT button.
#
# docs/DESIGN-SYSTEM.md and core/debug/design_system.html disagree about
# toolbars (btn-success allowed vs banned). That disagreement is about
# TOOLBARS; this table is the submit row, where both agree.
#
# The map is deliberately exhaustive over the verbs the estate actually uses.
# An unknown verb is an ERROR, not a default — see submit_variant.
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
    """Raise when strict (dev + pytest), log otherwise.

    Strictness is ``settings.COTTON_STRICT_COMPONENTS``, NOT ``settings.DEBUG``.
    pytest-django forces ``DEBUG = False`` for the whole suite, so a
    DEBUG-keyed guard is switched off in precisely the place it is supposed to
    catch things — verified: the first version of this guard logged instead of
    raising under pytest, which is how it stayed unnoticed that it also sat
    behind an ``{% if field.label %}`` and never ran at all.

    Every call site of this module is gated by ``scripts/check_cotton.py``
    (pre-commit) and ``test_cotton_call_site_gates.py`` (CI), so a mistake
    cannot reach production in the first place. The production branch therefore
    degrades and logs rather than 500-ing a whole page.
    """
    if getattr(settings, "COTTON_STRICT_COMPONENTS", settings.DEBUG):
        raise template.TemplateSyntaxError(message)
    logger.error("cotton form component: %s", message)


@register.simple_tag(name="require_bound_field")
def require_bound_field(field, component):
    """Assert that ``field`` is a BoundField. Renders nothing.

    Called unconditionally as the first tag of every field component. The
    earlier version of this guard lived inside ``field_label``, which is only
    reached when ``{% if field.label %}`` is true — and a stringified widget has
    no ``.label``, so the guard was unreachable in exactly the case it existed
    for. Verified: it never fired.
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
    """Render a BoundField's ``<label>`` (or ``<legend>``), optionally re-worded.

    ``text``      replacement label text. Empty means "use the field's own".
    ``css_class`` class attribute for the element.
    ``suffix``    label suffix. Defaults to ``""`` — NO trailing colon, anywhere.
                  This is the one normalisation decision the component family
                  makes about label copy, and it is made here so that both the
                  36 include sites and the 27 ``{{ form }}`` pages get the same
                  answer. Pass ``suffix=None`` to honour the form's own
                  ``label_suffix`` instead.
    ``tag``       ``"label"`` or ``"legend"``. ``legend`` correctly omits
                  ``for``, which is invalid on a ``<legend>``.
    ``note``      a short secondary annotation rendered inside the label as
                  ``<span class="text-secondary">``. Autoescaped. This is why
                  ``<c-form.cell>`` can share this one code path instead of
                  hand-rolling a second ``<label>`` (which is how the estate
                  grew 13 label-class variants in the first place).

    Renders nothing for a non-BoundField; ``require_bound_field`` has already
    raised by the time this runs.
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
    """Map a submit-row ``intent`` to a Bootstrap colour, loudly.

    An unmapped intent is a bug, not a default. ``{{ intents|get_item:intent
    |default:'success' }}`` — the shape this replaces — renders
    ``intent="destroy"`` and ``intent="Delete"`` as a GREEN button on a delete
    page, with no error anywhere. Green is not a neutral colour in this design
    system; it means "this creates or confirms something".

    Unknown intents raise in DEBUG (so they are found while writing the
    template) and fall back to ``secondary`` in production, which is visibly
    wrong rather than invisibly wrong.
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
    """Return ``" value"`` for a non-empty value, ``""`` otherwise.

    Two jobs, both about emitting attributes with exactly the right whitespace.

    1. ``{{ attrs }}`` written directly after a conditional ``class`` leaves a
       stray space on every element that has neither (``<div  >``). Harmless in
       a browser, fatal to a golden-HTML diff: it puts noise on EVERY field of
       EVERY form, and a reviewer who learns to normalise that away stops
       reading the diff that was supposed to catch the real changes. Written as
       ``{{ attrs|space_before }}`` the element renders as exactly ``<div>``.
       Safe strings stay safe, so cotton's attribute output is unchanged.

    2. Cotton does not merge classes, so every component concatenates the
       caller's ``class`` onto its own by hand. The obvious spelling of that —

           class="vstack gap-3{% if class %} {{ class }}{% endif %}"

       is not safe in a long attribute value: djlint reflows it and injects a
       NEWLINE INTO the class string. Verified on cotton/form/edit.html, with
       that exact markup. Short values survive; long ones do not, so the failure
       only appears once a component grows.
    """
    if value is None or value is False:
        return ""
    rendered = value if isinstance(value, str) else str(value)
    text = rendered.strip()
    if not text:
        return ""
    out = f" {text}"
    # `{{ attrs }}` is already mark_safe'd by cotton; passing it through a
    # filter must not re-escape it. Plain strings (a `class` prop) stay
    # escapable.
    #
    # The suppression below is safe: this PRESERVES safety, it never confers
    # it. The mark_safe branch is reachable only when the input was ALREADY
    # SafeData (cotton's own attribute output); anything else -- notably a
    # `class` prop carrying user-supplied text -- returns a plain str and is
    # escaped by the template engine as normal. Bandit cannot see the
    # isinstance guard. (Do not begin this comment with the suppression
    # keyword: bandit parses the following words as test ids and the real
    # directive on the return line then stops working.)
    return mark_safe(out) if isinstance(rendered, SafeData) else out  # nosec
