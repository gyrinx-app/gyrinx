"""Template helpers for the site navigation."""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def feature_open(context, slug):
    """Whether this reader is let into a gated feature.

    Lets the drawer draw a place as a link for the accounts that have it and
    as a plain word for everyone else, so a reader is never offered an
    address that would answer them 404.

    Drawing the link is not what grants access — every gated view asks the
    same question again for itself. This only decides what the drawer says.

    Memoised on the request because the drawer is drawn more than once on a
    page — the bar's list and the scriptless strip beneath it are the same
    include — and the page's query budget is a fixed number rather than one
    that grows with how often a template happens to ask.
    """
    from n26.flags import enabled

    request = context.get("request")
    if request is None:
        return False

    asked = getattr(request, "_n26_open_features", None)
    if asked is None:
        asked = request._n26_open_features = {}
    if slug not in asked:
        asked[slug] = enabled(slug, getattr(request, "user", None))
    return asked[slug]


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
def places_switcher(context, here=""):
    """The app's places, for the bar of a page that is not one of anything.

    The layout draws this as the default bar switcher, so the keyboard way
    into the bar works on every screen; pages that are one of something —
    a gang, a kind of content — override the block with their own. ``here``
    is the drawer slug of the place the page is, and naming it is what
    puts the leading link on.
    """
    from n26.core.navigation import places_switcher as build

    return build(context.get("request"), here=here)


@register.simple_tag
def model_screen_tabs(miniature, active):
    """The tabs of one model's own screens — Edit and Equip.

    A tag so the header component can build the strip itself: the two
    pages share the header, and a strip assembled at each call site is a
    strip the two can disagree about.
    """
    from n26.core.navigation import model_screen_tabs as build

    return build(miniature, active)


@register.simple_tag(takes_context=True)
def campaign_switcher(
    context, campaign, named=True, menu_label="Switch to another campaign"
):
    """The switcher on a screen that belongs to one campaign.

    A tag for the same reason the gang's is: the rows are the reader's own
    campaigns, wanted only by the pages that draw one, and read through the
    same memo so the bar spends one query on them however often it is drawn.
    """
    from n26.core.navigation import campaign_switcher as build

    return build(context["request"], campaign, named=named, menu_label=menu_label)


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
