"""A person's name as a React island draws it: their username, their public
profile and the badge beside it.

The badge's artwork goes into a separate mapping, once per badge, because the
same badge repeats on every row its holder appears on.
"""

from django.urls import reverse

from n26.badges import badge_mark, shown_badge


def person_link(user, badges, *, linked=True):
    """``user`` as a UserLink's props. Their badge's mark is added to
    ``badges`` under its key, unless it is already there. ``linked=False``
    leaves out the profile's address, for a name that goes nowhere."""
    badge = shown_badge(user)
    key = None
    if badge is not None:
        if badge.slug not in badges:
            mark = badge_mark(badge)
            if mark is not None:
                badges[badge.slug] = mark
        if badge.slug in badges:
            key = badge.slug
    person = {"name": user.username, "badge": key}
    if linked:
        person["href"] = reverse("n26-user-profile", args=[user.username])
    return person
