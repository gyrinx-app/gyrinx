"""Template helpers for the site navigation."""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def drawer_gangs(context):
    """The signed-in user's gangs, for the navigation drawer.

    A tag rather than a context processor: the drawer is drawn by this
    edition's layout and nowhere else, and a processor would run this query
    for every page on the site, including the ones that have no drawer.

    The rows themselves — the cap, the ordering, and the memo that keeps this
    and the bar's gang switcher to one query between them — belong to
    ``n26.core.navigation``. Anonymous visitors get an empty list, which the
    drawer reads as "no section at all" rather than an empty heading.
    """
    from n26.core.navigation import owned_gangs

    request = context.get("request")
    if request is None:
        return []
    return owned_gangs(request)


@register.simple_tag(takes_context=True)
def gang_switcher(context, gang):
    """The bar's switcher on a screen that belongs to one gang.

    A tag for the same reason the drawer's list is one: the rows are the
    reader's own gangs, wanted only by the pages that draw the bar with a
    gang in it, and read through the same memo — so a gang screen showing
    both the drawer and this switcher still spends one query on them.
    """
    from n26.core.navigation import gang_switcher as build

    return build(context["request"], gang)
