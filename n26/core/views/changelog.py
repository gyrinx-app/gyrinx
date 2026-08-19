"""The site's changelog, narrowed to the entries about this edition.

This is the one n26 module that reads the platform-owned changelog table.
Both pages are deliberately public: release notes hold no player data, and
an entry has the same meaning for every reader.
"""

from django.shortcuts import get_object_or_404, render
from django.urls import reverse

#: Both editions read one table, so an entry appears here only when its
#: author says which edition it concerns. Untagged news belongs to neither.
CHANGELOG_TAG = "N26"


def changelog_entries():
    """Live entries tagged for this edition, newest first.

    Tag names are unique case-sensitively, so matching both ``N26`` and
    ``n26`` can join one entry twice when it carries both spellings.
    """
    from gyrinx.site.models import ChangelogEntry

    return (
        ChangelogEntry.objects.filter(
            archived=False,
            tags__name__iexact=CHANGELOG_TAG,
        )
        .distinct()
        .order_by("-date", "-created")
    )


def changelog(request):
    """Every changelog entry about this edition."""
    entries = list(changelog_entries())
    return render(
        request,
        "n26/changelog.html",
        {"entries": entries, "sidebar": _sidebar(entries)},
    )


def changelog_entry(request, pk):
    """One complete entry, with every edition entry beside it."""
    entry = get_object_or_404(changelog_entries(), pk=pk)
    sidebar = _sidebar(changelog_entries().only("id", "title", "date"), entry)
    return render(
        request,
        "n26/changelog_entry.html",
        {"entry": entry, "sidebar": sidebar},
    )


def _sidebar(entries, current=None):
    """Links shared by the index and every entry page."""
    return [
        {
            "title": item.title,
            "date": item.date,
            "href": reverse("n26-changelog-entry", args=[item.pk]),
            "current": current is not None and item.pk == current.pk,
        }
        for item in entries
    ]
