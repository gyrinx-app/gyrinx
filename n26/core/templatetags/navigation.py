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
def gang_switcher(context, gang, named=True, menu_label="Switch to another gang"):
    """The switcher on a screen that belongs to one gang.

    A tag for the same reason the drawer's list is one: the rows are the
    reader's own gangs, wanted only by the pages that draw a gang, and
    read through the same memo — so a page drawing this in the bar, again
    beside its heading, and the drawer as well still spends one query on
    them between the three.

    ``named=False`` is the chevron on its own, for a heading that is
    already the gang's name. A page drawing this twice must give the
    second one its own ``menu_label``.
    """
    from n26.core.navigation import gang_switcher as build

    return build(context["request"], gang, named=named, menu_label=menu_label)


@register.simple_tag(takes_context=True)
def fighter_switcher(context, gang, miniature):
    """The gang's fighters, from the screen of one of them.

    A tag rather than view context: it is the same control on every
    fighter screen, and one query that only the pages drawing it should
    pay for. The rows are ``n26.core.navigation``'s — capped, scoped to
    the gang, and off the roster means out of the list.

    Which screen the rows lead to is read off the request rather than
    written at each call site: a page draws this to reach the *same*
    screen for the next fighter, so the answer is already the page being
    rendered and a name passed by hand is one more thing to get wrong —
    a template variable that stops matching resolves to empty in
    silence. A screen with no per-fighter address of its own, or a
    render with no resolved route at all, falls back to the kit screen.
    """
    from n26.core.navigation import fighter_switcher as build

    match = getattr(context.get("request"), "resolver_match", None)
    return build(gang, miniature, route=getattr(match, "url_name", "") or "")
