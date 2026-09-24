"""Where you are, and the short ways out of it.

Two things the chrome around a page needs and the page itself does not: the
reader's own gangs, which the drawer lists, and — on any screen that is *one
of* something — the siblings that screen has, which the bar offers as a
switcher.

A switcher is built as a plain structure here and drawn by
``<c-n26.quick-switcher.of>``; nothing in this module knows any HTML. Where
the siblings come from differs per surface (your gangs, the kinds of content,
the items of one kind), so each surface builds its own list and what they share
is the shape, the page size, and one rule: the thing you are on is in the list
from the moment it opens.

Every sibling is reachable from a switcher. The page sends the first ``SWITCHER_PAGE`` rows and the address of the rest
(``Switcher.source``); the control fetches further pages as the list scrolls,
and asks the server when the reader searches, because a name that was never
sent cannot be matched in the browser.
"""

from dataclasses import dataclass

#: How many rows a switcher is sent at a time: with the page, and with each
#: fetch as the list scrolls.
SWITCHER_PAGE = 30

#: How many of the reader's gangs the drawer lists. The drawer is not
#: paged; its Gangs place is the full list.
DRAWER_GANGS = 10


@dataclass(frozen=True)
class SwitcherItem:
    """One destination in a switcher's list.

    ``href`` is the identity: two items are the same place when they lead
    to the same one, which is how the current thing is recognised in a
    list that was fetched without knowing about it.
    """

    label: str
    href: str
    current: bool = False


@dataclass(frozen=True)
class Switcher:
    """A switcher, ready to draw: what you are on, and where else you could be.

    ``label`` empty is the chevron-only variant, for a surface that has
    already named the current thing a line away. Which variant a surface
    wants is settled where the switcher is built, not where it is drawn.

    ``menu_label`` is the chevron's accessible name and must differ from
    every other switcher's on the page: two controls both called "Switch"
    tell a reader who cannot see where they sit nothing at all.

    ``items`` is the first page. ``source`` is where the rest are read
    from (``switcher_rows``), and ``more`` says whether there is a rest
    at all. A switcher without a source holds its whole list in ``items``
    and is searched in the browser.
    """

    heading: str
    menu_label: str
    placeholder: str
    items: tuple[SwitcherItem, ...]
    label: str = ""
    href: str = ""
    empty: str = "No matches"
    source: str = ""
    more: bool = False


def with_current(items, current):
    """The destinations a switcher draws first, with the current one in them.

    The first page answers "the first page", not "the first page
    including this one": a gang named late in the alphabet is on a later
    page, and a switcher that opens without the page it is sitting on
    tells the reader they are nowhere. Prepended rather than sorted in,
    because a row that was fetched and a row that was rescued are not in
    one order anyway; the control drops the same row when its own page
    arrives later.
    """
    items = tuple(items)
    if current is None:
        return items
    if any(item.href == current.href for item in items):
        return items
    return (current, *items)


def first_page(rows):
    """The first page of ``rows`` and whether there are more after it.

    One more row than the page is read, so "is there a rest" costs
    nothing beyond the page itself.
    """
    found = list(rows[: SWITCHER_PAGE + 1])
    return found[:SWITCHER_PAGE], len(found) > SWITCHER_PAGE


def source_url(source, **params):
    """The address a switcher reads its further pages from."""
    from urllib.parse import urlencode

    from django.urls import reverse

    url = reverse("n26-switcher-rows", args=[source])
    return f"{url}?{urlencode(params)}" if params else url


def places_switcher(request, here=""):
    """The app's places, as the bar's switcher on pages that are no one thing.

    Every screen keeps a switcher in the bar so the keyboard way into it
    works everywhere, and on the pages that are not one of anything — the
    dashboard, the listings — the list it offers is the app itself: the
    same places the drawer holds, authoring included for the accounts
    that write content. Costs no query.

    Help is the one row that is a written-out path rather than a reversed
    route: the guides are flatpages, addressed by the URL they are stored
    under. It is also a place no screen with this switcher can be, so
    nothing ever names itself there.

    ``here`` is the drawer slug of the place the page is, and is what
    turns the label on: a page that is one of the places names itself as
    the leading link, and a page that is none of them passes nothing and
    gets the chevron alone beside its own heading.
    """
    from django.urls import reverse

    places = [
        ("home", "Home", reverse("n26-dashboard")),
        ("gangs", "Gangs", reverse("n26-gangs")),
        ("help", "Help", "/help/n26/"),
    ]
    user = getattr(request, "user", None)
    if user is not None and user.is_staff:
        places += [
            ("library", "Content library", reverse("authoring-index")),
            ("modifiers", "Modifiers", reverse("authoring-modifiers")),
            ("foundations", "Foundations", reverse("authoring-foundations")),
            ("ingest", "Ingest", reverse("authoring-ingest")),
        ]
    items = tuple(
        SwitcherItem(label=label, href=href, current=slug == here)
        for slug, label, href in places
    )
    named = next((item for item in items if item.current), None)
    return Switcher(
        label=named.label if named else "",
        href=named.href if named else "",
        heading="Pages",
        menu_label="Go to another page",
        placeholder="Search pages",
        empty="No pages match",
        items=items,
    )


def gang_rows(user):
    """Every live gang ``user`` owns, in the order a switcher lists them."""
    from n26.core.models import Gang

    if user is None or not user.is_authenticated:
        return Gang.objects.none()
    return (
        Gang.objects.filter(owner=user, archived=False)
        .select_related("gang_type")
        .order_by("name", "pk")
    )


def campaign_rows(user):
    """Every live campaign ``user`` arbitrates or plays in, in list order.

    Both halves, because the chevron beside a campaign's name is how
    somebody gets to another one and a player has no other way through to
    theirs.
    """
    from n26.core.models import Campaign

    return (
        Campaign.objects.involving(user).filter(archived=False).order_by("name", "pk")
    )


def fighter_rows(gang):
    """The gang's fighters on the roster, in list order.

    A fighter whose membership has been archived has left the roster and
    is not offered.
    """
    from n26.core.models import Miniature

    return Miniature.objects.filter(
        membership__gang=gang, membership__archived=False
    ).order_by("name", "pk")


def _first_gangs(request):
    """The reader's first page of gangs, memoised on the request.

    Two parts of the same page want it: the drawer lists them, and the
    bar's switcher offers them on every gang screen. Without the memo
    that is the same gangs fetched twice per page.
    """
    found = getattr(request, "_n26_owned_gangs", None)
    if found is None:
        found = request._n26_owned_gangs = first_page(
            gang_rows(getattr(request, "user", None))
        )
    return found


def owned_gangs(request):
    """The signed-in reader's gangs, for the drawer: the first few of them.

    Read from the switcher's page, so the drawer and the bar share one
    query. Anonymous readers get an empty list, which the drawer reads as
    "no section at all".
    """
    return _first_gangs(request)[0][:DRAWER_GANGS]


def reader_campaigns(request):
    """The reader's first page of campaigns, and whether there are more.

    Memoised on the request for the same reason a gang's list is: every
    screen belonging to one campaign offers the others in the bar, and a
    page drawing that twice would otherwise fetch them twice.
    """
    found = getattr(request, "_n26_reader_campaigns", None)
    if found is None:
        found = request._n26_reader_campaigns = first_page(
            campaign_rows(getattr(request, "user", None))
        )
    return found


def _signed_in(request):
    user = getattr(request, "user", None)
    return user is not None and user.is_authenticated


def campaign_item(row, current=None):
    from django.urls import reverse

    return SwitcherItem(
        label=row.name,
        href=reverse("n26-campaign", args=[row.pk]),
        current=current is not None and row.pk == current.pk,
    )


def campaign_switcher(
    request, campaign, named=True, menu_label="Switch to another campaign"
):
    """The switcher on any screen that belongs to one campaign.

    Every screen under a campaign draws this, naming the campaign rather
    than the screen: what an arbitrator wants from the bar halfway through
    recording a battle is the way to their other campaign, and the screen
    is named by the page's own heading directly below.

    ``named`` draws the campaign's name as the leading link, which is what
    the bar wants. ``menu_label`` is the chevron's accessible name, and a
    page drawing this twice must give the second one its own.
    """
    rows, more = reader_campaigns(request)
    here = campaign_item(campaign, campaign)
    return Switcher(
        label=campaign.name if named else "",
        href=here.href if named else "",
        heading="Your campaigns",
        menu_label=menu_label,
        placeholder="Search campaigns",
        empty="No campaigns match",
        items=with_current([campaign_item(row, campaign) for row in rows], here),
        source=source_url("campaigns") if _signed_in(request) else "",
        more=more,
    )


def gang_item(row, current=None):
    from django.urls import reverse

    return SwitcherItem(
        label=row.name,
        href=reverse("n26-gang", args=[row.pk]),
        current=current is not None and row.pk == current.pk,
    )


def gang_switcher(request, gang, named=True, menu_label="Switch to another gang"):
    """The switcher on any screen that belongs to one gang.

    A fighter's screens use it in the bar too, naming the gang rather
    than the fighter: what a player wants from the bar halfway through
    equipping someone is the way to their other gang, and the fighter is
    named by the page's own heading directly below.

    ``named`` draws the gang's name as the leading link. The bar wants
    that; a heading that is already the gang's name does not, and passes
    False for the chevron on its own.

    ``menu_label`` is the chevron's accessible name, and a page drawing
    this twice must give the second one its own: two controls announced
    identically tell a reader who cannot see where they sit nothing about
    either.

    A gang sheet is readable by anyone, so the gang being looked at may
    not be the reader's. It is still the row marked current; the rest are
    the reader's own.
    """
    rows, more = _first_gangs(request)
    here = gang_item(gang, gang)
    return Switcher(
        label=gang.name if named else "",
        href=here.href if named else "",
        heading="Your gangs",
        menu_label=menu_label,
        placeholder="Search gangs",
        empty="No gangs match",
        items=with_current([gang_item(row, gang) for row in rows], here),
        source=source_url("gangs") if _signed_in(request) else "",
        more=more,
    )


#: The screens a fighter has an address of their own for, and what the
#: switcher's chevron is called on each. A route absent from this map has
#: no counterpart for another fighter — a choice slot names one card and
#: one question, not a person — so its switcher leads to the kit screen,
#: the page every fighter has. Adding a per-fighter screen means adding a
#: line here; leaving it out costs a page its own destinations rather
#: than breaking it.
FIGHTER_SCREENS = {
    "n26-edit-fighter": "Edit another model",
    "n26-equip": "Equip another fighter",
    "n26-fighter-options": "Options for another fighter",
    "n26-skills": "Select skills for another fighter",
}

#: Where a screen with no per-fighter address sends the switcher.
FIGHTER_FALLBACK = "n26-equip"


def model_screen_tabs(miniature, active):
    """The screens one model owns, as a strip of link-tabs.

    Edit and Equip are two faces of the same model, so they are tabs of
    one header rather than pages that happen to link to each other —
    which is also why the list is built here once: two screens each
    writing their own strip is two screens free to disagree about what
    the model's screens are.

    ``active`` names the tab being drawn, not the URL: the equip screen
    stays the current tab whichever list ``?list=`` has open.

    Options appears only where the model's profile offers a choice to
    reopen — a tab whose page could only say "nothing to choose" is
    chrome on every fighter for a feature most profiles lack. Where the
    profile cannot be read (a gallery sample), the strip is drawn whole.
    """
    from django.urls import reverse

    tabs = [
        {
            "label": "Edit",
            "href": reverse("n26-edit-fighter", args=[miniature.pk]),
            "current": active == "edit",
        },
        {
            "label": "Equip",
            "href": reverse("n26-equip", args=[miniature.pk]),
            "current": active == "equip",
        },
    ]
    membership = getattr(miniature, "membership", None)
    profile = getattr(membership, "profile", None) if membership else None
    if profile is None or profile.offers_a_choice:
        tabs.append(
            {
                "label": "Options",
                "href": reverse("n26-fighter-options", args=[miniature.pk]),
                "current": active == "options",
            }
        )
    return tabs


def fighter_item(row, route, current=None):
    from django.urls import reverse

    return SwitcherItem(
        label=row.name,
        href=reverse(route, args=[row.pk]),
        current=current is not None and row.pk == current.pk,
    )


def fighter_switcher(gang, miniature, route=FIGHTER_FALLBACK):
    """The gang's other fighters, from the screen of one of them.

    Every destination is the screen this is drawn on, for a different
    fighter: what a player wants after kitting one out is the next one,
    and without this the way there is back to the sheet and in again. So
    ``route`` is the screen being drawn — a name in ``FIGHTER_SCREENS``
    — and anything else lands on the kit screen instead.

    The chevron's name follows the destination, because a page draws a
    gang switcher beside this one and two controls announced identically
    tell a reader who cannot see where they sit nothing about either.

    Scoped to the gang by the query rather than by anything a caller
    passes — a switcher that could name someone else's fighter would be a
    way of finding out that they exist.

    One query for the first page, whatever the size of the roster; the
    rest are fetched by the control as the list scrolls.
    """
    if route not in FIGHTER_SCREENS:
        route = FIGHTER_FALLBACK

    rows, more = first_page(fighter_rows(gang))
    return Switcher(
        heading="Fighters",
        menu_label=FIGHTER_SCREENS[route],
        placeholder="Search fighters",
        empty="No fighters match",
        items=with_current(
            [fighter_item(row, route, miniature) for row in rows],
            fighter_item(miniature, route, miniature),
        ),
        source=source_url("fighters", gang=gang.pk, route=route),
        more=more,
    )


def by_name(rows, query):
    return rows.filter(name__icontains=query)


def _gang_source(request, params):
    return gang_rows(request.user), gang_item, by_name


def _campaign_source(request, params):
    from django.http import Http404

    from n26.flags import CAMPAIGNS, enabled

    if not enabled(CAMPAIGNS, request.user):
        raise Http404("No such list")
    return campaign_rows(request.user), campaign_item, by_name


def _fighter_source(request, params):
    from django.core.exceptions import ValidationError
    from django.http import Http404

    from n26.core.models import Gang

    route = params.get("route", "")
    if route not in FIGHTER_SCREENS:
        route = FIGHTER_FALLBACK
    try:
        gang = Gang.objects.filter(
            pk=params.get("gang", ""), owner=request.user, archived=False
        ).first()
    except ValidationError:
        gang = None
    if gang is None:
        raise Http404("No such gang")
    return fighter_rows(gang), lambda row: fighter_item(row, route), by_name


def _sources():
    from n26.library.templatetags.authoring_nav import (
        sibling_source,
        weapon_profile_source,
    )

    return {
        "gangs": _gang_source,
        "campaigns": _campaign_source,
        "fighters": _fighter_source,
        "siblings": sibling_source,
        "weapon-profiles": weapon_profile_source,
    }


def switcher_rows(request, source, params, query="", offset=0):
    """One page of a switcher's list, for the control to add as it scrolls.

    ``source`` names the list and ``params`` say which one of it — the
    gang whose fighters, the kind whose rows. Each source checks that the
    reader may read what it lists and raises ``Http404`` when they may
    not, so an address copied out of somebody else's page reads nothing.

    ``query`` narrows the list on the server, because the rows the
    browser has not been sent are the ones a search is for. Each source
    says how its rows are searched; one that gives no search is matched
    on the label each row is drawn with.

    Returns the page's items and the offset of the next page, or None
    when this page is the last.
    """
    from django.http import Http404

    found = _sources().get(source)
    if found is None:
        raise Http404("No such list")
    rows, item, search = found(request, params)
    query = query.strip()
    if query:
        if search is not None:
            rows = search(rows, query)
        else:
            wanted = query.lower()
            rows = [row for row in rows if wanted in item(row).label.lower()]
    window = list(rows[offset : offset + SWITCHER_PAGE + 1])
    more = len(window) > SWITCHER_PAGE
    return (
        [item(row) for row in window[:SWITCHER_PAGE]],
        offset + SWITCHER_PAGE if more else None,
    )
