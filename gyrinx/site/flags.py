"""Feature access checks shared by both editions.

Editions register their feature slugs at startup. FeatureFlag stores access
settings in the platform. Missing records disable a feature; unknown slugs
raise ValueError. Denied requests return 404 to avoid disclosing gated URLs.
"""

from functools import wraps

from django.http import Http404

#: Every slug any edition has claimed. Editions add to this at startup; the
#: platform names none of them.
_known: set[str] = set()


def register_flags(*slugs) -> None:
    """Register edition feature slugs at startup; duplicate registrations are harmless."""
    _known.update(slugs)


def known_flags() -> frozenset:
    """Return the registered slugs for feature choices."""
    return frozenset(_known)


def enabled(slug, user) -> bool:
    """Return whether the user may access the feature.

    Raise ValueError for an unregistered slug. A missing flag record disables
    the feature.
    """
    from gyrinx.site.models import FeatureFlag

    if slug not in _known:
        raise ValueError(f"No such feature flag: {slug!r}")

    flag = FeatureFlag.objects.filter(slug=slug).first()
    if flag is None:
        return False
    return flag.open_to(user)


def switched_on(slug) -> bool:
    """Return whether the feature is enabled for any signed-in users.

    Background jobs use this without a user. Missing records disable the
    feature; unregistered slugs raise ValueError.
    """
    from gyrinx.site.models import Availability, FeatureFlag

    if slug not in _known:
        raise ValueError(f"No such feature flag: {slug!r}")

    # Unknown availability values must not enable background work.
    return FeatureFlag.objects.filter(
        slug=slug,
        availability__in=[Availability.ALLOWLIST, Availability.EVERYONE],
    ).exists()


def requires_flag(slug):
    """Return a view decorator that raises Http404 when access is denied.

    Place outside login_required so denied anonymous requests also return 404.
    Validate the slug when applying the decorator to catch registration errors
    before handling requests.
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
