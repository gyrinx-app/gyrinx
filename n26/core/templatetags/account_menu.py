"""The account menu as the account-menu island's props.

The menu is an ordered list of items the island draws as they come: the
reader's name, separators, links, headed groups, the theme choice and posting
rows. A section draws the break above itself, so one that is absent leaves no
rule behind; a headed group needs no rule, because its heading is the break.
"""

from django import template
from django.middleware.csrf import get_token
from django.urls import NoReverseMatch, reverse

from n26.core.people import person_link
from n26.core.templatetags.theme_choice import theme_choice_props

register = template.Library()


def _url(name):
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


@register.simple_tag(takes_context=True)
def account_menu(context, compact=False):
    """The signed-in reader's menu, or ``None`` for a visitor.

    ``compact`` is the platform account pages' shorter menu: no name line,
    the admin as a single row, and no rule over the way out.
    """
    request = context.get("request")
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    unread = context.get("unread_notification_count") or 0
    unread_noun = "unread notification" if unread == 1 else "unread notifications"
    badges = {}
    person = person_link(user, badges)
    notifications = {
        "type": "link",
        "label": "Notifications",
        "href": reverse("core:notifications"),
        "count": unread,
        "countLabel": unread_noun,
    }
    account = {
        "type": "link",
        "label": "Your account",
        "href": reverse("core:account_home"),
    }
    theme = {
        "type": "group",
        "label": "Theme",
        "items": [{"type": "theme", **theme_choice_props("theme")}],
    }
    admin_url = _url("admin:index")
    logout_url = _url("account_logout")
    sign_out = {
        "type": "link",
        "label": "Sign out",
        "href": logout_url,
        "tone": "danger",
    }

    if compact:
        items = [account, notifications, theme]
        if user.is_staff and admin_url:
            items.append({"type": "link", "label": "Admin", "href": admin_url})
        if logout_url:
            items.append(sign_out)
    else:
        items = [
            {"type": "person"},
            {"type": "separator"},
            account,
            notifications,
            theme,
        ]
        if user.is_staff:
            staff = []
            if admin_url:
                staff.append({"type": "link", "label": "Admin", "href": admin_url})
            staff.append(
                {
                    "type": "link",
                    "label": "Content library",
                    "href": reverse("authoring-index"),
                }
            )
            target = context.get("impersonate_target")
            if target is not None:
                staff.append(
                    {
                        "type": "form",
                        "label": f"Impersonate {target.username}",
                        "action": reverse("core:impersonate-start", args=[target.pk]),
                        "fields": [
                            ["csrfmiddlewaretoken", get_token(request)],
                            ["next", request.get_full_path()],
                        ],
                        "tone": "danger",
                    }
                )
            items.append({"type": "group", "label": "Staff only", "items": staff})
        if logout_url:
            items += [{"type": "separator"}, sign_out]

    return {
        "label": "Open account menu",
        "unread": unread,
        "unreadText": f"{unread} {unread_noun}",
        "person": person,
        "badges": badges,
        "items": items,
    }
