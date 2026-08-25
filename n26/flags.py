"""Which of this edition's features are gated, and the one door that asks.

Gating half-built work is the site's business, not an edition's: it is a
property of shipping software rather than of any one game. One table serves
both editions, so there is one admin page, one answer to "what is gated right
now", and no second implementation to drift from the first. A copy here would
give the two editions separate answers to one question — the same argument
that keeps analytics and the maintenance console in one place.

What this edition owns is *which* features it has. The slugs are declared
here and claimed at startup (``n26.core.apps``), the way this edition claims
its event nouns; the platform holds the state and never names the features.

So this module is the whole of n26's dependency on the platform's flags.
Every n26 call site goes through it; nothing else in ``n26/`` imports
``gyrinx.site.flags``. Keeping it to one file means the seam can be read,
tested and moved in one place, and it is the reason the boundary rule in
``n26/CLAUDE.md`` names this file rather than a package.
"""

from gyrinx.site.flags import enabled, register_flags, requires_flag

__all__ = ["CAMPAIGNS", "enabled", "requires_flag"]

#: Running a campaign: the campaign itself, who is in it, and what it owns.
CAMPAIGNS = "campaigns"

register_flags(CAMPAIGNS)
