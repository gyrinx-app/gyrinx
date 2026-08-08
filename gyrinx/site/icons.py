"""The site banner's icons, named once and drawn by each edition.

The banner is platform-owned and shown by every edition, but the editions do
not share an icon set: n23 draws Bootstrap Icons from a webfont, n26 draws the
hand-kept SVG registry in ``n26/core/icons.py``. So the banner cannot store a
drawing — it stores a *meaning*, and each edition resolves that meaning in its
own set.

Before this it stored a Bootstrap Icons class directly, in a free-text field.
That was fine for as long as Bootstrap was the only consumer, and stopped being
fine the moment n26 rendered the same row: a live banner set to
``bi-blockquote-left`` reached n26's registry, which raises on a name it does
not have, and took every page of the edition down. A key that both sides are
guaranteed to understand removes the failure rather than translating around it.

One table with both columns, rather than a key list here and a mapping in each
edition, so that adding an icon is a single edit and cannot be half-done. The
n26 column is *strings*, not imports — this module must never import from an
edition package (see ``gyrinx/site/templatetags/platform_tags.py`` for the same
rule and why). ``n26/tests/test_platform_integration.py`` checks the column
against the real registry, so the two cannot drift in silence.

Keys are meanings, not pictures: a banner author picks "News", not "a bell". If
the drawing for news should change, it changes here and both editions follow.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BannerIcon:
    """One meaning, and the drawing each edition uses for it."""

    key: str
    #: What the banner author sees in the select box.
    label: str
    #: A Bootstrap Icons class, for n23 and the platform's own templates.
    bootstrap: str
    #: A name in n26/core/icons.py.
    n26: str


#: Every icon a site banner may carry.
#:
#: Deliberately short, and semantic rather than decorative. A banner says one
#: thing to everyone who loads the site; the useful distinctions are what kind
#: of thing it is saying, and there are not many of those. A longer list would
#: mostly be inviting authors to pick a picture, which is how a warning ends up
#: wearing a star.
BANNER_ICONS: tuple[BannerIcon, ...] = (
    BannerIcon("info", "Information", "bi-info-circle", "information-circle"),
    BannerIcon("success", "Success", "bi-check-circle", "check-circle"),
    BannerIcon("warning", "Warning", "bi-exclamation-triangle", "exclamation-triangle"),
    BannerIcon("news", "News", "bi-bell", "bell"),
    BannerIcon("highlight", "Highlight", "bi-star", "star"),
    BannerIcon("thanks", "Thanks", "bi-heart", "heart"),
    BannerIcon("maintenance", "Maintenance", "bi-gear", "cog-6-tooth"),
)

_BY_KEY: dict[str, BannerIcon] = {icon.key: icon for icon in BANNER_ICONS}

#: For the model field, which makes the admin render a select box. No blank row
#: here — the field is blank=True, so Django adds the empty choice itself.
CHOICES: list[tuple[str, str]] = [(icon.key, icon.label) for icon in BANNER_ICONS]


def bootstrap_class(key: str) -> str:
    """The Bootstrap Icons class for a key, or "" if there is none.

    Total, like its n26 counterpart, and for the same reason: the value comes
    out of a database column. A select box makes an unknown key unlikely, not
    impossible — a row written before the choices existed, a key retired from
    the table, a banner restored from history. None of those is worth a 500.
    """
    icon = _BY_KEY.get(key or "")
    return icon.bootstrap if icon else ""


def n26_name(key: str) -> str:
    """The n26 registry name for a key, or "" if there is none.

    Empty is a real answer, not a failure: it leaves the n26 announcement to
    draw the icon its tone implies, which is the component's own decision and
    a better one than anything this module could guess.
    """
    icon = _BY_KEY.get(key or "")
    return icon.n26 if icon else ""
