"""The site changelog, one list for every edition.

A ``tag`` query narrows the list. The n26 dashboard links here with
``tag=N26``, so arriving from that home starts on this edition. The
footer link carries no tag, so it shows every live entry.

Tag names match without regard to case. An entry tagged both ``N26``
and ``n26`` is still one entry: the tag join can hit it twice.

Both pages are public. Release notes hold no player data, and an entry
means the same thing for every reader.
"""

from urllib.parse import urlencode

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

#: The dashboard, and the link from the n26 home, ask for this tag.
CHANGELOG_TAG = "N26"

#: Colour names from ``c-ui.badge``. The component owns the fills, so a
#: tag follows the design system in both modes. Amber is the site accent;
#: sky is the other named hue that stays distinct from it.
#: Any other tag takes a stable colour from the palette below.
EDITION_COLOURS = {
    "n23": "amber",
    "n26": "sky",
}
OTHER_COLOURS = (
    "violet",
    "teal",
    "rose",
    "lime",
    "indigo",
    "emerald",
    "fuchsia",
    "pink",
)


#: ``ChangelogEntryTag.name`` cannot be longer than this. A longer query
#: is not a tag, and must not be cut down to one that is.
TAG_NAME_MAX = 100


def tag_colour(name):
    """A ``c-ui.badge`` colour name. The same tag always gets the same one."""
    key = name.casefold()
    if key in EDITION_COLOURS:
        return EDITION_COLOURS[key]
    return OTHER_COLOURS[sum(key.encode()) % len(OTHER_COLOURS)]


def changelog_href(tag=None, pk=None):
    """The shared changelog, optionally narrowed to one tag or one entry."""
    if pk is None:
        url = reverse("changelog")
    else:
        url = reverse("changelog-entry", args=[pk])
    if not tag:
        return url
    return f"{url}?{urlencode({'tag': tag})}"


def changelog_entries():
    """Live entries tagged for the n26 dashboard, newest first.

    Tag names are unique case-sensitively, so matching both ``N26`` and
    ``n26`` can join one entry twice when it carries both spellings.
    """
    return (
        _live_entries()
        .filter(tags__name__iexact=CHANGELOG_TAG)
        .distinct()
        .order_by("-date", "-created")
    )


def changelog(request):
    """Every live changelog entry, or just those wearing the requested tag."""
    tag = _requested_tag(request)
    entries = list(_page_entries(tag))
    _attach_badges(entries)
    return render(
        request,
        "n26/changelog.html",
        {
            "entries": entries,
            "sidebar": _sidebar(entries, tag=tag),
            "filter_tags": _filter_tags(tag),
            "active_tag": tag,
            "tag_query": _tag_query(tag),
            "lead": _lead(tag),
            "empty": _empty(tag),
        },
    )


def changelog_entry(request, pk):
    """One complete entry. The tag query only narrows the menu beside it."""
    tag = _requested_tag(request)
    entry = get_object_or_404(_live_entries().prefetch_related("tags"), pk=pk)
    _attach_badges([entry])
    sidebar = _sidebar(
        _menu_entries(tag),
        current=entry,
        tag=tag,
    )
    return render(
        request,
        "n26/changelog_entry.html",
        {
            "entry": entry,
            "sidebar": sidebar,
            "filter_tags": _filter_tags(tag),
            "active_tag": tag,
            "tag_query": _tag_query(tag),
        },
    )


def n26_changelog(request):
    """The old address of this edition's changelog."""
    return redirect(changelog_href(CHANGELOG_TAG), permanent=True)


def n26_changelog_entry(request, pk):
    """The old address of one N26 entry. Anything else is a 404."""
    get_object_or_404(changelog_entries(), pk=pk)
    return redirect(changelog_href(CHANGELOG_TAG, pk), permanent=True)


def _live_entries():
    from gyrinx.site.models import ChangelogEntry

    return ChangelogEntry.objects.filter(archived=False)


def _page_entries(tag):
    """Live entries for the shared page, newest first, tags already loaded."""
    return _matching_entries(tag).prefetch_related("tags")


def _menu_entries(tag):
    """The same entries, without their bodies, for the menu beside a page.

    ``created`` is in the ordering, so it has to be loaded with the row.
    Leaving it deferred makes Django fetch it again per entry.
    """
    return _matching_entries(tag).only("id", "title", "date", "created")


def _matching_entries(tag):
    entries = _live_entries()
    if tag:
        entries = entries.filter(tags__name__iexact=tag).distinct()
    return entries.order_by("-date", "-created")


def _requested_tag(request):
    """The tag query, or None when the page should show every entry.

    Prefer the stored spelling when a tag of that name exists, so the
    chips, the lead and the links all agree on one writing of it.

    A query longer than a tag name is returned whole. Cutting it to the
    field length would select a real tag that happens to be that prefix.
    """
    raw = request.GET.get("tag", "").strip()
    if not raw:
        return None
    if len(raw) > TAG_NAME_MAX:
        return raw
    from gyrinx.site.models import ChangelogEntryTag

    stored = (
        ChangelogEntryTag.objects.filter(name__iexact=raw)
        .order_by("name")
        .values_list("name", flat=True)
        .first()
    )
    return stored or raw


def _filter_tags(active):
    """One chip per tag that a live entry actually wears.

    ``N26`` and ``n26`` are one filter, because matching ignores case.
    The chip keeps the spelling that sorts first within that case.
    """
    from gyrinx.site.models import ChangelogEntryTag

    names = (
        ChangelogEntryTag.objects.filter(entries__archived=False)
        .values_list("name", flat=True)
        .distinct()
    )
    chosen = {}
    for name in sorted(names, key=lambda item: (item.casefold(), item)):
        chosen.setdefault(name.casefold(), name)
    active_key = active.casefold() if active else None
    return [
        {
            "name": name,
            "color": tag_colour(name),
            "href": changelog_href(name),
            "current": active_key is not None and name.casefold() == active_key,
        }
        for name in chosen.values()
    ]


def _attach_badges(entries):
    """A colour per tag, computed once. Cotton cannot look a colour up itself."""
    for entry in entries:
        entry.tag_badges = [
            {"name": tag.name, "color": tag_colour(tag.name)}
            for tag in entry.tags.all()
        ]


def _sidebar(entries, current=None, tag=None):
    """Links shared by the index and every entry page."""
    return [
        {
            "title": item.title,
            "date": item.date,
            "href": changelog_href(tag, item.pk),
            "current": current is not None and item.pk == current.pk,
        }
        for item in entries
    ]


def _tag_query(tag):
    if not tag:
        return ""
    return f"?{urlencode({'tag': tag})}"


def _lead(tag):
    if not tag:
        return "Changes on Gyrinx."
    if len(tag) > TAG_NAME_MAX:
        return "No changes match that tag."
    return f"Changes tagged {tag}."


def _empty(tag):
    if not tag:
        return "Nothing yet."
    if len(tag) > TAG_NAME_MAX:
        return "Nothing matches that tag."
    return f"Nothing tagged {tag} yet."
