"""Where you are, and the short ways out of it.

Two things the chrome around a page needs and the page itself does not: the
reader's own gangs, which the drawer lists, and — on any screen that is *one
of* something — the siblings that screen has, which the bar offers as a
switcher.

A switcher is built as a plain structure here and drawn by
``<c-n26.quick-switcher.of>``; nothing in this module knows any HTML. Where
the siblings come from differs per surface (your gangs, the kinds of content,
the rows of one kind), so each surface builds its own list and what they share
is the shape, the cap, and one rule: the thing you are on is in the list
whatever the cap dropped.
"""

from dataclasses import dataclass

#: The most siblings a switcher lists, and the limit on the query that
#: fetches them. A switcher is a shortcut rather than an index — the page
#: that lists everything is one press away — so a reader with three hundred
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


def owned_gangs(request):
    """The signed-in reader's gangs, at most ``NAV_SIBLINGS`` of them.

    Memoised on the request because two parts of the same page want it:
    the drawer lists them, and the bar's switcher offers them on every
    gang screen. Without the memo that is the same rows fetched twice per
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


def gang_switcher(request, gang):
    """The bar's switcher on any screen that belongs to one gang.

    A fighter's screens use it too, naming the gang rather than the
    fighter: what a player wants from the bar halfway through equipping
    someone is the way to their other gang, and the fighter is named by
    the page's own heading directly below.
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
        label=gang.name,
        href=here.href,
        heading="Your gangs",
        menu_label="Switch to another gang",
        placeholder="Search gangs",
        empty="No gangs match",
        items=with_current([item(row) for row in owned_gangs(request)], here),
    )
