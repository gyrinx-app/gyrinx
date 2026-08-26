"""Which accounts may reach a feature that is still being built.

A feature under construction is gated rather than held back: its code ships
like any other, but only the accounts named on its flag can open it, so half
a screen is never a stranger's first impression of it.

This is the site's, not an edition's. Gating half-built work is a property of
shipping software rather than of any one game, so one table serves both
editions: one admin page, one answer to "what is gated right now", and no
second implementation to drift from this one. What an edition owns is which
features it has — so an edition *registers* its slugs here, the way it claims
its event nouns, and the platform never names them.

A gated view answers a reader who may not see it with **404, never 403**:
which features are being built is not something to be probed for. Signing in
is required even where the ungated page would not ask — being sent to a login
page would itself say that something is there.
"""

from functools import wraps

from django.http import Http404

#: Every slug any edition has claimed. Editions add to this at startup; the
#: platform names none of them.
_known: set[str] = set()


def register_flags(*slugs) -> None:
    """Claim slugs for gating. Registering the same one twice does nothing.

    An edition calls this as it starts, so a guard written against a slug
    nobody registered is a mistake that surfaces at once rather than a page
    that quietly protects nothing.
    """
    _known.update(slugs)


def known_flags() -> frozenset:
    """Every registered slug, for a caller offering them as a choice."""
    return frozenset(_known)


def enabled(slug, user) -> bool:
    """Whether this account may reach the named feature.

    A slug nobody registered raises: that is a mistake in the code, not
    something a reader can cause. A registered slug with no row is off, so a
    feature reaches nobody until somebody opens it.
    """
    from gyrinx.site.models import FeatureFlag

    if slug not in _known:
        raise ValueError(f"No such feature flag: {slug!r}")

    flag = FeatureFlag.objects.filter(slug=slug).first()
    if flag is None:
        return False
    return flag.open_to(user)


def switched_on(slug) -> bool:
    """Whether the named feature is on at all — the question background
    work asks, having no account to ask about.

    Any availability but off counts: a feature open to even one account
    needs the machinery behind it running. A slug with no row is off,
    and an unregistered one raises, exactly as ``enabled`` answers.
    """
    from gyrinx.site.models import Availability, FeatureFlag

    if slug not in _known:
        raise ValueError(f"No such feature flag: {slug!r}")

    # Named open states only, so a word nothing can read fails shut.
    return FeatureFlag.objects.filter(
        slug=slug,
        availability__in=[Availability.ALLOWLIST, Availability.EVERYONE],
    ).exists()


def requires_flag(slug):
    """Guard a view with a feature flag, answering 404 where it is closed.

    Sits outside ``login_required`` where a view has both, so a visitor to a
    gated address is told the page is not there rather than being sent to
    sign in and learning that it is.

    The slug is checked as the guard is applied, not as a request arrives: a
    mistyped one is a mistake in the code, and failing here says so at once.
    Left to the request, the same typo is a page that serves errors to
    whoever finds it first.
    """
    if slug not in _known:
        raise ValueError(f"No such feature flag: {slug!r}")

    def decorate(view):
        @wraps(view)
        def guarded(request, *args, **kwargs):
            if not enabled(slug, request.user):
                raise Http404(f"The {slug} feature is not open to this account")
            return view(request, *args, **kwargs)

        return guarded

    return decorate
