"""Reaching a feature that is still being built.

The state lives in a ``FeatureFlag`` row and is changed in the admin, so
opening a feature to another player is something somebody does on a page
rather than a deploy. This module is the read side: the slugs code may ask
for, the question, and the guard a view wears.

A gated view answers a reader who may not see it with **404, never 403**:
which features are being built is not something to be probed for, and every
other guard in this edition already answers a stranger the same way. Signing
in is required even where the ungated page would not ask — being sent to a
login page would itself say that something is there.
"""

from functools import wraps

from django.http import Http404

#: Every feature this edition gates, by the slug code asks for. A slug named
#: here with no row of its own is off: a feature whose row has not been
#: created yet fails shut rather than open. A slug *not* named here is a
#: caller's typo and raises, so a guard can never be silently inert.
CAMPAIGNS = "campaigns"

KNOWN_FLAGS = frozenset({CAMPAIGNS})


def enabled(slug, user):
    """Whether this account may reach the named feature."""
    from n26.core.models import FeatureFlag

    if slug not in KNOWN_FLAGS:
        raise ValueError(f"No such feature flag: {slug!r}")

    flag = FeatureFlag.objects.filter(slug=slug).first()
    if flag is None:
        return False
    return flag.open_to(user)


def requires_flag(slug):
    """Guard a view with a feature flag, answering 404 where it is closed.

    Sits outside ``login_required`` where a view has both, so a visitor to a
    gated address is told the page is not there rather than being sent to
    sign in and learning that it is.
    """

    def decorate(view):
        @wraps(view)
        def guarded(request, *args, **kwargs):
            if not enabled(slug, request.user):
                raise Http404(f"The {slug} feature is not open to this account")
            return view(request, *args, **kwargs)

        return guarded

    return decorate
