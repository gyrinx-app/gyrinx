"""Hiring a fighter — the web face of :mod:`n26.core.hire`.

Three submissions land on one URL, and each is a step of the same press:

``POST hire=<profile>``
    A Hire button in the list. It answers *which profile*, not "do it": the
    reply is a redirect to this page with ``?hire=<profile>`` and the row's
    ticked options in the query string.
``GET ?hire=<profile>``
    That page — the list, with the name dialog open over it. The dialog is
    a server state, so it survives a reload, it is a link, and a press
    works with scripting switched off.
``POST profile=<profile>``
    The dialog's own submit: the name, and the options it carried through
    as hidden fields. This is the one that hires, and it lands back on the
    list with a confirmation, because the next thing a player does after
    hiring a Ganger is hire another one.

The two-step exists so that the dialog's URL holds one profile's answer.
A form that reached it by GET would put every row's inputs and every filter
control into the address bar, and the filters would be a claim the page
does not honour when it loads.
"""

from dataclasses import dataclass
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.text import slugify

from n26.core.views.permissions import _own_gang_or_404


@dataclass(frozen=True)
class _Pick:
    """One option ticked on a row: the input that carried it, and what it is."""

    field: str
    value: str
    option: object


#: The hire screen's scopes: whose profiles are on offer. URL state
#: (``?list=``), so each is linkable and only the chosen one is built —
#: the all-profiles scope prices every card in the library, and paying
#: that on every visit to the gang list would be paying it for nothing.
HIRE_SCOPES = {
    "gang": "Gang list",
    "supplementary": "Supplementary",
    "all": "All profiles",
}


def _scope(request):
    """Which scope the request names — from the POST when a press carries
    it through, the URL otherwise. Anything unknown is the gang list."""
    named = request.POST.get("list", request.GET.get("list", ""))
    return named if named in HIRE_SCOPES else "gang"


def _scope_tabs(request, scope):
    return [
        {
            "label": label,
            "href": request.path if key == "gang" else f"{request.path}?list={key}",
            "current": key == scope,
        }
        for key, label in HIRE_SCOPES.items()
    ]


def _hireable(gang, pk):
    """The profile that ``pk`` names, if it can be hired at all.

    Any gang may hire any hireable profile — every one of them is
    legitimately on the all-profiles scope — so the check is
    hireability, not whose list it is: a pet still arrives behind its
    collar, never off this screen.

    A pk that is not a ULID at all raises out of the field's ``to_python``.
    The genuine buttons never send one, so it names nothing and the list is
    redisplayed — the same answer as a profile that does not exist.
    """
    from n26.library.models import Profile

    try:
        return Profile.objects.filter(pk=pk, hireable=True).first()
    except ValidationError:
        return None


def _picks(data, profile, entry):
    """The options a submission names, resolved against the drawn rows.

    Each option group's inputs are scoped ``{profile_pk}:{group_index}``
    with option indices as values. The indices are mapped back through
    ``build_hire_entry`` — the same derivation the rows were drawn from —
    because the entry *synthesises* a default group when the profile has
    only named ones, so raw ``grouped_options()`` would be off by one
    exactly there.

    The scope is slugified, which lowercases the pk, because that is what
    the row template renders (``value|slugify``). Read the raw pk back and
    every option ticked in a real browser is silently ignored and the
    fighter buys as default — while a test posting the raw pk passes.
    """
    scope = slugify(str(profile.pk))
    picks = []
    for group_index, group in enumerate(entry.groups):
        field = f"{scope}:{group_index}"
        for value in data.getlist(field):
            # A one-or-none group's "None" radio submits an empty value:
            # the player chose to take nothing, which is not a pick.
            if value == "":
                continue
            # isdigit before int: a negative index is a real index from
            # the far end, so "-1" would quietly resolve to another
            # option in the group rather than being refused like every
            # other index the group does not have.
            try:
                if not value.isdigit():
                    raise ValueError(value)
                option = group.options[int(value)]
            except ValueError, IndexError:
                raise Http404("No such option") from None
            picks.append(_Pick(field=field, value=value, option=option))
    return picks


def _chosen(picks):
    """The sets those picks stand for. The synthesised standard option
    stands for nothing — it is what a profile with no alternatives has."""
    return [pick.option.default_set for pick in picks if pick.option.default_set]


def _dialog(request, profile, picks, scope="gang"):
    """What the name dialog draws: who is being hired, at what price, and
    the hidden fields that carry the row's answer to the next request."""
    try:
        # The operation's own pricing, asked in advance, so the dialog
        # quotes the number the hire will charge rather than a second
        # arithmetic that could disagree with it. It also refuses a
        # tampered selection here rather than one screen later.
        price = profile.price_with(_chosen(picks))
    except ValueError:
        raise Http404("No such option") from None
    cancel_url = request.path if scope == "gang" else f"{request.path}?list={scope}"
    return {
        "profile": profile.name,
        "price": price,
        "scope": scope,
        "choices": [pick.option.name for pick in picks if pick.option.default_set],
        "fields": [
            {"name": "profile", "value": str(profile.pk)},
            *([{"name": "list", "value": scope}] if scope != "gang" else []),
            *({"name": pick.field, "value": pick.value} for pick in picks),
        ],
        "cancel_url": cancel_url,
    }


@login_required
def hire_fighter(request, pk):
    """The gang list, and the dialog that turns a press into a fighter.

    An overspend is refused by the operation itself (``NotEnoughCredits``
    unwinds the transaction), and lands back here as a message: nothing
    half-written, nothing lost but a click.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.forms import HireFighterForm
    from n26.core.hire import (
        build_entries,
        build_hire_entry,
        build_hire_list,
        hireable_profiles,
        section_by_gang_type,
        section_hire_list,
        supplementary_profiles,
    )
    from n26.core.models import Miniature
    from n26.core.operations import NotEnoughCredits, operation

    gang = _own_gang_or_404(request, pk)
    scope = _scope(request)
    # Where every step of the press lands: the list being browsed, so a
    # hire made from the supplementary scope confirms onto it rather
    # than snapping back to the gang list.
    back = request.path if scope == "gang" else f"{request.path}?list={scope}"
    form = HireFighterForm()
    dialog = None

    if request.method == "POST" and "profile" in request.POST:
        form = HireFighterForm(request.POST)
        profile = _hireable(gang, request.POST["profile"])
        if profile is not None:
            picks = _picks(request.POST, profile, build_hire_entry(profile))
            if form.is_valid():
                try:
                    with operation(gang, actor=request.user) as op:
                        miniature = op.hire(
                            profile,
                            form.cleaned_data["name"] or profile.name,
                            option=_chosen(picks),
                        )
                except NotEnoughCredits as refusal:
                    messages.error(request, str(refusal))
                    return redirect(back)
                except ValueError:
                    # Two picks in a choose-one group, or a set the profile
                    # does not offer — resolve_selection refuses tampering
                    # the option indices cannot express. Same answer as a
                    # bad index: this is a broken link, not a rule to
                    # explain.
                    raise Http404("No such option") from None
                # The confirmation quotes the ledger rather than the page's
                # own arithmetic: what a player was charged is whatever the
                # operation wrote down.
                #
                # Both hops are guarded, and the price is dropped rather
                # than guessed at when either is missing. membership is
                # nullable and ledger_entry is a reverse one-to-one that
                # raises rather than answering None, so reading them bare
                # turns a hire that did commit into a 500 on the way to
                # saying so — the fighter would exist with nothing on
                # screen to say they had been hired.
                entry = getattr(miniature.membership, "ledger_entry", None)
                # What the hire cost is read off the ledger for the same
                # reason the message is: the page's arithmetic is a guess,
                # the entry is what happened. Missing means unpriced, not free.
                record(
                    request,
                    N26Noun.MODEL,
                    EventVerb.CREATE,
                    miniature,
                    gang_id=str(gang.pk),
                    profile=profile.name,
                    paid=None if entry is None else entry.paid,
                )
                if entry is None:
                    messages.success(
                        request,
                        f"Hired {profile.name}."
                        if miniature.name == profile.name
                        else f"Hired {miniature.name} — {profile.name}.",
                    )
                else:
                    messages.success(
                        request,
                        f"Hired {profile.name} for {entry.paid}¢."
                        if miniature.name == profile.name
                        else f"Hired {miniature.name} — {profile.name}, {entry.paid}¢.",
                    )
                return redirect(back)
            # A name the field will not take. The dialog comes back holding
            # what was typed, with the error under it — the selection is in
            # the hidden fields, so nothing else has to be re-answered.
            dialog = _dialog(request, profile, picks, scope=scope)
    elif request.method == "POST":
        # A Hire button in the list. Which profile is now a URL, so the
        # dialog has an address of its own and the press survives a reload.
        profile = _hireable(gang, request.POST.get("hire"))
        if profile is not None:
            picks = _picks(request.POST, profile, build_hire_entry(profile))
            # The colon stays a colon: a query key is allowed one, and the
            # URL is worth reading — the row's own input names are what is
            # written there.
            query = urlencode(
                [
                    *([("list", scope)] if scope != "gang" else []),
                    ("hire", str(profile.pk)),
                    *((pick.field, pick.value) for pick in picks),
                ],
                safe=":",
            )
            return redirect(f"{request.path}?{query}")
    elif request.GET.get("hire"):
        profile = _hireable(gang, request.GET["hire"])
        if profile is not None:
            dialog = _dialog(
                request,
                profile,
                _picks(request.GET, profile, build_hire_entry(profile)),
                scope=scope,
            )

    # The whole screen, as one structure: every profile this gang could
    # hire, under the headings its content files them under. The page
    # draws what the structure says rather than assembling headings of
    # its own, so what a tab is called and what a heading is called are
    # one answer.
    if scope == "supplementary":
        hire_list = section_hire_list(build_entries(list(supplementary_profiles())))
    elif scope == "all":
        hire_list = section_by_gang_type(build_entries(list(hireable_profiles())))
    else:
        hire_list = section_hire_list(build_hire_list(gang.gang_type))
    prices = [
        entry.base_price for section in hire_list for entry in section.all_entries()
    ]
    return render(
        request,
        "n26/hire_fighter.html",
        {
            "gang": gang,
            "form": form,
            "dialog": dialog,
            "hire_list": hire_list,
            "scope_tabs": _scope_tabs(request, scope),
            "scope": scope,
            "scope_label": HIRE_SCOPES[scope],
            # How many models the gang already fields, for the figures
            # strip beside the wealth: hiring is decided against what is
            # already on the roster as much as against the credits.
            "roster_count": Miniature.objects.filter(
                membership__gang=gang, membership__archived=False
            ).count(),
            # The tab strip, one tab per section. This list is also the
            # picker's whole navigation once tabs are on: a section whose
            # name is missing here can never be the active tab, and its
            # rows would be served in the HTML with no way to reach them.
            #
            # Taken as they come: the grouping draws a section once, so a
            # name cannot repeat, and deduplicating here would hide one
            # if that ever stopped being true.
            "sections": [section.name for section in hire_list],
            # The picker's all-on category state. These are *registration*
            # names — an item in an unnamed category registers under its
            # section's name, and a list that omits that name silently
            # hides every such row: categoryOn(name) is the filter.
            #
            # Deduplicated, and not because of the sections: a category
            # name is only unique within its section, so two sections'
            # categories can register under one name. The filter keys on
            # the string and a repeated key draws neither.
            "categories": list(
                dict.fromkeys(
                    category.name or section.name
                    for section in hire_list
                    for category in section.categories
                )
            ),
            "category_options": [
                {"value": name, "label": name}
                for name in dict.fromkeys(
                    category.name
                    for section in hire_list
                    for category in section.categories
                    if category.name
                )
            ],
            "price_floor": min(prices, default=0),
            "price_ceiling": max(prices, default=0),
        },
    )
