"""JSON props for the accessory link beside a held weapon's name."""

from django import template

register = template.Library()


@register.simple_tag
def accessorise_link_props(href, copy_id, label, name):
    """The address the link follows, and the dialog that address opens.

    The dialog id is ``n26-accessorise-`` plus the copy id, the same id
    ``equip_accessorise.html`` writes on the panel. The click names that
    panel; without a script the link still goes to ``href``.
    """
    return {
        "href": "" if href is None else str(href),
        "dialogId": f"n26-accessorise-{'' if copy_id is None else copy_id}",
        "label": "" if label is None else str(label),
        "name": "" if name is None else str(name),
    }
