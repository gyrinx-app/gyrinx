from django import template
from django.contrib.auth.models import User
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def user_badge(user):
    """Display the active badge for a user inline."""
    if not isinstance(user, User):
        return ""

    active_badge = (
        user.badge_assignments.select_related("badge").filter(is_active=True).first()
    )
    if not active_badge:
        return ""

    badge = active_badge.badge
    icon_html = f'<i class="{badge.icon_class}"></i> ' if badge.icon_class else ""

    badge_html = (
        f'<span class="badge {badge.color_class} rounded-pill ms-1">'
        f"{icon_html}{badge.display_text}"
        f"</span>"
    )

    return mark_safe(badge_html)


@register.simple_tag
def user_badges(user):
    """Display all badges for a user (used on profile page)."""
    if not isinstance(user, User):
        return ""

    badges = user.badge_assignments.select_related("badge").order_by(
        "-is_active", "created"
    )
    if not badges:
        return ""

    badge_html_list = []
    for assignment in badges:
        badge = assignment.badge
        icon_html = f'<i class="{badge.icon_class}"></i> ' if badge.icon_class else ""
        active_indicator = (
            ' <i class="bi bi-star-fill"></i>' if assignment.is_active else ""
        )

        badge_html = (
            f'<span class="badge {badge.color_class} rounded-pill">'
            f"{icon_html}{badge.display_text}{active_indicator}"
            f"</span>"
        )
        badge_html_list.append(badge_html)

    return mark_safe(" ".join(badge_html_list))


@register.inclusion_tag("core/includes/user_with_badge.html")
def user_with_badge(user, link=True):
    """Include tag that displays username with active badge."""
    return {
        "user": user,
        "link": link,
    }
