"""Buy equipment for models or the gang stash through a shared purchase parser.

Both pages derive the current offer, validate submitted selections and prices,
and write through operations. Confirmation objects let callers choose between
React display data and native confirmation responses without duplicating purchase logic.

_screen supplies the same card, collection and budget derivation for the React
owner and retained native POST adapters. Shared fragments still serve native
controls on other screens and cached clients.
"""

from dataclasses import dataclass
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache

from n26.core.confirm import CONFIRM_FIELD, Confirmation
from n26.core.owned import thing_key as _thing_key
from n26.core.prices import PRICE_CEILING
from n26.core.views.htmx import is_htmx, no_update, with_toasts
from n26.core.views.permissions import (
    _own_gang_or_404,
    _own_miniature_or_404,
    credits_href,
    may_mark_status,
    may_see_founding,
    status_href,
    trade_points_href,
)
from n26.library.staged import sees_staged


def _parts_picked(data, key, line):
    from n26.core.equip_purchase import UnavailableEquipment, parts_picked

    try:
        return parts_picked(data, key, line)
    except UnavailableEquipment as error:
        raise Http404(str(error)) from None


LIST_SUFFIX = "equipment list"


def _tab_label(collection):
    """Remove a redundant equipment-list suffix while retaining an otherwise empty name."""
    name = str(collection)
    if not name.lower().endswith(LIST_SUFFIX):
        return name
    return name[: -len(LIST_SUFFIX)].strip(" -–—:") or name


def buyable_lists(held):
    """Select held gear lists, then the standard Trading Post.

    Collection assignments also include skill sets, so filter by content family.
    Resolve the standard post within the default pack; same-named custom posts
    remain available only through their ordinary held-collection access.
    """
    from n26.library.models import Collection, Family, get_default_pack
    from n26.library.standard_content import TRADING_POST_COLLECTION

    held = list(held)
    buyable = set(
        Collection.objects.filter(pk__in=[c.pk for c in held])
        .containing(Family.GEAR)
        .values_list("pk", flat=True)
    )
    collections = [c for c in held if c.pk in buyable]
    post = Collection.objects.filter(
        name=TRADING_POST_COLLECTION, pack=get_default_pack()
    ).first()
    if post is not None:
        collections = [c for c in collections if c.pk != post.pk] + [post]
    return collections


def collection_tabs(collections, chosen):
    """Build collection tabs, shortening names unless that creates duplicate labels.

    Include the full name as a tooltip only when shortened.
    """
    labels = [_tab_label(collection) for collection in collections]
    if len(set(labels)) != len(labels):
        labels = [str(collection) for collection in collections]
    return [
        {
            "label": label,
            "title": "" if label == str(collection) else str(collection),
            "href": f"?list={collection.pk}",
            "current": chosen is not None and collection.pk == chosen.pk,
        }
        for label, collection in zip(labels, collections, strict=True)
    ]


@dataclass(frozen=True)
class Screen:
    """The shared card, budget and catalogue derivation for an equipment surface."""

    gang: object
    miniature: object | None
    card: object
    computed: object
    collections: list
    chosen: object | None
    view: object | None
    #: The personal allowance supplying activity and confirmation figures; absent for stash views.
    budget: object | None = None

    def host(self, at):
        """Resolve model or stash assignment roots using the supplied page URL."""
        from n26.core.owned import EquipHost

        if self.miniature is not None:
            return EquipHost.fighter(self.gang, self.card, self.miniature, at=at)
        return EquipHost.stash(self.gang, self.card, at=at)


def _screen(gang, miniature=None, list_param="", budgets=True, *, include_staged=False):
    """Derive the current equipment view for a model or the gang stash.

    A model view includes usability notes and an optional founding budget.
    ALL_SCOPE browses unrestricted gear priced through held lists. STASH_SCOPE
    shows only holdings on the gang screen. Apply staged-content access throughout.
    """
    from n26.core.access import collections_for, gang_collections, hidden_categories_for
    from n26.core.browse import (
        all_gear,
        browse,
        narrow,
        priced_from,
        usability_for,
        with_use_notes,
    )
    from n26.core.card import (
        build_card,
        build_gang_card,
        build_modifier_index,
        carriers,
    )
    from n26.core.effects import compute, compute_gang
    from n26.core.founding import budget_for

    def chosen_from(collections):
        """Choose the named held collection or the first available collection."""
        named = next((c for c in collections if str(c.pk) == list_param), None)
        return named or (collections[0] if collections else None)

    if miniature is not None:
        # Load option provenance for owned-copy controls and statlines for the displayed model card.
        card = build_card(miniature, with_statlines=True, with_options=True)
        index = build_modifier_index(carriers(card))
        computed = compute(card, index)
        # Load personal budgets only when needed; each collection determines whether it charges points.
        budget = budget_for(gang, miniature, computed) if budgets else None
        collections = buyable_lists(
            [
                access.collection
                for access in collections_for(miniature, card=card, computed=computed)
            ],
        )
        pricing_collections = collections
        # Tab order does not change which held list supplies an unrestricted price.
        collections = [c for c in collections if c.name != "Supplementary Pets"] + [
            c for c in collections if c.name == "Supplementary Pets"
        ]
        if list_param == ALL_SCOPE:
            # Price unrestricted gear through held collections and retain model usability notes.
            chosen = None
            view = priced_from(
                all_gear(
                    ALL_LABEL,
                    for_use_notes=True,
                    include_staged=include_staged,
                ),
                [
                    browse(collection, include_staged=include_staged)
                    for collection in pricing_collections
                ],
            )
        else:
            chosen = chosen_from(collections)
            view = (
                narrow(
                    browse(chosen, include_staged=include_staged),
                    exclude_categories=hidden_categories_for(chosen, computed),
                )
                if chosen is not None
                else None
            )
        if view is not None:
            view = with_use_notes(view, usability_for(computed))
        return Screen(
            gang, miniature, card, computed, collections, chosen, view, budget
        )

    card = build_gang_card(gang, with_statlines=False, with_options=True)
    index = build_modifier_index(carriers(card))
    computed = compute_gang(card, index)
    collections = buyable_lists(
        access.collection
        for access in gang_collections(gang, card=card, computed=computed)
    )
    if list_param == STASH_SCOPE:
        chosen, view = None, None
    elif list_param == ALL_SCOPE:
        chosen = None
        view = priced_from(
            all_gear(ALL_LABEL, include_staged=include_staged),
            [
                browse(collection, include_staged=include_staged)
                for collection in collections
            ],
        )
    else:
        chosen = chosen_from(collections)
        # Usability notes apply to models, not stashes.
        view = (
            browse(chosen, include_staged=include_staged)
            if chosen is not None
            else None
        )
    return Screen(gang, None, card, computed, collections, chosen, view)


def render_update(
    request,
    gang,
    key,
    *,
    miniature=None,
    list_param="",
    expanded_key="",
    at="",
    closed=False,
    also="",
):
    """Rebuild affected catalogue rows and shared panels after an equipment operation.

    Use the same _screen derivation as the page. Preserve at, expanded_key and
    list_param in returned controls. closed clears the confirmation panel;
    also identifies a second affected row on this screen. A missing owned-only
    row is removed when its final copy leaves.
    """
    from n26.core.listing import listing_row, owned_row, owned_row_manage_only
    from n26.core.owned import possessions
    from n26.core.views.owned import accessorise_dialogs

    founding_seen = may_see_founding(gang, request.user)
    screen = _screen(
        gang,
        miniature=miniature,
        list_param=list_param,
        budgets=founding_seen,
        include_staged=sees_staged(request.user),
    )
    host = screen.host(at)
    held = possessions(host)
    refunds = not gang.credits_unlimited

    def row_for(row_key):
        copies = held.get(row_key)
        expanded = row_key == expanded_key
        if screen.view is None:
            # Remove an owned-only row when the final copy leaves; catalogue rows retain their offer.
            return (
                owned_row_manage_only(
                    row_key, copies, refunds=refunds, expanded=expanded
                )
                if copies
                else None
            )
        line = next(
            (
                line
                for line in screen.view.all_lines()
                if _thing_key(line.thing) == row_key
            ),
            None,
        )
        if line is None:
            # Do not update catalogue keys this screen does not display.
            return None
        row = listing_row(line)
        return (
            owned_row(row, copies, refunds=refunds, expanded=expanded)
            if copies
            else row
        )

    rows = [(key, row_for(key))]
    if also and also != key:
        rows.append((also, row_for(also)))

    response = render(
        request,
        "n26/includes/equip_update.html",
        {
            "rows": rows,
            "gang": gang,
            **_card_context(request, screen, host, at=at),
            "trade_points_href": trade_points_href(gang, request.user),
            "credits_href": credits_href(gang, request.user),
            "held_label": host.held_label,
            "miniature": miniature,
            "founding_budget": screen.budget,
            "closed": closed,
            # Rebuild accessory panels because newly bought weapons need hosts and removed weapons must lose them.
            "accessorise": accessorise_dialogs(request, host),
        },
    )
    return with_toasts(request, response)


def carried_confirmation(request):
    """Detect a submission returned from a confirmation panel."""
    return bool(request.POST.get(CONFIRM_FIELD))


def render_confirmation(request, confirmation):
    """Render an htmx confirmation panel with queued toast messages."""
    response = render(
        request,
        "n26/includes/equip_overspend.html",
        {"confirmation": confirmation},
    )
    return with_toasts(request, response)


def _buy_clicked(
    request, gang, catalogue, *, scope, at="", event=None, activity_seen=None
):
    """Render shared purchase decisions using native messages and analytics."""
    from n26.core.equip_purchase import UnavailableEquipment, purchase

    try:
        result = purchase(
            gang,
            request.user,
            request.POST,
            catalogue,
            action=request.get_full_path(),
            back=at,
            activity_seen=activity_seen,
            identity={
                "holder": (event or {}).get("miniature_id", "stash"),
                "list": scope,
            },
        )
    except UnavailableEquipment as error:
        raise Http404(str(error)) from None
    if result.confirmation is not None:
        return result.confirmation
    if result.refused:
        messages.error(request, result.refused)
        return None
    purchase_feedback(request, result, event=event)
    return result.key


def purchase_feedback(request, result, *, event=None):
    """Emit success feedback once for a committed equipment purchase."""
    from n26.analytics import EventVerb, N26Noun, record

    if not result.replayed:
        record(
            request,
            N26Noun.ASSIGNMENT,
            EventVerb.CREATE,
            result.assignment,
            **result.facts,
            **(event or {}),
        )
    messages.success(request, result.message)


def _purchase_catalogue(request, gang, miniature, wanted):
    """Reload the offers and destination while the purchase holds the gang lock."""
    from n26.core.equip_purchase import PurchaseCatalogue
    from n26.core.models import Miniature

    if miniature is not None:
        miniature = Miniature.objects.select_related("membership").get(pk=miniature.pk)
    screen = _screen(
        gang,
        miniature=miniature,
        list_param=wanted,
        budgets=may_see_founding(gang, request.user),
        include_staged=sees_staged(request.user),
    )
    if wanted not in {"", ALL_SCOPE} and (
        screen.chosen is None or str(screen.chosen.pk) != wanted
    ):
        from n26.core.operations import Refusal

        raise Refusal("This equipment list has changed. Reload the page before buying.")
    return PurchaseCatalogue(
        holder=miniature if miniature is not None else gang.stash,
        view=screen.view,
        into=miniature.name if miniature is not None else "the stash",
        collection=ALL_LABEL
        if wanted == ALL_SCOPE
        else (screen.chosen.name if screen.chosen is not None else ""),
        budget=screen.budget,
    )


@login_required
@never_cache
def equip(request, pk):
    """Buy and manage equipment on an owned model's current catalogue.

    Keep collection, section and expanded-row state in navigation destinations.
    Use _buy_clicked for typed payment, optional parts and acquisition options.
    Each purchase is atomic, with paid weapon profiles hosted on that weapon.

    Build owned-copy controls from the same computed card as the catalogue.
    GET renders one React workflow. Retained native POSTs use the same purchase
    behaviour and support cached htmx forms.
    """
    from n26.core.views.choose import SHOW_DISMISSED, SHOWING, showing_dismissed
    from n26.core.views.equip_react import equipment_read

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.gang
    if request.method != "POST":
        if is_htmx(request):
            response = HttpResponse()
            response["HX-Redirect"] = request.get_full_path()
            return response
        return render(
            request,
            "n26/equip.html",
            {
                "miniature": miniature,
                "gang": gang,
                "equip_props": equipment_read(request, gang, miniature),
            },
        )

    wanted = request.GET.get("list", "")
    everything = wanted == ALL_SCOPE
    screen = _screen(
        gang,
        miniature=miniature,
        list_param=wanted,
        budgets=may_see_founding(gang, request.user),
        include_staged=sees_staged(request.user),
    )
    chosen = screen.chosen

    # Carry section state through POST and redirects; unknown tabs fall back in the picker.
    section = request.POST.get("section", request.GET.get("section", ""))[:100]
    expanded_key = request.POST.get("owned", request.GET.get("owned", ""))[:200]

    dismissed_shown = showing_dismissed(request.get_full_path())

    def here(collection):
        params = []
        if everything:
            params.append(("list", ALL_SCOPE))
        elif collection is not None:
            params.append(("list", collection.pk))
        if section:
            params.append(("section", section))
        if expanded_key:
            params.append(("owned", expanded_key))
        if dismissed_shown:
            params.append((SHOW_DISMISSED, SHOWING))
        return f"{request.path}?{urlencode(params)}" if params else request.path

    if request.method == "POST":
        hx = is_htmx(request)
        key = _buy_clicked(
            request,
            gang,
            lambda: _purchase_catalogue(request, gang, miniature, wanted),
            scope=wanted,
            at=here(chosen),
            event={"miniature_id": str(miniature.pk)},
            activity_seen=str(screen.budget.activity.pk)
            if screen.budget is not None
            else "",
        )
        if isinstance(key, Confirmation):
            if not hx:
                return render(
                    request,
                    "n26/confirm.html",
                    {"gang": gang, "confirmation": key},
                )
            return render_confirmation(request, key)
        if not hx:
            return redirect(here(chosen))
        if key is None:
            return no_update(request)
        return render_update(
            request,
            gang,
            key,
            miniature=miniature,
            list_param=wanted,
            expanded_key=expanded_key,
            at=here(chosen),
            closed=carried_confirmation(request),
        )

    return redirect(here(chosen))


def _card_context(request, screen, host, *, at):
    """Build linked model-card and action props from the screen's existing computation.

    Stash screens return no model-card context.
    """
    from n26.core.views.edit import action_panel_context, link_model_card

    if screen.miniature is None:
        return {}
    gang, miniature = screen.gang, screen.miniature
    return {
        **action_panel_context(miniature, screen.card, screen.computed),
        "card": link_model_card(
            gang, miniature, screen.card, screen.computed, host, back=at
        ),
        "status_href": (
            status_href(gang, miniature, back="edit")
            if may_mark_status(gang, request.user)
            else ""
        ),
    }


def picker_context(catalogue, view, gang=None, budget=None):
    """Build catalogue navigation, filter registrations and price ranges.

    Use browsed lines for price limits and only visible trade-point figures for
    that slider. A personal budget suppresses the no-open-visit notice.
    """
    sections = catalogue.sections if catalogue is not None else []
    lines = list(view.all_lines()) if view is not None else []
    trade_points = [
        line.trade_points
        for line in lines
        if line.shows_trade_points and line.trade_points is not None
    ]
    return {
        # A closed-post notice informs the owner but does not block purchasing.
        "post_is_shut": bool(
            gang is not None
            and budget is None
            and not gang.visiting_trading_post
            and any(line.charges_trade_points for line in lines)
        ),
        # Match filter registration keys, using section names for unnamed categories.
        # Deduplicate names shared across sections.
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
        # Include every rendered section in navigation so none becomes unreachable.
        "sections": [section.name for section in sections],
        "price_floor": min((line.credits for line in lines), default=0),
        "price_ceiling": max((line.credits for line in lines), default=0),
        "tp_ceiling": max(trade_points, default=0),
        "has_trade_points": bool(trade_points),
        # Expose the enforced server price ceiling as an input hint too.
        "price_cap": PRICE_CEILING,
    }


#: Reserved non-ULID query value for unrestricted gear browsing.
ALL_SCOPE = "all"

ALL_LABEL = "Unrestricted"

ALL_BROWSING = "all equipment"

#: Reserved query value for all stash holdings, including gear absent from the catalogue.
STASH_SCOPE = "stash"

STASH_LABEL = "In stash"


def library_tab(everything):
    """Build the unrestricted-library tab shared by model and stash catalogues."""
    return {
        "label": ALL_LABEL,
        "title": "",
        "href": f"?list={ALL_SCOPE}",
        "current": everything,
    }


def list_tabs(collections, chosen, everything):
    """Append unrestricted library browsing after held catalogue tabs."""
    tabs = collection_tabs(collections, chosen)
    tabs.append(library_tab(everything))
    return tabs


def gang_tabs(collections, chosen, everything, *, stash=False):
    """Prepend stash holdings to the catalogue and unrestricted-library tabs."""
    tabs = list_tabs(collections, chosen, everything)
    tabs.insert(
        0,
        {
            "label": STASH_LABEL,
            "title": "",
            "href": f"?list={STASH_SCOPE}",
            "current": stash,
        },
    )
    return tabs


@login_required
@never_cache
def equip_gang(request, pk):
    """Buy into the owned gang's stash and manage its stored possessions.

    The stash tab lists all stash holdings, including gear absent from held catalogues.
    ALL_SCOPE browses the unrestricted library. Stash listings omit model-specific usability notes.
    """

    from n26.core.views.equip_react import stash_read

    gang = _own_gang_or_404(request, pk)
    if request.method == "GET":
        if is_htmx(request):
            return HttpResponse(headers={"HX-Redirect": request.get_full_path()})
        return render(
            request,
            "n26/gang_equip.html",
            {"gang": gang, "equip_props": stash_read(request, gang)},
        )

    wanted = request.POST.get("list", request.GET.get("list", ""))
    stash_tab = wanted == STASH_SCOPE
    everything = wanted == ALL_SCOPE
    screen = _screen(gang, list_param=wanted, include_staged=sees_staged(request.user))
    chosen = screen.chosen

    section = request.POST.get("section", request.GET.get("section", ""))[:100]
    expanded_key = request.POST.get("owned", request.GET.get("owned", ""))[:200]

    params = []
    if stash_tab:
        params.append(("list", STASH_SCOPE))
    elif everything:
        params.append(("list", ALL_SCOPE))
    elif chosen is not None:
        params.append(("list", chosen.pk))
    if section:
        params.append(("section", section))
    if expanded_key:
        params.append(("owned", expanded_key))
    here = f"{request.path}?{urlencode(params)}" if params else request.path

    if request.method == "POST":
        hx = is_htmx(request)
        key = _buy_clicked(
            request,
            gang,
            lambda: _purchase_catalogue(request, gang, None, wanted),
            scope=wanted,
            at=here,
        )
        if isinstance(key, Confirmation):
            if not hx:
                return render(
                    request,
                    "n26/confirm.html",
                    {"gang": gang, "confirmation": key},
                )
            return render_confirmation(request, key)
        if not hx:
            return redirect(here)
        if key is None:
            return no_update(request)
        return render_update(
            request,
            gang,
            key,
            list_param=wanted,
            expanded_key=expanded_key,
            at=here,
            closed=carried_confirmation(request),
        )

    return render(
        request,
        "n26/gang_equip.html",
        {"gang": gang, "equip_props": stash_read(request, gang)},
    )
