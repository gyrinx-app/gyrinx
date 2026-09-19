"""The access policy shared by flat-page views and navigation."""

from django.contrib.flatpages.models import FlatPage
from django.db.models import Q, QuerySet


def accessible_flatpages(
    *, site_id: int, user, include_registration_required: bool = True
) -> QuerySet[FlatPage]:
    """Return the pages on ``site_id`` that ``user`` is allowed to discover.

    A page without a visibility rule is public. Once a rule exists, the user
    must belong to at least one group assigned by any rule. Consequently, a
    page whose rules contain no groups is deliberately visible to nobody.

    ``registration_required`` is handled separately from group visibility so
    direct requests can retain Django's redirect-to-login response.
    """
    pages = FlatPage.objects.filter(sites__id=site_id)
    if user is not None and user.is_authenticated:
        pages = pages.filter(
            Q(flatpagevisibility__isnull=True)
            | Q(flatpagevisibility__groups__in=user.groups.all())
        )
    else:
        pages = pages.filter(flatpagevisibility__isnull=True)

    if not include_registration_required:
        pages = pages.filter(registration_required=False)

    return pages.distinct()
