"""Supporter badge registry.

Badges a user can display next to their name. These are the three Patreon
supporter tiers plus a staff badge; eligibility is *derived* from a user's live
state (Patreon status / ``is_staff``; see
:class:`gyrinx.core.models.auth.UserProfile`), not stored as a grant.

This is deliberately a small in-code registry rather than a database model: the
tiers are fixed and their eligibility logic is computed regardless of where the
metadata lives. The selection is stored on ``UserProfile.selected_badge`` as a
``slug`` string, so generalising to an admin-managed badge table later is a
localised change here that doesn't touch stored data.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BadgeDef:
    """A displayable badge.

    ``rank`` orders the Patreon tiers (higher unlocks the lower ones). ``svg`` is
    a static path resolved via the staticfiles finders. ``description`` is the
    short, user-facing tooltip shown next to a username explaining the badge.
    """

    slug: str
    title: str
    rank: int
    svg: str
    description: str


# Patreon tiers, lowest to highest. ``rank`` drives "tiers up to and including
# the user's current tier".
PATREON_BADGES: list[BadgeDef] = [
    BadgeDef(
        slug="scummer",
        title="Scummer",
        rank=1,
        svg="core/img/badges/scummer.svg",
        description="Gyrinx supporter — Scummer tier",
    ),
    BadgeDef(
        slug="guilder",
        title="Guilder",
        rank=2,
        svg="core/img/badges/guilder.svg",
        description="Gyrinx supporter — Guilder tier",
    ),
    BadgeDef(
        slug="uphiver",
        title="Uphiver",
        rank=3,
        svg="core/img/badges/uphiver.svg",
        description="Gyrinx supporter — Uphiver tier",
    ),
]

# Staff badge. Eligibility derives from ``User.is_staff`` rather than Patreon, so
# it's kept out of ``PATREON_BADGES`` (and thus out of the tier-rank machinery).
# Its ``rank`` only matters as the default-selection tie-break in
# ``display_badge``: above the Patreon tiers, so a staff member who also supports
# on Patreon shows the staff badge by default (either can still be picked).
STAFF_BADGE = BadgeDef(
    slug="staff",
    title="Staff",
    rank=100,
    svg="core/img/badges/staff.svg",
    description="Gyrinx staff",
)

# All badges, indexed for lookup.
ALL_BADGES: list[BadgeDef] = [*PATREON_BADGES, STAFF_BADGE]

# Sentinel stored in ``UserProfile.selected_badge`` meaning "explicitly hide my
# badge". This is distinct from the empty string: empty means "no explicit
# choice — show the badge for my current tier by default", whereas ``HIDE_BADGE``
# is a deliberate opt-out. No real badge uses this slug.
HIDE_BADGE = "none"

_BY_SLUG: dict[str, BadgeDef] = {b.slug: b for b in ALL_BADGES}

# Map normalised Patreon tier titles to their rank. Built from the registry so
# the canonical order lives in one place. Patreon sends tier titles verbatim
# (confirmed against production: "Scummer", "Guilder", "Uphiver"). A free $0
# tier ("Free") is also sent — including to former patrons — so it must NOT map
# to a badge-eligible rank.
#
# Titles could in principle be renamed in Patreon; a more robust mapping would
# key on the stable numeric tier IDs, but we only store the title today, so map
# by (normalised) title and tolerate minor formatting drift.
_RANK_BY_TITLE: dict[str, int] = {
    b.title.strip().lower(): b.rank for b in PATREON_BADGES
}


def badge_by_slug(slug: str) -> BadgeDef | None:
    """Return the badge with this slug, or ``None``."""
    if not slug:
        return None
    return _BY_SLUG.get(slug)


def rank_for_tier_title(title: str) -> int:
    """Return the badge rank for a Patreon tier title.

    Returns ``0`` for unknown titles, the empty string, and the free tier — i.e.
    anything that doesn't unlock a supporter badge.
    """
    if not title:
        return 0
    return _RANK_BY_TITLE.get(title.strip().lower(), 0)


def badge_choices(badges: list[BadgeDef]) -> list[tuple[str, str]]:
    """Form choices for a set of badges, with an explicit "hide" option last.

    Active patrons show their current-tier badge by default, so there's no
    "no badge" choice — instead ``HIDE_BADGE`` lets a user opt out entirely.
    """
    return [(b.slug, b.title) for b in badges] + [(HIDE_BADGE, "Hide badge")]
