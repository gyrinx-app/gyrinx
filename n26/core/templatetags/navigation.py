"""Template helpers for the site navigation."""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def drawer_gangs(context):
    """Read the signed-in user's drawer gangs through the shared navigation cache.

    Use a tag so pages without the N26 drawer perform no query. Anonymous
    visitors receive an empty list and no section.
    """
    from n26.core.navigation import owned_gangs

    request = context.get("request")
    if request is None:
        return []
    return owned_gangs(request)


@register.simple_tag(takes_context=True)
def places_switcher(context, here=""):
    """Build the default app-place switcher for pages without a resource switcher.

    ``here`` identifies the current drawer destination and leading link.
    """
    from n26.core.navigation import places_switcher as build

    return build(context.get("request"), here=here)


@register.simple_tag
def quick_switcher_props(
    switcher, align="start", min_width="16rem", hotkey="", trigger_words=""
):
    """Build quick-switcher props with the next server page offset.

    The offset is SWITCHER_PAGE even when the current destination was prepended,
    preventing it from skipping ordinary list entries.
    """
    from n26.core.navigation import SWITCHER_PAGE

    items = tuple(switcher.items)
    return {
        "label": switcher.label,
        "href": switcher.href,
        "heading": switcher.heading,
        "menuLabel": switcher.menu_label,
        "placeholder": switcher.placeholder,
        "empty": switcher.empty,
        "align": "end" if align == "end" else "start",
        "minWidth": min_width,
        "hotkey": hotkey,
        "triggerWords": trigger_words,
        "items": [
            {"label": item.label, "href": item.href}
            | ({"title": item.title} if item.title else {})
            for item in items
        ],
        "current": next((item.href for item in items if item.current), ""),
        "source": switcher.source,
        "next": SWITCHER_PAGE if switcher.source and switcher.more else None,
    }


@register.simple_tag
def tab_overflow_switcher(tabs, label):
    """Build overflow destinations excluding the current tab.

    Accept tab dictionaries or objects. Omit titles that repeat their label.
    """
    from n26.core.navigation import Switcher, SwitcherItem

    def read(tab, key):
        return tab.get(key, "") if isinstance(tab, dict) else getattr(tab, key, "")

    items = []
    for tab in tabs:
        if read(tab, "current"):
            continue
        title = read(tab, "title") or ""
        items.append(
            SwitcherItem(
                label=str(read(tab, "label")),
                href=str(read(tab, "href")),
                title=title if title != read(tab, "label") else "",
            )
        )
    return Switcher(
        heading=label,
        menu_label="Other tabs",
        placeholder="Search tabs",
        empty="No tabs match",
        items=tuple(items),
    )


@register.simple_tag
def model_screen_tabs(miniature, active):
    """Build the shared model-screen tab strip for the common page header."""
    from n26.core.navigation import model_screen_tabs as build

    return build(miniature, active)


@register.simple_tag(takes_context=True)
def campaign_switcher(
    context, campaign, named=True, menu_label="Switch to another campaign"
):
    """Build the current campaign's switcher using cached viewer-specific destinations."""
    from n26.core.navigation import campaign_switcher as build

    return build(context["request"], campaign, named=named, menu_label=menu_label)


@register.simple_tag(takes_context=True)
def gang_switcher(context, gang, named=True, menu_label="Switch to another gang"):
    """Build a gang switcher using the drawer's cached gang query.

    ``named=False`` omits the name beside an existing heading. Repeated switchers
    on one page require distinct ``menu_label`` values.
    """
    from n26.core.navigation import gang_switcher as build

    return build(context["request"], gang, named=named, menu_label=menu_label)


@register.simple_tag(takes_context=True)
def fighter_switcher(context, gang, miniature):
    """Build this gang's fighter destinations for the current request's screen.

    Use the resolved route to retain the workflow while switching fighters.
    Unknown or unresolvable per-fighter routes use equipment. Query only when
    the page renders this tag.
    """
    from n26.core.navigation import fighter_switcher as build

    match = getattr(context.get("request"), "resolver_match", None)
    return build(gang, miniature, route=getattr(match, "url_name", "") or "")
