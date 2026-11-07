"""Banner icon keys and their mappings for each edition.

N23 uses Bootstrap Icons; N26 uses the registry in n26/core/icons.py. Store
a shared semantic key on the banner and resolve it here for each edition.
Keep N26 names as strings to avoid importing edition code into the platform.
n26/tests/test_platform_integration.py validates them against the registry.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BannerIcon:
    """A banner icon key with display names for each edition."""

    key: str
    #: What the banner author sees in the select box.
    label: str
    #: A Bootstrap Icons class, for n23 and the platform's own templates.
    bootstrap: str
    #: A canonical Lucide or approved brand name resolved by n26/core/icons.py.
    n26: str


#: Banner choices describe the message type, with a matching icon for each edition.
BANNER_ICONS: tuple[BannerIcon, ...] = (
    BannerIcon("info", "Information", "bi-info-circle", "info"),
    BannerIcon("success", "Success", "bi-check-circle", "circle-check"),
    BannerIcon("warning", "Warning", "bi-exclamation-triangle", "triangle-alert"),
    BannerIcon("news", "News", "bi-bell", "bell"),
    BannerIcon("highlight", "Highlight", "bi-star", "star"),
    BannerIcon("thanks", "Thanks", "bi-heart", "heart"),
    BannerIcon("maintenance", "Maintenance", "bi-gear", "settings"),
)

_BY_KEY: dict[str, BannerIcon] = {icon.key: icon for icon in BANNER_ICONS}

#: Django adds the empty choice because the model field has blank=True.
CHOICES: list[tuple[str, str]] = [(icon.key, icon.label) for icon in BANNER_ICONS]


def bootstrap_class(key: str) -> str:
    """Return the Bootstrap Icons class, or an empty string for an unknown key.

    Stored values may outlive the available choices, so unknown keys must not
    prevent a banner from rendering.
    """
    icon = _BY_KEY.get(key or "")
    return icon.bootstrap if icon else ""


def n26_name(key: str) -> str:
    """Return the N26 icon name, or an empty string for an unknown key.

    An empty value lets the announcement component use its default tone icon.
    """
    icon = _BY_KEY.get(key or "")
    return icon.n26 if icon else ""
