"""JSON props for the accessory link beside a held weapon's name."""

from django import template

register = template.Library()


@register.simple_tag
def accessorise_link_props(href, copy_id, label, name):
    """Build a link URL and the matching accessorising dialog ID.

    The ID uses n26-accessorise- plus the copy ID, matching equip_accessorise.html.
    Without scripting, navigation still follows href.
    """
    return {
        "href": "" if href is None else str(href),
        "dialogId": f"n26-accessorise-{'' if copy_id is None else copy_id}",
        "label": "" if label is None else str(label),
        "name": "" if name is None else str(name),
    }
