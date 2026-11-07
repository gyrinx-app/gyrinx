"""Badge definitions and lookup helpers shared by both editions.

Patreon and staff badges derive eligibility from account state. Grantable
badges use Badge and BadgeGrant records. Both resolve to immutable BadgeDef
objects for display. Code-defined badges have no database records, so grants
cannot confer Patreon or staff eligibility.
"""

from base64 import b64encode
from dataclasses import dataclass, field
from hashlib import sha256

from django.contrib.staticfiles import finders
from django.core.cache import cache

from gyrinx import artwork
from gyrinx.svg import sanitize_inline_svg


@dataclass(frozen=True)
class BadgeDef:
    """Immutable display data for a code-defined or grantable badge.

    Rank orders Patreon tiers and breaks ties for UserProfile.display_badge.
    Description supplies the tooltip. Static SVG files are trusted repository
    assets; uploaded artwork is sanitised at rendering. A false auto_display
    value requires a holder to choose the badge before it is shown.
    """

    slug: str
    title: str
    rank: int
    description: str
    svg: str = ""
    artwork_url: str = ""
    auto_display: bool = True
    # Set on badges that came from a row, so a caller that needs to get back to
    # one (the admin, mostly) does not have to look it up by slug.
    id: object = field(default=None, compare=False)

    def inline_svg(self) -> str:
        """Return cached SVG markup, or an empty string if artwork is unavailable.

        Cache both file reads and sanitised uploads because a page may draw the
        same badge beside many usernames.
        """
        if self.artwork_url:
            return _uploaded_svg(self.artwork_url)
        if self.svg:
            return _committed_svg(self)
        return ""

    def image_url(self) -> str:
        """The same sanitised artwork as an image, preserving its SVG rendering.

        An image's SVG does not inherit the surrounding page's icon CSS.
        """
        svg = self.inline_svg()
        return (
            f"data:image/svg+xml;base64,{b64encode(svg.encode()).decode()}"
            if svg
            else ""
        )


def _committed_svg(badge: BadgeDef) -> str:
    """Read trusted static artwork and cache it by slug.

    Keep the committed colours unchanged. Cache missing or unreadable files as
    an empty string to avoid repeated filesystem reads.
    """
    cache_key = f"badge_svg:{sha256(badge.slug.encode('utf-8')).hexdigest()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    svg = ""
    path = finders.find(badge.svg)
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                svg = fh.read()
        except OSError:
            svg = ""

    cache.set(cache_key, svg)
    return svg


def _uploaded_svg(address: str) -> str:
    """Read uploaded artwork and cache its sanitised markup by source content.

    Preserve badge colours. Sanitising at rendering applies allowlist changes
    to existing uploads.
    """
    raw = artwork.read(address)
    if not raw:
        return ""

    cache_key = f"badge_artwork:{sha256(raw.encode('utf-8')).hexdigest()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    cleaned = sanitize_inline_svg(raw, preserve_colour=True)
    cache.set(cache_key, cleaned)
    return cleaned


# Patreon tiers, lowest to highest. ``rank`` drives "tiers up to and including
# the user's current tier".
PATREON_BADGES: list[BadgeDef] = [
    BadgeDef(
        slug="scummer",
        title="Scummer",
        rank=1,
        svg="platform/img/badges/scummer.svg",
        description="Gyrinx supporter — Scummer tier",
    ),
    BadgeDef(
        slug="guilder",
        title="Guilder",
        rank=2,
        svg="platform/img/badges/guilder.svg",
        description="Gyrinx supporter — Guilder tier",
    ),
    BadgeDef(
        slug="uphiver",
        title="Uphiver",
        rank=3,
        svg="platform/img/badges/uphiver.svg",
        description="Gyrinx supporter — Uphiver tier",
    ),
]

# Staff eligibility uses User.is_staff. Its higher rank makes it the default
# for staff who also hold Patreon badges; users may select either badge.
STAFF_BADGE = BadgeDef(
    slug="staff",
    title="Staff",
    rank=100,
    svg="platform/img/badges/staff.svg",
    description="Gyrinx staff",
)

# Grantable badges are loaded separately by granted_badges_by_id.
ALL_BADGES: list[BadgeDef] = [*PATREON_BADGES, STAFF_BADGE]

# An empty selection allows a default badge; this reserved slug hides all badges.
HIDE_BADGE = "none"

_BY_SLUG: dict[str, BadgeDef] = {b.slug: b for b in ALL_BADGES}

# Patreon stores tier titles on UserProfile. Normalise case and surrounding
# whitespace, and exclude the free tier from badge eligibility.
_RANK_BY_TITLE: dict[str, int] = {
    b.title.strip().lower(): b.rank for b in PATREON_BADGES
}


# Cache the small grantable-badge table to avoid a query per username.
# Write signals invalidate only the current process; the timeout bounds staleness elsewhere.
_GRANTED_CACHE_KEY = "badges:granted:v1"
_GRANTED_CACHE_SECONDS = 60


def _granted_payload() -> dict:
    """Return active grantable badges and the IDs granted to everyone.

    Exclude archived badges from both lists so retirement removes eligibility.
    """
    cached = cache.get(_GRANTED_CACHE_KEY)
    if cached is not None:
        return cached

    # Imported here rather than at module scope: the models import this module.
    from gyrinx.accounts.models import Badge, BadgeGrant

    badges = {b.id: b.as_def() for b in Badge.objects.filter(archived=False)}
    everyone = [
        badge_id
        for badge_id in BadgeGrant.objects.filter(
            audience=BadgeGrant.Audience.EVERYONE
        ).values_list("badge_id", flat=True)
        if badge_id in badges
    ]

    payload = {"by_id": badges, "everyone": everyone}
    cache.set(_GRANTED_CACHE_KEY, payload, _GRANTED_CACHE_SECONDS)
    return payload


def invalidate_granted_badges() -> None:
    """Invalidate the grantable badge cache in this process.

    Other processes retain their cached values until the timeout expires.
    """
    cache.delete(_GRANTED_CACHE_KEY)


def granted_badges_by_id() -> dict:
    """Return active grantable badges keyed by primary key.

    Callers can resolve prefetched grants by badge_id without fetching Badge
    objects for each grant.
    """
    return _granted_payload()["by_id"]


def granted_badges_by_slug() -> dict[str, BadgeDef]:
    """Grantable badges keyed by slug."""
    return {b.slug: b for b in _granted_payload()["by_id"].values()}


def everyone_badge_ids() -> list:
    """Row ids of the badges granted to everybody."""
    return _granted_payload()["everyone"]


def badge_by_slug(slug: str) -> BadgeDef | None:
    """Return a code-defined or grantable badge, or None if the slug is unknown."""
    if not slug:
        return None
    found = _BY_SLUG.get(slug)
    if found is not None:
        return found
    return granted_badges_by_slug().get(slug)


def code_badge_slugs() -> set[str]:
    """Return reserved slugs for code-defined badges.

    UserProfile stores a bare slug, so grantable badges must use other slugs.
    """
    return set(_BY_SLUG)


def rank_for_tier_title(title: str) -> int:
    """Return the badge rank for a Patreon tier title.

    Returns ``0`` for unknown titles, the empty string, and the free tier — i.e.
    anything that doesn't unlock a supporter badge.
    """
    if not title:
        return 0
    return _RANK_BY_TITLE.get(title.strip().lower(), 0)


def badge_choices(badges: list[BadgeDef]) -> list[tuple[str, str]]:
    """Return choices for the supplied badges, followed by an explicit hide option."""
    return [(b.slug, b.title) for b in badges] + [(HIDE_BADGE, "Hide badge")]
