"""Form components.

``FormField`` reproduces ``core/includes/form_field.html`` exactly (label,
widget, help text, errors). Django bound-field methods return ``SafeString``,
which the engine renders without double-escaping.
"""

from __future__ import annotations

from typing import Any, Iterable

from ..elements import Element, Node, fragment
from ..tags import div, form, input_, small
from .buttons import SubmitButton

__all__ = ["FormField", "FormFields", "Form", "CsrfInput"]


def FormField(field: Any, *, class_: Any = None, **attrs: Any) -> Element:
    """Render a Django ``BoundField`` with the standard label/widget/help/error
    structure (matches ``core/includes/form_field.html``)."""
    return div(class_=class_, **attrs)[
        field.label_tag(),
        field,
        small(class_="form-text text-secondary")[field.help_text]
        if field.help_text
        else None,
        div(class_="invalid-feedback d-block")[field.errors] if field.errors else None,
    ]


def FormFields(form_obj: Any, *, fields: Iterable[str] | None = None) -> Node:
    """Render several bound fields with :func:`FormField`. ``fields`` selects and
    orders field names; defaults to the form's visible fields."""
    if fields is not None:
        bound = [form_obj[name] for name in fields]
    else:
        bound = list(form_obj.visible_fields())
    return fragment[tuple(FormField(field) for field in bound)]


def CsrfInput(request: Any) -> Element:
    """A CSRF hidden input for POST forms (replaces ``{% csrf_token %}``)."""
    from django.middleware.csrf import get_token

    return input_(type="hidden", name="csrfmiddlewaretoken", value=get_token(request))


def Form(
    *children: Any,
    method: str = "post",
    request: Any = None,
    csrf: bool | None = None,
    gap: int | None = 3,
    submit: Any = None,
    action: str | None = None,
    class_: Any = None,
    **attrs: Any,
) -> Element:
    """A ``<form>`` with the standard ``vstack gap-3`` layout.

    When ``method`` is post and ``request`` is given (``csrf`` not explicitly
    ``False``), a CSRF hidden input is inserted automatically. ``submit`` adds a
    trailing ``div.mt-3`` submit-button row."""
    include_csrf = (
        csrf if csrf is not None else (method.lower() == "post" and request is not None)
    )
    body: list[Any] = []
    if include_csrf and request is not None:
        body.append(CsrfInput(request))
    body.extend(children)
    if submit is not None:
        submit_row = submit if not isinstance(submit, str) else SubmitButton(submit)
        body.append(div(class_="mt-3")[submit_row])
    classes = [f"vstack gap-{gap}" if gap is not None else None, class_]
    return form(method=method, action=action, class_=classes, **attrs)[tuple(body)]
