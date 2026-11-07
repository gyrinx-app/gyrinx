"""Model-independent search and relation helpers shared by applications."""

from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db.models import Q


def search_queryset(queryset, query, fields):
    """Combine PostgreSQL full-text search with substring matching across fields.

    Return the original queryset for an empty query. Reject a nonempty search
    without fields. Filter through distinct primary keys so reverse relations
    and many-to-many joins cannot duplicate the returned objects.
    """
    query = (query or "").strip()
    if not query:
        return queryset

    if not fields:
        raise ValueError("search_queryset() requires at least one field")

    icontains_q = Q()
    for field in fields:
        icontains_q |= Q(**{f"{field}__icontains": query})

    search_vector = SearchVector(*fields)
    search_q = SearchQuery(query)

    # Deduplicate primary keys before filtering the original queryset. Joined
    # search vectors differ per related record, so DISTINCT over the full
    # annotation would retain duplicates. Clear inherited ordering first.
    matching_pks = (
        queryset.annotate(search=search_vector)
        .filter(Q(search=search_q) | icontains_q)
        .order_by()
        .values_list("pk", flat=True)
        .distinct()
    )
    return queryset.filter(pk__in=matching_pks)


def toggle_membership(relation, user):
    """Toggle a user in the relation and return whether they are now a member."""
    if relation.filter(pk=user.pk).exists():
        relation.remove(user)
        return False
    relation.add(user)
    return True
