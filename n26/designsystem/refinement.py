"""Paired compositions for reviewing layout with the same sample content."""

from dataclasses import dataclass

from .demos import Demo, demos_for


@dataclass(frozen=True)
class RefinementCase:
    slug: str
    title: str
    label: str
    problem: str
    principle: str
    tradeoff: str
    components: tuple[str, ...]

    def examples(self) -> tuple[Demo, ...]:
        return tuple(
            demo
            for demo in demos_for("refinement")
            if demo.slug in (f"{self.slug}-before", f"{self.slug}-after")
        )


CASES = (
    RefinementCase(
        "density",
        "Useful density",
        "Density",
        "Repeated padding separates each name from its facts and pushes useful content down the page.",
        "Keep each fighter’s name, facts and action together.",
        "Keep enough room for readable text, wrapped names and touch targets. More visible records is useful only while each remains easy to read.",
        ("button", "section"),
    ),
    RefinementCase(
        "hierarchy",
        "Typography and action emphasis",
        "Typography",
        "Large metadata and several strong buttons compete with the campaign name and the next action.",
        "Emphasise the campaign name and next action. Keep supporting facts secondary.",
        "Secondary facts and actions remain readable and available. Small grey text is not a substitute for deciding what matters.",
        ("button", "action-bar"),
    ),
    RefinementCase(
        "alignment",
        "Shared alignment anchors",
        "Alignment",
        "Different insets and changing action positions make comparable entries hard to scan.",
        "Align names, ratings and actions on shared columns.",
        "Let long names wrap and let columns adapt on phones. Text baselines, icons and optical alignment need judgement; every glyph need not sit on a square grid.",
        ("button", "section"),
    ),
    RefinementCase(
        "disclosure",
        "Required context and optional help",
        "Disclosure",
        "A long introduction gives optional background the same prominence as the required context and next step.",
        "Keep the next step visible. Put background explanation in the heading help.",
        "Do not hide validation, permission restrictions or facts needed to choose. Check that the help works with a keyboard and on a phone.",
        ("help-popover", "button"),
    ),
)

FIGHTERS = (
    {"name": "Rook", "role": "Leader", "rating": "240", "state": "Ready"},
    {
        "name": "Mara of the Eastern Sumps",
        "role": "Champion",
        "rating": "180",
        "state": "In recovery",
    },
    {"name": "Ash", "role": "Ganger", "rating": "95", "state": "Ready"},
)


def case_for(slug: str) -> RefinementCase | None:
    return next((case for case in CASES if case.slug == slug), None)
