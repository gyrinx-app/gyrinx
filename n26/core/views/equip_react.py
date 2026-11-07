"""Complete gang-stash equipment reads and narrowly scoped JSON commands."""

from urllib.parse import urlencode
from uuid import uuid4

from django.contrib import messages
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from n26.core.equip_display import (
    catalogue_data,
    choices_data,
    confirmation_data,
    dialog_data,
)
from n26.core.equip_purchase import UnavailableEquipment, purchase
from n26.core.hire_display import figures_data
from n26.core.owned import DIALOGS, possessions
from n26.core.owned_actions import change
from n26.core.views.equip import (
    ALL_SCOPE,
    STASH_LABEL,
    STASH_SCOPE,
    _purchase_catalogue,
    _screen,
    gang_tabs,
    picker_context,
    purchase_feedback,
)
from n26.core.views.owned import accessorise_dialogs, owned_dialog, owned_feedback
from n26.core.views.permissions import (
    _own_gang_or_404,
    credits_href,
    may_see_founding,
    trade_points_href,
)
from n26.library.staged import sees_staged


def stash_read(request, gang):
    """Build the same initial and refreshed equipment display for this owner."""
    from n26.core.activities import founding_blocks_visit
    from n26.core.browse import offered_choices
    from n26.core.listing import build_catalogue, build_stash_catalogue
    from n26.core.people import person_link
    from n26.core.render import roster, summarise_roster

    data = request.POST if request.method == "POST" else request.GET
    wanted = data.get("list", "")[:100]
    section = data.get("section", "")[:100]
    expanded = data.get("owned", "")[:200]
    screen = _screen(gang, list_param=wanted, include_staged=sees_staged(request.user))
    scope = (
        wanted
        if wanted in {STASH_SCOPE, ALL_SCOPE}
        else str(screen.chosen.pk)
        if screen.chosen
        else ""
    )
    path = reverse("n26-equip-gang", args=[gang.pk])
    params = {"list": scope, "section": section, "owned": expanded}
    back = (
        path + "?" + urlencode({key: value for key, value in params.items() if value})
    )
    host = screen.host(back)
    held = possessions(host)
    if scope == STASH_SCOPE:
        catalogue = build_stash_catalogue(
            held, STASH_LABEL, refunds=not gang.credits_unlimited, expanded_key=expanded
        )
    elif screen.view is not None:
        catalogue = build_catalogue(
            screen.view, held, refunds=not gang.credits_unlimited, expanded_key=expanded
        )
    else:
        catalogue = None
    picker = picker_context(catalogue, screen.view, gang)
    named_kind, named_key = next(
        ((kind, request.GET[kind]) for kind in DIALOGS if request.GET.get(kind)),
        ("", ""),
    )
    panel = owned_dialog(request, host)
    accessories = accessorise_dialogs(request, host)
    if named_kind == "accessorise":
        panel = next((panel for panel in accessories if panel["id"] == named_key), None)
    choices = None
    if panel is not None and named_kind == "rechoose":
        from n26.core.views.owned import _held

        assignment = _held(host, named_key)
        if assignment is not None:
            taken = {
                option.default_set_id for option in assignment.chosen_options.all()
            }
            choices = choices_data(offered_choices(assignment.assignable), taken=taken)
    badges = {}
    owner = person_link(gang.owner, badges)
    owner["badge"] = badges.get(owner.get("badge"))
    points_href = trade_points_href(gang, request.user)
    return {
        "gangName": gang.name,
        "gangHref": reverse("n26-gang", args=[gang.pk]),
        "owner": owner,
        "scope": scope,
        "scopeLabel": STASH_LABEL
        if scope == STASH_SCOPE
        else "all equipment"
        if scope == ALL_SCOPE
        else str(screen.chosen or "equipment"),
        "scopeTabs": [
            {**tab, "key": tab["href"].partition("list=")[2]}
            for tab in gang_tabs(
                screen.collections,
                screen.chosen,
                scope == ALL_SCOPE,
                stash=scope == STASH_SCOPE,
            )
        ],
        "section": section,
        "owned": expanded,
        "listingHref": back,
        "sections": catalogue_data(catalogue, screen.view),
        "categories": picker["categories"],
        "categoryOptions": [option["label"] for option in picker["category_options"]],
        "priceFloor": picker["price_floor"],
        "priceCeiling": picker["price_ceiling"],
        "tradePointsCeiling": picker["tp_ceiling"],
        "hasTradePoints": picker["has_trade_points"],
        "postIsShut": picker["post_is_shut"],
        "foundingBlocksVisit": founding_blocks_visit(
            gang, may_see_founding(gang, request.user)
        )
        if picker["post_is_shut"]
        else False,
        "tradePointsHref": points_href,
        "visitingTradingPost": gang.visiting_trading_post,
        "figures": figures_data(
            gang,
            summarise_roster(roster(gang)),
            trade_points_href=points_href,
            credits_href=credits_href(gang, request.user),
        ),
        "dialog": dialog_data(panel, named_key, choices=choices),
        "messages": [
            {
                "text": str(message),
                "tone": message.level_tag
                if message.level_tag in {"success", "error", "warning"}
                else "info",
            }
            for message in messages.get_messages(request)
        ],
        "requestKey": str(uuid4()),
        "csrfToken": get_token(request),
        "action": back,
        "displayHref": reverse("n26-equip-stash-display", args=[gang.pk]),
        "commandHref": reverse("n26-equip-stash-command", args=[gang.pk]),
        "recoveryKey": f"equip-stash:{request.user.pk}:{gang.pk}",
        "signInHref": reverse("account_login")
        + "?"
        + urlencode(
            {
                "next": back
                + (
                    "&" + urlencode({named_kind: named_key})
                    if panel is not None
                    else ""
                )
            }
        ),
    }


@never_cache
@require_GET
def stash_display(request, pk):
    """Refresh the catalogue and URL-selected owned-item panel for the gang owner."""
    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "Sign in again to view this equipment."}, status=401
        )
    gang = _own_gang_or_404(request, pk)
    return JsonResponse({"page": stash_read(request, gang)})


@never_cache
@require_POST
def stash_command(request, pk):
    """Apply one retry-safe equipment command through the native domain path."""
    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "Sign in again to change this equipment."}, status=401
        )
    gang = _own_gang_or_404(request, pk)
    data = request.POST
    action = data.get("action", "")
    try:
        if action == "buy":
            wanted = data.get("list", "")
            result = purchase(
                gang,
                request.user,
                data,
                lambda: _purchase_catalogue(request, gang, None, wanted),
                action=reverse("n26-equip-gang", args=[gang.pk]),
                back=reverse("n26-equip-gang", args=[gang.pk]),
                identity={"holder": "stash", "list": wanted},
                require_key=True,
            )
        elif action in {
            "sell",
            "refund",
            "remove",
            "reassign",
            "rechoose",
            "accessorise",
        }:
            result = change(
                gang,
                request.user,
                action,
                data.get("assignment", ""),
                data,
                include_staged=sees_staged(request.user),
                require_key=True,
            )
        else:
            raise UnavailableEquipment("Choose an equipment action again.")
    except UnavailableEquipment as error:
        return JsonResponse({"errors": {"__all__": [str(error)]}}, status=422)
    if result.refused:
        gang = _own_gang_or_404(request, pk)
        return JsonResponse(
            {
                "errors": {"__all__": [result.refused]},
                "page": stash_read(request, gang),
            },
            status=409 if result.conflict else 422,
        )
    question = result.confirmation if action == "buy" else None
    if question is None:
        if action == "buy":
            purchase_feedback(request, result)
        else:
            owned_feedback(request, result)
    gang = _own_gang_or_404(request, pk)
    return JsonResponse(
        {
            "outcome": "confirmation" if question is not None else "completed",
            "requestKey": data["request_key"],
            "confirmation": confirmation_data(question)
            if question is not None
            else None,
            "page": stash_read(request, gang),
        }
    )
