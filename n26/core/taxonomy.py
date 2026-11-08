"""Group catalogue and hire entries by their authored category and section.

Callers supply row values and within-category ordering. The common grouping
uses each category's section and keeps uncategorised content visible at the end.
"""

#: Shared visible label for uncategorised content, including section tabs.
UNCATEGORISED = "Uncategorised"


def group_by_home(homed_rows, *, section, category, order):
    """Group ``(Category or None, row)`` pairs into ordered sections and categories.

    ``section`` and ``category`` construct caller-specific containers; ``order``
    sorts rows within a category.

    Group sections by name using their earliest position. Tabs use the same name
    keys, so equal section names must form one heading. Gather all categories
    under each section once, even when category positions interleave.
    Categories are dictionary keys and group by equality. Their names are unique
    only within a section.

    Place uncategorised rows last under an empty heading. Callers can substitute
    UNCATEGORISED where a visible tab label is required.
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
