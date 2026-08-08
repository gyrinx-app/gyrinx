"""Template helpers for the site navigation."""

from django import template

register = template.Library()

# The drawer is a shortcut, not the roster. The Gangs link directly above it
# is the complete list, so a player with more than this many still reaches all
# of them in one more press, and the drawer stays a glance rather than a scroll.
DRAWER_GANGS = 10


@register.simple_tag(takes_context=True)
def drawer_gangs(context):
    """The signed-in user's gangs, for the navigation drawer.

    A tag rather than a context processor: the drawer is drawn by this
    edition's layout and nowhere else, and a processor would run this query
    for every page on the site, including the ones that have no drawer.

    Anonymous visitors get an empty list, which the drawer reads as "no
    section at all" rather than an empty heading.
    """
    from n26.core.models import Gang

    user = getattr(context.get("request"), "user", None)
    if user is None or not user.is_authenticated:
        return []
    return list(
        Gang.objects.filter(owner=user, archived=False)
        .select_related("gang_type")
        .order_by("name")[:DRAWER_GANGS]
    )
