"""Resolve computed choices and record picks, rolls and dismissal state.

Assignment choice URLs identify the displayed card, carrier assignment and
offer. Status follow-ups add a status revision. Recompute the card to resolve
each address; removed carriers or changed revisions invalidate it.

Holding choices identify the holding, ownership revision and slot.
Lock affected campaigns before the gang, matching ownership operations.

Single-pick choices replace their existing pick. Multi-pick choices add or
remove one result per submission without evicting another pick when full.
Rolls are recorded before selection and scoped to the same card and choice.
"""

from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

# Preserve the chooser import surface while native card and asset callers migrate.
from n26.core.choice_workflow import (
    NotOnTheList as NotOnTheList,
)
from n26.core.choice_workflow import (
    _campaign_label_or_404 as _campaign_label_or_404,
)
from n26.core.choice_workflow import (
    _Found as _Found,
)
from n26.core.choice_workflow import (
    _host as _host,
)
from n26.core.choice_workflow import (
    _pick_of as _pick_of,
)
from n26.core.choice_workflow import (
    _roll_at as _roll_at,
)
from n26.core.choice_workflow import (
    _roll_result as _roll_result,
)
from n26.core.choice_workflow import (
    _roll_table as _roll_table,
)
from n26.core.choice_workflow import (
    _settled as _settled,
)
from n26.core.choice_workflow import (
    choice_operation as choice_operation,
)
from n26.core.choice_workflow import (
    find_slot as find_slot,
)
from n26.core.choice_workflow import (
    find_slots as find_slots,
)
from n26.core.owned import with_query
from n26.core.views.permissions import _own_gang_or_404, own_address

#: URL state requesting dismissed offers and their restoration controls.
SHOW_DISMISSED = "dismissed"
SHOWING = "show"


def showing_dismissed(url):
    """Read dismissed-choice display state from an explicit source URL.

    Partial redraw requests may use an operation URL rather than the page URL.
    """
    from urllib.parse import parse_qs, urlsplit

    query = parse_qs(urlsplit(url).query)
    return SHOWING in query.get(SHOW_DISMISSED, [])


def settle_dismissed(gang, *holders, hide_only=()):
    """Read dismissal keys once for all holders.

    Move model choices into their dismissed list; hide_only holders receive no
    restoration controls.
    """
    from n26.core.models import DismissedOffer
    from n26.core.render import hide_dismissed

    keys = DismissedOffer.keys_for(gang)
    for holder in holders:
        hide_dismissed(keys, holder, removed=holder.dismissed_choices)
    for holder in hide_only:
        hide_dismissed(keys, holder)


def link_slots(gang, *holders, back="", dismiss_back=None):
    """Link all addressable questions to their picker and permitted dismissal actions.

    Use the supplied source-page back destination rather than an operation request
    path. dismiss_back can independently choose where dismissal controls return.
    Preview questions without keys remain unlinked.
    """
    from n26.core.owned import with_query
    from n26.core.status import Status

    if dismiss_back is None:
        dismiss_back = back
    for holder in holders:
        # Dead models retain picker links but receive no dismissal or restoration controls.
        dead = getattr(holder, "status", None) == Status.DEAD
        for line in [*holder.questions, *getattr(holder, "dismissed_choices", ())]:
            if not line.key:
                continue
            if line.is_full and not line.is_resolved:
                # Zero-capacity choices remain plain facts; resolved choices keep links for editing.
                continue
            line.href = reverse("n26-choose", args=[gang.pk, line.key])
            if back:
                line.href = with_query(line.href, **{"return": back})
            if dead:
                continue
            # Add dismissal controls only to eligible unresolved, non-full owner questions.
            # Dismissed questions offer restoration instead.
            line.back = dismiss_back
            if not line.allow_dismissal:
                continue
            if line.dismissed:
                line.restore_href = with_query(
                    reverse("n26-restore-offer", args=[gang.pk, line.key]),
                    request_key=uuid4(),
                )
            elif not line.is_resolved and not line.is_full:
                line.dismiss_href = with_query(
                    reverse("n26-dismiss-offer", args=[gang.pk, line.key]),
                    request_key=uuid4(),
                )


def _choice_addresses(request, gang, slot):
    returning = (
        request.POST.get("returning", request.POST.get("return", ""))
        if request.method == "POST"
        else request.GET.get("return", "")
    )
    returning = own_address(request, returning)
    back = returning or reverse("n26-gang", args=[gang.pk])
    here = reverse("n26-choose", args=[gang.pk, slot])
    if returning:
        here = with_query(here, **{"return": returning})
    if request.GET.get("dialog") == "campaign":
        here = with_query(here, dialog="campaign")
    return here, back, returning


def _choice_feedback(request, gang, result):
    from n26.analytics import EventVerb, N26Noun, record

    if not result.replayed:
        choices = result.facts.get("choices", [result.facts])
        for facts in choices:
            intent = facts.get("action")
            if intent in {"choose", "remove", "none"}:
                verb = (
                    EventVerb.ARCHIVE
                    if intent in {"remove", "none"}
                    else EventVerb.CONFIRM
                )
                record(
                    request,
                    N26Noun.CHOICE,
                    verb,
                    gang,
                    offer=facts["offer"],
                    picked=facts["picked"],
                )
            elif intent in {"roll", "enter"}:
                record(
                    request,
                    N26Noun.CHOICE,
                    EventVerb.UPDATE,
                    gang,
                    offer=facts["offer"],
                    action="roll",
                    entered=facts["entered"],
                )
            elif intent == "dismiss":
                record(
                    request,
                    N26Noun.CHOICE,
                    EventVerb.ARCHIVE,
                    gang,
                    offer=facts["offer"],
                    action="dismiss",
                )
            elif intent == "restore":
                record(
                    request,
                    N26Noun.CHOICE,
                    EventVerb.RESTORE,
                    gang,
                    offer=facts["offer"],
                )
    if result.message:
        message = result.message
        if result.replayed and result.facts.get("action") in {"dismiss", "restore"}:
            action = (
                "dismissal" if result.facts["action"] == "dismiss" else "restoration"
            )
            message = f"This {action} was already saved. Review the current choice on the Edit page."
        elif result.replayed:
            message = (
                "These choices were already saved. No new change was made."
                if "choices" in result.facts
                else "This choice was already saved. No new change was made."
            )
        tag = f"computed-choice-{result.form.cleaned_data['request_key']}"
        storage = messages.get_messages(request)
        retained = list(storage)
        queued = any(tag in (item.extra_tags or "").split() for item in retained)
        storage.used = False
        if result.replayed and queued:
            for item in retained:
                if tag in (item.extra_tags or "").split():
                    item.message = message
            # Persist the historical replacement without adding a second tagged message.
            storage.added_new = True
        elif not queued:
            messages.success(request, message, extra_tags=tag)


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def choose(request, pk, slot):
    """Only the current gang owner may inspect or resolve a computed choice."""
    from n26.core import choice_display, choice_workflow
    from n26.core.action_records import battle_action_for_slot

    gang = _own_gang_or_404(request, pk)
    here, back, returning = _choice_addresses(request, gang, slot)
    result = None
    if request.method == "POST":
        result = choice_workflow.change(
            gang,
            request.user,
            slot,
            request.POST,
            here=here,
            back=back,
            campaign_dialog=request.GET.get("dialog") == "campaign",
        )
        if result.saved:
            _choice_feedback(request, gang, result)
            return redirect(result.next_url)
        if "roll" in result.form.errors:
            raise Http404("No such roll")
        if not result.terminal and "request_key" not in result.form.errors:
            for errors in result.form.errors.values():
                for message in errors:
                    messages.error(request, message)
            return redirect(here)
    try:
        found = find_slot(gang, slot)
    except Http404:
        if not (result and result.terminal) and request.GET.get("recover") != "1":
            raise
        found = None
    if found:
        battle_action = battle_action_for_slot(found.anchor)
        if battle_action is not None:
            return redirect(
                "n26-action-flow",
                pk=battle_action.fighter_id,
                record_id=battle_action.pk,
                step="resume",
            )
        if request.GET.get("dialog") == "campaign":
            _campaign_label_or_404(gang, found)
    form = result.form if result else choice_workflow.initial(found)
    context = {"gang": gang}
    props = choice_display.picker(
        request,
        gang,
        slot,
        found,
        form=form,
        here=here,
        back=back,
        returning=returning,
        terminal=bool(result and result.terminal),
        context=context,
    )
    template = (
        "n26/includes/campaign_label_dialog.html"
        if props["dialog"]
        else "n26/choose.html"
    )
    context["choice_props"] = props
    response = render(
        request,
        template,
        context,
        status=409 if result and result.terminal else 422 if result else 200,
    )
    if props["dialog"]:
        response["HX-Replace-Url"] = here
    return response


@never_cache
@require_POST
def choose_command(request, pk, slot):
    """Resolve native and React commands through the same locked workflow."""
    from urllib.parse import parse_qs, urlsplit

    from n26.core import choice_display, choice_workflow

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in again to save this choice."}, status=401)
    gang = _own_gang_or_404(request, pk)
    here, back, returning = _choice_addresses(request, gang, slot)
    result = choice_workflow.change(
        gang,
        request.user,
        slot,
        request.POST,
        here=here,
        back=back,
        campaign_dialog=request.GET.get("dialog") == "campaign",
    )
    if result.saved:
        _choice_feedback(request, gang, result)
        if (
            request.GET.get("dialog") == "campaign"
            and request.GET.get("display") == "dialog"
            and urlsplit(result.next_url).path == urlsplit(here).path
        ):
            try:
                found = find_slot(gang, slot)
                _campaign_label_or_404(gang, found)
                page = choice_display.picker(
                    request,
                    gang,
                    slot,
                    found,
                    form=choice_workflow.initial(found),
                    here=here,
                    back=back,
                    returning=returning,
                    dialog=True,
                    roll_key=parse_qs(urlsplit(result.next_url).query).get(
                        "roll", [""]
                    )[0],
                )
            except Http404:
                return JsonResponse({"nextUrl": back})
            return JsonResponse({"nextUrl": result.next_url, "page": page})
        return JsonResponse({"nextUrl": result.next_url})
    if result.terminal:
        return JsonResponse(
            {"code": "choice_unavailable", "errors": dict(result.form.errors)},
            status=409,
        )
    return JsonResponse({"errors": dict(result.form.errors)}, status=422)


def _dismissal(request, pk, slot, intent):
    from n26.core import choice_workflow

    gang = _own_gang_or_404(request, pk)
    fallback = (
        with_query(reverse("n26-edit-gang", args=[gang.pk]), tab="dismissed")
        if intent == "restore"
        else reverse("n26-gang", args=[gang.pk])
    )
    back = own_address(request, request.POST.get("back", "")) or fallback
    data = request.POST.copy()
    data["act"] = intent
    if "request_key" not in data:
        data["request_key"] = request.GET.get("request_key", "")
    result = choice_workflow.change(
        gang,
        request.user,
        slot,
        data,
        here=reverse("n26-choose", args=[gang.pk, slot]),
        back=back,
    )
    if result.saved:
        _choice_feedback(request, gang, result)
    else:
        for errors in result.form.errors.values():
            for message in errors:
                messages.error(request, message)
    return redirect(back)


@login_required
@require_POST
@never_cache
def dismiss_offer(request, pk, slot):
    """Dismiss one eligible choice through its rendered command identity."""
    return _dismissal(request, pk, slot, "dismiss")


@login_required
@require_POST
@never_cache
def restore_offer(request, pk, slot):
    """Restore a choice, including vanished keys, through the shared command."""
    return _dismissal(request, pk, slot, "restore")


def _write_pick(op, request, gang, slot_key, found, offer, wanted, *, dropped=""):
    """Keep native callers on the current, locked computed-choice validation."""
    from n26.core.choice_workflow import write_pick

    gang.refresh_from_db(fields=["owner", "archived"])
    if gang.owner_id != request.user.pk or gang.archived:
        from n26.core.operations import Refusal

        raise Refusal("You can no longer change this gang's choices.")
    _, _, picked = write_pick(
        op,
        gang,
        request.user,
        slot_key,
        wanted,
        dropped=dropped,
        roll=request.POST.get("roll", ""),
    )
    return picked


def _record_pick(request, gang, offer, picked, dropped):
    """Record the submitted choice outcome without rewriting earlier analytics events."""
    from n26.analytics import EventVerb, N26Noun, record

    record(
        request,
        N26Noun.CHOICE,
        EventVerb.ARCHIVE if dropped or picked is None else EventVerb.CONFIRM,
        gang,
        offer=offer.label,
        picked="None" if picked is None else picked.name,
    )
