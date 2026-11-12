"""Public account presentation supplied by each edition.

Edition readers own visibility and queries. The platform owns the account,
canonical address and shared page, and receives only prepared display data.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.text import slugify

from gyrinx.accounts.validators import social_link_href
from gyrinx.analytics.models import EventVerb, log_event
from gyrinx.analytics.nouns import PlatformNoun
from gyrinx.editions import EDITIONS, N23
from gyrinx.impersonation import can_impersonate_target, note_page_subject


@dataclass(frozen=True)
class ProfileGangSheet:
    model_count: int
    rating: int
    credits: int
    stash_rating: int
    wealth: int
    credits_unlimited: bool = False


@dataclass(frozen=True)
class ProfileEntry:
    name: str
    href: str
    detail: str = ""
    detail_href: str = ""
    stars: int | None = None
    state: str = ""
    is_gang: bool = False
    colour: str = ""
    icon: str = ""
    modified: datetime | None = None
    sheet: ProfileGangSheet | None = None

    @property
    def wealth(self):
        return self.sheet.wealth if self.sheet else 0


@dataclass(frozen=True)
class ProfileSection:
    title: str
    entries: tuple[ProfileEntry, ...]
    empty: str
    add_href: str = ""


@dataclass(frozen=True)
class ProfileAction:
    label: str
    href: str


@dataclass(frozen=True)
class ProfileSource:
    edition: str
    sections: Callable
    actions: Callable = lambda person, request: ()


_sources: dict[str, ProfileSource] = {}


def register_profile_source(source: ProfileSource):
    _sources[source.edition] = source


def profile_person(username):
    """An exact active username wins; a case fallback must be unambiguous."""
    people = (
        get_user_model()
        .objects.filter(is_active=True)
        .select_related("profile")
        .prefetch_related("badge_grants")
    )
    exact = people.filter(username=username).first()
    if exact is not None:
        return exact
    matches = list(people.filter(username__iexact=username)[:2])
    if len(matches) == 1:
        return matches[0]
    raise Http404("No unambiguous active username matches.")


def profile_href(person, tab=None):
    href = reverse("user-profile", args=[person.username])
    if tab in EDITIONS:
        href += "?" + urlencode({"tab": tab})
    return href


def profile_redirect(request, person, default_tab=None):
    tab = request.GET.get("tab")
    return redirect(profile_href(person, tab if tab in EDITIONS else default_tab))


def social_contacts(profile):
    links = [
        {"text": v, "href": social_link_href(v)} for v in profile.social_links if v
    ]
    if profile.instagram_handle:
        links.append(
            {
                "text": "Instagram: @" + profile.instagram_handle,
                "href": "https://www.instagram.com/" + profile.instagram_handle + "/",
            }
        )
    if profile.discord_handle or profile.discord_user_id:
        links.append(
            {
                "text": "Discord: @" + profile.discord_handle
                if profile.discord_handle
                else "Discord",
                "href": "https://discord.com/users/" + profile.discord_user_id
                if profile.discord_user_id
                else "",
            }
        )
    return links


def user_profile(
    request, username, *, settings_form=None, settings_conflict=False, status=200
):
    """Public edition listings, with owner-only records filtered by readers."""
    person = profile_person(username)
    tab = request.GET.get("tab")
    if tab not in EDITIONS:
        tab = getattr(request, "edition", N23)
    sections = _sources[tab].sections(person, request)
    actions = tuple(
        action
        for source in _sources.values()
        for action in source.actions(person, request)
    )
    note_page_subject(request, person)
    may_impersonate = not getattr(
        request, "is_impersonating", False
    ) and can_impersonate_target(request.user, person)
    if request.user.is_authenticated:
        log_event(
            user=request.user,
            noun=PlatformNoun.USER,
            verb=EventVerb.VIEW,
            object=person,
            request=request,
            viewed_user_id=str(person.pk),
            viewed_username=person.username,
            profile_tab=tab,
        )
    from gyrinx.accounts.models import UserProfile
    from gyrinx.accounts.profile_settings import settings_props
    from gyrinx.colours import GANG_COLOURS

    try:
        profile = person.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile(user=person)
    colour = profile.colour if profile.colour in GANG_COLOURS else ""
    category = request.GET.get("category", "")
    if tab == "n23" and category in ("public-gangs", "unlisted"):
        category = "lists"
    active = next(
        (s for s in sections if slugify(s.title) == category),
        next((s for s in sections if s.entries), sections[0] if sections else None),
    )
    sort = request.GET.get("sort", "name")
    if sort not in ("name", "modified", "wealth"):
        sort = "name"
    entries = (
        sorted(active.entries, key=lambda e: (e.name.casefold(), e.href))
        if active
        else []
    )
    if sort == "modified":
        entries.sort(
            key=lambda e: e.modified.timestamp() if e.modified else 0, reverse=True
        )
    elif sort == "wealth":
        entries.sort(key=lambda e: e.wealth, reverse=True)
    page = Paginator(entries, 7).get_page(request.GET.get("page"))

    def listing_href(**changes):
        values = {
            "tab": tab,
            "category": slugify(active.title) if active else "",
            "sort": sort,
        }
        values.update(changes)
        return profile_href(person) + "?" + urlencode(values)

    return render(
        request,
        "platform/user_profile.html",
        {
            "person": person,
            "profile_location": profile.location,
            "profile_picture": profile.picture.url if profile.picture else "",
            "profile_colour": colour,
            "social_links": social_contacts(profile),
            "profile_settings": settings_props(
                request, person, profile, settings_form, conflict=settings_conflict
            ),
            "active_section": active,
            "category_tabs": [
                {
                    "label": s.title,
                    "count": len(s.entries),
                    "href": listing_href(category=slugify(s.title)),
                    "current": s == active,
                }
                for s in sections
            ],
            "page": page,
            "pagination": [
                {"elided": True}
                if n == page.paginator.ELLIPSIS
                else {
                    "label": str(n),
                    "href": listing_href(page=n),
                    "current": n == page.number,
                }
                for n in page.paginator.get_elided_page_range(
                    page.number, on_each_side=1, on_ends=1
                )
            ],
            "previous_page": listing_href(page=page.previous_page_number())
            if page.has_previous()
            else "",
            "next_page": listing_href(page=page.next_page_number())
            if page.has_next()
            else "",
            "profile_sort": {
                "choices": [
                    {
                        "label": label,
                        "href": listing_href(sort=value),
                        "current": sort == value,
                    }
                    for value, label in (
                        ("name", "Name"),
                        ("modified", "Last modified"),
                        ("wealth", "Wealth"),
                    )
                ]
            },
            "gang_section": bool(
                active and active.entries and active.entries[0].is_gang
            ),
            "sections": sections,
            "profile_actions": actions,
            "may_impersonate": may_impersonate,
            "tabs": [
                {
                    "label": edition.upper(),
                    "href": profile_href(person, edition),
                    "current": edition == tab,
                }
                for edition in ("n23", "n26")
            ],
        },
        status=status,
    )


def user_profile_compat(request, slug_or_id):
    return user_profile(request, slug_or_id)
