"""The pick-list island's props, from the offer a view already built."""

from django import template

register = template.Library()


def _option(option):
    return {
        "key": str(option.key),
        "name": str(option.name),
        "detail": str(getattr(option, "detail", "") or ""),
        "grantedBy": str(getattr(option, "granted_by", "") or ""),
        "fixedBecause": str(getattr(option, "fixed_because", "") or ""),
        "picked": bool(getattr(option, "is_current", False)),
    }


@register.simple_tag
def pick_list_props(
    offer,
    addable,
    name="thing",
    add_label="Add",
    placeholder="Search",
    grouped=False,
    added_label="",
    save="",
    reset_form="",
):
    """A pick list as plain data: its groups, the options it can add, and
    what its buttons say.

    ``addable`` is the rest of the library, offered by the switcher and
    listed once ticked. Everything here is display data; which ticks the
    view accepts is decided again when the form arrives.
    """
    groups = getattr(offer, "groups", None) or []
    return {
        "name": name,
        "groups": [
            {
                "name": str(getattr(group, "name", "") or ""),
                "caption": str(getattr(group, "caption", "") or ""),
                "options": [_option(option) for option in group.options],
            }
            for group in groups
        ],
        "addable": [_option(option) for option in addable or []],
        "addLabel": add_label,
        "placeholder": placeholder,
        "grouped": bool(grouped),
        "addedLabel": added_label,
        "save": save,
        "resetForm": reset_form,
    }
