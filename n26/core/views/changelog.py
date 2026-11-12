"""Show public release notes shared by every edition.

The tag query filters case-insensitively. N26 dashboard links supply tag=N26;
untagged links show all live entries. Deduplicate entries because one entry
can have multiple case variants of a tag.
"""

from urllib.parse import urlencode

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

#: Tag supplied by N26 dashboard and home links.
CHANGELOG_TAG = "N26"

#: Queries exceeding the tag field limit must remain intact rather than match a truncated prefix.
TAG_NAME_MAX = 100


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
    """List live changelog entries under the optional tag filter."""
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
            "tag_query": _tag_query(tag),
        },
    )


def n26_changelog(request):
    """Permanently redirect to the shared changelog filtered by the N26 tag."""
    return redirect(changelog_href(CHANGELOG_TAG), permanent=True)


def n26_changelog_entry(request, pk):
    """Permanently redirect an N26-tagged entry; return 404 for other entries."""
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
    return _matching_entries(tag).only(
        "id",
        "title",
        "date",
        "created",
        "flair_text",
        "flair_colour",
        "flair_pulse",
        "second_flair_text",
        "second_flair_colour",
        "second_flair_pulse",
        "flair_active",
        "second_flair_active",
    )


def _matching_entries(tag):
    entries = _live_entries()
    if tag:
        entries = entries.filter(tags__name__iexact=tag).distinct()
    return entries.order_by("-date", "-created")


def _requested_tag(request):
    """Read the requested tag, preferring a matching stored spelling.

    Preserve overlong queries intact. Truncation could accidentally select a real
    tag sharing that prefix.
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
    """Build case-insensitive filter chips from tags used by live entries.

    Keep the alphabetically first stored spelling among case variants.
    """
    from gyrinx.site.models import ChangelogEntryTag

    tags = (
        ChangelogEntryTag.objects.filter(entries__archived=False)
        .only("name", "colour")
        .distinct()
    )
    chosen = {}
    for tag in sorted(tags, key=lambda item: (item.name.casefold(), item.name)):
        chosen.setdefault(tag.name.casefold(), tag)
    active_key = active.casefold() if active else None
    return [
        {
            "name": tag.name,
            "color": "ink" if tag.colour == "default" else tag.colour,
            "href": changelog_href(tag.name),
            "current": active_key is not None and tag.name.casefold() == active_key,
        }
        for tag in chosen.values()
    ]


def _attach_badges(entries):
    """Resolve tag badge colours and links before rendering."""
    for entry in entries:
        entry.tag_badges = [
            {
                "name": tag.name,
                "color": "ink" if tag.colour == "default" else tag.colour,
                "href": changelog_href(tag.name),
            }
            for tag in entry.tags.all()
        ]


def _sidebar(entries, current=None, tag=None):
    """Links shared by the index and every entry page."""
    return [
        {
            "title": item.title,
            "flairs": item.flairs,
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
