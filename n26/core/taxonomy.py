"""Where a row sits under the catalogue's headings, and how rows gather there.

An assignable's home is its own data: a ``Category``, inside a
``Section`` heading. So every surface that shows rows under headings is
grouping the same way — a shopping list, the gang list you hire from —
and this is the one place that grouping is written down. What differs
between them is what a row *is* and what order rows take within a
category, which are the two things :func:`group_by_home` is told.
"""

#: What the section of homeless rows is called on screen. The grouping
#: itself has no name for it, because "no category" is what the content
#: actually says; a picker that draws its sections as tabs needs a word
#: to put on the tab, and an unnamed section would be one nobody could
#: reach. Named here so every surface calls it the same thing.
UNCATEGORISED = "Uncategorised"


def group_by_home(homed_rows, *, section, category, order):
    """Group ``(home, row)`` pairs into sections of categories.

    ``home`` is the row's ``Category``, or ``None`` where the content
    filed it nowhere. ``section(name, categories)`` and
    ``category(name, rows)`` build the two containers the calling
    surface draws, and ``order`` is how rows sort within a category —
    nothing here knows what a row is or what its containers are called.

    **A section is drawn once.** Every category filed under it goes in
    one group, whatever the categories' own positions are. Ordering the
    categories alone and starting a new group each time the heading
    changed let two sections' categories alternate, and the same section
    then opened over and over with its rows split between the copies —
    a reader saw one heading two or three times down the page, each with
    a chevron of its own, and only the first of them open.

    Sections are keyed by name, which is what a strip of tabs keys them
    by: two tabs reading alike is worse than a long one, and a section
    the strip cannot draw is a section whose rows are unreachable. Two
    sections sharing a name are therefore one heading, ordered by the
    earliest of them.

    Categories are keyed by identity, not by name. A category name is
    only unique within its section — the rulebook has Esoteric weapons
    under both Ranged and Close combat — so matching on the string would
    fold two different categories into one.

    Homeless rows gather at the end under an empty heading — missing a
    category is a content gap to show, not an error to hide. What that
    heading is called on screen is the surface's business: pass
    :data:`UNCATEGORISED` through ``section`` where a name is needed.
    """
    #: section name -> (its earliest position, {category: rows})
    sections = {}
    for home, row in homed_rows:
        heading = home.section if home is not None else None
        name = heading.name if heading is not None else ""
        position = heading.position if heading is not None else float("inf")
        held, categories = sections.setdefault(name, (position, {}))
        if position < held:
            sections[name] = (position, categories)
        categories.setdefault(home, []).append(row)

    def taxonomy_order(home):
        if home is None:
            return (1, 0, "")
        return (0, home.position, home.name.lower())

    return [
        section(
            name,
            [
                category(home.name if home else "", sorted(categories[home], key=order))
                for home in sorted(categories, key=taxonomy_order)
            ],
        )
        for name, (_, categories) in sorted(
            sections.items(), key=lambda item: (item[1][0], item[0])
        )
    ]
