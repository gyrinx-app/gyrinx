"""The preview endpoint: form state in, card state out.

Tom's framing (design/authoring.md): the scratch-card UI is earnable if
"an endpoint that takes the form state and gives back card state"
exists. This is that endpoint, deliberately thin — everything it does
lives in :mod:`n26.preview`, and nothing it does survives the request:
the preview rolls its own transaction back.
"""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from n26.core.preview import PreviewError, preview


@require_POST
def preview_view(request):
    try:
        state = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"errors": {"body": ["Not JSON."]}}, status=400)
    try:
        result = preview(state)
    except PreviewError as refusal:
        return JsonResponse({"errors": refusal.errors}, status=400)
    return JsonResponse(result.as_dict())


@login_required
def dashboard(request):
    """The edition's front page: your gangs, and what changed lately.

    Assembled entirely from the design system's components — the view
    supplies rows and the components draw them, so this page and the
    gallery's shell can only drift by someone editing the library. The
    gang search and the type filter are the gang-table's own; the rows
    just register their facets.
    """
    from gyrinx.site.models import ChangelogEntry
    from n26.core.models import Gang

    gangs = (
        Gang.objects.filter(owner=request.user, archived=False)
        .select_related("gang_type", "stash")
        .order_by("name")
    )
    return render(
        request,
        "n26/dashboard.html",
        {
            "gangs": gangs,
            # Deduplicated in order rather than sorted: the filter reads
            # better in the order the reader saw the types down the list.
            "gang_type_options": [
                {"value": name, "label": name}
                for name in dict.fromkeys(str(gang.gang_type) for gang in gangs)
            ],
            "changelog": ChangelogEntry.objects.filter(archived=False)[:5],
        },
    )


@login_required
def gang_sheet(request, pk):
    """One gang, whole: what it is worth, what it owns, who is in it.

    The design system's gang sheet over real rows. ``render_gang``
    already does the derivation — the gang's own lines, its choices and
    counters, the stash, a card per member — in a fixed number of
    queries however big the roster, so this view is the lookup and
    nothing else, and the page draws the same component the gallery's
    shell does.

    Scoped to the owner, and a gang belonging to someone else is a 404
    rather than a 403: which gangs exist is not something a stranger
    should be able to probe for.
    """
    from n26.core.render import render_gang

    gang = _own_gang_or_404(request, pk)
    return render(
        request,
        "n26/gang_sheet.html",
        {"gang": gang, "sheet": render_gang(gang)},
    )


def _own_gang_or_404(request, pk):
    """The gang, if it is the viewer's to act on.

    A pk that is not a ULID reaches ``to_python`` and raises
    ``ValidationError`` — a 500 for what is only ever a bad URL, so it is
    caught here. Well-formed-but-absent already 404s on its own.
    """
    from n26.core.models import Gang

    try:
        return get_object_or_404(
            Gang.objects.select_related("gang_type", "owner", "stash"),
            pk=pk,
            owner=request.user,
            archived=False,
        )
    except ValidationError:
        raise Http404("No such gang") from None


def _own_miniature_or_404(request, pk):
    """The fighter, if theirs to act on — the miniature-shaped twin of
    ``_own_gang_or_404``, with the same bad-ULID guard. Archived
    memberships and archived gangs are out: a dead fighter's Equip link
    should go the way the fighter did."""
    from n26.core.models import Miniature

    try:
        return get_object_or_404(
            Miniature.objects.select_related(
                "membership__gang__gang_type",
                "membership__gang__owner",
                "membership__gang__stash",
            ),
            pk=pk,
            membership__gang__owner=request.user,
            membership__gang__archived=False,
            membership__archived=False,
        )
    except ValidationError:
        raise Http404("No such fighter") from None


def _thing_key(thing):
    """One string naming a browsed line's item — what the Buy buttons
    submit. Model label plus pk, the same pair ``browse`` dedupes on,
    because a pk alone is ambiguous across the assignable tables."""
    return f"{thing._meta.label_lower}:{thing.pk}"


@login_required
def equip(request, pk):
    """Buy equipment for one fighter, from a list they can actually browse.

    Which list is URL state (``?list=<pk>``), picked from
    ``collections_for`` — the fighter's own lists, their gang's, computed
    grants — plus the standard Trading Post when the library has one.

    The Buy buttons submit the *identity* of a line, never its price:
    the server re-browses the chosen collection and hands the found line
    whole to ``Operation.buy``, so what is paid is always the server's
    derivation and a tampered form can name nothing that is not on the
    list. Browsed on equipment-list terms for now — Trade Points are
    shown, not charged, because a TP budget is a session concept that
    does not exist yet.

    A purchase stays on the page: kitting out a fighter is a run of
    purchases, and the breadcrumb is the way back.
    """
    from n26.core.access import collections_for
    from n26.core.browse import browse, usability_for, with_use_notes
    from n26.core.card import build_card, build_modifier_index
    from n26.core.effects import compute
    from n26.core.operations import NotEnoughCredits, operation
    from n26.library.models import Collection, get_default_pack
    from n26.library.standard_content import TRADING_POST_COLLECTION

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.gang

    collections = [access.collection for access in collections_for(miniature)]
    # Pinned to the default pack: collection names are only unique per
    # pack, so a homebrew pack's own "Trading Post" must not shadow the
    # standard one here. A pack's post reaches a fighter the way any list
    # does — by being assigned or granted, which collections_for found.
    post = Collection.objects.filter(
        name=TRADING_POST_COLLECTION, pack=get_default_pack()
    ).first()
    if post is not None and post.pk not in {c.pk for c in collections}:
        collections.append(post)

    chosen = None
    wanted = request.GET.get("list")
    for collection in collections:
        if str(collection.pk) == wanted:
            chosen = collection
            break
    if chosen is None and collections:
        chosen = collections[0]

    view = None
    if chosen is not None:
        card = build_card(miniature)
        index = build_modifier_index([node.assignable for node in card.all_nodes()])
        view = with_use_notes(browse(chosen), usability_for(compute(card, index)))

    if request.method == "POST" and view is not None:
        key = request.POST.get("thing", "")
        line = next(
            (row for row in view.all_lines() if _thing_key(row.thing) == key), None
        )
        back = f"{request.path}?list={chosen.pk}"
        if line is None:
            # Not on this list — a stale page or a tampered form. The
            # list itself is the answer either way.
            messages.error(request, "That item is not on this list.")
            return redirect(back)
        try:
            with operation(gang, actor=request.user) as op:
                op.buy(miniature, line=line)
        except NotEnoughCredits as refusal:
            messages.error(request, str(refusal))
            return redirect(back)
        messages.success(request, f"Bought {line.name} for {miniature.name}.")
        return redirect(back)

    lines = list(view.all_lines()) if view is not None else []
    trade_points = [
        line.trade_points for line in lines if line.trade_points is not None
    ]
    sections = view.sections if view is not None else []
    return render(
        request,
        "n26/equip.html",
        {
            "miniature": miniature,
            "gang": gang,
            "collections": collections,
            "chosen": chosen,
            # Each line paired with the key its Buy button submits, so the
            # template never composes an identity of its own.
            "section_rows": [
                {
                    "name": section.name,
                    "first": index == 0,
                    "categories": [
                        {
                            "name": category.name,
                            "lines": [
                                {"line": line, "key": _thing_key(line.thing)}
                                for line in category.lines
                            ],
                        }
                        for category in section.categories
                    ],
                }
                for index, section in enumerate(sections)
            ],
            # Registration names, "" included — see the hire view: a row
            # in an unnamed category registers under its section's name,
            # and a list that omits one hides those rows client-side.
            "categories": list(
                dict.fromkeys(
                    category.name or section.name
                    for section in sections
                    for category in section.categories
                )
            ),
            "category_options": [
                {"value": name, "label": name}
                for name in dict.fromkeys(
                    category.name
                    for section in sections
                    for category in section.categories
                    if category.name
                )
            ],
            # All-or-nothing, as on the hire page: tabs are the whole
            # navigation once on, and an unnamed section can never be the
            # active tab — mixed content would hide it.
            "sections": (
                [section.name for section in sections]
                if sections and all(section.name for section in sections)
                else []
            ),
            "cost_floor": min((line.credits for line in lines), default=0),
            "cost_ceiling": max((line.credits for line in lines), default=0),
            "tp_ceiling": max(trade_points, default=0),
            "has_trade_points": bool(trade_points),
            # Distinct from has_trade_points: an exclusive line has
            # trade_points=None ("E" is not a number), so a list of
            # exclusive-only items would otherwise never draw the toggle
            # that is the only way to filter them.
            "has_exclusive": any(line.is_exclusive for line in lines),
        },
    )


@login_required
def hire_fighter(request, pk):
    """Hire a fighter: the design system's picker over the real gang list.

    GET is ``build_hire_list`` shelved by each profile's home category.
    POST is the picker's own contract: every Hire button submits the form
    carrying ``profile``, and each option group's inputs are scoped
    ``{profile_pk}:{group_index}`` with option indices as values. The
    indices are mapped back through ``build_hire_entry`` — the same
    derivation the rows were drawn from — because the entry *synthesises*
    a default group when the profile has only named ones, so raw
    ``grouped_options()`` would be off by one exactly there.

    An overspend is refused by the operation itself (``NotEnoughCredits``
    unwinds the transaction), and lands back here as a message: nothing
    half-written, nothing lost but a click.
    """
    from n26.core.forms import HireFighterForm
    from n26.core.hire import build_hire_entry, build_hire_list, shelve_hire_list
    from n26.core.operations import NotEnoughCredits, operation
    from n26.library.models import Profile

    gang = _own_gang_or_404(request, pk)

    if request.method == "POST":
        form = HireFighterForm(request.POST)
        try:
            profile = Profile.objects.filter(
                pk=request.POST.get("profile"), gang_type=gang.gang_type
            ).first()
        except ValidationError:
            # A tampered pk, not a ULID at all. The genuine buttons never
            # send one, so redisplaying the list is all it deserves.
            profile = None
        if profile is not None and form.is_valid():
            entry = build_hire_entry(profile)
            chosen = []
            # The row template scopes its option inputs with
            # `value|slugify`, which lowercases the pk — so the keys must
            # be read back through the same filter, or every option ticked
            # in a real browser is silently ignored and the fighter buys
            # as default. (A test posting the raw pk would pass anyway,
            # which is exactly how that bug shipped the first time.)
            scope = slugify(str(profile.pk))
            for group_index, group in enumerate(entry.groups):
                picked = request.POST.getlist(f"{scope}:{group_index}")
                for value in picked:
                    try:
                        option = group.options[int(value)]
                    except ValueError, IndexError:
                        raise Http404("No such option") from None
                    if option.default_set is not None:
                        chosen.append(option.default_set)
            try:
                with operation(gang, actor=request.user) as op:
                    miniature = op.hire(
                        profile,
                        form.cleaned_data["name"] or profile.name,
                        option=chosen,
                    )
            except NotEnoughCredits as refusal:
                messages.error(request, str(refusal))
                return redirect("n26-hire-fighter", pk=gang.pk)
            except ValueError:
                # Two picks in a choose-one group, or a set the profile
                # does not offer — resolve_selection refuses tampering
                # the option indices cannot express. Same answer as a
                # bad index: this is a broken link, not a rule to explain.
                raise Http404("No such option") from None
            messages.success(request, f"Hired {miniature.name}.")
            return redirect("n26-gang", pk=gang.pk)
    else:
        form = HireFighterForm()

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


@login_required
def create_gang(request):
    """Found a gang: the design system's create form, wired to write.

    POST founds for real — the Gang row, then its founding assignment
    and whatever the type's built-ins bring, in one operation — and
    lands back on the dashboard where the new gang is now a row.
    """
    from n26.core.forms import CreateGangForm
    from n26.core.models import Gang
    from n26.core.operations import operation

    if request.method == "POST":
        form = CreateGangForm(request.POST)
        if form.is_valid():
            budget = form.cleaned_data["starting_credits"]
            gang_type = form.cleaned_data["gang_type"]
            if budget is None:
                budget = gang_type.starting_credits
            gang = Gang.objects.create(
                name=form.cleaned_data["name"],
                gang_type=gang_type,
                owner=request.user,
                starting_credits=budget,
                credits=budget or 0,
                colour=form.cleaned_data["colour"],
            )
            with operation(gang, actor=request.user) as op:
                op.found(gang_type)
            messages.success(request, f"Founded {gang.name}.")
            return redirect("n26-dashboard")
    else:
        form = CreateGangForm()

    return render(
        request,
        "n26/create_gang.html",
        {"form": form, "gang_types": form.gang_type_choices()},
    )
