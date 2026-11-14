"""Top-level gallery destinations and their shared page introductions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GalleryPage:
    label: str
    title: str
    intro: str


PAGES = {
    "index": GalleryPage(
        "Overview",
        "Design system",
        "Browse components and examples from the installed UI library.",
    ),
    "theming": GalleryPage(
        "Theming",
        "Theming",
        "Apply a preset and inspect it on a sample screen.",
    ),
    "tokens": GalleryPage(
        "Tokens",
        "Tokens",
        "Inspect the current CSS values and the utilities they generate.",
    ),
    "react": GalleryPage(
        "React islands",
        "React islands",
        "Compare the same content rendered with Cotton and React.",
    ),
    "print_lab": GalleryPage(
        "Print lab",
        "Print lab",
        "Adjust the sheet, then check the preview and printed output.",
    ),
    "refinement_lab": GalleryPage(
        "Refinement lab",
        "Refinement lab",
        "Compare layouts and source. Sample actions are for display.",
    ),
}
