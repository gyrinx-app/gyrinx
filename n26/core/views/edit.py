"""Edit a model's characteristics, skills, traits, notes and owned-content controls."""

from dataclasses import dataclass
from typing import NamedTuple

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from n26.core.views.permissions import (
    _own_miniature_or_404,
    credits_href,
    link_model_cards,
    may_mark_status,
    may_see_founding,
    status_href,
    trade_points_href,
)
from n26.library.staged import sees_staged

#: Editable form sections mapped to their assignment fields.
EDITABLE_KINDS = {"subtypes": "subtype", "rules": "rule"}


@dataclass(frozen=True)
class _EditState:
    """Content offered, stored, granted, manually changed or fixed for one editable kind.

    Track provenance because clearing an owner addition archives it, while clearing
    inherited content requires a stored removal. Fixed purchased content cannot
    be cleared through these controls.
    """

    #: Current selectable content of this kind.
    offered: list
    #: Stored assignments by content key.
    stored: dict
    #: Stored owner additions by content key.
    own_adds: dict
    #: Gang-broadcast content keys applying to this model.
    gang_held: set
    #: Computed grant sources by content key.
    granted: dict
    #: Owner removal assignments by content key.
    removed: dict
    #: Content keys immune to removal while purchased assignments remain.
    fixed: set


def _edit_state(own, computed, field, *, include_staged=False):
    """Classify offered content and card provenance for an editable kind.

    Ignore suppressed assignments. Distinguish broadcast content, owner additions,
    computed grants, owner removals and content immune to removal.
    """
    from n26.core.effects import stands_whatever_happens
    from n26.core.models import Assignment, Reason
    from n26.core.views.skills import _key

    kind_class = Assignment._meta.get_field(field).related_model
    # Apply archive and staged-content discovery rules to editable choices.
    offered = list(kind_class.objects.selectable(include_staged=include_staged))
    stored, own_adds, gang_held = {}, {}, set()
    for node in own.all_nodes():
        if node.suppressed or node.assignment is None:
            continue
        if not isinstance(node.assignable, kind_class):
            continue
        key = _key(node.assignable)
        stored.setdefault(key, node.assignment)
        if node.broadcast:
            # A model-specific removal can suppress broadcast content only for this model.
            gang_held.add(key)
            continue
        entry = getattr(node.assignment, "ledger_entry", None)
        if entry is not None and entry.reason == Reason.EDITED:
            own_adds.setdefault(key, node.assignment)
    granted = {
        _key(contribution.thing): contribution.source
        for contribution in getattr(computed, f"{field}s")
    }
    removed = {
        _key(row.assignable): row
        for row in own.removals
        if isinstance(row.assignable, kind_class)
    }
    # Use the effects engine's removal rule so fixed controls match actual behaviour.
    fixed = {
        key
        for key, assignment in stored.items()
        if stands_whatever_happens(own, assignment.assignable)
    }
    return _EditState(
        offered=offered,
        stored=stored,
        own_adds=own_adds,
        gang_held=gang_held,
        granted=granted,
        removed=removed,
        fixed=fixed,
    )


def _edits_offer(own, computed, field, heading, *, include_staged=False):
    """Build current editable checkboxes and remaining searchable options.

    Keep owner removals visible for restoration. Granted content can be cleared
    through a stored removal; fixed purchased content has no clearable control.
    """
    from n26.core.render import ChoiceOffer, Choosable, ChoosableGroup
    from n26.core.views.skills import _key

    state = _edit_state(own, computed, field, include_staged=include_staged)
    current, rest = [], []
    for thing in state.offered:
        key = _key(thing)
        fixed_because = ""
        if key in state.fixed:
            # Direct purchased-content removal through equipment sale controls.
            fixed_because = "bought — sell it to take it away"
        if key in state.own_adds:
            detail = "added by you"
        elif key in state.removed:
            detail = "taken away by you"
        elif key in state.granted and key not in state.stored:
            detail = f"from {state.granted[key]}"
        elif key in state.gang_held:
            detail = "from the gang"
        else:
            detail = ""
        option = Choosable(
            key=key,
            name=str(thing),
            thing=thing,
            is_current=key in state.stored or key in state.granted,
            detail=detail,
            fixed_because=fixed_because,
        )
        if option.is_current or detail:
            current.append(option)
        else:
            rest.append(option)

    held = (
        ChoiceOffer(label="", groups=[ChoosableGroup(name=heading, options=current)])
        if current
        else None
    )
    return held, rest, bool(state.own_adds or state.removed)


#: Supported skill-tab values carried by the URL.
OWN_SETS, ALL_SETS = "their-sets", "all-sets"


def _skills_tabs(miniature, current):
    """Link the placed-or-held and complete skill offers through stable URL values."""
    here = reverse("n26-edit-fighter", args=[miniature.pk])
    return [
        {
            "label": "Their sets",
            "href": f"{here}?skills={OWN_SETS}",
            "current": current == OWN_SETS,
        },
        {
            "label": "All sets",
            "href": f"{here}?skills={ALL_SETS}",
            "current": current == ALL_SETS,
        },
    ]


def _skills_here(request, miniature):
    """Return a skills save to its supported tab on this model's edit page.

    Select only predefined route and tab values; never use submitted destinations
    directly in a link.
    """
    here = reverse("n26-edit-fighter", args=[miniature.pk])
    asked = request.POST.get("tab")
    for tab in (OWN_SETS, ALL_SETS):
        if asked == tab:
            return f"{here}?skills={tab}"
    return here


def _apply_edits(op, miniature, own, computed, field, ticked, *, include_staged=False):
    """Match an editable kind to the submitted checkboxes using current library content.

    Archive cleared owner additions and create removals for other cleared content.
    Restore re-ticked content by archiving its removal; add newly ticked content
    through the operation. Skip fixed content.
    """
    from n26.core.models import Reason
    from n26.core.views.skills import _key

    state = _edit_state(own, computed, field, include_staged=include_staged)
    added, taken, restored = [], [], []
    for thing in state.offered:
        key = _key(thing)
        if key in state.fixed:
            # Fixed boxes submit no value; do not interpret their absence as a removal.
            continue
        shown = key in state.stored or key in state.granted
        if key in ticked:
            if key in state.removed and not shown:
                op.remove(state.removed[key], note="restored")
                restored.append(str(thing))
            elif not shown and key not in state.removed:
                op.assign(thing, miniature=miniature, paid=0, reason=Reason.EDITED)
                added.append(str(thing))
        elif key in state.own_adds:
            op.remove(state.own_adds[key])
            if key in state.granted and key not in state.removed:
                # Clearing an owner addition must also suppress a simultaneous grant.
                op.take_away(miniature, thing)
            taken.append(str(thing))
        elif shown and key not in state.removed:
            op.take_away(miniature, thing)
            taken.append(str(thing))
    return added, taken, restored


def link_model_card(
    gang,
    miniature,
    own,
    computed,
    host,
    *,
    back,
    among=None,
    dismissal_at=None,
    rank_summaries=None,
    amount_dialog=False,
):
    """Build a model card and link controls consistently across Edit, Equip and Options.

    Use host.at for equipment panels and back for choices and counters.
    Amount-dialog controls require explicit opt-in by pages hosting that dialog.
    Reuse collection data through among and dismissal state through dismissal_at.
    """
    from n26.core.access import model_collections
    from n26.core.owned import with_query
    from n26.core.render import build_model_card
    from n26.core.views.choose import link_slots, settle_dismissed
    from n26.core.views.owned import link_counters, link_possession_actions
    from n26.core.views.skills import link_skills

    # Keep separate owned assignments so each equipment menu targets one copy.
    card = build_model_card(
        miniature,
        card=own,
        computed=computed,
        collapse_repeats=False,
        rank_summaries=rank_summaries,
        open_lasting_effects=True,
    )
    dismissal_at = back if dismissal_at is None else dismissal_at
    settle_dismissed(
        gang,
        *_dismissal_holders(miniature, card),
        hide_only=_dismissal_hidden(miniature, card),
    )
    link_slots(gang, card, back=back, dismiss_back=dismissal_at)
    link_skills(card, among=model_collections() if among is None else among)
    link_counters(card, back=back)
    # Only pages with the amount-dialog host opt into counter pencil controls.
    if amount_dialog:
        for line in card.counters:
            if line.href:
                line.adjust_href = with_query(line.href, back=back)
    link_possession_actions(card, host, refunds=not gang.credits_unlimited)
    # Preserve dismissal state on Options even when other controls return to Edit.
    if dismissal_at.split("?")[0] == reverse("n26-edit-fighter", args=[miniature.pk]):
        addresses = edit_dialog_addresses(miniature, dismissal_at)
        if card.skills_href:
            card.skills_href = f"{addresses.back}#n26-skills-box"
        card.base_rating_href = addresses.rating
        card.rename_href = addresses.rename
    return card


class CardScreen(NamedTuple):
    """Supported card-surface navigation state and whether it hosts equipment dialogs."""

    #: Whether equipment dialogs can open on this surface; otherwise use Edit.
    hosts_dialogs: bool
    #: Shareable navigation keys retained after a card action, excluding open dialogs.
    carries: tuple[str, ...]


#: Supported card routes and navigation keys.
#: Edit retains skills and dismissed state; Equip retains its listing state;
#: Options retains dismissal state while equipment actions return to Edit.
CARD_SCREENS = {
    "n26-edit-fighter": CardScreen(hosts_dialogs=True, carries=("skills", "dismissed")),
    "n26-equip": CardScreen(
        hosts_dialogs=True, carries=("list", "section", "owned", "dismissed")
    ),
    "n26-fighter-options": CardScreen(hosts_dialogs=False, carries=("dismissed",)),
}


def card_screen(miniature, back):
    """Validate a posted card source and rebuild its address from supported routes and keys.

    Require this model's identifier and one CARD_SCREENS route. Drop unsupported
    query parameters and ignore the supplied origin. Return (address, host_at),
    falling back to Edit for unknown, malformed or unrelated sources.
    """
    from urllib.parse import parse_qsl, urlencode, urlsplit

    from django.urls import Resolver404, resolve

    edit = reverse("n26-edit-fighter", args=[miniature.pk])
    try:
        parts = urlsplit(back or "")
        match = resolve(parts.path)
    except ValueError, Resolver404:
        # Malformed or unresolved source URLs fall back to Edit without an error.
        return edit, edit
    screen = CARD_SCREENS.get(match.url_name)
    if screen is None or match.kwargs.get("pk") != str(miniature.pk):
        return edit, edit
    address = reverse(match.url_name, args=[miniature.pk])
    kept = [
        (key, value) for key, value in parse_qsl(parts.query) if key in screen.carries
    ]
    if kept:
        address = f"{address}?{urlencode(kept)}"
    return address, (address if screen.hosts_dialogs else edit)


class EditDialogAddresses(NamedTuple):
    back: str
    rating: str
    rename: str


def edit_dialog_addresses(miniature, at=None):
    """Build rename and rating URLs retaining validated Edit-page state."""
    from urllib.parse import urlencode

    edit = reverse("n26-edit-fighter", args=[miniature.pk])
    back, _ = card_screen(miniature, at)
    if back.split("?")[0] != edit:
        back = edit
    state = {"at": back} if back != edit else {}
    rating = reverse("n26-base-rating", args=[miniature.pk])
    if state:
        rating = f"{rating}?{urlencode(state)}"
    rename = reverse("n26-rename-fighter", args=[miniature.pk])
    return EditDialogAddresses(
        back, rating, f"{rename}?{urlencode({'back': 'edit', **state})}"
    )


def dialog_url(back, **state):
    from urllib.parse import urlencode

    return f"{back}{'&' if '?' in back else '?'}{urlencode(state)}"


def request_edit_dialog_addresses(request, miniature):
    return edit_dialog_addresses(
        miniature,
        request.headers.get("HX-Current-URL")
        or request.GET.get("at")
        or request.get_full_path(),
    )


def _dismissal_holders(miniature, card):
    """Collect dismissed choices only on live models' edit cards."""
    from n26.core.status import Status

    return [] if miniature.status == Status.DEAD else [card]


def _dismissal_hidden(miniature, card):
    """Hide dismissed choices without restoration controls on dead models."""
    from n26.core.status import Status

    return [card] if miniature.status == Status.DEAD else []


def action_panel_context(miniature, own, computed, *, counter_tracking_active=None):
    """Build shared action-flow and history props for Edit, Equip and partial updates."""
    from n26.core.action_flow import action_panels
    from n26.core.counter_tracking import is_active as counter_tracking_is_active
    from n26.core.views.action_flows import link_action_panels, split_action_panels

    if counter_tracking_active is None:
        counter_tracking_active = counter_tracking_is_active()
    flows, history = split_action_panels(
        link_action_panels(
            miniature,
            action_panels(
                miniature,
                card=own,
                computed=computed,
                counter_tracking_active=counter_tracking_active,
            ),
        )
    )
    return {
        "action_panels": flows,
        "action_history_panels": history,
    }


def render_card_update(
    request, miniature, at, *, close_counter_dialog=False, announce_counter=""
):
    """Rebuild a model card and its relevant partial-update sections.

    Validate at through card_screen before linking returned controls. Reuse one
    computed card and load progression or action sections only where displayed.
    """
    from n26.core.card import build_card, build_modifier_index, carriers
    from n26.core.effects import compute
    from n26.core.owned import EquipHost
    from n26.core.progression import progression_for
    from n26.core.result_history import result_history
    from n26.core.views.htmx import with_toasts

    gang = miniature.membership.gang
    own = build_card(miniature, with_statlines=True, with_options=True)
    index = build_modifier_index(carriers(own))
    computed = compute(own, index)
    # Derive equipment action destinations from the validated source surface.
    back, host_at = card_screen(miniature, at)
    host = EquipHost.fighter(gang, own, miniature, host_at)
    on_edit = back.split("?")[0] == reverse("n26-edit-fighter", args=[miniature.pk])
    on_equip = back.split("?")[0] == reverse("n26-equip", args=[miniature.pk])
    progression = (
        progression_for(miniature, card=own, computed=computed) if on_edit else None
    )
    card = link_model_card(
        gang,
        miniature,
        own,
        computed,
        host,
        back=back,
        rank_summaries=progression.summaries if progression is not None else None,
        amount_dialog=on_edit,
    )
    link_model_cards(gang, [card], request.user)
    if announce_counter:
        # Announce the displayed counter total, including computed contributions.
        announced = next(
            (line for line in card.counters if line.assignment_id == announce_counter),
            None,
        )
        if announced is not None:
            messages.success(request, f"{announced.name} is now {announced.value}.")

    response = render(
        request,
        "n26/includes/model_card_update.html",
        {
            "card": card,
            "miniature": miniature,
            "progression": progression,
            **({"result_history": result_history(miniature)} if on_edit else {}),
            **(
                action_panel_context(miniature, own, computed)
                if on_edit or on_equip
                else {}
            ),
            "update_action_panels": on_edit or on_equip,
            "update_progression_status": on_edit,
            "update_progression_history": on_edit,
            "update_dismissed_choices": on_edit,
            "close_counter_dialog": close_counter_dialog,
            "status_href": (
                status_href(gang, miniature, back="edit")
                if may_mark_status(gang, request.user)
                else ""
            ),
        },
    )
    return with_toasts(request, response)


@login_required
def base_rating(request, pk):
    """Edit the owned model's hire-rating contribution or remove its override."""
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.forms import BaseRatingForm
    from n26.core.operations import Refusal, operation
    from n26.core.views.htmx import is_htmx, with_toasts

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.gang
    addresses = request_edit_dialog_addresses(request, miniature)
    back = addresses.back
    form = BaseRatingForm(
        request.POST if request.method == "POST" else None,
        initial={"rating": miniature.membership.ledger_entry.rating_contribution},
    )
    removing = request.POST.get("act") == "remove-override"
    if request.method == "POST" and (removing or form.is_valid()):
        try:
            with operation(gang, actor=request.user) as op:
                changed = op.set_base_rating(
                    miniature, None if removing else form.cleaned_data["rating"]
                )
        except Refusal as refusal:
            form.add_error(None, str(refusal))
        else:
            if changed:
                record(request, N26Noun.MODEL, EventVerb.UPDATE, miniature, rating=True)
            messages.success(
                request,
                ("Base rating override removed." if removing else "Base rating saved.")
                if changed
                else "Nothing changed.",
            )
            if is_htmx(request):
                from n26.core.rating import read_rating_receipt
                from n26.core.render import roster, summarise_roster

                miniature.refresh_from_db()
                gang.refresh_from_db()
                response = render(
                    request,
                    "n26/includes/base_rating_saved.html",
                    {
                        "miniature": miniature,
                        "gang": gang,
                        "summary": summarise_roster(roster(gang)),
                        "rating_href": addresses.rating,
                        "rating_breakdown": read_rating_receipt(
                            miniature
                        ).popover_props(miniature.name),
                        "trade_points_href": trade_points_href(gang, request.user),
                        "credits_href": credits_href(gang, request.user),
                    },
                )
                response["HX-Replace-Url"] = back
                return with_toasts(request, response)
            return redirect(back)
    if is_htmx(request):
        response = render(
            request,
            "n26/includes/base_rating_dialog.html",
            {
                "rating_dialog": _base_rating_dialog(request, miniature, form),
                "oob": True,
            },
        )
        response["HX-Replace-Url"] = dialog_url(back, rating=1)
        return response
    return render(
        request,
        "n26/base_rating.html",
        {
            "miniature": miniature,
            "gang": gang,
            "form": form,
            "back": back,
            "default_rating": miniature.membership.ledger_entry.rating_without_override,
        },
    )


def _base_rating_dialog(request, miniature, form=None):
    """Build controls for the editable hire contribution, excluding equipment rating."""
    from django.middleware.csrf import get_token

    from n26.core.forms import BaseRatingForm

    if form is None:
        form = BaseRatingForm(
            initial={"rating": miniature.membership.ledger_entry.rating_contribution}
        )
    field = form["rating"]
    entry = miniature.membership.ledger_entry
    default_rating = entry.rating_without_override
    addresses = request_edit_dialog_addresses(request, miniature)
    return {
        "value": str(field.value() if field.value() is not None else ""),
        "errors": list(field.errors),
        "formErrors": list(form.non_field_errors()),
        "description": str(field.help_text),
        "actionUrl": addresses.rating,
        "cancelUrl": addresses.back,
        "csrfToken": get_token(request),
        "returnFocusId": f"n26-rating-pencil-{miniature.pk}",
        "defaultRating": default_rating,
        "hasOverride": entry.rating_contribution != default_rating,
    }


@login_required
def edit_fighter(request, pk):
    """Render one computed model and process independently submitted edit actions.

    Route every player-data change through an operation, including notes, lore,
    images and characteristics. Unknown POST actions write nothing.
    Notes and lore htmx saves preserve the other live editor.

    Use one card for displayed facts, skill selection and manual subtype or rule
    edits. Owner removals can be reset to restore content-derived facts.
    Characteristic validation errors retain submitted values.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.access import model_collections
    from n26.core.card import build_card, build_modifier_index, carriers
    from n26.core.departure import departure_for
    from n26.core.effects import compute
    from n26.core.forms import (
        FighterLoreForm,
        FighterNotesForm,
        PictureForm,
        statline_override_form_for,
    )
    from n26.core.images import MAX_PX, PORTRAIT
    from n26.core.operations import Refusal, operation
    from n26.core.owned import DIALOGS, EquipHost
    from n26.core.render import roster, summarise_roster
    from n26.core.views.gangs import _fighter_named
    from n26.core.views.htmx import is_htmx, stay_or_redirect
    from n26.core.views.owned import (
        accessorise_dialogs,
        owned_dialog,
        panel_response,
    )
    from n26.core.views.skills import apply_ticks, skills_offer

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.membership.gang
    profile = miniature.membership.profile
    # Reuse staged-content access for every offered list and submitted selection.
    shown = sees_staged(request.user)
    # Omit characteristic controls when there is no profile defining their shape.
    statline_class = statline_override_form_for(profile) if profile else None
    statline_edit = None

    if request.method == "POST" and request.POST.get("act") == "track-progression":
        try:
            with operation(gang, actor=request.user) as op:
                assignment = op.track_progression_counter(
                    miniature, request.POST.get("counter", "")
                )
            messages.success(request, f"{assignment.counter} tracking started at 0.")
        except Refusal as refusal:
            messages.error(request, str(refusal))
        return redirect("n26-edit-fighter", pk=miniature.pk)
    elif request.method == "POST" and request.POST.get("act") == "statline":
        if statline_class is not None:
            statline_edit = statline_class.opened_on(miniature, request.POST)
            if statline_edit.is_valid():
                with operation(gang, actor=request.user) as op:
                    op.set_stats(miniature, statline_edit.changes())
                record(
                    request, N26Noun.MODEL, EventVerb.UPDATE, miniature, statline=True
                )
                messages.success(request, "Characteristics saved.")
                return redirect("n26-edit-fighter", pk=miniature.pk)
    elif request.method == "POST" and request.POST.get("act") == "skills":
        own = build_card(miniature)
        index = build_modifier_index(carriers(own))
        try:
            with operation(gang, actor=request.user) as op:
                selected, cleared = apply_ticks(
                    op,
                    miniature,
                    own,
                    compute(own, index),
                    set(request.POST.getlist("skills")),
                    include_staged=shown,
                )
        except Refusal as refusal:
            messages.error(request, str(refusal))
            return redirect(_skills_here(request, miniature))
        record(
            request,
            N26Noun.MODEL,
            EventVerb.UPDATE,
            miniature,
            selected=len(selected),
            cleared=len(cleared),
        )
        # Name selected and cleared content in the confirmation.
        moved = [
            phrase
            for phrase in (
                f"selected {', '.join(selected)}" if selected else "",
                f"lost {', '.join(cleared)}" if cleared else "",
            )
            if phrase
        ]
        messages.success(
            request,
            f"{miniature.name} {' and '.join(moved)}." if moved else "Skills saved.",
        )
        return redirect(_skills_here(request, miniature))
    elif request.method == "POST" and request.POST.get("act") in EDITABLE_KINDS:
        field = EDITABLE_KINDS[request.POST["act"]]
        own = build_card(miniature)
        index = build_modifier_index(carriers(own))
        try:
            with operation(gang, actor=request.user) as op:
                added, taken, restored = _apply_edits(
                    op,
                    miniature,
                    own,
                    compute(own, index),
                    field,
                    set(request.POST.getlist(request.POST["act"])),
                    include_staged=shown,
                )
        except Refusal as refusal:
            messages.error(request, str(refusal))
            return redirect("n26-edit-fighter", pk=miniature.pk)
        record(
            request,
            N26Noun.MODEL,
            EventVerb.UPDATE,
            miniature,
            edits=field,
            added=len(added),
            taken=len(taken),
            restored=len(restored),
        )
        # Confirm only actual changes; fixed content is neither removed nor reported lost.
        moved = [
            phrase
            for phrase in (
                f"gained {', '.join(added)}" if added else "",
                f"lost {', '.join(taken)}" if taken else "",
                f"got {', '.join(restored)} back" if restored else "",
            )
            if phrase
        ]
        messages.success(
            request,
            f"{miniature.name} {' and '.join(moved)}." if moved else "Saved.",
        )
        return redirect("n26-edit-fighter", pk=miniature.pk)
    elif request.method == "POST" and request.POST.get("act") == "reset-edits":
        field = request.POST.get("kind")
        if field in EDITABLE_KINDS.values():
            try:
                with operation(gang, actor=request.user) as op:
                    undone = op.reset_edits(miniature, field)
            except Refusal as refusal:
                messages.error(request, str(refusal))
                return redirect("n26-edit-fighter", pk=miniature.pk)
            record(
                request,
                N26Noun.MODEL,
                EventVerb.UPDATE,
                miniature,
                reset=field,
                undone=len(undone),
            )
            messages.success(
                request,
                f"{miniature.name}'s {field} edits are undone."
                if undone
                else "Nothing to reset.",
            )
        return redirect("n26-edit-fighter", pk=miniature.pk)
    elif request.method == "POST" and request.POST.get("act") == "lore":
        form = FighterLoreForm(request.POST)
        if form.is_valid():
            with operation(gang, actor=request.user) as op:
                op.edit_lore(miniature, form.cleaned_data["lore"])
            record(request, N26Noun.MODEL, EventVerb.UPDATE, miniature, lore=True)
            messages.success(request, "Lore saved.")
        return stay_or_redirect(
            request, reverse("n26-edit-fighter", args=[miniature.pk])
        )
    elif request.method == "POST" and request.POST.get("act") == "notes":
        form = FighterNotesForm(request.POST)
        if form.is_valid():
            with operation(gang, actor=request.user) as op:
                op.edit_notes(miniature, form.cleaned_data["notes"])
            record(request, N26Noun.MODEL, EventVerb.UPDATE, miniature, notes=True)
            messages.success(request, "Notes saved.")
        return stay_or_redirect(
            request, reverse("n26-edit-fighter", args=[miniature.pk])
        )
    elif request.method == "POST" and request.POST.get("act") == "picture":
        form = PictureForm(request.POST, request.FILES, ratio=PORTRAIT)
        if form.is_valid():
            new_picture = bool(form.cleaned_data["image"])
            dropped_picture = (
                form.cleaned_data["remove_image"]
                and bool(miniature.image)
                and not new_picture
            )
            with operation(gang, actor=request.user) as op:
                op.set_image(
                    miniature,
                    form.cleaned_data["image"],
                    clear=form.cleaned_data["remove_image"],
                )
            record(
                request,
                N26Noun.MODEL,
                EventVerb.UPDATE,
                miniature,
                image=new_picture or dropped_picture,
            )
            if new_picture:
                messages.success(request, "Picture saved.")
            elif dropped_picture:
                messages.success(request, "Picture removed.")
            else:
                messages.success(request, "Nothing changed.")
        else:
            # Report upload validation errors on the destination page.
            for wrong in form.errors.get("image", []):
                messages.error(request, wrong)
        return redirect("n26-edit-fighter", pk=miniature.pk)
    elif request.method == "POST":
        # Unknown POST actions must not fall through to an empty notes submission.
        return redirect("n26-edit-fighter", pk=miniature.pk)

    if statline_edit is None and statline_class is not None:
        statline_edit = statline_class.opened_on(miniature)

    # Reuse one model card with option provenance for the page's facts, skills and owned-copy controls.
    own = build_card(miniature, with_statlines=True, with_options=True)
    index = build_modifier_index(carriers(own))
    computed = compute(own, index)
    from n26.core.progression import progression_for

    progression = progression_for(miniature, card=own, computed=computed)

    from n26.core.counter_tracking import is_active as counter_tracking_is_active
    from n26.core.result_history import result_history

    counter_tracking_active = counter_tracking_is_active()
    panels = action_panel_context(
        miniature, own, computed, counter_tracking_active=counter_tracking_active
    )
    panels["result_history"] = result_history(miniature)

    # Link equipment controls to this page's confirmation host.
    at, _ = card_screen(miniature, request.get_full_path())
    host = EquipHost.fighter(gang, own, miniature, at)

    renaming = _fighter_named(request, gang, "rename")
    if renaming is not None and renaming.pk != miniature.pk:
        renaming = None
    from n26.core.views.gangs import rename_dialog_props

    # Give rename priority over equipment dialogs so only one modal opens.
    dialog = None
    if not renaming and any(request.GET.get(kind) for kind in DIALOGS):
        dialog = owned_dialog(request, host)
        if dialog is None:
            dialog = next(
                (
                    panel
                    for panel in accessorise_dialogs(request, host)
                    if panel["open"]
                ),
                None,
            )
        # Return only the requested htmx panel; its submit remains a full-page action
        # because this surface has no equipment-row update hosts.
        if (panel := panel_response(request, dialog, htmx=False)) is not None:
            return panel

    # Share the collection lookup between skill offers and the card's Skills control.
    sets = model_collections()
    skills = skills_offer(own, computed, sets, include_staged=shown)
    asked = request.GET.get("skills")
    # Default to All sets when the placed-or-held partition is empty; honour explicit supported tabs.
    tab = (
        asked
        if asked in (OWN_SETS, ALL_SETS)
        else (ALL_SETS if skills.own.is_empty else OWN_SETS)
    )
    skills_box = {
        "miniature": miniature,
        "edit_url": reverse("n26-edit-fighter", args=[miniature.pk]),
        # Omit the skills box only when the complete offer is empty.
        "skills": None
        if skills.everything.is_empty
        else (skills.own if tab == OWN_SETS else skills.everything),
        # Search only options outside the currently displayed skill partition.
        "skills_more": skills.rest if tab == OWN_SETS else [],
        "skills_tab": tab,
        "skills_tabs": _skills_tabs(miniature, tab),
    }

    # Return only the htmx skills box and update URL state before building other display sections.
    if request.method == "GET" and asked and is_htmx(request):
        answer = render(
            request, "n26/includes/skills_box.html", {**skills_box, "oob": True}
        )
        answer["HX-Replace-Url"] = request.get_full_path()
        return answer

    # Build the card from the existing model computation; load only the roster summary separately.
    card = link_model_card(
        gang,
        miniature,
        own,
        computed,
        host,
        back=request.get_full_path(),
        among=sets,
        rank_summaries=progression.summaries,
        amount_dialog=True,
    )
    link_model_cards(gang, [card], request.user)

    subtype_edits, subtype_more, subtype_edits_dirty = _edits_offer(
        own, computed, "subtype", "Subtypes", include_staged=shown
    )
    rule_edits, rule_more, rule_edits_dirty = _edits_offer(
        own, computed, "rule", "Special rules", include_staged=shown
    )

    # Load the gang's shared figures and roster summary for the header.
    members = roster(gang)
    may_mark = may_mark_status(gang, request.user)
    may_refund = not gang.credits_unlimited
    if not may_refund:
        try:
            may_refund = departure_for(miniature).refund[1] > 0
        except Refusal:
            may_refund = False
    from n26.core.allowances import missing_progression_counters
    from n26.core.views.trade_points import hire_time_context

    return render(
        request,
        "n26/fighter_edit.html",
        {
            "miniature": miniature,
            **(
                hire_time_context(gang, miniature, computed)
                if may_see_founding(gang, request.user)
                else {}
            ),
            "rating_dialog": _base_rating_dialog(request, miniature)
            if request.GET.get("rating") == "1" and not renaming
            else None,
            "gang": gang,
            "card": card,
            "progression": progression,
            **panels,
            "missing_progression_counters": missing_progression_counters(
                miniature, card=own, computed=computed
            )
            if counter_tracking_active
            else [],
            "summary": summarise_roster(members),
            "trade_points_href": trade_points_href(gang, request.user),
            "credits_href": credits_href(gang, request.user),
            # Status badges can open ransom; the menu item always opens manual status editing.
            "status_href": (
                status_href(gang, miniature, back="edit") if may_mark else ""
            ),
            "mark_href": (
                status_href(gang, miniature, back="edit", ransom=False)
                if may_mark
                else ""
            ),
            # Generated models share their originating purchase and cannot be cloned independently.
            "may_clone": miniature.membership.caused_by_id is None,
            # Unlimited-credit gangs refund only founding trade points, including a generated model's originating purchase.
            "may_refund": may_refund,
            # Use the profile category's bare name for the displayed rank.
            "role": profile.category.name if profile and profile.category else "",
            "form": FighterNotesForm(initial={"notes": miniature.notes}),
            "lore_form": FighterLoreForm(initial={"lore": miniature.lore}),
            # Pass prepared characteristic cells rather than form internals to the display component.
            "statline_cells": statline_edit.cells() if statline_edit else None,
            # Share skill-box props between full pages and tab partials.
            **skills_box,
            # Hide empty edit sections and show Reset only for existing owner changes.
            "subtype_edits": subtype_edits,
            "subtype_more": subtype_more,
            "subtype_edits_dirty": subtype_edits_dirty,
            "rule_edits": rule_edits,
            "rule_more": rule_more,
            "rule_edits_dirty": rule_edits_dirty,
            "renaming": renaming,
            "rename_dialog": rename_dialog_props(request, renaming)
            if renaming
            else None,
            "dialog": dialog,
            # Use the server's crop constants for browser image controls too.
            "picture_shape": PORTRAIT,
            "picture_max": MAX_PX,
            "picture_url": miniature.image.url if miniature.image else "",
        },
    )
