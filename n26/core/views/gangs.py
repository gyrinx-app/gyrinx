"""Read gang dashboards and shared sheets, and manage owner-authorised gang actions."""

import json
from dataclasses import dataclass
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from n26.core.listing import DANGER, LINK, SECONDARY, Action
from n26.core.status import Status
from n26.core.status import explains as status_explains
from n26.core.views.changelog import CHANGELOG_TAG, changelog_entries
from n26.core.views.permissions import (
    _any_gang_or_404,
    _own_gang_or_404,
    credits_href,
    link_campaign,
    link_model_cards,
    may_mark_status,
    may_see_founding,
    own_address,
    trade_points_href,
)

GANGS_PER_PAGE = 25


#: Static application markup for the invitation indicator; it contains no user input.
CAMPAIGNS_WAITING = mark_safe(  # nosec B703 B308 - literal, no user input
    '<span aria-hidden="true" class="inline-block size-2 rounded-full'
    ' bg-accent align-middle"></span>'
)

#: Allowlisted dashboard tabs; unknown values fall back to Gangs.
DASHBOARD_TABS = ("Gangs", "Campaigns", "Content Packs")


@dataclass
class CampaignBudgetNotice:
    title: str
    lead: str
    budget: int | None
    variant: str
    show_budget_options: bool
    dismiss_signature: str


def _active_campaign_membership(gang):
    from n26.core.models import CampaignMembership

    return (
        CampaignMembership.objects.filter(
            gang=gang, left__isnull=True, campaign__archived=False
        )
        .select_related("campaign")
        .first()
    )


def _budget_notice_signature(gang, membership):
    # Invalidate the dismissed notice when membership or either budget changes.
    return [str(membership.pk), membership.campaign.budget, gang.starting_credits]


def _campaign_budget_notice(request, gang):
    from n26.core.campaigns import over_budget

    membership = _active_campaign_membership(gang)
    if membership is None:
        return None
    if request.session.get(
        f"n26-budget-dismissed-{gang.pk}"
    ) == _budget_notice_signature(gang, membership):
        return None
    dismiss_signature = json.dumps(_budget_notice_signature(gang, membership))
    if gang.credits_unlimited:
        return CampaignBudgetNotice(
            "Unlimited credits",
            "This gang currently has unlimited credits. Set a budget using the options below:",
            membership.campaign.budget,
            "info",
            True,
            dismiss_signature,
        )
    if over_budget(membership.campaign, gang):
        return CampaignBudgetNotice(
            "Above campaign budget",
            f"This gang's rating ({gang.rating}¢), stash ({gang.stash_rating}¢) "
            f"and credits ({gang.credits}¢) total {gang.wealth}¢. "
            f"The campaign budget is {membership.campaign.budget}¢.",
            membership.campaign.budget,
            "warning",
            False,
            dismiss_signature,
        )
    return None


@login_required
def dashboard(request):
    """Show the signed-in user's gangs, campaigns, invitations and N26 release notes.

    Use the shared gang-table context; submitted search goes to the gangs page.
    """
    from n26.core.models import Campaign
    from n26.core.views.campaigns import campaign_rows, invitations_for

    campaigns = campaign_rows(
        Campaign.objects.involving(request.user)
        .filter(archived=False)
        .select_related("owner", "owner__profile", "campaign_type")
        .prefetch_related("owner__badge_grants")
        .order_by("name", "pk"),
    )
    invitations = list(invitations_for(request.user))
    tab = request.GET.get("tab", "Gangs")

    return render(
        request,
        "n26/dashboard.html",
        {
            **_record_table_context(request),
            "changelog": changelog_entries()[:5],
            "changelog_tag": CHANGELOG_TAG,
            "campaigns": campaigns,
            "invitations": invitations,
            "waiting_invitations": len(invitations),
            "campaigns_mark": CAMPAIGNS_WAITING if invitations else "",
            "dashboard_tab": tab if tab in DASHBOARD_TABS else "Gangs",
        },
    )


@login_required
def gangs(request):
    """List the viewer's gangs, or all live gangs when everyone is requested."""
    return render(
        request,
        "n26/gangs.html",
        _record_table_context(
            request,
            everyone=bool(request.GET.get("everyone")),
            per_page=GANGS_PER_PAGE,
        ),
    )


def _record_table_context(request, everyone=False, per_page=None):
    """Build gang-table rows, facets and optional pagination under URL search state.

    Search name and type through the platform search_queryset helper. Annotate
    live roster counts and expose campaign links only for campaigns involving
    the viewer. Without per_page, return the complete matching list.
    """
    from gyrinx.querysets import search_queryset
    from n26.core.models import Campaign, CampaignMembership, Gang, Miniature

    query = request.GET.get("q", "").strip()
    listed = Gang.objects.filter(archived=False)
    if not everyone:
        listed = listed.filter(owner=request.user)
    # Count active, non-dead members, including pets and vehicles, through a correlated
    # subquery rather than aggregating all gangs in a join.
    living = (
        Miniature.objects.filter(
            membership__gang=OuterRef("pk"), membership__archived=False
        )
        .exclude(status=Status.DEAD)
        .order_by()
        .values("membership__gang")
        .annotate(count=Count("pk"))
        .values("count")
    )
    listed = (
        listed.select_related("gang_type", "stash", "owner")
        .annotate(model_count=Coalesce(Subquery(living), 0))
        .order_by("name")
    )
    found = search_queryset(listed, query, ["name", "gang_type__name"])
    total = None
    pages = None
    if per_page is not None:
        page = Paginator(found, per_page).get_page(request.GET.get("page"))
        total = page.paginator.count
        pages = _pages(request, page) if page.paginator.num_pages > 1 else None
        found = page.object_list
    found = list(found)
    # Expose campaign links only for campaigns the viewer runs or has joined.
    campaigns = {}
    if found:
        campaigns = {
            membership.gang_id: membership.campaign
            for membership in CampaignMembership.objects.filter(
                gang__in=found,
                left__isnull=True,
                campaign__in=Campaign.objects.involving(request.user).filter(
                    archived=False
                ),
            ).select_related("campaign")
        }
    for row in found:
        campaign = campaigns.get(row.pk)
        row.campaign_name = campaign.name if campaign else ""
        row.campaign_href = (
            reverse("n26-campaign", args=[campaign.pk]) if campaign else ""
        )
    return {
        "gangs": found,
        "query": query,
        "listed": len(found),
        "total": total,
        "pages": pages,
        "show_owners": everyone,
        "everyone": everyone,
        "mine_only": not everyone,
        "gang_type_options": [
            {"value": name, "label": name}
            for name in dict.fromkeys(str(gang.gang_type) for gang in found)
        ],
    }


def _pages(request, page):
    """Build elided pagination links while preserving every other query parameter."""

    def address(number):
        asked = request.GET.copy()
        asked["page"] = number
        return f"?{asked.urlencode()}"

    numbers = []
    for number in page.paginator.get_elided_page_range(page.number):
        if number == page.paginator.ELLIPSIS:
            numbers.append({"elided": True})
        else:
            numbers.append(
                {
                    "elided": False,
                    "label": number,
                    "href": address(number),
                    "current": number == page.number,
                }
            )
    return {
        "numbers": numbers,
        "previous": address(page.previous_page_number()) if page.has_previous() else "",
        "next": address(page.next_page_number()) if page.has_next() else "",
        "number": page.number,
        "of": page.paginator.num_pages,
    }


def gang_sheet(request, pk):
    """Render a public live-gang sheet with management controls for its owner.

    Derive the gang and link displayed facts to permitted actions. Hide dismissed
    offers for every reader. Signed-in non-owners retain read, print and clone
    navigation but receive no owner equipment or status controls.

    URL parameters select one confirmation; owner htmx status requests can return
    only that panel. Common card and stash links use already-derived identities.
    """
    from django.template.response import TemplateResponse

    from n26.core.activities import activities_square, founding_blocks_visit
    from n26.core.card import build_gang_card
    from n26.core.owned import DIALOGS, EquipHost, with_query
    from n26.core.render import render_gang
    from n26.core.views.choose import link_slots, settle_dismissed
    from n26.core.views.htmx import is_htmx
    from n26.core.views.owned import link_counters, link_stash_actions, owned_dialog
    from n26.core.views.skills import link_skills

    gang = _any_gang_or_404(request, pk)
    yours = gang.owner_id == getattr(request.user, "id", None)
    at = reverse("n26-gang", args=[gang.pk])
    # Use the fixed back=edit destination rather than accepting a submitted status URL.
    status_back = "edit" if request.GET.get("back") == "edit" else ""
    may_mark = may_mark_status(gang, request.user)
    if may_mark and request.method == "GET" and is_htmx(request):
        marking = _marking(request, gang)
        ransoming = None if marking else _ransoming(request, gang)
        if marking or ransoming:
            response = render(
                request,
                "n26/includes/status_dialogs.html",
                {
                    "gang": gang,
                    "marking": marking,
                    "ransoming": ransoming,
                    "redrawn": True,
                    "status_back": status_back,
                    "status_cancel_url": _status_cancel_url(
                        gang, marking or ransoming, status_back
                    ),
                },
            )
            if not status_back:
                response["HX-Replace-Url"] = request.get_full_path()
            return response
    card = build_gang_card(gang)
    # Require authentication as well as matching ownership, including ownerless gangs.
    signed_in_owner = may_see_founding(gang, request.user)
    # Compute founding details only for an authenticated owner.
    # Keep owner copies separate for assignment-specific menus; other viewers can collapse repeats.
    sheet = render_gang(
        gang, card=card, for_owner=signed_in_owner, collapse_repeats=not yours
    )
    link_model_cards(gang, sheet.models, request.user)
    dialog = None
    link_campaign(sheet.campaign, request.user)
    budget_notice = (
        _campaign_budget_notice(request, gang)
        if signed_in_owner and sheet.campaign is not None
        else None
    )
    link_owners(sheet)
    # Hide dismissed choices with one shared read; restoration controls belong on Edit pages.
    settle_dismissed(
        gang,
        hide_only=(sheet, *sheet.models, *sheet.dead),
    )
    if yours:
        from n26.core.action_flow import available_action_names
        from n26.core.counter_tracking import is_active as counter_tracking_is_active

        action_names = available_action_names(
            gang, sheet.models, counter_tracking_active=counter_tracking_is_active()
        )
        for model in sheet.models:
            model.action_names = action_names.get(model.id, ())
            if (
                model.hire_time_state is not None
                and model.hire_time_state.act != "reopen"
            ):
                label = (
                    "Continue hire-time TP"
                    if model.hire_time_state.act == "finish"
                    else "Spend hire-time TP"
                )
                model.action_names += (label,)
        link_slots(
            gang,
            sheet,
            *sheet.models,
            back=at,
            dismiss_back=at,
        )
        link_skills(*sheet.models)
        host = EquipHost.stash(gang, card, at=at)
        link_stash_actions(
            sheet, at, refunds=not gang.credits_unlimited, bound_items=host.bound_items
        )
        if sheet.campaign:
            link_counters(sheet.campaign, back=at, adjust=True)
            for choice in sheet.campaign.choices:
                if choice.href and not choice.holding_name:
                    choice.href = with_query(choice.href, dialog="campaign")
    # Give departure confirmation priority so only one modal opens.
    leaving = _leaving(request, gang) if yours else None
    renaming = None if leaving or not yours else _renaming(request, gang)
    marking = None if leaving or renaming or not may_mark else _marking(request, gang)
    ransoming = (
        None
        if leaving or renaming or marking or not may_mark
        else _ransoming(request, gang)
    )
    if (
        yours
        and not leaving
        and not renaming
        and not marking
        and not ransoming
        and any(request.GET.get(kind) for kind in DIALOGS)
    ):
        dialog = owned_dialog(request, host)
    return TemplateResponse(
        request,
        "n26/gang_sheet.html",
        {
            "gang": gang,
            "sheet": sheet,
            "yours": yours,
            "trade_points_href": trade_points_href(gang, request.user),
            "credits_href": credits_href(gang, request.user),
            "founding_blocks_visit": founding_blocks_visit(gang, signed_in_owner),
            "activities_square": (
                activities_square(
                    gang,
                    sheet,
                    founding_at=reverse("n26-gang-founding-action", args=[gang.pk]),
                    visit_at=reverse("n26-gang-trade-points", args=[gang.pk]),
                    history_at=reverse("n26-gang-history", args=[gang.pk]),
                    clean_house_at=reverse("n26-clean-house", args=[gang.pk])
                    if may_mark
                    else "",
                    ransoms=tuple(
                        (model.name, f"{at}?ransom={model.id}")
                        for model in sheet.models
                        if may_mark and model.status == Status.RANSOMED
                    ),
                    post_battle_at=reverse("n26-gang-post-battle", args=[gang.pk]),
                )
                if signed_in_owner
                else None
            ),
            "may_print": request.user.is_authenticated,
            "more_actions": more_actions(
                gang, yours=yours, signed_in=request.user.is_authenticated
            ),
            "card_mode": "gang" if yours else "view",
            "renaming": renaming,
            "leaving": leaving,
            "marking": marking,
            "ransoming": ransoming,
            "may_mark": may_mark,
            "status_back": status_back,
            "status_cancel_url": _status_cancel_url(
                gang, marking or ransoming, status_back
            ),
            "dialog": dialog,
            "budget_notice": budget_notice,
        },
    )


def more_actions(gang, *, yours, signed_in):
    """Build whole-gang navigation for the viewer's access level.

    Owners receive management and read links, with Delete last. Signed-in readers
    receive Notes, Lore and Clone; anonymous readers receive no menu.
    """

    def link(label, route, tone=SECONDARY):
        return Action(label, LINK, reverse(route, args=[gang.pk]), tone)

    if yours:
        return [
            link("History", "n26-gang-history"),
            link("Other actions", "n26-gang-other-actions"),
            link("Notes", "n26-gang-notes"),
            link("Lore", "n26-gang-lore"),
            link("Clone gang", "n26-clone-gang"),
            link("Delete gang", "n26-delete-gang", DANGER),
        ]
    if signed_in:
        return [
            link("Notes", "n26-gang-notes"),
            link("Lore", "n26-gang-lore"),
            link("Clone gang", "n26-clone-gang"),
        ]
    return []


@dataclass(frozen=True)
class Marking:
    """A model status confirmation with choices and kit-disposal defaults."""

    miniature: object
    current: str
    choices: tuple
    stashable: bool
    kit_lost_by_default: bool
    kit_stashed: bool


def _marking(request, gang):
    """Build status choices for a named live gang member, including vehicle labels."""
    from n26.core.operations import refund_of
    from n26.core.status import label_for

    miniature = _fighter_named(request, gang, "status")
    if miniature is None:
        return None
    profile = miniature.membership.profile
    vehicle = profile.profile_type.name == "Vehicle"
    lost = vehicle or _kit_is_lost_on_death(profile)
    return Marking(
        miniature=miniature,
        current=miniature.status,
        choices=tuple(
            (
                value,
                label_for(value, vehicle),
                status_explains(value, vehicle),
                value == miniature.status,
            )
            for value in Status.values
        ),
        stashable=any(refund_of(root)[1] > 0 for root in _kit_roots(miniature)),
        kit_lost_by_default=lost,
        kit_stashed=not lost,
    )


@dataclass(frozen=True)
class Ransoming:
    """Ransom confirmation data with eligible payees, available credits and allowed amounts."""

    miniature: object
    payees: tuple
    credits: object
    amounts: tuple = tuple(range(10, 70, 10))


def _payees(gang):
    """List other active gangs in the same campaign as eligible in-app ransom recipients.

    An empty list still permits payment to a recipient outside the app.
    """
    from n26.core.models import CampaignMembership

    membership = (
        CampaignMembership.objects.filter(gang=gang, left__isnull=True)
        .select_related("campaign")
        .first()
    )
    if membership is None:
        return ()
    return tuple(
        (str(other.gang_id), other.gang.name)
        for other in CampaignMembership.objects.filter(
            campaign=membership.campaign, left__isnull=True
        )
        .exclude(gang=gang)
        .select_related("gang")
        .order_by("gang__name")
    )


def _ransoming(request, gang):
    """Build a ransom dialog only for a named live member currently held for ransom."""
    from n26.core.status import Status

    miniature = _fighter_named(request, gang, "ransom")
    if miniature is None or miniature.status != Status.RANSOMED:
        return None
    return Ransoming(
        miniature=miniature,
        payees=_payees(gang),
        credits=None if gang.credits_unlimited else gang.credits,
    )


def _status_cancel_url(gang, asking, back):
    """Return a status dialog to Edit when requested, otherwise to the gang sheet."""
    if back == "edit" and asking is not None:
        return reverse("n26-edit-fighter", args=[asking.miniature.pk])
    return reverse("n26-gang", args=[gang.pk])


def _kit_is_lost_on_death(profile):
    """Read Brute and Hanger-on built-ins to determine the default kit-loss choice."""
    from n26.library.models import Subtype

    if profile.built_ins_id is None:
        return False
    return any(
        isinstance(member.assignable, Subtype)
        and member.assignable.name in {"Brute", "Hanger-on"}
        for member in profile.built_ins.members.all()
    )


def _renaming(request, gang):
    """Resolve the named live gang member for a rename dialog, or return None."""
    return _fighter_named(request, gang, "rename")


MODEL_ANCHOR = "#model-"


def link_owners(sheet):
    """Link pet-owner labels only when the referenced card appears on this sheet.

    Preserve names without anchors when the owner's card is absent.
    """
    cards = [*sheet.models, *sheet.dead]
    drawn = {card.id for card in cards}
    for card in cards:
        if card.owned_by_id in drawn:
            card.owner_href = f"{MODEL_ANCHOR}{card.owned_by_id}"


def _fighter_named(request, gang, param):
    """Resolve a query-named live member, returning None for malformed, missing or unrelated IDs."""
    from django.core.exceptions import ValidationError

    from n26.core.models import Miniature

    named = request.GET.get(param)
    if not named:
        return None
    try:
        return Miniature.objects.select_related("membership").get(
            pk=named, membership__gang=gang, membership__archived=False
        )
    except Miniature.DoesNotExist, ValidationError:
        return None


def _kit_roots(miniature):
    """Load live top-level equipment assignments carried by this model."""
    from n26.core.models import Assignment

    return list(
        Assignment.objects.filter(
            miniature=miniature, parent__isnull=True, archived=False
        ).select_related("ledger_entry")
    )


def _leaving(request, gang):
    """Build delete or refund confirmation from the shared departure calculation.

    Show complete and stash-first returns, including founding trade points.
    Unlimited-credit gangs with no refundable points use deletion wording.
    """
    from n26.core.departure import departure_for
    from n26.core.operations import Refusal
    from n26.core.views.owned import refund_words

    for kind in ("delete", "refund"):
        miniature = _fighter_named(request, gang, kind)
        if miniature is not None:
            break
    else:
        return None

    try:
        departure = departure_for(miniature)
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return None
    full_paid, full_points = departure.refund
    fighter_paid, fighter_points = departure.stash_refund
    # Use deletion wording when an unlimited-credit departure returns no founding points.
    if kind == "refund" and gang.starting_credits is None and not full_points:
        kind = "delete"

    return {
        "kind": kind,
        "miniature": miniature,
        "purchase": (
            str(departure.anchor.assignable)
            if departure.anchor.pk != miniature.membership_id
            else ""
        ),
        "models": ", ".join(model.name for model in departure.models),
        # Read refunds before archiving because archived assignments are excluded from refund totals.
        "full_returned": refund_words(gang, full_paid, full_points),
        "stash_label": _stash_label(gang, kind, fighter_paid, fighter_points),
        "stashable": bool(departure.stashable),
    }


def _stash_label(gang, kind, paid, trade_points):
    """Name the stash-first departure option and any remaining refundable payment."""
    from n26.core.views.owned import refund_words, refunded_credits

    if kind != "refund":
        return "Stash their kit, then delete"
    if refunded_credits(gang, paid) or trade_points:
        return f"Stash kit, refund {refund_words(gang, paid, trade_points)}"
    return "Stash their kit, then refund"


@login_required
def delete_fighter(request, pk):
    """Remove the model through its shared departure flow without refunding payment."""
    return _dismiss(request, pk, kind="delete")


@login_required
def refund_fighter(request, pk):
    """Refund the model through its shared departure flow using recorded payments."""
    return _dismiss(request, pk, kind="refund")


def _dismiss(request, pk, kind):
    """Perform a confirmed departure using its current purchase roots.

    GET redirects to confirmation. Under the gang lock, recalculate departure,
    optionally stash paid equipment and then remove or refund the remaining roots.
    Any refusal rolls back the entire move and departure.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.departure import departure_for
    from n26.core.operations import Refusal, operation
    from n26.core.views.owned import refund_words, refunded_credits
    from n26.core.views.permissions import _own_miniature_or_404

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.gang
    sheet_url = reverse("n26-gang", args=[gang.pk])
    if request.method != "POST":
        return redirect(f"{sheet_url}?{kind}={miniature.pk}")

    was = miniature.name
    stash_kit = request.POST.get("kit") == "stash"
    try:
        with operation(gang, actor=request.user) as op:
            # Recalculate the purchase scope under the gang lock before departure.
            miniature.refresh_from_db()
            departure = departure_for(miniature)
            moved = 0
            if stash_kit:
                for root in departure.stashable:
                    op.move(root, gang.stash, note=f"{was} left it behind")
                    moved += 1
                departure = departure_for(miniature)
            # Read refunds before archiving because archived assignments are excluded from refund totals.
            paid_back = points_back = 0
            if (
                kind == "refund"
                and gang.starting_credits is None
                and not departure.refund[1]
            ):
                kind = "delete"
            if kind == "refund":
                paid_back, points_back = departure.refund
            act = op.refund if kind == "refund" else op.remove
            for root in departure.roots:
                act(root)
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return redirect(sheet_url)

    record(
        request,
        N26Noun.MODEL,
        EventVerb.DELETE,
        miniature,
        kind=kind,
        kit="stash" if stash_kit else "with",
        refunded=paid_back,
        trade_points=points_back,
    )
    stashed = f" Their kit is in the stash ({moved} line{'s' if moved != 1 else ''})."
    # Calculate the final refund after stashing gear, whose payments remain with the gang.
    if kind == "refund" and (refunded_credits(gang, paid_back) or points_back):
        messages.success(
            request,
            f"Refunded {was} — {refund_words(gang, paid_back, points_back)} back."
            + (stashed if moved else ""),
        )
    else:
        messages.success(request, f"Deleted {was}." + (stashed if moved else ""))
    return redirect(sheet_url)


@login_required
def mark_fighter(request, pk):
    """Set an owned model's status through an operation.

    GET opens confirmation. On death, a submitted kit choice can move paid gear
    to the stash or remove it. Validate status against the declared values.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal, operation, refund_of
    from n26.core.status import Status
    from n26.core.views.permissions import _own_miniature_or_404

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.membership.gang
    if not may_mark_status(gang, request.user):
        raise Http404("Setting a status by hand is not open here.")
    sheet_url = reverse("n26-gang", args=[gang.pk])
    back_url = _back_url(request, miniature, sheet_url)
    if request.method != "POST":
        return redirect(f"{sheet_url}?status={miniature.pk}")
    try:
        status = Status(request.POST.get("status", ""))
    except ValueError:
        messages.error(request, "Select a status from the list.")
        return redirect(f"{sheet_url}?status={miniature.pk}")
    kit = request.POST.get("kit", "")
    try:
        with operation(gang, actor=request.user) as op:
            if status == Status.DEAD and kit in {"stash", "lost"}:
                for root in _kit_roots(miniature):
                    if refund_of(root)[1] <= 0:
                        continue
                    if kit == "stash":
                        op.move(root, gang.stash, note=f"{miniature.name} died")
                    else:
                        op.remove(root, note=f"lost with {miniature.name}")
            op.set_status(miniature, status)
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return redirect(back_url)
    record(request, N26Noun.MODEL, EventVerb.UPDATE, miniature, status=status, kit=kit)
    messages.success(request, f"{miniature.name} is now {status_label_for(miniature)}.")
    return redirect(back_url)


def _back_url(request, miniature, sheet_url):
    """Select the model edit page only for back=edit; otherwise use the fixed gang sheet."""
    if request.GET.get("back") == "edit":
        return reverse("n26-edit-fighter", args=[miniature.pk])
    return sheet_url


def status_label_for(miniature):
    from n26.core.status import label_for

    profile = miniature.membership.profile
    return label_for(miniature.status, profile.profile_type.name == "Vehicle")


@login_required
def pay_ransom(request, pk):
    """Pay a validated ransom and mark Recovery, or mark an unpaid model Dead.

    Limit in-app payees to other campaign gangs and amounts to the offered values.
    Lock payer and payee together and recheck ransom status before transferring.
    Unpaid departures stash paid equipment; refusal rolls back the transaction.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.models import Gang
    from n26.core.operations import Refusal, operation, refund_of
    from n26.core.status import Status
    from n26.core.views.permissions import _own_miniature_or_404

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.membership.gang
    if not may_mark_status(gang, request.user):
        raise Http404("Paying a ransom is not open here.")
    sheet_url = reverse("n26-gang", args=[gang.pk])
    back_url = _back_url(request, miniature, sheet_url)
    if request.method != "POST":
        return redirect(f"{sheet_url}?ransom={miniature.pk}")
    if miniature.status != Status.RANSOMED:
        messages.error(request, f"{miniature.name} is not held for ransom.")
        return redirect(back_url)

    outcome = request.POST.get("outcome", "")
    try:
        credits = to = None
        if outcome == "paid":
            # Validate offered ransom amounts and same-campaign recipients before writing another gang's ledger.
            try:
                credits = int(request.POST.get("credits", ""))
            except ValueError:
                credits = None
            if credits not in Ransoming.amounts:
                raise Refusal("Select what the ransom came to.")
            payee = request.POST.get("to", "")
            if payee:
                if payee not in {pk for pk, _ in _payees(gang)}:
                    raise Refusal("Select who was paid from the list.")
                to = Gang.objects.get(pk=payee)
        # Lock payer and payee together, then recheck ransom status to prevent duplicate payment.
        with operation(gang, actor=request.user, also=[to]) as op:
            miniature.refresh_from_db(fields=["status"])
            if miniature.status != Status.RANSOMED:
                raise Refusal(f"{miniature.name} is not held for ransom.")
            if outcome == "paid":
                op.transfer(
                    to, credits, note=f"ransom for {miniature.name}", about=miniature
                )
                op.set_status(miniature, Status.RECOVERY, note="Ransom paid")
            elif outcome == "unpaid":
                # Unpaid-ransom kit goes to the stash independently of ordinary death defaults.
                for root in _kit_roots(miniature):
                    if refund_of(root)[1] > 0:
                        op.move(root, gang.stash, note=f"{miniature.name} died")
                op.set_status(miniature, Status.DEAD, note="Ransom not paid")
            else:
                raise Refusal("Say whether the ransom was paid.")
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return redirect(f"{sheet_url}?ransom={miniature.pk}")
    record(request, N26Noun.MODEL, EventVerb.UPDATE, miniature, ransom=outcome)
    if outcome == "paid":
        messages.success(
            request, f"Ransom paid. {miniature.name} is back, In Recovery."
        )
    else:
        messages.success(request, f"{miniature.name} is now Dead.")
    return redirect(back_url)


@login_required
def clean_house(request, pk):
    """Clear Recovery statuses through an owner-authorised operation and report affected models."""
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import operation

    gang = _own_gang_or_404(request, pk)
    if not may_mark_status(gang, request.user):
        raise Http404("Clean House is not open here.")
    sheet_url = reverse("n26-gang", args=[gang.pk])
    if request.method != "POST":
        return redirect(sheet_url)
    with operation(gang, actor=request.user) as op:
        cleared = op.clean_house()
    record(request, N26Noun.GANG, EventVerb.UPDATE, gang, cleaned_house=len(cleared))
    if cleared:
        messages.success(
            request,
            f"Cleaned house: {len(cleared)} models are back from Recovery."
            if len(cleared) > 1
            else f"Cleaned house: {cleared[0].name} is back from Recovery.",
        )
    else:
        messages.info(request, "No models were In Recovery.")
    return redirect(sheet_url)


@login_required
def rename_fighter(request, pk):
    """Rename an owned model through an operation, recording the previous name.

    GET opens confirmation. Retain validated Edit-page navigation state and return
    htmx dialog or saved-header partials when requested from that surface.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.forms import RenameFighterForm
    from n26.core.operations import operation
    from n26.core.views.edit import dialog_url, request_edit_dialog_addresses
    from n26.core.views.htmx import is_htmx, with_toasts
    from n26.core.views.permissions import _own_miniature_or_404

    miniature = _own_miniature_or_404(request, pk)
    # Rebuild allowed Edit-page return state; the gang sheet remains a fixed destination.
    if request.GET.get("back") == "edit":
        addresses = request_edit_dialog_addresses(request, miniature)
        back_url = addresses.back
    else:
        back_url = reverse("n26-gang", args=[miniature.membership.gang_id])
    partial = request.GET.get("back") == "edit" and is_htmx(request)
    form = RenameFighterForm(
        request.POST if request.method == "POST" else None,
        initial={"name": miniature.name},
    )
    if partial and (request.method != "POST" or not form.is_valid()):
        response = render(
            request,
            "n26/includes/rename_dialog.html",
            {
                "rename_dialog": rename_dialog_props(request, miniature, form),
                "oob": True,
            },
        )
        response["HX-Replace-Url"] = dialog_url(back_url, rename=miniature.pk)
        return response
    if request.method != "POST":
        return redirect(dialog_url(back_url, rename=miniature.pk))

    if not form.is_valid():
        messages.error(request, "A model needs a name.")
        return redirect(dialog_url(back_url, rename=miniature.pk))

    was = miniature.name
    name = form.cleaned_data["name"]
    if name != was:
        with operation(miniature.membership.gang, actor=request.user) as op:
            op.rename(miniature, name)
        record(request, N26Noun.MODEL, EventVerb.UPDATE, miniature, renamed_from=was)
        messages.success(request, f"Renamed {was} to {miniature.name}.")
    if partial:
        from n26.core.navigation import fighter_switcher
        from n26.core.rating import read_rating_receipt
        from n26.core.render import roster, summarise_roster

        response = render(
            request,
            "n26/includes/rename_saved.html",
            {
                "miniature": miniature,
                "gang": miniature.gang,
                "summary": summarise_roster(roster(miniature.gang)),
                "fighter_switcher": fighter_switcher(
                    miniature.gang, miniature, route="n26-edit-fighter"
                ),
                "rating_href": addresses.rating,
                "rating_breakdown": read_rating_receipt(miniature).popover_props(
                    miniature.name
                ),
                "rename_href": addresses.rename,
                "trade_points_href": trade_points_href(miniature.gang, request.user),
                "credits_href": credits_href(miniature.gang, request.user),
                "profile_name": str(miniature.membership.profile)
                if miniature.membership.profile
                else "",
            },
        )
        response["HX-Replace-Url"] = back_url
        return with_toasts(request, response)
    return redirect(back_url)


def rename_dialog_props(request, miniature, form=None):
    """The owner's name draft, with server validation and fixed destinations."""
    from django.middleware.csrf import get_token

    from n26.core.forms import RenameFighterForm
    from n26.core.views.edit import request_edit_dialog_addresses

    form = (
        form
        if form is not None
        else RenameFighterForm(initial={"name": miniature.name})
    )
    addresses = request_edit_dialog_addresses(request, miniature)
    return {
        "name": miniature.name,
        "value": str(form["name"].value() or ""),
        "errors": list(form["name"].errors),
        "actionUrl": addresses.rename,
        "cancelUrl": addresses.back,
        "csrfToken": get_token(request),
        "returnFocusId": f"n26-name-pencil-{miniature.pk}",
    }


@login_required
def create_gang(request):
    """Create a gang and its founding assignment in one transaction.

    Validate gang-type staging access and the starting budget. After founding,
    show only gang-hosted arrival questions before opening the new sheet.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.arrivals import onward
    from n26.core.forms import CreateGangForm
    from n26.core.models import Gang
    from n26.core.operations import operation
    from n26.core.render import GANG_SLOT_HOST
    from n26.library.staged import sees_staged

    # Use the same staged-type access in initial choices and submitted form validation.
    shown = sees_staged(request.user)
    if request.method == "POST":
        form = CreateGangForm(request.POST, include_staged=shown)
        if form.is_valid():
            from django.db import transaction

            from n26.write_pause import write_guard

            budget = form.cleaned_data["starting_credits"]
            gang_type = form.cleaned_data["gang_type"]
            if budget is None:
                budget = gang_type.starting_credits
            with transaction.atomic(), write_guard():
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
            # Record analytics after the founding transaction succeeds.
            record(
                request,
                N26Noun.GANG,
                EventVerb.CREATE,
                gang,
                gang_type=gang_type.name,
                starting_credits=budget,
            )
            messages.success(request, f"Founded {gang.name}.")
            # Route founding through gang-hosted interstitials only.
            # Model questions belong to the acquisition that introduces each model.
            return redirect(
                onward(
                    request,
                    gang,
                    op,
                    reverse("n26-gang", args=[gang.pk]),
                    hosts={GANG_SLOT_HOST},
                )
            )
    else:
        form = CreateGangForm(include_staged=shown)

    return render(
        request,
        "n26/create_gang.html",
        {"form": form, "gang_types": form.gang_type_choices()},
    )


def _written_page(request, pk, *, field, template):
    """Render shared gang and model writing with owner-only editing links.

    Omit models without writing or an image.
    """
    from n26.core.render import roster, summarise_roster

    gang = _any_gang_or_404(request, pk)
    yours = gang.owner_id == getattr(request.user, "id", None)
    members = roster(gang)
    entries = [
        {
            "name": model.name,
            "profile": (
                str(model.membership.profile)
                if model.membership
                and model.membership.profile
                and str(model.membership.profile) != model.name
                else ""
            ),
            "prose": getattr(model, field),
            "image_url": model.image.url if model.image else "",
            "edit_url": reverse("n26-edit-fighter", args=[model.pk]) if yours else "",
        }
        for model in members
        if getattr(model, field) or model.image
    ]
    return render(
        request,
        template,
        {
            "gang": gang,
            "gang_prose": getattr(gang, field),
            "gang_image_url": gang.image.url if gang.image else "",
            "entries": entries,
            "yours": yours,
            "summary": summarise_roster(members),
            "trade_points_href": trade_points_href(gang, request.user),
            "credits_href": credits_href(gang, request.user),
        },
    )


def gang_lore(request, pk):
    """Render public gang and model lore using the shared writing-page builder."""
    return _written_page(request, pk, field="lore", template="n26/gang_lore.html")


def gang_notes(request, pk):
    """Render public gang and model notes using the shared writing-page builder."""
    return _written_page(request, pk, field="notes", template="n26/gang_notes.html")


@login_required
@require_POST
def use_campaign_budget(request, pk):
    """Start tracking this owner's unlimited gang against its campaign budget."""
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.campaigns import campaign_operation
    from n26.core.operations import NotEnoughCredits, operation

    gang = _own_gang_or_404(request, pk)
    membership = _active_campaign_membership(gang)
    if membership is None or membership.campaign.budget is None:
        raise Http404("No campaign budget")
    if not gang.credits_unlimited:
        return redirect("n26-gang", pk=gang.pk)
    try:
        # Acquire campaign locks before the gang lock.
        with campaign_operation(membership.campaign, actor=request.user):
            with operation(gang, actor=request.user) as op:
                current = _active_campaign_membership(gang)
                if (
                    current is None
                    or current.pk != membership.pk
                    or current.campaign.budget is None
                ):
                    raise Http404("No campaign budget")
                # Recheck unlimited status and campaign budget under lock to avoid resetting established credits.
                if not gang.credits_unlimited:
                    return redirect("n26-gang", pk=gang.pk)
                op.set_budget(current.campaign.budget)
    except NotEnoughCredits as refusal:
        messages.error(request, str(refusal))
        return redirect("n26-gang", pk=gang.pk)
    record(
        request,
        N26Noun.GANG,
        EventVerb.UPDATE,
        gang,
        starting_credits=gang.starting_credits,
    )
    messages.success(request, f"Credits budget set to {gang.starting_credits}¢.")
    return redirect("n26-gang", pk=gang.pk)


@login_required
@require_POST
def dismiss_campaign_budget(request, pk):
    """Hide this owner's budget prompt for this session and these budgets."""
    gang = _own_gang_or_404(request, pk)
    membership = _active_campaign_membership(gang)
    if membership is None:
        raise Http404("No active campaign")
    signature = _budget_notice_signature(gang, membership)
    if request.POST.get("notice_signature") == json.dumps(signature):
        request.session[f"n26-budget-dismissed-{gang.pk}"] = signature
    return redirect("n26-gang", pk=gang.pk)


@login_required
def edit_gang(request, pk):
    """Edit an owned gang's name, presentation, budget, writing and image.

    The type remains fixed. Record name, budget and writing through operations;
    colour uses a plain save. Reconcile budget changes and refresh the instance
    after rollback. Notes and lore save separately without replacing live editors.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.forms import EditGangForm, GangLoreForm, GangNotesForm, PictureForm
    from n26.core.images import LANDSCAPE, MAX_PX
    from n26.core.operations import NotEnoughCredits, operation
    from n26.core.views.htmx import stay_or_redirect

    gang = _own_gang_or_404(request, pk)
    at = reverse("n26-edit-gang", args=[gang.pk])
    tab = request.GET.get("tab", "general")
    if tab not in {"general", "notes", "dismissed"}:
        tab = "general"
    if request.method == "POST" and request.POST.get("act") == "picture":
        form = PictureForm(request.POST, request.FILES, ratio=LANDSCAPE)
        if form.is_valid():
            new_picture = bool(form.cleaned_data["image"])
            dropped_picture = (
                form.cleaned_data["remove_image"]
                and bool(gang.image)
                and not new_picture
            )
            with operation(gang, actor=request.user) as op:
                op.set_gang_image(
                    form.cleaned_data["image"],
                    clear=form.cleaned_data["remove_image"],
                )
            record(
                request,
                N26Noun.GANG,
                EventVerb.UPDATE,
                gang,
                image=new_picture or dropped_picture,
            )
            if new_picture:
                messages.success(request, "Picture saved.")
            elif dropped_picture:
                messages.success(request, "Picture removed.")
            else:
                messages.success(request, "Nothing changed.")
        else:
            for wrong in form.errors.get("image", []):
                messages.error(request, wrong)
        return redirect(f"{at}?tab=notes")
    elif request.method == "POST" and request.POST.get("act") == "notes":
        form = GangNotesForm(request.POST)
        if form.is_valid():
            with operation(gang, actor=request.user) as op:
                op.edit_gang_notes(form.cleaned_data["notes"])
            record(request, N26Noun.GANG, EventVerb.UPDATE, gang, notes=True)
            messages.success(request, "Notes saved.")
        return stay_or_redirect(request, f"{at}?tab=notes")
    elif request.method == "POST" and request.POST.get("act") == "lore":
        form = GangLoreForm(request.POST)
        if form.is_valid():
            with operation(gang, actor=request.user) as op:
                op.edit_gang_lore(form.cleaned_data["lore"])
            record(request, N26Noun.GANG, EventVerb.UPDATE, gang, lore=True)
            messages.success(request, "Lore saved.")
        return stay_or_redirect(request, f"{at}?tab=notes")
    elif request.method == "POST" and not request.POST.get("act"):
        form = EditGangForm(gang, request.POST)
        if form.is_valid():
            try:
                with operation(gang, actor=request.user) as op:
                    # Name and budget changes record history through operations; colour is a presentation save.
                    op.rename_gang(form.cleaned_data["name"])
                    op.set_budget(form.cleaned_data["starting_credits"])
                    gang.colour = form.cleaned_data["colour"]
                    gang.save(update_fields=["colour", "modified"])
                    op.settle()
            except NotEnoughCredits as refusal:
                # Reject budgets incompatible with recorded spending.
                # Refresh the rolled-back instance before rendering so unsaved figures do not appear.
                gang.refresh_from_db()
                form.add_error("starting_credits", str(refusal))
            else:
                record(
                    request,
                    N26Noun.GANG,
                    EventVerb.UPDATE,
                    gang,
                    starting_credits=gang.starting_credits,
                )
                messages.success(request, f"Saved {gang.name}.")
                return redirect("n26-gang", pk=gang.pk)
    elif tab in {"notes", "dismissed"}:
        form = None
    else:
        form = EditGangForm(
            gang,
            initial={
                "name": gang.name,
                "starting_credits": gang.starting_credits,
                "colour": gang.colour,
            },
        )

    # Display failed general saves on their own tab; writing forms return separately.
    if request.method == "POST":
        tab = "general"

    return render(
        request,
        "n26/edit_gang.html",
        {
            "gang": gang,
            "form": form,
            "notes_form": GangNotesForm(initial={"notes": gang.notes}),
            "lore_form": GangLoreForm(initial={"lore": gang.lore}),
            "wealth": gang.wealth,
            "tab": tab,
            # Share crop constants between server processing and browser controls.
            "picture_shape": LANDSCAPE,
            "picture_max": MAX_PX,
            "picture_url": gang.image.url if gang.image else "",
            "edit_tabs": _edit_tabs(gang, tab),
            "dismissed_choices": (
                _dismissed_gang_choices(gang) if tab == "dismissed" else []
            ),
        },
    )


#: Bound manually entered visit points before storage.
TRADE_POINT_CEILING = 999


def _brought(data, ticked):
    """Use an explicit bounded trade-point amount when supplied, otherwise the selected-model total.

    Zero is explicit. Raise ValueError for non-digits or values above the ceiling.
    """
    typed = (data.get("brought") or "").strip()
    if not typed:
        return ticked
    if not typed.isdigit() or int(typed) > TRADE_POINT_CEILING:
        raise ValueError(typed)
    return int(typed)


def _trade_points_form(offered, offer, amount_label, empty_message):
    """Build visit-selection props with each model's contribution and an optional total override."""
    points = {visitor.key: visitor.trade_points for visitor in offered}
    return {
        "amountLabel": amount_label,
        "amountDescription": "Optional. Replaces the selected models' total."
        if offered
        else "",
        "emptyMessage": empty_message,
        "groups": [
            {
                "name": group.name,
                "options": [
                    {
                        "key": option.key,
                        "name": option.name,
                        "points": points[option.key],
                    }
                    for option in group.options
                ],
            }
            for group in offer.groups
        ],
    }


def _start_help(offered):
    """Describe the available model-selection or amount-only visit form."""
    if offered:
        return "Select models to add their Trade Points, or enter the total yourself."
    return "Enter the Trade Points available for this visit."


def _the_trading_post():
    """Resolve the standard Trading Post in the default pack, excluding same-named custom posts."""
    from n26.library.models import Collection, get_default_pack
    from n26.library.standard_content import TRADING_POST_COLLECTION

    return Collection.objects.filter(
        name=TRADING_POST_COLLECTION, pack=get_default_pack()
    ).first()


def _dismissed_gang_choices(gang):
    """The gang's live dismissed choices, without loading its models or stash."""
    from n26.core.card import (
        build_gang_cards,
        build_modifier_index,
        carriers,
        held_assets,
    )
    from n26.core.effects import compute
    from n26.core.models import DismissedOffer
    from n26.core.render import GANG_SLOT_HOST, choice_lines, hide_dismissed_choices

    card = build_gang_cards([gang], {gang.pk: held_assets(gang)})[gang.pk]
    computed = compute(card, build_modifier_index(carriers(card)))
    choices = choice_lines(computed, host=GANG_SLOT_HOST)
    dismissed = []
    hide_dismissed_choices(DismissedOffer.keys_for(gang), choices, removed=dismissed)
    for line in dismissed:
        line.restore_href = reverse("n26-restore-offer", args=[gang.pk, line.key])
    return dismissed


def _edit_tabs(gang, current):
    """Build gang edit navigation, showing Trade Points only when relevant or already open."""
    at = reverse("n26-edit-gang", args=[gang.pk])
    tabs = [
        {"label": "General", "href": at, "current": current == "general"},
        {
            "label": "Notes and Lore",
            "href": f"{at}?tab=notes",
            "current": current == "notes",
        },
        {
            "label": "Trade Points",
            "href": reverse("n26-gang-trade-points", args=[gang.pk]),
            "current": current == "trade-points",
        },
        {
            "label": "Dismissed choices",
            "href": f"{at}?tab=dismissed",
            "current": current == "dismissed",
        },
    ]

    from n26.core.built_in_actions import trading_post_visit_relevant

    if (
        current != "trade-points"
        and not trading_post_visit_relevant(gang)
        and not gang.visiting_trading_post
    ):
        tabs = [tab for tab in tabs if tab["label"] != "Trade Points"]
    return tabs


@login_required
def gang_other_actions(request, pk):
    from n26.core.built_in_actions import trading_post_visit_relevant

    gang = _own_gang_or_404(request, pk)
    return render(
        request,
        "n26/other_actions.html",
        {
            "gang": gang,
            "visit_excluded": not trading_post_visit_relevant(gang),
        },
    )


@login_required
def gang_trade_points(request, pk):
    """Start or finish the gang's Visit Trading Post activity through operations.

    Starting uses selected models' points or an explicit bounded amount, including
    zero. Reject an empty unconfigured visit and a second open visit. Completing
    discards unspent points. Purchases separately confirm permitted overspending.

    Reuse roster and contribution reads for the picker; read any existing receipt
    separately from its recorded attendance and spending.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.activities import founding_card, visit_card
    from n26.core.models import Activity
    from n26.core.operations import Refusal, operation
    from n26.core.render import roster
    from n26.core.trading import (
        as_offer,
        computed_members,
        minted,
        receipt_for,
        visitors,
    )

    gang = _own_gang_or_404(request, pk)
    from n26.core.built_in_actions import trading_post_visit_relevant

    visit_excluded = not trading_post_visit_relevant(gang)
    at = reverse("n26-gang-trade-points", args=[gang.pk])

    if request.method == "POST" and request.POST.get("act") == "finish":
        if gang.visiting_trading_post:
            left = gang.trade_points_left
            with operation(gang, actor=request.user) as op:
                op.leave_trading_post()
            record(request, N26Noun.GANG, EventVerb.UPDATE, gang, trade_points=None)
            if left == 1:
                lost = " 1 unspent Trade Point was discarded."
            elif left > 0:
                lost = f" {left} unspent Trade Points were discarded."
            else:
                lost = ""
            messages.success(request, f"{gang.name} left the Trading Post.{lost}")
        return redirect(at)

    if request.method == "POST":
        # Do not replace an open visit or silently discard its remaining points.
        if gang.visiting_trading_post:
            messages.error(
                request,
                "Complete the open Visit Trading Post action before starting another.",
            )
            return redirect(at)
        # Resolve visiting model keys only against this gang's current roster.
        going = visitors(gang, set(request.POST.getlist("visiting")))
        performing = [visitor for visitor in going if visitor.visiting]
        typed = (request.POST.get("brought") or "").strip()
        if not performing and not typed:
            messages.error(
                request,
                "Select at least one model to visit the Trading Post, or "
                "enter a Trade Point amount.",
            )
            return redirect(at)
        try:
            brought = _brought(request.POST, minted(performing))
        except ValueError:
            messages.error(
                request,
                "Trade Points are a whole number, from 0 to 999.",
            )
            return redirect(at)
        try:
            with operation(gang, actor=request.user) as op:
                op.visit_trading_post(going, brought=brought)
        except Refusal as refused:
            messages.error(request, str(refused))
            return redirect(at)
        record(request, N26Noun.GANG, EventVerb.UPDATE, gang, trade_points=brought)
        if performing:
            who = (
                f"{len(performing)} model{'' if len(performing) == 1 else 's'} "
                f"visited the Trading Post, adding "
            )
        else:
            who = f"{gang.name} visited the Trading Post, adding "
        messages.success(
            request,
            f"{who}{brought} Trade Point{'' if brought == 1 else 's'}.",
        )
        return redirect(at)

    # Reuse one roster read for the displayed models and contribution offer.
    members = roster(gang)
    completed = gang.founding_completed_at()
    founding_at = ""
    reopen_founding = False
    computed = None
    if may_see_founding(gang, request.user):
        founding_at = (
            reverse("n26-gang-founding-action", args=[gang.pk])
            + "?"
            + urlencode({"return_url": at})
        )
        if completed is not None and gang.open_activity(Activity.Kind.FOUNDING) is None:
            computed = computed_members(gang)
            from n26.core.founding import original_models_have_grants

            reopen_founding = original_models_have_grants(
                completed, computed, models=members
            )
    offered = visitors(gang, going=set(), members=members, computed=computed)
    offer = as_offer(offered)
    receipt = receipt_for(gang)
    amount_label = "Custom TP amount" if offered else "Trade Points"
    return render(
        request,
        "n26/trade_points.html",
        {
            "visit_excluded": visit_excluded,
            "gang": gang,
            "action": at,
            "post": _the_trading_post(),
            "visit_card": visit_card(receipt, at) if receipt else None,
            "founding_card": founding_card(gang, founding_at) if founding_at else None,
            "start_founding": founding_at
            if completed is None and not gang.visiting_trading_post
            else "",
            "reopen_founding": founding_at if reopen_founding else "",
            "founding_activity": gang.latest_founding_activity()
            if reopen_founding
            else None,
            "visitors": offered,
            "start_help": _start_help(offered),
            "amount_label": amount_label,
            "trade_points_form": _trade_points_form(
                offered,
                offer,
                amount_label,
                f"No model in {gang.name} adds Trade Points.",
            ),
            # Visit points belong to the gang and can be spent on models beyond its performers.
            "roster": members,
            "offer": offer,
            "edit_tabs": _edit_tabs(gang, "trade-points"),
        },
    )


@login_required
def gang_founding_action(request, pk):
    """Start, reopen or complete founding trade-point activity under the gang lock.

    Validate expected activity identifiers for completion and reopening.
    Reopening requires completed founding with original grants still available.
    Repeated starts of an already open activity change nothing. GET only redirects.
    Report operation refusals, including budget reconciliation, on the source page.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.models import Activity
    from n26.core.operations import Refusal, operation

    gang = _own_gang_or_404(request, pk)
    if not may_see_founding(gang, request.user):
        raise Http404
    at = own_address(
        request, request.POST.get("return_url") or request.GET.get("return_url")
    ) or reverse("n26-gang", args=[gang.pk])
    if request.method != "POST":
        return redirect(at)

    kind = Activity.Kind.FOUNDING
    label = kind.label
    act = request.POST.get("act")

    if act == "finish":
        try:
            with operation(gang, actor=request.user) as op:
                open_now = gang.open_activity(kind)
                expected = request.POST.get("activity")
                if open_now is not None and str(open_now.pk) != expected:
                    raise Refusal(
                        "This action has changed. Reload the page before completing it."
                    )
                closed = op.close_activity(open_now) if open_now is not None else None
        except Refusal as refused:
            messages.error(request, str(refused))
            return redirect(at)
        if closed is not None:
            record(
                request, N26Noun.GANG, EventVerb.UPDATE, gang, action=kind, act="finish"
            )
            messages.success(request, f"Completed the {label} action.")
        return redirect(at)

    if act in ("start", "reopen"):
        try:
            with operation(gang, actor=request.user) as op:
                completed = gang.founding_completed_at()
                if (completed is not None) != (act == "reopen"):
                    raise Refusal(
                        "Founding is complete. Reopen the action from Trade Points to use the remaining points."
                    )
                if act == "reopen":
                    previous = gang.latest_founding_activity()
                    if previous is None or str(previous.pk) != request.POST.get(
                        "activity"
                    ):
                        raise Refusal(
                            "This action has changed. Reload the page before reopening it."
                        )
                if gang.open_activity(kind) is not None:
                    return redirect(at)
                if act == "reopen":
                    from n26.core.founding import original_models_have_grants
                    from n26.core.render import roster
                    from n26.core.trading import computed_members

                    if not original_models_have_grants(
                        completed, computed_members(gang), models=roster(gang)
                    ):
                        raise Refusal(
                            "This action has changed. Reload the page before reopening it."
                        )
                op.open_activity(kind)
        except Refusal as refused:
            messages.error(request, str(refused))
            return redirect(at)
        record(request, N26Noun.GANG, EventVerb.UPDATE, gang, action=kind, act=act)
        verb = "Reopened" if act == "reopen" else "Started"
        messages.success(request, f"{verb} the {label} action.")
    return redirect(at)


@login_required
def delete_gang(request, pk):
    """Confirm and archive an owned gang while preserving assignments and ledger history.

    POST removes active campaign membership and returns campaign assets within
    the archive transaction. GET shows the live roster count and active campaign
    before confirmation.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.campaigns import archive_gang
    from n26.core.models import CampaignMembership, Miniature

    gang = _own_gang_or_404(request, pk)
    playing = (
        CampaignMembership.objects.filter(gang=gang, left__isnull=True)
        .select_related("campaign")
        .first()
    )
    if request.method == "POST":
        archive_gang(gang, actor=request.user)
        record(request, N26Noun.GANG, EventVerb.DELETE, gang)
        messages.success(request, f"Deleted {gang.name}.")
        return redirect("n26-gangs")

    return render(
        request,
        "n26/delete_gang.html",
        {
            "gang": gang,
            "campaign": playing.campaign if playing else None,
            # Count only live memberships in the archive confirmation.
            "roster": Miniature.objects.filter(
                membership__gang=gang, membership__archived=False
            ).count(),
        },
    )
