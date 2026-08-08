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


def _hireable(gang, pk):
    """The profile that ``pk`` names, if this gang could hire it.

    A pk that is not a ULID at all raises out of the field's ``to_python``.
    The genuine buttons never send one, so it names nothing and the list is
    redisplayed — the same answer as a profile from somebody else's list.
    """
    from n26.library.models import Profile

    try:
        return Profile.objects.filter(pk=pk, gang_type=gang.gang_type).first()
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
            try:
                option = group.options[int(value)]
            except ValueError, IndexError:
                raise Http404("No such option") from None
            picks.append(_Pick(field=field, value=value, option=option))
    return picks


def _chosen(picks):
    """The sets those picks stand for. The synthesised standard option
    stands for nothing — it is what a profile with no alternatives has."""
    return [pick.option.default_set for pick in picks if pick.option.default_set]


def _dialog(request, profile, picks):
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
    return {
        "profile": profile.name,
        "price": price,
        "choices": [pick.option.name for pick in picks if pick.option.default_set],
        "fields": [
            {"name": "profile", "value": str(profile.pk)},
            *({"name": pick.field, "value": pick.value} for pick in picks),
        ],
        "cancel_url": request.path,
    }


@login_required
def hire_fighter(request, pk):
    """The gang list, and the dialog that turns a press into a fighter.

    An overspend is refused by the operation itself (``NotEnoughCredits``
    unwinds the transaction), and lands back here as a message: nothing
    half-written, nothing lost but a click.
    """
    from n26.core.forms import HireFighterForm
    from n26.core.hire import build_hire_entry, build_hire_list, shelve_hire_list
    from n26.core.operations import NotEnoughCredits, operation

    gang = _own_gang_or_404(request, pk)
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
                    return redirect("n26-hire-fighter", pk=gang.pk)
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
                paid = miniature.membership.ledger_entry.paid
                messages.success(
                    request,
                    f"Hired {profile.name} for {paid}¢."
                    if miniature.name == profile.name
                    else f"Hired {miniature.name} — {profile.name}, {paid}¢.",
                )
                return redirect("n26-hire-fighter", pk=gang.pk)
            # A name the field will not take. The dialog comes back holding
            # what was typed, with the error under it — the selection is in
            # the hidden fields, so nothing else has to be re-answered.
            dialog = _dialog(request, profile, picks)
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
            )

    section_rows = shelve_hire_list(build_hire_list(gang.gang_type))
    entries = [
        entry
        for section_row in section_rows
        for category in section_row["categories"]
        for entry in category["entries"]
    ]
    prices = [entry.base_price for entry in entries]
    return render(
        request,
        "n26/hire_fighter.html",
        {
            "gang": gang,
            "form": form,
            "dialog": dialog,
            "section_rows": [
                {"section": section_row, "first": index == 0}
                for index, section_row in enumerate(section_rows)
            ],
            # Tabs only when *every* section is named. The tab strip is
            # the picker's whole navigation once it is on: a section
            # whose name is not in this list can never be the active tab,
            # so mixed content — some profiles homed, some not — would
            # serve the unnamed shelf in the HTML and make it unreachable.
            # All-or-nothing keeps every row reachable either way.
            "sections": (
                [row["name"] for row in section_rows]
                if section_rows and all(row["name"] for row in section_rows)
                else []
            ),
            # The picker's all-on category state. These are *registration*
            # names — an item in an unnamed category registers under its
            # section's name (possibly ""), and a list that omits that name
            # silently hides every such row: categoryOn("") is the filter.
            "categories": list(
                dict.fromkeys(
                    category["name"] or section_row["name"]
                    for section_row in section_rows
                    for category in section_row["categories"]
                )
            ),
            "category_options": [
                {"value": name, "label": name}
                for name in dict.fromkeys(
                    category["name"]
                    for section_row in section_rows
                    for category in section_row["categories"]
                    if category["name"]
                )
            ],
            "price_floor": min(prices, default=0),
            "price_ceiling": max(prices, default=0),
        },
    )
