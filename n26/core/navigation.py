"""Where you are, and the short ways out of it.

Two things the chrome around a page needs and the page itself does not: the
reader's own gangs, which the drawer lists, and — on any screen that is *one
of* something — the siblings that screen has, which the bar offers as a
switcher.

A switcher is built as a plain structure here and drawn by
``<c-n26.quick-switcher.of>``; nothing in this module knows any HTML. Where
the siblings come from differs per surface (your gangs, the kinds of content,
the items of one kind), so each surface builds its own list and what they share
is the shape, the cap, and one rule: the thing you are on is in the list
whatever the cap dropped.
"""

from dataclasses import dataclass

#: The most siblings a switcher lists, and the limit on the query that
#: fetches them. A switcher is a shortcut rather than an index — the page
#: that lists everything is one click away — so a reader with three hundred
#: of something still pays for eleven rows and a panel that fits on screen.
NAV_SIBLINGS = 10


@dataclass(frozen=True)
class SwitcherItem:
    """One destination in a switcher's list.

    ``href`` is the identity: two items are the same place when they lead
    to the same one, which is how the current thing is recognised in a
    list that was fetched without knowing about it.
    """

    label: str
    href: str
    icon: str = ""
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
    """

    heading: str
    menu_label: str
    placeholder: str
    items: tuple[SwitcherItem, ...]
    label: str = ""
    href: str = ""
    icon: str = ""
    empty: str = "No matches"


def with_current(items, current):
    """The destinations a switcher draws, with the current one guaranteed.

    A capped query answers "ten of them", not "ten of them including this
    one": a gang named late in the alphabet falls off the end, and a
    switcher that omits the page it is sitting on tells the reader they
    are nowhere. Prepended rather than sorted in, because a row that was
    fetched and a row that was rescued are not in one order anyway.
    """
    items = tuple(items)
    if current is None:
        return items
    if any(item.href == current.href for item in items):
        return items
    return (current, *items)


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


def owned_gangs(request):
    """The signed-in reader's gangs, at most ``NAV_SIBLINGS`` of them.

    Memoised on the request because two parts of the same page want it:
    the drawer lists them, and the bar's switcher offers them on every
    gang screen. Without the memo that is the same gangs fetched twice per
    page. Anonymous readers get an empty list, which the drawer reads as
    "no section at all".
    """
    from n26.core.models import Gang

    found = getattr(request, "_n26_owned_gangs", None)
    if found is not None:
        return found

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        found = []
    else:
        found = list(
            Gang.objects.filter(owner=user, archived=False)
            .select_related("gang_type")
            .order_by("name")[:NAV_SIBLINGS]
        )
    request._n26_owned_gangs = found
    return found


def owned_campaigns(request):
    """The signed-in reader's campaigns, at most ``NAV_SIBLINGS`` of them.

    Memoised on the request for the same reason a gang's list is: every
    screen belonging to one campaign offers the others in the bar, and a
    page drawing that twice would otherwise fetch them twice.
    """
    from n26.core.models import Campaign

    found = getattr(request, "_n26_owned_campaigns", None)
    if found is not None:
        return found

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        found = []
    else:
        found = list(
            Campaign.objects.filter(owner=user, archived=False).order_by("name")[
                :NAV_SIBLINGS
            ]
        )
    request._n26_owned_campaigns = found
    return found


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
    from django.urls import reverse

    def item(row):
        return SwitcherItem(
            label=row.name,
            href=reverse("n26-campaign", args=[row.pk]),
            current=row.pk == campaign.pk,
        )

    here = item(campaign)
    return Switcher(
        label=campaign.name if named else "",
        href=here.href if named else "",
        heading="Your campaigns",
        menu_label=menu_label,
        placeholder="Search campaigns",
        empty="No campaigns match",
        items=with_current([item(row) for row in owned_campaigns(request)], here),
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
    """
    from django.urls import reverse

    def item(row):
        return SwitcherItem(
            label=row.name,
            href=reverse("n26-gang", args=[row.pk]),
            current=row.pk == gang.pk,
        )

    here = item(gang)
    return Switcher(
        label=gang.name if named else "",
        href=here.href if named else "",
        heading="Your gangs",
        menu_label=menu_label,
        placeholder="Search gangs",
        empty="No gangs match",
        items=with_current([item(row) for row in owned_gangs(request)], here),
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
    "n26-learn": "Select skills for another fighter",
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
    way of finding out that they exist. A fighter whose membership has
    been archived has left the roster and is not offered.

    One capped query, the same shape the drawer's gang list uses: the cap
    is on the query, so a gang of thirty costs this page what a gang of
    three does. The fighter being looked at is put back if the cap
    dropped it.
    """
    from django.urls import reverse

    from n26.core.models import Miniature

    if route not in FIGHTER_SCREENS:
        route = FIGHTER_FALLBACK

    def item(row):
        return SwitcherItem(
            label=row.name,
            href=reverse(route, args=[row.pk]),
            current=row.pk == miniature.pk,
        )

    rows = Miniature.objects.filter(
        membership__gang=gang, membership__archived=False
    ).order_by("name")[:NAV_SIBLINGS]
    return Switcher(
        heading="Fighters",
        menu_label=FIGHTER_SCREENS[route],
        placeholder="Search fighters",
        empty="No fighters match",
        items=with_current([item(row) for row in rows], item(miniature)),
    )
