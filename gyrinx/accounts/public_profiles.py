"""Public account presentation supplied by each edition.

Edition readers own visibility and queries. The platform owns the account,
canonical address and shared page, and receives only prepared display data.
"""

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from gyrinx.analytics.models import EventVerb, log_event
from gyrinx.analytics.nouns import PlatformNoun
from gyrinx.editions import EDITIONS, N23
from gyrinx.impersonation import can_impersonate_target, note_page_subject


@dataclass(frozen=True)
class ProfileEntry:
    name: str
    href: str
    detail: str = ""
    detail_href: str = ""
    stars: int | None = None
    amount: str = ""
    state: str = ""


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


def user_profile(request, username):
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
    return render(
        request,
        "platform/user_profile.html",
        {
            "person": person,
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
    )


def user_profile_compat(request, slug_or_id):
    return user_profile(request, slug_or_id)
