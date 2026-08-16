"""Supporter badge registry, and the shape every badge is read as.

Badges a user can display next to their name. They arrive two ways:

* **Derived** — the three Patreon supporter tiers and the staff badge, defined
  here in code because their *eligibility* is code (Patreon status, ``is_staff``;
  see :class:`gyrinx.accounts.models.UserProfile`) and their artwork ships with
  the app. Nobody is granted these; holding them follows from live state, so
  they retract on their own when someone lapses.
* **Granted** — rows in the ``Badge`` table, defined by staff in the admin with
  uploaded artwork, and held by whoever has a ``BadgeGrant`` for them.

Both are read as a ``BadgeDef``, so nothing downstream of this module has to ask
which kind it has. A database badge is converted to one on the way out of the
cache, which also means the objects the render path handles are immutable and
cheap to keep around.

The derived four are deliberately *not* rows. Keeping them out of the table is
what makes it impossible for a grant to hand somebody the staff badge: there is
no row to point a grant at.
"""

from dataclasses import dataclass, field
from hashlib import sha256

from django.contrib.staticfiles import finders
from django.core.cache import cache

from gyrinx import artwork
from gyrinx.svg import sanitize_inline_svg


@dataclass(frozen=True)
class BadgeDef:
    """A displayable badge, whether defined in code or in the database.

    ``rank`` orders the Patreon tiers (higher unlocks the lower ones) and breaks
    the tie when someone holds several — see ``UserProfile.display_badge``.
    ``description`` is the short, user-facing tooltip shown next to a username.

    Artwork comes from exactly one of two places. ``svg`` is a static path
    resolved through the staticfiles finders, for badges committed to the repo.
    ``artwork_url`` is an address in the site's own storage, for badges somebody
    uploaded. Uploaded artwork is untrusted and is sanitised every time it is
    drawn; committed artwork is not, which is why the two are separate fields
    rather than one address.

    ``auto_display`` is whether the badge can be shown to someone who has not
    picked it. False means opt-in: it appears in the picker and nowhere else,
    which is what makes granting a badge to everybody safe.
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
        """The artwork, ready to drop into a page, or ``""`` if unavailable.

        Cached either way: the render path draws one badge per row on the busy
        list pages, and both sources are expensive in their own way — a file
        read for committed artwork, a storage round trip plus sanitising for
        uploaded artwork.
        """
        if self.artwork_url:
            return _uploaded_svg(self.artwork_url)
        if self.svg:
            return _committed_svg(self)
        return ""


def _committed_svg(badge: BadgeDef) -> str:
    """Read a badge's static SVG, cached by slug.

    The committed SVGs are inline-ready and are trusted repo assets, not user
    uploads, so they are not sanitised — which is what keeps the Patreon badges'
    two-tone palette and their pixel-art crisp edges exactly as drawn. Failures
    cache as an empty string so a missing or broken file doesn't re-hit the
    filesystem on every render.
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
    """Read and clean uploaded artwork, cached against the cleaned result.

    Colour is kept: a badge is identity artwork, so flattening it to the
    surrounding text colour would throw away the thing that makes it worth
    having. Sanitising happens here, at render, rather than at upload, so
    tightening the allowlist re-secures artwork that is already stored.
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

# Staff badge. Eligibility derives from ``User.is_staff`` rather than Patreon, so
# it's kept out of ``PATREON_BADGES`` (and thus out of the tier-rank machinery).
# Its ``rank`` only matters as the default-selection tie-break in
# ``display_badge``: above the Patreon tiers, so a staff member who also supports
# on Patreon shows the staff badge by default (either can still be picked).
STAFF_BADGE = BadgeDef(
    slug="staff",
    title="Staff",
    rank=100,
    svg="platform/img/badges/staff.svg",
    description="Gyrinx staff",
)

# Every badge defined in code. Not every badge that exists — the grantable ones
# live in the ``Badge`` table and are reached through ``granted_badges_by_id``.
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


# Everything read out of the ``Badge`` table, held as one entry. The table has
# tens of rows at most and is read on every page that draws a username, so the
# alternative is a query per render for data that changes a few times a year.
#
# Writes invalidate it (see ``gyrinx.accounts.models``), but the cache is
# per-process: a write clears the entry in the process that handled it and
# nowhere else. The timeout, not the signal, is what bounds how long another
# process can still be drawing a badge that has just been retired — so it is
# stated here rather than left to the global default.
_GRANTED_CACHE_KEY = "badges:granted:v1"
_GRANTED_CACHE_SECONDS = 60


def _granted_payload() -> dict:
    """Every grantable badge, plus which of them everybody holds.

    Archived badges are left out here rather than filtered at each call site,
    so retiring a badge takes it out of the pickers and off the pages at once.
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
    """Drop the cached badge table, in this process.

    Called whenever a badge or a grant changes, which makes the change show up
    at once for whoever made it. Other processes wait out the timeout.
    """
    cache.delete(_GRANTED_CACHE_KEY)


def granted_badges_by_id() -> dict:
    """Grantable badges keyed by row id.

    Keyed by id, not slug, because the render path has ``grant.badge_id`` in
    hand and looking a badge up by it avoids joining the grant to its badge —
    which is the difference between one prefetch and a join on every row of a
    list page.
    """
    return _granted_payload()["by_id"]


def granted_badges_by_slug() -> dict[str, BadgeDef]:
    """Grantable badges keyed by slug."""
    return {b.slug: b for b in _granted_payload()["by_id"].values()}


def everyone_badge_ids() -> list:
    """Row ids of the badges granted to everybody."""
    return _granted_payload()["everyone"]


def badge_by_slug(slug: str) -> BadgeDef | None:
    """Return the badge with this slug, or ``None``.

    Total across both kinds: a caller holding a slug — a stored selection, a
    template tag argument — should not have to know whether it names a badge
    that ships with the app or one somebody created.
    """
    if not slug:
        return None
    found = _BY_SLUG.get(slug)
    if found is not None:
        return found
    return granted_badges_by_slug().get(slug)


def code_badge_slugs() -> set[str]:
    """Slugs that belong to badges defined in code.

    A ``Badge`` row may not take one of these: the two kinds share the slug
    namespace, because ``UserProfile.selected_badge`` stores a bare slug.
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
    """Form choices for a set of badges, with an explicit "hide" option last.

    Active patrons show their current-tier badge by default, so there's no
    "no badge" choice — instead ``HIDE_BADGE`` lets a user opt out entirely.
    """
    return [(b.slug, b.title) for b in badges] + [(HIDE_BADGE, "Hide badge")]
