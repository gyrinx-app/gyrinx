"""Generic queryset helpers.

Model-agnostic operations that any app can apply to any queryset or relation.
Nothing here knows what it is querying — see ``n23/core/utils.py`` for the
edition's own list/campaign query helpers.
"""

from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db.models import Q


def search_queryset(queryset, query, fields):
    """
    Apply a combined full-text and substring search to a queryset.

    Uses PostgreSQL full-text search (SearchVector + SearchQuery) for
    word-level matching, combined with icontains fallback on every field
    so that partial/substring queries (e.g. "scav" matching "scavvies")
    also return results.

    Args:
        queryset: The Django queryset to filter.
        query: The search string. Stripped internally; if empty/None after
            stripping, the queryset is returned unchanged.
        fields: An iterable of field lookup strings to search across
            (e.g. ["name", "summary", "owner__username"]).

    Returns:
        The filtered queryset, deduplicated via a PK subquery so that
        reverse-FK and M2M search fields don't produce duplicate rows.

    Example::

        qs = search_queryset(
            Pack.objects.all(),
            request.GET.get("q", "").strip(),
            ["name", "summary", "owner__username"],
        )
    """
    query = (query or "").strip()
    if not query:
        return queryset

    if not fields:
        raise ValueError("search_queryset() requires at least one field")

    # Build icontains fallback: OR across all fields
    icontains_q = Q()
    for field in fields:
        icontains_q |= Q(**{f"{field}__icontains": query})

    # Full-text search via SearchVector + SearchQuery
    search_vector = SearchVector(*fields)
    search_q = SearchQuery(query)

    # Use a subquery to find matching PKs, then filter the original queryset.
    # This avoids duplicates from JOINs created by SearchVector on related
    # fields (e.g. reverse FK or M2M lookups like contentweaponprofile__name
    # or contentweaponprofile__traits__name). With the annotation approach,
    # DISTINCT is ineffective because the tsvector varies per joined row.
    # Clear any inherited ordering so DISTINCT applies only to the PK column.
    matching_pks = (
        queryset.annotate(search=search_vector)
        .filter(Q(search=search_q) | icontains_q)
        .order_by()
        .values_list("pk", flat=True)
        .distinct()
    )
    return queryset.filter(pk__in=matching_pks)


def toggle_membership(relation, user):
    """
    Toggle a user's membership in a many-to-many relation.

    Used by the pin/star toggle views on lists and campaigns.

    Returns:
        True if the user is now a member, False if they were removed.
    """
    if relation.filter(pk=user.pk).exists():
        relation.remove(user)
        return False
    relation.add(user)
    return True
