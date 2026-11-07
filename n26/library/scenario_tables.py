"""The shared scenario catalogue, loaded from authored library content.

Display objects are immutable. One catalogue can be passed through forms,
rolling and history without querying again. Known references resolve retired
content; menus offer complete, live tables only.

Table keys, side-job-set keys and roll values are stored in links and battles
and must remain stable. Display names and text can change; saved battles
render current text. Asterisks mark bold text.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioEntry:
    """One result on one table: the roll that lands on it, its name, a
    paragraph saying what it means, and an optional image under the
    static root."""

    roll: int
    name: str
    text: str
    image: str = ""
    image_url: str = ""
    diagram_alt: str = ""

    @property
    def label(self):
        """The name as a line of text says it. A name may end in a colon
        or spaces when written as a heading; a sentence leaves them off."""
        return self.name.strip().rstrip(":").strip()

    def parts(self):
        """The text as ``(words, bold)`` pairs, split at the asterisks."""
        return [
            (words, index % 2 == 1)
            for index, words in enumerate(_BOLD.split(self.text))
            if words
        ]

    @property
    def plain(self):
        """The text without the asterisks that mark bold."""
        return self.text.replace("*", "")


_BOLD = re.compile(r"\*([^*]+)\*")


@dataclass(frozen=True)
class ScenarioTable:
    """A scenario table with a stable stored key and a display name.

    A side-job instance also identifies its source set and numbered position.
    """

    key: str
    name: str
    entries: tuple[ScenarioEntry, ...]
    side_job_set: SideJobSet | None = None

    def entry(self, roll):
        """The entry a roll lands on, or None for a roll off the table."""
        for entry in self.entries:
            if entry.roll == roll:
                return entry
        return None


@dataclass(frozen=True)
class SideJobSet:
    """A set of six side jobs to roll on, such as the Escher ones. ``key``
    is what links and stored battles use, with the roll: "escher-3"."""

    key: str
    name: str
    entries: tuple[ScenarioEntry, ...]
    available: bool = True

    @property
    def label(self):
        """The set as the generator's menu names it."""
        return f"{self.name} side jobs"

    def entry(self, roll):
        """The entry a roll lands on, or None for a roll off the table."""
        for entry in self.entries:
            if entry.roll == roll:
                return entry
        return None


PRIMARY_KEYS = ("deployment", "objective", "crew")
SIDE_JOB_LIMIT = 6


def side_job_key(place):
    """Return the stored key for a one-based side-job position.

    The first uses ``side_job`` for compatibility; later keys include the number.
    """
    return "side_job" if place == 1 else f"side_job_{place}"


SIDE_JOB_KEYS = tuple(side_job_key(place) for place in range(1, SIDE_JOB_LIMIT + 1))


@dataclass(frozen=True)
class ScenarioCatalogue:
    tables: tuple[ScenarioTable, ...]
    side_job_sets: tuple[SideJobSet, ...]
    all_side_job_sets: tuple[SideJobSet, ...]

    def table(self, key):
        return next((table for table in self.tables if table.key == key), None)

    def side_job_set(self, key):
        return next(
            (table for table in self.all_side_job_sets if table.key == key), None
        )

    def permits(self, results, retained=None):
        offered = {table.key for table in self.side_job_sets}
        retained = retained or {}
        return all(
            not result.table.side_job_set
            or result.table.side_job_set.key in offered
            or retained.get(result.table.key) == result.value
            for result in results
        )


def load_catalogue(*, include_staged=False):
    from django.conf import settings
    from django.templatetags.static import static

    from n26.library.models import ScenarioTable as Table

    tables, sets = {}, []
    rows = (
        Table.objects.filter(pack__slug=settings.DEFAULT_CONTENT_PACK_SLUG)
        .select_related("pack")
        .prefetch_related("entries")
    )
    for row in rows:
        entries = tuple(
            ScenarioEntry(
                roll=entry.roll,
                name=entry.name,
                text=entry.text,
                image=entry.image,
                image_url=entry.diagram.url
                if entry.diagram
                else (static(entry.image) if entry.image else ""),
                diagram_alt=entry.diagram_alt
                or f"Deployment map for {entry.name.strip().rstrip(':')}",
            )
            for entry in row.entries.all()
        )
        complete = tuple(entry.roll for entry in entries) == (1, 2, 3, 4, 5, 6) and all(
            entry.name.strip() and entry.text.strip() for entry in entries
        )
        if row.purpose == Table.Purpose.SIDE_JOB:
            available = (
                complete
                and not row.archived
                and not row.pack.archived
                and (include_staged or not row.staged)
            )
            sets.append(
                SideJobSet(
                    key=row.key, name=row.name, entries=entries, available=available
                )
            )
        else:
            tables[row.purpose] = ScenarioTable(
                key=row.purpose, name=row.name, entries=entries
            )
    return ScenarioCatalogue(
        tables=tuple(tables[key] for key in PRIMARY_KEYS if key in tables),
        side_job_sets=tuple(table for table in sets if table.available),
        all_side_job_sets=tuple(sets),
    )


def side_job_set(key, catalogue=None):
    return (catalogue or load_catalogue()).side_job_set(key)


def side_job_table(place, found):
    return ScenarioTable(
        key=side_job_key(place),
        name=f"Side job {place}",
        entries=found.entries,
        side_job_set=found,
    )


def table(key, catalogue=None):
    return (catalogue or load_catalogue()).table(key)


def request_catalogue(request):
    """Reuse one loaded catalogue throughout a page and its prop builders."""
    from n26.library.staged import sees_staged

    if not hasattr(request, "_scenario_catalogue"):
        request._scenario_catalogue = load_catalogue(
            include_staged=sees_staged(request.user)
        )
    return request._scenario_catalogue
